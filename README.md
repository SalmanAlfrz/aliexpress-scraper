## Setup

```bash
# 1. Create virtual environment
python3 -m venv env
source env/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your proxy credentials and optional Chromium path
```

## Environment Variables

Create a `.env` file in the project root:

```env
# Proxy
PROXY_HOST=proxy.example.com
PROXY_PORT=10000
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password

# Chromium path (leave empty to auto-detect)
CHROMIUM_PATH=
```

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXY_HOST` | Proxy server hostname | *(required)* |
| `PROXY_PORT` | Proxy server port | *(required)* |
| `PROXY_USERNAME` | Proxy username | *(required)* |
| `PROXY_PASSWORD` | Proxy password | *(required)* |
| `CHROMIUM_PATH` | Custom Chromium/Chrome binary path. Leave empty for auto-detect | *(empty)* |
| `HEADLESS` | Run browser without GUI (for VPS/server) | `false` |
| `NO_SANDBOX` | Disable Chrome sandbox (required on VPS/root) | `false` |

### Custom Chromium Path

If you want to use a specific Chromium installation:

```env
# macOS
CHROMIUM_PATH=/Applications/Chromium.app/Contents/MacOS/Chromium

# Linux
CHROMIUM_PATH=/usr/bin/chromium-browser
```

When empty, Zendriver auto-detects the installed Chrome/Chromium.

## Usage

### Start the server

```bash
python server.py
```

The server starts on port **3001**. On startup it:
1. Launches a persistent Chrome browser with proxy
2. Verifies the proxy IP via `ipinfo.io`
3. Starts the FastAPI server

### API Endpoints

#### `POST /api/aliexpress/sync`

Scrape an AliExpress page.

```bash
curl -X POST http://localhost:3001/api/aliexpress/sync \
  -H "Content-Type: application/json" \
  -d '{"url": "https://pt.aliexpress.com/"}'
```

**Response:**

```json
{
  "success": true,
  "captcha_detected": false,
  "proxy": {
    "ip": "177.x.x.x",
    "city": "São Paulo",
    "region": "São Paulo",
    "country": "BR",
    "org": "...",
    "latency_ms": 1200
  },
  "page": {
    "url": "https://pt.aliexpress.com/",
    "title": "AliExpress Brasil",
    "load_time_ms": 5400,
    "html": "<!DOCTYPE html>...",
    "screenshot_base64": "iVBORw0KGgo..."
  },
  "duration_ms": 8500
}
```

#### `GET /health`

```bash
curl http://localhost:3001/health
```

## Project Structure

```
├── .env                 # Proxy & Chromium config (not committed)
├── server.py            # FastAPI server (entry point)
├── scraper.py           # Zendriver browser automation
├── requirements.txt     # Python dependencies
└── README.md
```

## Anti-Detection

The scraper strips 25+ automation-telltale Chrome flags that zendriver adds by default (e.g. `--disable-infobars`, `--no-first-run`, `--disable-dev-shm-usage`). This mimics a clean, user-installed Chrome and reduces CAPTCHA triggers.

Proxy authentication is handled via a dynamically generated Chrome extension (Manifest V3).

If CAPTCHA is detected, the browser automatically resets (wipes profile, new proxy session) and retries once.

## Notes

- The browser runs in **visible mode** (`headless=False`) for debugging. Change in `scraper.py` if needed.
- Browser profile is stored at `~/.aliexpress-zd-profile` and wiped on CAPTCHA reset.
- Only AliExpress domains are allowed (`pt.aliexpress.com`, `www.aliexpress.com`, `aliexpress.com`).
