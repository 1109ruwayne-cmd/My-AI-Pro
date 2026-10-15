# My AI: coding, engineering, cybersecurity and your files - plus other AIs on call

Your own AI assistant. It writes and fixes code in any language, solves engineering problems step by step,
is a master of cybersecurity, and also knows the files you give it, which it searches by itself whenever a
question needs them. When you run other AIs - OpenHands, Dify, Open-LLM-VTuber, Ollama with orca-mini, or
free model APIs - it can hand work to them, automatically or with one click.

---

## Quick start (3 steps)

**1. Connect a free AI "brain"** (takes about 2 minutes)
1. Go to **https://aistudio.google.com/apikey** and sign in with your Google account.
2. Click **Create API key** and copy it.
3. In the app, click **Settings**, paste the key, click **Test connection**, then **Save**.

No credit card is needed. Without a key the app only works in *search-only* mode (it shows matching passages
from your files, but it can't write code or answer questions).

**2. Add your files (optional)**
Drag them onto the app (or click **Add files** on the left). A whole folder can be uploaded as a **.zip**.
Files with the same name (for example several `README.md`) never overwrite each other: they're named after
their heading, like `README - AI.md`, and exact copies are skipped.
You can also copy files straight into the `knowledge` folder; the app picks them up automatically.

**3. Ask anything**
For example: *"Build a one-page website for my shop as a single HTML file"*, *"Why does this Python code crash?"*
(attach the file with 📎), *"Size a steel beam for a 6 m span carrying 12 kN/m"*, or *"Which API can scrape
Google Maps reviews?"*

---

## What it can do

**Coding**
* Complete, working code in any language (Python, JavaScript/TypeScript, HTML/CSS, C/C++, C#, Java, Go, Rust,
  SQL, MATLAB, Arduino, Verilog/VHDL, G-code, shell scripts and many more), with install and run instructions.
* Debugging: explains the cause, then gives the fixed code. Attach code files or **screenshots of errors**
  with 📎, paste a screenshot with Ctrl+V, or drop files on the message box.
* Every code block has **Copy** and **Download** buttons and coloured syntax.
* **▶ Run** for Python and JavaScript, right in the chat. Python includes numpy, pandas, scipy, sympy and
  matplotlib (plots are shown). **Send to chat** passes the output back to the AI.
* **▶ Preview** for HTML and SVG: see web pages, apps and drawings working, in a safe sandbox.

**Engineering, maths and science**
* All fields: mechanical, electrical, electronic, civil and structural, chemical, mining, industrial,
  aerospace, mechatronics, computer engineering and more.
* Shows the given data, assumptions, formulas and step-by-step working with units, and names the relevant
  standards (SANS, Eurocodes, ISO, IEC, IEEE, ASME, ASTM ...).
* Formulas are shown properly typeset, like in a textbook.
* For safety-critical designs (structures, lifting, pressure, mains electricity, gas, fire) it adds a one-line
  reminder that a registered engineer should check the design before it is built or used.

**Cybersecurity**
* A core skill, not an add-on: secure coding and code review, hardening of servers, containers, cloud,
  networks and endpoints, vulnerability analysis ranked by risk with the exact commands and configs to fix
  each finding, threat modelling, detection rules (Sigma, YARA, Suricata), log and packet analysis, incident
  response and forensics, malware triage in a lab, penetration testing of systems you own or have written
  permission to test, CTF challenges, cryptography, and compliance (OWASP Top 10 & ASVS, NIST CSF 2.0,
  ISO/IEC 27001, CIS Controls, MITRE ATT&CK, PCI DSS, POPIA/GDPR).
* It draws one line, like any professional: no working malware, ransomware or spyware for real victims, and
  no help breaking into systems or people without authorisation. Every such request gets the legitimate
  version instead - a detection rule, a hardened config, a lab setup, a proof-of-concept against your own
  test system.

**Other AIs (connectors)**
* Your AI can hand work to other AIs you run - see *Connectors* below.

**Your files**
* Small collections are read in full with every question. For big ones (like the API list), the AI
  **searches them itself** when a question needs them: you'll see *"🔎 Searched your files for …"* plus the
  sources it used. Pure coding or engineering questions don't trigger a search, so they stay fast.

**Handy extras**
* **↻ Retry** asks again for a fresh answer. **Continue** appears if a very long answer gets cut off.
* The chat is saved in your browser. **New chat** starts over.

---

## Connectors: let other AIs answer too

Your AI has its own brain, but it can also hand a question to another AI you run. Above the message box
there is a row of buttons: **✨ Auto** (your AI picks the right one for each question), **🧠 My AI**
(always itself), and one button for every connector you switched on. Whichever one answers is shown on a
small badge above its answer. Nothing breaks if a service is switched off or not running - your AI just
answers by itself.

| Connector | What it is | Default address | Needs |
|---|---|---|---|
| 🤖 OpenHands agent | An AI software engineer that works in a real workspace: reads and writes files, runs tests, fixes what breaks. Best for whole-project jobs. | `http://127.0.0.1:8000` (its agent server) | optional session key |
| 🧩 Dify app or workflow | A chatbot, agent or workflow you built in Dify (self-hosted or cloud). | `http://127.0.0.1/v1` or `https://api.dify.ai/v1` | app API key |
| 🎭 Open-LLM-VTuber | Answers out loud with the Live2D avatar; the voice plays right in the chat (switch voice off in Settings if you prefer text). | `http://127.0.0.1:12393` | nothing |
| 🦙 Ollama | Any model on your own computer: free, private, works offline. | `http://127.0.0.1:11434/v1` | nothing |
| 🐋 orca-mini | The small fast orca-mini model through Ollama - a second opinion that costs nothing. Pull it with `ollama pull orca-mini`. | `http://127.0.0.1:11434/v1` | nothing |
| 🆓 Free model APIs | Free tiers from OpenRouter, Groq, Hugging Face, NVIDIA NIM and Mistral: one key, hundreds of open models. Settings shows a ready-made table of addresses and models. | `https://openrouter.ai/api/v1` | free key |
| 🔌 Another OpenAI-compatible server | LM Studio, vLLM, llama.cpp server, LocalAI, text-generation-webui, LiteLLM - anything that speaks the OpenAI API. | you choose | usually a key |

**Set one up:** ⚙️ Settings → *Connectors: other AIs it can use* → flip the switch on the one you want →
check the address → paste a key if it needs one → **Test** (it talks to the real service and tells you what
it found, e.g. the OpenHands agent profiles or the Dify bot's greeting) → **Save**.

**How it chooses:** with **✨ Auto** on, questions that read like a whole-project job ("build me an app and
run the tests", "fix the bug in my repo") go to OpenHands; "say it out loud" / avatar talk goes to the
VTuber; mentions of orca, Ollama, offline or a specific model go there; Dify catches workflow questions.
Everything else - coding, engineering, security, your files - your AI answers itself. Click a button to
override the choice for the next messages.

**Keys** you type are saved in `config.json` on the server and are never shown or sent back to the browser.
You can keep them out of the config file entirely by putting them in `.env`
(`OPENHANDS_API_KEY`, `DIFY_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `HF_TOKEN`, `NVIDIA_API_KEY`,
`MISTRAL_API_KEY`, `OLLAMA_API_KEY`).

---

## Run it on your own computer

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/
   (on Windows, tick **"Add Python to PATH"** during installation).
2. Start the app:
   * **Windows:** double-click `start.bat`
   * **Mac / Linux:** open a terminal in this folder and run `./start.sh`
3. Your browser opens at **http://localhost:8000**. The first start takes a minute while it installs things.

(Manual way: `pip install -r requirements.txt` then `python app.py`.)

---

## Settings explained

| Setting | What it does |
|---|---|
| **Your AI's name** | Shown in the app, and the AI introduces itself by this name. |
| **AI brain (provider)** | Google Gemini (free), OpenAI, OpenRouter, Groq, **Ollama** (free and offline on your own PC), or any OpenAI-compatible service. |
| **API key** | Your key for that provider. It's saved only in your browser. |
| **Model** | Which AI model to use. Click **Load models** to pick from everything your key allows. Bigger models write better code for hard problems but are slower and may cost money. |
| **How should it answer?** | *Everything* (recommended): coding, engineering and general knowledge, plus your files whenever they're relevant. *Only from my files*: strict, answers only from your documents (this turns off coding and general help). |
| **Extra instructions** | Personality, tone, language and rules. For example: *"You are the assistant for Thabo's Plumbing. Be friendly and brief. Prices in Rand."* |
| **Connectors** | Switch on the other AIs your AI may use (OpenHands, Dify, Open-LLM-VTuber, Ollama, orca-mini, free model APIs, anything OpenAI-compatible), with a **Test** button for each. |
| **Play the VTuber's voice** | On by default; switch off if you only want text from Open-LLM-VTuber. |
| **Advanced → Thinking effort** | How long the AI thinks before answering. *High* is best for hard coding and engineering problems (slower). Works with Gemini and OpenAI reasoning models. |
| **Advanced → reading amount** | If all your files fit, the AI reads them completely with every question. If not, it searches them, and this sets how much it reads per search. |
| **Advanced → Starter questions** | The buttons on the welcome screen. |
| **Advanced → Chat memory** | How many earlier messages it remembers (20 is good for coding sessions; 40 for very long ones). |

---

## Which files work

**Knowledge (left side, kept permanently):**

| Works | Notes |
|---|---|
| PDF | Must contain real text. **Scanned PDFs** (photos of pages) show a ⚠ warning, because they need OCR first. |
| Word `.docx`, PowerPoint `.pptx`, Excel `.xlsx` / `.xlsm` | Tables, slides, speaker notes and every sheet are included. |
| `.csv`, `.tsv`, `.txt`, `.md`, `.html`, `.json`, `.xml`, `.yaml` | |
| Old `.doc`, `.xls`, `.ppt` | Open them and use **Save as** to save in the new format (`.docx` / `.xlsx` / `.pptx`). |
| `.zip` | Unpacked automatically, including folders inside it. |

**Attachments (📎 in the message box, for one message):** code and text files of any kind (`.py`, `.js`,
`.c`, `.ino`, `.m`, `.log`, `.csv` ...) and pictures (`.png`, `.jpg`, `.webp`, `.gif`), for example
screenshots, circuit diagrams, drawings or photos of handwritten calculations.

---

## Put it online

**Right now (free, no account):** the app can run behind a Cloudflare quick tunnel - a real public
`https://….trycloudflare.com` address anyone can open, on any device:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

It prints the public address. The tunnel lives as long as the machine running it stays on; a quick
tunnel gets a new random address each time you start it. Good for showing people your AI today.

**Permanent home:** the folder is ready for any host that runs Docker (Render, Railway,
Hugging Face Spaces, Fly.io) - the `Dockerfile` is included. Set these environment variables on the
host (see `.env.example`):

* `AI_API_KEY`: your Gemini (or other) key, so visitors don't need their own. **Heads-up:** every
  visitor's question then uses *your* free quota, so keep an eye on it or protect the address.
* `ADMIN_PASSWORD`: **important.** Only someone with this password can change settings, connectors or
  files. Visitors can still chat, and they can bring their own key in their browser.
* Connector keys (`DIFY_API_KEY`, `OPENHANDS_API_KEY`, …) if you use connectors online. Remember the
  connectors' addresses must be reachable **from the host** - a `127.0.0.1` address only works when the
  other AI runs on the same machine/container network.

Tip: free hosts often wipe uploaded files when they restart. Put your files in the `knowledge`
folder **before** deploying so they're always there.

**Your own computer as the server:** run the app at home and point a tunnel at it
(`cloudflared tunnel --url http://127.0.0.1:8000`, or a named tunnel on your own domain). Everything -
files, connectors, Ollama - stays in your house; only the chat traffic goes through Cloudflare.

---

## Free allowance, paywall and subscriptions

Every visitor gets a free taste, then the app asks for a subscription. It is on by default:

* **Free allowance** - 15 questions and about 120 000 tokens per browser (a token is roughly 4
  characters of question + answer). The pill in the top bar shows what is left.
* **Paywall** - when the allowance runs out, the next question shows a plan card instead of an
  answer: the plan name, price and the payment options you enabled.
* **Subscription** - paying (or a coupon) unlocks unlimited questions until the plan expires.

Change everything in **Settings → Plans & payments** (owner password required): the free
allowance, plan name, price/currency/interval, a lifetime or monthly window, and which payment
methods to offer.

**Getting paid into your bank account:**

1. **Bank transfer / EFT (works today, no accounts needed).** Tick "manual". Fill in your bank,
   account name, account number and branch in the same Settings section. Visitors get those details
   plus a unique reference; when the money lands, open **Settings → Plans & payments → Open the
   payment dashboard** and press *Approve* next to their payment. That is the whole flow - straight
   into your account.
2. **Card payments (when you're ready).** Stripe and Paystack buttons are already built. Paste a
   Stripe secret key (+ webhook secret) or a Paystack secret key in Settings, tick the provider, and
   visitors can pay by card; webhook callbacks activate their subscription automatically. Stripe and
   Paystack both settle into your linked bank account. Until you add keys, leave those unticked -
   the paywall simply won't show those buttons.

The dashboard also shows visitors, questions, tokens, paywall hits, revenue per currency, lets you
reject a payment, grant a free subscription, and create coupon codes (percentage-free, day-based,
with a usage limit). Data lives in `usage.db` (SQLite, next to the app; set `USAGE_DB` to move it).
You - the owner, signed in with the admin password - are never metered or paywalled.

---

## Privacy

* Your files stay on the computer or server that runs the app. Only your messages, attachments and the
  passages the AI looks up are sent to the AI provider.
* On **Google's free tier**, Google may use what you send to improve its products. For confidential work, use
  a paid key, or **Ollama** to run everything offline on your own computer.
* **▶ Run** runs code in your own browser (nothing is sent anywhere). The first Python run downloads Python
  (about 10 MB, then cached) from cdn.jsdelivr.net. **▶ Preview** shows pages in a sealed-off frame that can't
  see your keys, chats or files.

---

## Troubleshooting

| Message / problem | Fix |
|---|---|
| "Your API key was rejected" | Copy the key again from aistudio.google.com/apikey and paste it in Settings. |
| "The model … wasn't found" | Settings → **Load models** → pick one → Save. |
| "You've reached the AI service's limit" | Free plans allow only a few questions per minute and per day. Wait a minute. Questions that search your files use two requests. |
| "This model can't read pictures" | Remove the picture, or choose a model that understands images (Gemini Flash does). |
| "Can't reach OpenHands / Dify / VTuber / Ollama …" | The service isn't running, or the address is wrong. Start it, then Settings → Connectors → **Test**. Each connector page shows the default address. |
| "… rejected the API key" | Paste the right key for that connector (Dify: your app → API Access; OpenHands: the server's session key). |
| OpenHands answers slowly | Normal: it runs a real agent that reads files and executes code before replying. Give it a minute. |
| The VTuber answers with no voice | Check `conf.yaml`: it needs a TTS voice configured. Text still works without one. |
| An error about "Thinking effort" | Settings → Advanced → Thinking effort → *Model default*. |
| Python says "Couldn't load Python" | Running Python needs an internet connection the first time. |
| `input()` doesn't work when running Python | Put the values directly in the code (the chat can't type into a running program). |
| File shows ⚠ "No readable text" | It's probably a scanned PDF or an image. Use a text-based version. |
| Answers miss details in very big files | Ask more specific questions, or Settings → Advanced → read more. |

---

## How it works (for the curious)

* `app.py`: the web server. It gives the AI its instructions (expert engineer and coder, plus your rules) and
  streams the answer. For big knowledge bases it offers the AI a `search_files` tool, so the AI decides when
  to look something up (it can search several times per question). If a model can't use tools, the app
  automatically falls back to sending the best-matching passages with the question.
* `knowledge_base.py`: reads each file, splits it into passages and ranks them with BM25 (classic
  search-engine ranking). This part runs locally and needs no AI. Big tables and lists (like an API directory)
  are split one row per passage, and the same entry listed in several files is only used once.
* `static/index.html`: the chat page (one file). `static/vendor/` holds KaTeX (maths) and highlight.js (code
  colours), so these work offline too. Python runs with Pyodide in the browser.
* `connectors.py`: the other AIs. Each one is a small translator: OpenAI-compatible servers (Ollama,
  orca-mini, OpenRouter, Groq, LM Studio …), Dify's chat API, the OpenHands agent server (through its
  OpenAI-compatible gateway), and Open-LLM-VTuber's WebSocket. It also holds the automatic routing rules
  that decide which AI suits a question.
* `config.json`: your saved settings (created when you click Save). Connector keys live here or in `.env`,
  never in the browser.

---

## What's loaded right now

The `knowledge` folder contains the **API Mega List** (github.com/cporter202/API-mega-list): 23 category files
with about 11,700 unique APIs, mostly Apify tools. The links in the list contain the list author's Apify
referral code (`?fpr=p2hrc6`). Remove any category with the ✕ next to it in the app.
