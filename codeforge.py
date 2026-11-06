"""Code Forge — Smash AI Pro's any-language code writer + standalone app kits.

Two jobs:
  1. Turn a plain-English ask into a complete, runnable program in ~30 languages
     (or any custom language the user names).
  2. Package that program into a STANDALONE KIT zip: double-click launchers for
     Windows/Linux/macOS, install + uninstall scripts (Start Menu / app-menu
     entries, desktop shortcut), and per-language build scripts that produce a
     true native single-file executable/installer (PyInstaller, pkg, CPack-style
     gcc, dotnet self-contained, Go static binary, jpackage, dart compile...).

Honesty rule baked into every kit: launchers need the language runtime until the
user runs the build script; after that the built executable is fully standalone.
BUILD.md says exactly this, per language, per OS.
"""
from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------ catalog
# run_win / run_unix: what launchers execute (from inside src/)
# check_win / check_unix: presence probe before running
# build_*: recipe lines that produce a TRUE standalone binary/installer
# extra: {relative path: content} extra kit files (templates use {NAME}, {MAIN})

def _l(id, label, ext, main, runtime, check_win, check_unix, run_win, run_unix,
       build_win, build_linux, build_macos, note="", extra=None):
    return {"id": id, "label": label, "ext": ext, "main": main, "runtime": runtime,
            "check_win": check_win, "check_unix": check_unix,
            "run_win": run_win, "run_unix": run_unix,
            "build_win": build_win, "build_linux": build_linux, "build_macos": build_macos,
            "note": note, "extra": extra or {}}


CATALOG: List[Dict[str, Any]] = [
    _l("python", "Python", ".py", "app.py", "Python 3", "py", "python3",
       "py app.py", "python3 app.py",
       ["py -m pip install pyinstaller", "pyinstaller --onefile --name {NAME} app.py",
        "result: dist\\{NAME}.exe - fully standalone, no Python needed"],
       ["python3 -m pip install pyinstaller", "pyinstaller --onefile --name {NAME} app.py",
        "result: dist/{NAME} - fully standalone"],
       ["python3 -m pip install pyinstaller", "pyinstaller --onefile --name {NAME} app.py",
        "result: dist/{NAME} - fully standalone"]),
    _l("javascript", "JavaScript (Node)", ".js", "app.js", "Node.js", "node", "node",
       "node app.js", "node app.js",
       ["npm install -g pkg", "pkg --targets node18-win-x64 --output {NAME}.exe app.js",
        "result: {NAME}.exe - standalone"],
       ["npm install -g pkg", "pkg --targets node18-linux-x64 --output {NAME} app.js"],
       ["npm install -g pkg", "pkg --targets node18-macos-x64 --output {NAME} app.js"]),
    _l("typescript", "TypeScript", ".ts", "app.ts", "Node.js + tsx", "node", "node",
       "npx --yes tsx app.ts", "npx --yes tsx app.ts",
       ["npm install -g typescript pkg", "tsc app.ts",
        "pkg --targets node18-win-x64 --output {NAME}.exe app.js"],
       ["npm install -g typescript pkg", "tsc app.ts",
        "pkg --targets node18-linux-x64 --output {NAME} app.js"],
       ["npm install -g typescript pkg", "tsc app.ts",
        "pkg --targets node18-macos-x64 --output {NAME} app.js"]),
    _l("html", "HTML web app", ".html", "app.html", "any browser", "", "",
       "start app.html", "xdg-open app.html 2>/dev/null || open app.html",
       [], [], [],
       note="A single HTML file IS the standalone app - double-click it on any OS, no build needed."),
    _l("java", "Java", ".java", "{BASE}.java", "Java 17+ (JDK)", "java", "java",
       "javac {MAIN} && java -cp . {BASE}", "javac {MAIN} && java -cp . {BASE}",
       ["javac {MAIN}",
        "jpackage --type msi --name {NAME} --main-jar {MAIN} --main-class {BASE} "
        "--input . --dest dist",
        "result: dist\\{NAME}.msi - native Windows installer"],
       ["javac {MAIN}",
        "jpackage --type deb --name {NAME} --main-class {BASE} --input . --dest dist",
        "result: dist/{NAME}.deb - native installer"],
       ["javac {MAIN}",
        "jpackage --type dmg --name {NAME} --main-class {BASE} --input . --dest dist",
        "result: dist/{NAME}.dmg - native installer"],
       note="The public class name must match the file name - the generator is told yours."),
    _l("c", "C", ".c", "app.c", "gcc / clang", "gcc", "gcc",
       "gcc -O2 -o {NAME}.exe app.c && {NAME}.exe", "gcc -O2 -o {NAME} app.c && ./{NAME}",
       ["(install MSYS2 or MinGW-w64 for gcc)", "gcc -O2 -static -o {NAME}.exe app.c",
        "result: {NAME}.exe - standalone"],
       ["gcc -O2 -o {NAME} app.c", "result: {NAME} - standalone"],
       ["clang -O2 -o {NAME} app.c", "result: {NAME} - standalone"]),
    _l("cpp", "C++", ".cpp", "app.cpp", "g++ / clang++", "g++", "g++",
       "g++ -O2 -o {NAME}.exe app.cpp && {NAME}.exe", "g++ -O2 -o {NAME} app.cpp && ./{NAME}",
       ["(install MSYS2 or MinGW-w64 for g++)", "g++ -O2 -static -o {NAME}.exe app.cpp"],
       ["g++ -O2 -o {NAME} app.cpp"],
       ["clang++ -O2 -o {NAME} app.cpp"]),
    _l("csharp", "C#", ".cs", "Program.cs", ".NET 8 SDK", "dotnet", "dotnet",
       "dotnet run --project ..", "dotnet run --project ..",
       ["dotnet publish .. -r win-x64 --self-contained -p:PublishSingleFile=true -o dist",
        "result: dist\\{NAME}.exe - fully standalone, no .NET install needed"],
       ["dotnet publish .. -r linux-x64 --self-contained -p:PublishSingleFile=true -o dist"],
       ["dotnet publish .. -r osx-arm64 --self-contained -p:PublishSingleFile=true -o dist"],
       extra={"../{NAME}.csproj":
              "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
              "  <PropertyGroup>\n"
              "    <OutputType>Exe</OutputType>\n"
              "    <TargetFramework>net8.0</TargetFramework>\n"
              "    <AssemblyName>{NAME}</AssemblyName>\n"
              "    <Nullable>enable</Nullable>\n"
              "  </PropertyGroup>\n"
              "</Project>\n"}),
    _l("go", "Go", ".go", "main.go", "Go toolchain", "go", "go",
       "go run main.go", "go run main.go",
       ["set GOOS=windows&& go build -ldflags -s -o {NAME}.exe main.go",
        "result: {NAME}.exe - static, standalone"],
       ["go build -ldflags \"-s\" -o {NAME} main.go", "result: {NAME} - static, standalone"],
       ["go build -ldflags \"-s\" -o {NAME} main.go"],
       note="Go cross-compiles: build for any OS from any OS with GOOS/GOARCH."),
    _l("rust", "Rust", ".rs", "main.rs", "rustc", "rustc", "rustc",
       "rustc -O main.rs -o {NAME}.exe && {NAME}.exe", "rustc -O main.rs -o {NAME} && ./{NAME}",
       ["rustc -O main.rs -o {NAME}.exe", "result: {NAME}.exe - standalone"],
       ["rustc -O main.rs -o {NAME}"], ["rustc -O main.rs -o {NAME}"]),
    _l("php", "PHP", ".php", "app.php", "PHP 8", "php", "php8",
       "php app.php", "php8 app.php 2>/dev/null || php app.php",
       ["(php -a stays interpreted; for a single file use a phar:)",
        "php -d phar.readonly=0 -r \"...\" # see BUILD.md"],
       ["echo 'PHP runs interpreted; bundle with a .desktop entry (install.sh did that).'"],
       ["echo 'PHP runs interpreted; bundle as .app with platypus (see BUILD.md).'"]),
    _l("ruby", "Ruby", ".rb", "app.rb", "Ruby 3", "ruby", "ruby",
       "ruby app.rb", "ruby app.rb",
       ["gem install ocra", "ocra --windows app.rb", "result: app.exe - standalone"],
       ["ruby app.rb (interpreted; desktop entry installed)"],
       ["ruby app.rb (interpreted; .app via platypus)"]),
    _l("swift", "Swift", ".swift", "main.swift", "Swift 5.9+", "swift", "swift",
       "echo Swift builds on macOS/Linux - use build-macos.sh or build-linux.sh",
       "swiftc -O main.swift -o {NAME} && ./{NAME}",
       ["(install the Swift toolchain for Windows first)",
        "swiftc -O main.swift -o {NAME}.exe", "result: {NAME}.exe - standalone"],
       ["swiftc -O main.swift -o {NAME}", "result: {NAME} - standalone"],
       ["swiftc -O main.swift -o {NAME}",
        "productbuild --component {NAME} /usr/local/bin --identifier pro.smash.{NAME} "
        "dist/{NAME}.pkg", "result: dist/{NAME}.pkg - native macOS installer"],
       note="Windows: Swift toolchain exists but native installers are Linux/macOS territory."),
    _l("kotlin", "Kotlin", ".kt", "app.kt", "kotlinc + Java", "kotlinc", "kotlinc",
       "kotlinc app.kt -include-runtime -d {NAME}.jar && java -jar {NAME}.jar",
       "kotlinc app.kt -include-runtime -d {NAME}.jar && java -jar {NAME}.jar",
       ["kotlinc app.kt -include-runtime -d {NAME}.jar",
        "jpackage --type msi --name {NAME} --main-jar {NAME}.jar --input . --dest dist"],
       ["kotlinc app.kt -include-runtime -d {NAME}.jar"],
       ["kotlinc app.kt -include-runtime -d {NAME}.jar"]),
    _l("dart", "Dart", ".dart", "main.dart", "Dart SDK", "dart", "dart",
       "dart run main.dart", "dart run main.dart",
       ["dart compile exe main.dart -o {NAME}.exe", "result: {NAME}.exe - standalone"],
       ["dart compile exe main.dart -o {NAME}", "result: {NAME} - standalone"],
       ["dart compile exe main.dart -o {NAME}"]),
    _l("scala", "Scala", ".scala", "app.scala", "scala-cli", "scala-cli", "scala-cli",
       "scala-cli run app.scala", "scala-cli run app.scala",
       ["scala-cli --power package app.scala -o {NAME}.exe --assembly"],
       ["scala-cli --power package app.scala -o {NAME} --assembly"],
       ["scala-cli --power package app.scala -o {NAME} --assembly"]),
    _l("r", "R", ".R", "app.R", "R 4", "Rscript", "Rscript",
       "Rscript app.R", "Rscript app.R",
       ["R stays interpreted; distribute with install.bat (done)"],
       ["R stays interpreted; distribute with install.sh (done)"],
       ["R stays interpreted; distribute with install.sh (done)"]),
    _l("julia", "Julia", ".jl", "app.jl", "Julia 1.9+", "julia", "julia",
       "julia app.jl", "julia app.jl",
       ["julia -e 'using Pkg; Pkg.add(\"PackageCompiler\")'",
        "julia -e 'using PackageCompiler; create_app(\".\", \"dist\")'"],
       ["(same PackageCompiler recipe as Windows)"], ["(same PackageCompiler recipe)"]),
    _l("lua", "Lua", ".lua", "main.lua", "Lua 5.4 / LuaJIT", "lua", "lua5.4",
       "lua main.lua", "lua5.4 main.lua 2>/dev/null || lua main.lua",
       ["luajit is already near-native; ship main.lua + launcher"],
       ["luajit -b main.lua {NAME}  # bytecode single file"], ["luajit -b main.lua {NAME}"]),
    _l("perl", "Perl", ".pl", "app.pl", "Perl 5", "perl", "perl",
       "perl app.pl", "perl app.pl",
       ["pp -o {NAME}.exe app.pl  (PAR::Packer)"], ["perl app.pl (perl is preinstalled nearly everywhere)"],
       ["perl app.pl"]),
    _l("haskell", "Haskell", ".hs", "main.hs", "GHC", "ghc", "ghc",
       "ghc -O2 main.hs -o {NAME}.exe && {NAME}.exe", "ghc -O2 main.hs -o {NAME} && ./{NAME}",
       ["ghc -O2 main.hs -o {NAME}.exe"], ["ghc -O2 main.hs -o {NAME}"], ["ghc -O2 main.hs -o {NAME}"]),
    _l("elixir", "Elixir", ".exs", "app.exs", "Elixir 1.15+", "elixir", "elixir",
       "elixir app.exs", "elixir app.exs",
       ["escriptize via mix (see BUILD.md)", "for a single file: elixirc --ignore-module-conflict app.exs"],
       ["mix release for a self-contained bundle"], ["mix release"]),
    _l("clojure", "Clojure", ".clj", "core.clj", "Clojure CLI + Java", "clojure", "clojure",
       "clojure -M core.clj", "clojure -M core.clj",
       ["clojure -T:build uber  # then jpackage the uberjar (see BUILD.md)"],
       ["clojure -T:build uber"], ["clojure -T:build uber"]),
    _l("fortran", "Fortran", ".f90", "app.f90", "gfortran", "gfortran", "gfortran",
       "gfortran -O2 -o {NAME}.exe app.f90 && {NAME}.exe", "gfortran -O2 -o {NAME} app.f90 && ./{NAME}",
       ["gfortran -O2 -static -o {NAME}.exe app.f90"], ["gfortran -O2 -o {NAME} app.f90"],
       ["gfortran -O2 -o {NAME} app.f90"]),
    _l("bash", "Bash", ".sh", "app.sh", "bash", "bash", "bash",
       "bash app.sh   (install Git Bash on Windows)", "bash app.sh",
       ["bash stays interpreted - that IS the native form"],
       ["chmod +x app.sh; the install.sh already linked it into PATH"],
       ["chmod +x app.sh"]),
    _l("powershell", "PowerShell", ".ps1", "app.ps1", "PowerShell", "powershell", "pwsh",
       "powershell -NoProfile -ExecutionPolicy Bypass -File app.ps1", "pwsh -File app.ps1",
       ["ps2exe -inputFile app.ps1 -outputFile {NAME}.exe  (PS2EXE module)"],
       ["pwsh stays interpreted"], ["pwsh stays interpreted"]),
    _l("batch", "Windows Batch", ".bat", "app.bat", "cmd.exe", "cmd", "",
       "app.bat", "echo Batch is Windows-only - run app.bat there",
       ["batch IS the native Windows shell form - no build needed"], [], [],
       note="Windows-only by nature."),
    _l("sql", "SQL script", ".sql", "app.sql", "sqlite3 / psql / mysql client", "sqlite3", "sqlite3",
       "sqlite3 smash.db < app.sql", "sqlite3 smash.db < app.sql",
       ["SQL runs inside a DB engine - ship the script + install.bat"],
       ["sqlite3 is preinstalled on macOS/most Linux"], ["same"]),
    _l("other", "Other (name any language)", ".txt", "app.txt", "see BUILD.md", "", "",
       "type app.txt   (follow BUILD.md for this language)",
       "cat app.txt   (follow BUILD.md for this language)",
       ["ask Smash AI Pro chat for the exact build recipe for this language"],
       ["ask Smash AI Pro chat for the exact build recipe"],
       ["ask Smash AI Pro chat for the exact build recipe"],
       note="Any language works for generation; the kit uses a generic recipe."),
]

BY_ID = {s["id"]: s for s in CATALOG}

STORE_URL = "https://1109ruwayne-cmd.github.io/smash-ai-pro/#store"


def catalog() -> List[Dict[str, str]]:
    return [{"id": s["id"], "label": s["label"], "note": s["note"]} for s in CATALOG]


def resolve(language: str, custom: str = "") -> Dict[str, Any]:
    spec = BY_ID.get(str(language or "").strip().lower())
    if spec is None:
        spec = dict(BY_ID["other"])
        if custom.strip():
            spec = dict(spec, label=custom.strip()[:60])
    return spec


# ------------------------------------------------------------------ naming

def slugify(prompt: str) -> str:
    stop = {"a", "an", "the", "app", "application", "program", "script", "write", "make",
            "create", "build", "me", "for", "that", "with", "in", "of", "to", "and", "please"}
    words = [w for w in re.findall(r"[a-z0-9]+", (prompt or "").lower()) if w not in stop]
    return "-".join(words[:4])[:40] or "smash-app"


def pascal(slug: str) -> str:
    return "".join(p.capitalize() for p in slug.split("-")) or "SmashApp"


def main_filename(spec: Dict[str, Any], slug: str) -> str:
    base = pascal(slug)
    return spec["main"].replace("{BASE}", base)


def fill(template: str, name: str, main: str) -> str:
    return template.replace("{NAME}", name).replace("{MAIN}", main)


# ------------------------------------------------------------------ generation

def system_prompt(spec: Dict[str, Any], main_name: str) -> str:
    label = spec["label"]
    lines = [
        f"You are Code Forge inside Smash AI Pro. Write ONE complete, runnable {label} program.",
        f"Deliver it as a single file named exactly {main_name}.",
        "Respond with EXACTLY one fenced code block containing the full source - no prose before or after.",
        "Rules:",
        "- Standard library only. No third-party packages, no downloads at runtime.",
        "- Must run as-is with the stock runtime on a clean machine.",
        "- Complete: real error handling, real output. No TODOs, no placeholders, no '...' gaps.",
        "- Short helpful comments inside the code; a top comment block stating what it does and how to run it.",
        "- Console/terminal programs by default unless the user asks for a GUI or web app.",
        "- If the user asks for a GUI/web app in a compiled language, keep it dependency-free or explain the",
        "  one install command in the top comment.",
    ]
    if spec["id"] == "java":
        lines.append(f"- The public class MUST be named {main_name[:-5]} (file-name match is enforced by javac).")
    if spec["id"] == "html":
        lines.append("- Single self-contained HTML file: inline CSS and JS only, no external CDNs or fonts.")
    if spec["id"] == "csharp":
        lines.append("- Top-level statements in Program.cs, .NET 8 compatible.")
    if spec["id"] == "go":
        lines.append("- package main with func main().")
    if spec["id"] == "other" and label != BY_ID["other"]["label"]:
        lines.append(f"- The user named the language '{label}' - write idiomatic {label}.")
    return "\n".join(lines)


_FENCE = re.compile(r"```[a-zA-Z0-9_+#.-]*\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> Tuple[str, bool]:
    m = _FENCE.search(text or "")
    if m:
        return m.group(1).strip() + "\n", True
    return (text or "").strip() + "\n", False


# ------------------------------------------------------------------ kit builder

_README = """{NAME} - built with Smash AI Pro Code Forge
=================================================

RUN IT NOW
  Windows : double-click launch.bat
  Linux   : ./launch.sh          (chmod +x once)
  macOS   : double-click launch.command

INSTALL IT (shortcuts + menu entry)
  Windows : double-click install.bat   (Start Menu + Desktop shortcuts)
  Linux/macOS: ./install.sh            (app-menu entry, launcher on PATH)

MAKE IT TRULY STANDALONE (no runtime needed afterwards)
  Windows : build-windows.bat
  Linux   : ./build-linux.sh
  macOS   : ./build-macos.sh
  -> open BUILD.md for exactly what each produces.

WHAT THIS APP DOES
  {PROMPT}

Source lives in src/{MAIN}. Generated {WHEN} by Smash AI Pro - {STORE}
"""


def _build_md(name: str, spec: Dict[str, Any], main: str, bin_name: str = "") -> str:
    bin_name = bin_name or name
    out = [f"# BUILD.md - making {name} a true standalone executable", "",
           f"Language: **{spec['label']}**. Runtime needed to *run* the launchers: "
           f"**{spec['runtime']}**.",
           "After building below, the produced executable needs **no runtime at all** "
           "(unless a line says otherwise).", ""]
    if spec["note"]:
        out += [f"> {spec['note']}", ""]
    for title, key in (("Windows", "build_win"), ("Linux", "build_linux"), ("macOS", "build_macos")):
        out.append(f"## {title}")
        lines = [fill(x, bin_name, main) for x in spec[key]]
        out += [f"    {x}" if not x.startswith(("result", "(", "echo", "for", "ask"))
                else f"> {x}" for x in lines] or ["    (nothing to build - this form is already native)"]
        out.append("")
    out += ["## Honest limits",
            "- Launchers need the runtime installed; builds remove that need where a recipe exists.",
            "- Interpreted languages marked above stay interpreted - the install scripts integrate them "
            "into the OS menu/PATH instead.",
            "- Antivirus sometimes flags fresh PyInstaller/pkg builds; code-sign for wide distribution.",
            "", f"Built by Smash AI Pro Code Forge - {STORE_URL}"]
    return "\n".join(out)


def _launcher_bat(spec: Dict[str, Any], name: str, main: str, bin_name: str = "") -> str:
    check = f"where {spec['check_win']} >nul 2>nul\r\n" if spec["check_win"] else ""
    guard = (f"if errorlevel 1 (\r\n  echo {spec['runtime']} was not found on this PC.\r\n"
             f"  echo Install it, or run build-windows.bat to make a standalone exe.\r\n"
             f"  pause\r\n  exit /b 1\r\n)\r\n") if spec["check_win"] else ""
    return ("@echo off\r\n"
            f"title {name}\r\n"
            "cd /d \"%~dp0src\"\r\n"
            f"{check}{guard}"
            f"{fill(spec['run_win'], bin_name or name, main)}\r\n"
            "echo.\r\npause\r\n")


def _launcher_sh(spec: Dict[str, Any], name: str, main: str, macos: bool = False,
                 bin_name: str = "") -> str:
    head = "#!/usr/bin/env bash\n"
    check = (f"command -v {spec['check_unix']} >/dev/null 2>&1 || {{\n"
             f"  echo '{spec['runtime']} not found. Install it, or run build-linux.sh / "
             f"build-macos.sh for a standalone build.'\n  exit 1\n}}\n"
             ) if spec["check_unix"] else ""
    run = fill(spec["run_unix"], bin_name or name, main)
    tail = "\nread -r -p 'Press Enter to close...' _\n" if macos else ""
    return f"{head}cd \"$(dirname \"$0\")/src\" || exit 1\n{check}{run}\n{tail}"


def _install_bat(name: str) -> str:
    return ("@echo off\r\nsetlocal\r\n"
            f"set APPNAME={name}\r\n"
            "set DEST=%LOCALAPPDATA%\\%APPNAME%\r\n"
            "if exist \"%DEST%\" rmdir /s /q \"%DEST%\"\r\n"
            "xcopy \"%~dp0\" \"%DEST%\\\" /e /i /q >nul\r\n"
            "powershell -NoProfile -Command \""
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut([Environment]::GetFolderPath('Programs')+'\\%APPNAME%.lnk');"
            "$s.TargetPath='%DEST%\\launch.bat';$s.WorkingDirectory='%DEST%\\src';$s.Save();"
            "$d=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\\%APPNAME%.lnk');"
            "$d.TargetPath='%DEST%\\launch.bat';$d.Save()\"\r\n"
            "echo %APPNAME% installed to %DEST% (Start Menu + Desktop shortcuts created).\r\n"
            "pause\r\n")


def _install_sh(name: str) -> str:
    return f"""#!/usr/bin/env bash
set -e
APPNAME="{name}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/$APPNAME"
mkdir -p "$DEST"
cp -R "$HERE/." "$DEST/"
chmod +x "$DEST/launch.sh" "$DEST/launch.command" 2>/dev/null || true
chmod +x "$DEST/build-linux.sh" "$DEST/build-macos.sh" 2>/dev/null || true
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/bin"
cat > "$HOME/.local/share/applications/$APPNAME.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=$APPNAME
Exec=$DEST/launch.sh
Terminal=true
DESK
ln -sf "$DEST/launch.sh" "$HOME/.local/bin/$APPNAME"
echo "$APPNAME installed to $DEST (app-menu entry + ~/.local/bin/$APPNAME)."
"""


def _uninstall_bat(name: str) -> str:
    return ("@echo off\r\n"
            f"set DEST=%LOCALAPPDATA%\\{name}\r\n"
            "if exist \"%DEST%\" rmdir /s /q \"%DEST%\"\r\n"
            f"del /q \"%USERPROFILE%\\Desktop\\{name}.lnk\" 2>nul\r\n"
            "powershell -NoProfile -Command \"Remove-Item "
            f"([Environment]::GetFolderPath('Programs')+'\\\\{name}.lnk') "
            "-ErrorAction SilentlyContinue\"\r\n"
            "echo Uninstalled.\r\npause\r\n")


def _uninstall_sh(name: str) -> str:
    return f"""#!/usr/bin/env bash
rm -rf "$HOME/.local/share/{name}"
rm -f "$HOME/.local/share/applications/{name}.desktop" "$HOME/.local/bin/{name}"
echo "{name} uninstalled."
"""


def _build_script_os(spec: Dict[str, Any], name: str, main: str, os_key: str,
                     bin_name: str = "") -> Optional[str]:
    lines = spec.get(os_key) or []
    if not lines:
        return None
    bin_name = bin_name or name
    if os_key == "build_win":
        body = "\r\n".join(fill(x, bin_name, main) for x in lines)
        return f"@echo off\r\ncd /d \"%~dp0src\"\r\necho Building {name} (standalone)...\r\n{body}\r\necho Done - see BUILD.md for the output location.\r\npause\r\n"
    shebang = "#!/usr/bin/env bash\nset -e\ncd \"$(dirname \"$0\")/src\"\n"
    body = "\n".join(fill(x, bin_name, main) for x in lines)
    return f"{shebang}echo 'Building {name} (standalone)...'\n{body}\necho 'Done - see BUILD.md for the output location.'\n"


def _python_zipapp(code: str) -> Optional[bytes]:
    """Bonus for Python: app.pyz - one file, runs with `python3 app.pyz` anywhere."""
    try:
        import zipapp
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "__main__.py"), "w", encoding="utf-8") as f:
                f.write(code)
            buf = io.BytesIO()
            zipapp.create_archive(td, target=buf, interpreter="/usr/bin/env python3")
            return buf.getvalue()
    except Exception:
        return None


def build_kit(slug: str, spec: Dict[str, Any], code: str, prompt: str,
              when: str) -> bytes:
    name = slug.replace("-", " ").title()   # display name: shortcuts, README, titles
    bin_name = slug                          # safe name: executables, jars, packages
    main = main_filename(spec, slug)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"src/{main}", code)
        z.writestr("README.txt", _README.replace("{NAME}", name).replace("{MAIN}", main)
                   .replace("{PROMPT}", (prompt or "").strip()[:300] or "(no description given)")
                   .replace("{WHEN}", when).replace("{STORE}", STORE_URL))
        z.writestr("launch.bat", _launcher_bat(spec, name, main, bin_name))
        z.writestr("launch.sh", _launcher_sh(spec, name, main, bin_name=bin_name))
        z.writestr("launch.command", _launcher_sh(spec, name, main, macos=True,
                                                  bin_name=bin_name))
        z.writestr("install.bat", _install_bat(name))
        z.writestr("install.sh", _install_sh(name))
        z.writestr("uninstall.bat", _uninstall_bat(name))
        z.writestr("uninstall.sh", _uninstall_sh(name))
        z.writestr("BUILD.md", _build_md(name, spec, main, bin_name))
        for path, script in (("build-windows.bat",
                              _build_script_os(spec, name, main, "build_win", bin_name)),
                             ("build-linux.sh",
                              _build_script_os(spec, name, main, "build_linux", bin_name)),
                             ("build-macos.sh",
                              _build_script_os(spec, name, main, "build_macos", bin_name))):
            if script:
                z.writestr(path, script)
        for rel, content in spec.get("extra", {}).items():
            path = rel[3:] if rel.startswith("../") else f"src/{rel}"
            z.writestr(fill(path, bin_name, main), fill(content, bin_name, main))
        if spec["id"] == "python":
            pyz = _python_zipapp(code)
            if pyz:
                z.writestr("app.pyz", pyz)
    return buf.getvalue()
