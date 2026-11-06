"""Code Forge engine tests: catalog integrity, code extraction, kit building."""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import codeforge  # noqa: E402


def test_catalog_integrity():
    assert len(codeforge.CATALOG) >= 25
    ids = [s["id"] for s in codeforge.CATALOG]
    assert len(ids) == len(set(ids))
    for spec in codeforge.CATALOG:
        assert spec["label"] and spec["ext"].startswith(".") and spec["main"]
        assert isinstance(spec["build_win"], list) and isinstance(spec["build_linux"], list)
    # the honest marquee: these really produce single-file natives
    for pid in ("python", "go", "c", "cpp", "rust", "dart", "csharp"):
        assert codeforge.BY_ID[pid]["build_win"] or codeforge.BY_ID[pid]["build_linux"]


def test_resolve_falls_back_to_other_with_custom_label():
    spec = codeforge.resolve("cobol-not-in-list", custom="COBOL")
    assert spec["id"] == "other" and spec["label"] == "COBOL"
    assert codeforge.resolve("python")["id"] == "python"


def test_slugify_skips_filler_words():
    assert codeforge.slugify("Write me an app for Stock Taking please") == "stock-taking"
    assert codeforge.slugify("!!!") == "smash-app"


def test_extract_code_prefers_first_fence():
    text = "Sure!\n```python\nprint('hi')\n```\nThen some prose ```js\nx\n```"
    code, fenced = codeforge.extract_code(text)
    assert fenced and code == "print('hi')\n"
    code2, fenced2 = codeforge.extract_code("plain code no fences")
    assert not fenced2 and code2.startswith("plain code")


def test_system_prompt_language_specifics():
    java = codeforge.resolve("java")
    p = codeforge.system_prompt(java, "StockTaking.java")
    assert "StockTaking" in p and "public class" in p
    html = codeforge.system_prompt(codeforge.resolve("html"), "app.html")
    assert "self-contained" in html and "CDN" in html


def _kit(lang, prompt="Stock taking tool", code="print('hi')\n"):
    spec = codeforge.resolve(lang)
    slug = codeforge.slugify(prompt)
    return slug, zipfile.ZipFile(io.BytesIO(
        codeforge.build_kit(slug, spec, code, prompt, "2026-11-06 03:30")))


def test_python_kit_is_complete_with_zipapp():
    slug, z = _kit("python")
    names = z.namelist()
    for required in (f"src/app.py", "launch.bat", "launch.sh", "launch.command",
                     "install.bat", "install.sh", "uninstall.bat", "uninstall.sh",
                     "BUILD.md", "README.txt", "build-windows.bat", "build-linux.sh",
                     "build-macos.sh", "app.pyz"):
        assert required in names, required
    assert "pyinstaller --onefile --name stock-taking-tool" in z.read("build-windows.bat").decode()
    assert "Stock Taking" in z.read("README.txt").decode()
    # the zipapp is itself a valid zip with __main__.py
    pyz = zipfile.ZipFile(io.BytesIO(z.read("app.pyz")))
    assert "__main__.py" in pyz.namelist()


def test_java_kit_names_class_file_and_uses_jpackage():
    slug, z = _kit("java")
    assert f"src/{codeforge.pascal(slug)}.java" in z.namelist()
    assert "jpackage" in z.read("build-windows.bat").decode()


def test_csharp_kit_includes_csproj_at_root():
    slug, z = _kit("csharp")
    names = z.namelist()
    assert f"{slug}.csproj" in names and "src/Program.cs" in names
    assert "--self-contained" in z.read("build-windows.bat").decode()


def test_html_kit_has_no_build_scripts_but_full_installers():
    slug, z = _kit("html")
    names = z.namelist()
    assert "build-windows.bat" not in names  # nothing to compile
    assert "install.bat" in names and "launch.command" in names
    assert "start app.html" in z.read("launch.bat").decode()


def test_go_kit_builds_static_binary():
    slug, z = _kit("go")
    assert "go build" in z.read("build-linux.sh").decode()


def test_launcher_checks_runtime_before_running():
    slug, z = _kit("python")
    bat = z.read("launch.bat").decode()
    assert "where py" in bat and "was not found" in bat
    sh = z.read("launch.sh").decode()
    assert "command -v python3" in sh


def test_install_scripts_create_os_entries():
    slug, z = _kit("python")
    assert "WScript.Shell" in z.read("install.bat").decode()      # Start Menu shortcut
    assert ".desktop" in z.read("install.sh").decode()             # Linux app menu
    assert "uninstall" in z.read("uninstall.sh").decode().lower()
