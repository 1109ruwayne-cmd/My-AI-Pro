# My AI Pro source code: infrastructure

## Dockerfile

The Docker image the site runs in (Render free tier).

~~~~dockerfile
# For putting your AI online (Render, Railway, Hugging Face Spaces, Fly.io ...)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
~~~~

## requirements.txt

Python dependencies.

~~~~text
fastapi>=0.110
uvicorn>=0.29
python-multipart>=0.0.9
openai>=1.40
pypdf>=4.0
cryptography>=42
python-docx>=1.1
python-pptx>=0.6.23
openpyxl>=3.1
websockets>=12
httpx>=0.27
~~~~

## render.yaml

Render deploy blueprint (secrets are set as env vars, never in files).

~~~~yaml
services:
  - type: web
    name: my-ai-pro
    runtime: docker
    region: frankfurt
    plan: free
    dockerfilePath: ./Dockerfile
    healthCheckPath: /api/status
    envVars:
      - key: ADMIN_PASSWORD
        sync: false
      - key: AI_API_KEY
        sync: false
      - key: TURSO_DB_URL
        value: https://onny-ruwayne.aws-ca-central-1.turso.io
      - key: TURSO_AUTH_TOKEN
        sync: false
~~~~

## start.sh

Startup script.

~~~~bash
#!/usr/bin/env bash
# Start your AI on Mac / Linux:  ./start.sh   (then open http://localhost:8000)
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First start: setting things up (takes a minute)..."
  python3 -m venv .venv || { echo "Please install Python 3.10+ from https://www.python.org/downloads/"; exit 1; }
fi
. .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements.txt
python app.py --open
~~~~
