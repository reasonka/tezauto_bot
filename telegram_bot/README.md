# Car Diagnostics AI — Telegram Group Bot

A Telegram group bot that reads uploaded car diagnostic report files (PDF/TXT/CSV), extracts OBD2 trouble codes, and explains results + repair recommendations using an LLM, following the **Car Diagnostics AI** behavior rules (plain English, accurate, no guessing).

## Features
- Addable to group chats
- Handles uploaded documents:
  - **PDF** (scan reports)
  - **TXT** (logs)
  - **CSV** (code lists)
- Extracts likely OBD2 codes (e.g., `P0420`, `C1201`, `B1600`)
- Produces:
  - Clear meaning/system affected
  - Likely causes (as conditional possibilities, not guesses)
  - Recommended next steps / repair approach
  - Notes when a code may be manufacturer-specific / ambiguous

## Setup

### 1) Create a Telegram bot token
- Talk to `@BotFather` in Telegram
- Create a bot and copy the token

### 2) Create an OpenAI API key
- Create an API key and copy it

### 3) Configure environment variables
Create or update `.env` in the project root:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
MAX_FILE_MB=10
```

### 4) Install dependencies
From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5) Run

```bash
python main.py
```

## Usage
- Add the bot to a group.
- Send a diagnostic report file to the group.
- The bot will:
  1) Download the file
  2) Extract text + OBD2 codes
  3) Respond with explanation + next steps

## Hosting on an external server (VPS)

To run the bot 24/7 on a Linux server (e.g. VPS from DigitalOcean, Hetzner, AWS, etc.):

### 1. Prepare the server
- SSH into the server: `ssh user@your-server-ip`
- Install Python 3.10+ (e.g. `sudo apt update && sudo apt install -y python3 python3-venv python3-pip` on Debian/Ubuntu)

### 2. Upload the project
- Option A: clone from Git: `git clone <your-repo-url> telegram_bot && cd telegram_bot`
- Option B: copy files with `scp -r ./telegram_bot user@your-server-ip:~`

### 3. Configure and run
```bash
cd ~/telegram_bot   # or your path
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env            # paste TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, etc.
```

### 4. Run in the background

**Option A — systemd (recommended)**  
Create a service file:

```bash
sudo nano /etc/systemd/system/car-diagnostics-bot.service
```

Paste (adjust `User`, `WorkingDirectory`, and `ExecStart` path):

```ini
[Unit]
Description=Car Diagnostics Telegram Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/telegram_bot
Environment=PATH=/home/YOUR_USER/telegram_bot/.venv/bin
ExecStart=/home/YOUR_USER/telegram_bot/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable car-diagnostics-bot
sudo systemctl start car-diagnostics-bot
sudo systemctl status car-diagnostics-bot
```

**Option B — screen or tmux**  
```bash
screen -S bot
source .venv/bin/activate && python main.py
# Detach: Ctrl+A, then D. Reattach: screen -r bot
```

### 5. Firewall
The bot uses **polling** (outgoing HTTPS to Telegram). No need to open inbound ports; ensure outbound HTTPS (443) is allowed.

### 6. Logs
- systemd: `journalctl -u car-diagnostics-bot -f`
- To log to a file, redirect in `ExecStart`: `ExecStart=.../python main.py >> /var/log/car-bot.log 2>&1`

---

## Language

The bot is configured to **respond in Russian** (все ответы на русском). To change the language, edit the "Language" section in `llm.py` and the reply strings in `main.py`.

---

## Notes / Limitations
- This bot does **not** connect to an OEM service database. It will clearly say when codes are ambiguous or not present in the extracted report.
- For best results, diagnostic reports should include vehicle **make/model/year/engine** and the scan tool’s reported code descriptions.

