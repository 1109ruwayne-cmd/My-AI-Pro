"""Deploy Smash AI to a Hugging Face Space (free, fixed URL).

    python3 deploy_hf.py <HF_TOKEN> [space-name]

- Creates the Space if needed (Docker SDK, public).
- Uploads the app WITHOUT .env / usage.db / tests (never publish secrets).
- Replaces README.md with the HF landing page (front matter + short welcome);
  the full guide goes up as GUIDE.md.
- Prints the Space URL. Secrets (ADMIN_PASSWORD, AI_API_KEY) must be added in
  the Space Settings > Variables and secrets (the script prints the link),
  or pass them as env vars HF_ADMIN_PASSWORD / HF_AI_API_KEY and the script
  will try the variables REST API.
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "tests", "node_modules"}
EXCLUDE_FILES = {".env", "usage.db", "usage.db-wal", "usage.db-shm", "deploy_hf.py"}
EXCLUDE_SUFFIX = (".pyc", ".db", ".db-wal", ".db-shm", "-wal", "-shm", ".log")

HF_README = """---
title: {title}
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# {title}

AI assistant for coding, engineering, cybersecurity and your own documents -
with an API directory of 30 000+ tools built in.

**Free allowance:** 15 questions per visitor, then subscribe with
**Smash AI Pro** (R49/month, EFT into the owner's Capitec account).

Full operator guide: see `GUIDE.md` in the Files tab.
"""


def sh(cmd, **kw):
    print("+", " ".join(cmd) if isinstance(cmd, list) else cmd, flush=True)
    return subprocess.run(cmd, check=True, **kw)


def api(url, token, data=None, method=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Content-Type": "application/json"},
                                 data=json.dumps(data).encode() if data is not None else None,
                                 method=method or ("POST" if data is not None else "GET"))
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode() or "{}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    token = sys.argv[1].strip()
    name = (sys.argv[2] if len(sys.argv) > 2 else "my-ai-pro").strip().lower()

    sh([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"])
    from huggingface_hub import HfApi
    hf = HfApi(token=token)
    user = hf.whoami()["name"]
    space = f"{user}/{name}"
    print(f"Deploying as @{user} → Space {space}")

    hf.create_repo(repo_id=name, repo_type="space", space_sdk="docker",
                   exist_ok=True)
    print("Space ready.")

    # staging copy without secrets
    stage = "/tmp/hf-deploy"
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel_root = os.path.relpath(root, APP_DIR)
        for f in files:
            if f in EXCLUDE_FILES or f.endswith(EXCLUDE_SUFFIX):
                continue
            src = os.path.join(root, f)
            dst_dir = stage if rel_root == "." else os.path.join(stage, rel_root)
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(dst_dir, f))
    with open(os.path.join(APP_DIR, "README.md"), encoding="utf-8") as fh:
        dev_readme = fh.read()
    open(os.path.join(stage, "GUIDE.md"), "w", encoding="utf-8").write(dev_readme)
    title = "Smash AI Pro"
    open(os.path.join(stage, "README.md"), "w", encoding="utf-8").write(
        HF_README.format(title=title))

    hf.upload_folder(folder_path=stage, repo_id=space, repo_type="space",
                     commit_message="Deploy Smash AI")
    print("Files uploaded.")

    # try to set secrets via REST (falls back to manual instructions)
    for key, env in (("ADMIN_PASSWORD", "HF_ADMIN_PASSWORD"),
                     ("AI_API_KEY", "HF_AI_API_KEY")):
        val = os.environ.get(env, "")
        if not val:
            continue
        try:
            api(f"https://huggingface.co/api/spaces/{space}/variables", token,
                {"key": key, "value": val, "isSecret": True})
            print(f"Secret {key} set.")
        except Exception as e:
            print(f"Could not set {key} automatically ({e}) - add it in the UI.")

    print("\nDONE.")
    print(f"  Space:    https://huggingface.co/spaces/{space}")
    print(f"  Live URL: https://{user}-{name.replace('_', '-')}.hf.space")
    print(f"  Secrets:  https://huggingface.co/spaces/{space}/settings/variables")
    print("  The Space builds in 2-5 minutes; watch the logs on the Space page.")


if __name__ == "__main__":
    main()
