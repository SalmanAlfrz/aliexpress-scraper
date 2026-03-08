import asyncio
import base64
import json
import os
import random
import shutil
import tempfile
import time
from pathlib import Path

from bs4 import BeautifulSoup  # pyright: ignore[reportMissingModuleSource]
from dotenv import load_dotenv
import zendriver as zd

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = int(os.getenv("PROXY_PORT", "0"))
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH", "")
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("true", "1", "yes")
NO_SANDBOX = os.getenv("NO_SANDBOX", "false").lower() in ("true", "1", "yes")

USER_DATA_DIR = Path.home() / ".aliexpress-zd-profile"

POPUP_SELECTORS = [
    "button.close-icon-container.dialog-close-icon",
    "img.pop-close-btn",
    ".close-btn",
    ".btn-close",
    "a.close",
]

# Automation-telltale flags to strip from zendriver defaults
EXCLUDE_CHROME_ARGS = {
    "--allow-pre-commit-input",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-client-side-phishing-detection",
    "--disable-component-extensions-with-background-pages",
    "--disable-default-apps",
    "--disable-dev-shm-usage",
    "--disable-hang-monitor",
    "--disable-infobars",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-search-engine-choice-screen",
    "--disable-setuid-sandbox",
    "--disable-sync",
    "--export-tagged-pdf",
    "--force-color-profile=srgb",
    "--generate-pdf-document-outline",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
}

# ── State ─────────────────────────────────────────────────────────────────────

_browser = None
_proxy_info = None


def log(tag: str, msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] [{tag}] {msg}")


# ── Proxy ─────────────────────────────────────────────────────────────────────


def _build_proxy() -> dict:
    return {
        "host": PROXY_HOST,
        "port": PROXY_PORT,
        "user": PROXY_USERNAME,
        "pass": PROXY_PASSWORD,
    }


def _create_proxy_extension(proxy: dict) -> str:
    ext_dir = tempfile.mkdtemp(prefix="proxy_ext_")

    manifest = {
        "version": "1.0.0",
        "manifest_version": 3,
        "name": "Proxy Auth",
        "permissions": ["proxy", "webRequest", "webRequestAuthProvider"],
        "host_permissions": ["<all_urls>"],
        "background": {"service_worker": "background.js"},
        "minimum_chrome_version": "22.0.0",
    }

    background_js = f"""
var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{ scheme: "http", host: "{proxy['host']}", port: {proxy['port']} }},
        bypassList: ["localhost"]
    }}
}};
chrome.proxy.settings.set({{ value: config, scope: "regular" }}, function() {{}});
chrome.webRequest.onAuthRequired.addListener(
    function() {{ return {{ authCredentials: {{ username: "{proxy['user']}", password: "{proxy['pass']}" }} }}; }},
    {{ urls: ["<all_urls>"] }},
    ["blocking"]
);
"""

    with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    with open(os.path.join(ext_dir, "background.js"), "w") as f:
        f.write(background_js)

    return ext_dir


async def _check_proxy() -> dict:
    """Verify proxy IP via ipinfo.io (non-fatal)."""
    try:
        t = time.time()
        page = await _browser.get("https://ipinfo.io/json")
        await asyncio.sleep(5)
        info = json.loads(await page.evaluate("document.body.innerText"))
        ms = int((time.time() - t) * 1000)
        return {k: info.get(k) for k in ("ip", "city", "region", "country", "org")} | {"latency_ms": ms}
    except Exception:
        return {"ip": "unknown", "city": "unknown", "region": "unknown", "country": "unknown", "org": "unknown", "latency_ms": 0}


# ── Browser ───────────────────────────────────────────────────────────────────


async def init_browser():
    global _browser, _proxy_info

    if _browser:
        return

    lock = USER_DATA_DIR / "SingletonLock"
    if lock.exists():
        lock.unlink()

    proxy = _build_proxy()
    ext_dir = _create_proxy_extension(proxy)
    log("INIT", f"Proxy {proxy['host']}:{proxy['port']} | {proxy['user']}")

    browser_args = [
        f"--load-extension={ext_dir}",
        "--accept-lang=pt-BR,pt,en-US,en",
        "--window-size=1920,1080",
    ]
    if NO_SANDBOX:
        browser_args.append("--no-sandbox")

    config_kwargs = dict(
        headless=HEADLESS,
        sandbox=not NO_SANDBOX,
        user_data_dir=str(USER_DATA_DIR),
        browser_args=browser_args,
    )
    if CHROMIUM_PATH:
        config_kwargs["browser_executable_path"] = CHROMIUM_PATH

    config = zd.Config(**config_kwargs)

    # Strip automation-telltale flags
    config._default_browser_args = [
        arg for arg in config._default_browser_args
        if arg not in EXCLUDE_CHROME_ARGS
        and not any(arg.startswith(ex) for ex in EXCLUDE_CHROME_ARGS)
    ]
    config._default_browser_args = [
        arg.replace("DisableLoadExtensionCommandLineSwitch,", "")
        if "DisableLoadExtensionCommandLineSwitch" in arg else arg
        for arg in config._default_browser_args
    ]

    _browser = await zd.start(config=config)
    _proxy_info = await _check_proxy()
    log("INIT", f"Ready | IP: {_proxy_info['ip']} ({_proxy_info['country']}) | {_proxy_info['latency_ms']}ms")


async def close_browser():
    global _browser, _proxy_info

    if not _browser:
        return
    try:
        await _browser.stop()
    except Exception:
        pass
    _browser = None
    _proxy_info = None


async def reset_browser():
    """Wipe profile and restart with a fresh proxy session."""
    log("RESET", "Resetting browser ...")
    await close_browser()
    if USER_DATA_DIR.exists():
        shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
    await init_browser()


# ── Page Helpers ──────────────────────────────────────────────────────────────


async def _dismiss_popups(page):
    for sel in POPUP_SELECTORS:
        try:
            el = await page.select(sel, timeout=1)
            if el:
                await el.click()
                await asyncio.sleep(0.3)
        except Exception:
            pass


async def _wait_for_csr(page, timeout: int = 30) -> bool:
    """Poll until #root has rendered children."""
    t = time.time()
    while time.time() - t < timeout:
        if await page.evaluate("document.querySelector('#root')?.children.length > 2"):
            log("CSR", f"Rendered in {int((time.time() - t) * 1000)}ms")
            return True
        await asyncio.sleep(1)
    log("CSR", f"Timeout after {timeout}s")
    return False


async def _has_captcha(page) -> bool:
    return await page.evaluate("""
        !!document.querySelector('iframe[src*="captcha"]') ||
        !!document.querySelector('iframe[src*="recaptcha"]') ||
        !!document.querySelector('.nc-container') ||
        document.body.innerText.includes('check if you are a robot') ||
        document.body.innerText.includes('need to check if you are a robot')
    """)


# ── Scrape ────────────────────────────────────────────────────────────────────


async def scrape(target_url: str) -> dict:
    if not _browser:
        await init_browser()

    log("SCRAPE", f"GET {target_url}")
    t = time.time()
    page = await _browser.get(target_url)
    await asyncio.sleep(random.uniform(3, 5))

    if await _has_captcha(page):
        log("SCRAPE", "CAPTCHA detected — resetting browser")
        await reset_browser()
        t = time.time()
        page = await _browser.get(target_url)
        await asyncio.sleep(random.uniform(4, 6))

    await _wait_for_csr(page, timeout=30)
    load_ms = int((time.time() - t) * 1000)

    # await page.scroll_down(200)
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await _dismiss_popups(page)

    html = BeautifulSoup(await page.get_content(), "html.parser")
    title = await page.evaluate("document.title")
    url = await page.evaluate("window.location.href")
    captcha = await _has_captcha(page)

    screenshot_path = Path(tempfile.gettempdir()) / "aliexpress_screenshot.png"
    await page.save_screenshot(screenshot_path)
    screenshot_b64 = base64.b64encode(screenshot_path.read_bytes()).decode()

    log("SCRAPE", f"Done {load_ms}ms | {len(str(html))} chars | captcha={'yes' if captcha else 'no'}")

    return {
        "success": not captcha,
        "captcha_detected": captcha,
        "proxy": _proxy_info,
        "data": {
            "url": url,
            "title": title,
            "load_time_ms": load_ms,
            "html": str(html),
            "screenshot_base64": screenshot_b64,
        },
    }
