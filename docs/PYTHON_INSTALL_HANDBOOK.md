# ClippyMe — Windows Python install handbook

Run ClippyMe natively on Windows with Python + Node. No Docker.

**Open the app at:** http://localhost:5175

---

## One-page cheat sheet

Print this or keep it in a second monitor tab.

### What you need (once)

| Tool | Install (PowerShell) | Check |
|------|----------------------|-------|
| Python **3.11** | `winget install Python.Python.3.11` | `python --version` |
| ffmpeg | `winget install Gyan.FFmpeg` | `ffmpeg -version` |
| Deno | `winget install DenoLand.Deno` | `deno --version` |
| Node **20+** | `winget install OpenJS.NodeJS.LTS` | `node --version` |
| auto-editor | [GitHub releases](https://github.com/WyattBlue/auto-editor/releases) → `auto-editor-windows-x86_64.exe` → rename to `auto-editor.exe` → add to PATH | `auto-editor --version` |

Close and reopen PowerShell after `winget` installs.

### First-time setup (project folder)

Replace `C:\path\to\clippyme` with your real folder.

```powershell
cd C:\path\to\clippyme

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

cd dashboard
npm install
cd ..
```

First `pip install` takes **10–30+ min** (PyTorch is huge). You only do this once.

If venv activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Every day — two PowerShell windows

**Window 1 — backend**

```powershell
cd C:\path\to\clippyme
.\.venv\Scripts\Activate.ps1
python -m uvicorn clippyme.api.app:app --reload --host 0.0.0.0 --port 8000
```

**Window 2 — frontend**

```powershell
cd C:\path\to\clippyme\dashboard
npm run dev
```

**Browser:** http://localhost:5175 · **Stop:** `Ctrl+C` in each window

### Settings (first launch)

**Settings** tab → paste **Gemini** key ([AI Studio](https://aistudio.google.com/apikey)) → optional **Deepgram** (faster than local Whisper) → Save.

No `.env` file. Keys live in `data\config.json` on your PC.

### Quick fixes

| Problem | Fix |
|---------|-----|
| `python` not found | Reinstall Python 3.11, tick **Add to PATH**, reopen PowerShell |
| Can't connect in browser | Both terminals running? Use **5175**, not 8000 |
| YouTube download fails | Upload the file instead, or add cookies in **Settings** |
| Very slow processing | Normal on CPU — add Deepgram key, or wait |
| Smart Cut weak / `ffmpeg-concat` in logs | Install `auto-editor.exe` on PATH, restart backend |
| Port in use | `netstat -ano \| findstr :5175` then `taskkill /PID <pid> /F` |
| `No module named 'clippyme'` | Activate `.venv`, run `pip install -e .` from project root |

### Paste this into ChatGPT / Cursor when stuck

```
Windows 10/11. Installing ClippyMe per docs/PYTHON_INSTALL_HANDBOOK.md.
Step: [first-time setup / daily start / error].
Command: [what you ran]
Error (last 30 lines): [paste here]
python --version: [output]
ffmpeg -version: [works / fails]
```

**Never paste API keys or data\config.json.**

### Health check (`.venv` activated, project root)

```powershell
python -c "import torch, cv2, mediapipe, clippyme; print('OK')"
ffmpeg -version
deno --version
auto-editor --version
node --version
```

---

## What you are running

| Part | Terminal | URL |
|------|----------|-----|
| **Backend** (Python) | Window 1 | http://localhost:8000 (API — don't open manually) |
| **Frontend** (dashboard) | Window 2 | **http://localhost:5175** ← use this |

---

## Before you start

| | Minimum | Recommended |
|---|---------|-------------|
| **OS** | Windows 10/11 | Windows 11 |
| **RAM** | 8 GB | 16 GB+ |
| **Free disk** | 15 GB | 25 GB+ |
| **Python** | 3.11 | 3.11.x |
| **Node** | 20+ | 20 LTS |

**API keys** (in-app **Settings**, not env files):

| Key | Needed? | Without it |
|-----|---------|------------|
| **Gemini** | Yes, for good clips | Offline fallback — works but much weaker |
| **Deepgram** | Optional | Local Whisper on CPU (slow) |
| **ElevenLabs** | Optional | Alt cloud transcription |
| **HuggingFace** | Optional | Helps model downloads |

---

## Step 1 — Get the code

**ZIP:** https://github.com/fralapo/clippyme → **Code** → **Download ZIP** → unzip to e.g. `C:\Users\You\clippyme`

**Git:**

```powershell
git clone https://github.com/fralapo/clippyme.git
cd clippyme
```

All commands below assume you're in the folder that has `requirements.txt` and `dashboard\`.

---

## Step 2 — Install system tools

Open **PowerShell**:

```powershell
winget install Python.Python.3.11
winget install Gyan.FFmpeg
winget install DenoLand.Deno
winget install OpenJS.NodeJS.LTS
```

**auto-editor** (recommended for Smart Cut):

1. https://github.com/WyattBlue/auto-editor/releases
2. Download `auto-editor-windows-x86_64.exe`
3. Rename to `auto-editor.exe`
4. Put it in e.g. `C:\Users\You\bin\`
5. **Settings → System → About → Advanced system settings → Environment Variables → Path → New** → add that folder

Verify (new PowerShell window):

```powershell
python --version
ffmpeg -version
deno --version
node --version
auto-editor --version
```

---

## Step 3 — Python virtual environment

```powershell
cd C:\Users\You\clippyme

python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` in the prompt. Activate this **every time** you start the backend.

---

## Step 4 — Python packages

With `(.venv)` active:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Grab coffee — first run downloads several GB.

**NVIDIA GPU (optional):** install latest Game Ready drivers, then after the pip install above:

```powershell
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

`False` is fine — everything still works on CPU, just slower.

---

## Step 5 — Dashboard packages

```powershell
cd dashboard
npm install
cd ..
```

Once per clone, or again after updates that touch `package.json`.

---

## Step 6 — Start it

See **cheat sheet → Every day** above. Two windows, then http://localhost:5175.

---

## Step 7 — Configure & run

1. **Settings** → Gemini key → Save
2. **Create** → paste YouTube URL or upload file → process
3. First job also downloads YOLO/Whisper weights — extra wait, one-time

---

## After updates

```powershell
cd C:\Users\You\clippyme
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
cd dashboard
npm install
```

---

## Optional — CLI only (no dashboard)

```powershell
.\.venv\Scripts\Activate.ps1
python -m clippyme.pipeline.main "https://www.youtube.com/watch?v=VIDEO_ID" --instructions "focus on hooks"
```

Clips land in `output\`.

---

## Troubleshooting (detail)

### `pip install` fails (torch / opencv / mediapipe)

- 15+ GB free disk
- Install [VC++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
- `python -m pip install --upgrade pip` then retry
- Paste last 20 lines of error into AI (template in cheat sheet)

### Wrong Python version

```powershell
python --version
deactivate
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### YouTube blocked / 429

1. Upload the video file instead
2. **Settings** → upload `cookies.txt` (Netscape format, exported while logged into YouTube)
3. Check `deno --version`
4. Debug only: `$env:YTDLP_VERBOSE="1"` before starting backend (don't share those logs)

### `CUDA not usable for Whisper` in logs

Ignore if you use Deepgram/ElevenLabs. Otherwise CPU Whisper runs — slower but fine.

### Timezone errors when publishing

```powershell
pip install "tzdata>=2024.1"
```

Restart backend.

### Broken frontend after pull

```powershell
cd dashboard
Remove-Item -Recurse -Force node_modules
npm install
```

---

## Using AI effectively

1. Open this repo in **Cursor** (or paste errors into ChatGPT/Claude).
2. Say which cheat-sheet step you're on.
3. Paste the **command** and **last ~30 lines** of output.
4. Run the health-check block and include results.
5. Never share keys or `data\`.

Example:

> *"Windows 11, PYTHON_INSTALL_HANDBOOK cheat sheet first-time setup. `pip install -r requirements.txt` fails at torch with [error]. python 3.11.9, 20GB free disk."*

---

## Security

- For **your PC only** — don't expose 8000/5175 to the internet.
- `data\config.json` = secrets. Don't commit or screenshot it.

---

## More docs

- [README — Configuration](../README.md#configuration)
- [TESTING.md](../TESTING.md)
- [CLAUDE.md](../CLAUDE.md) — developer architecture reference

<p align="right"><a href="#one-page-cheat-sheet">back to cheat sheet</a></p>
