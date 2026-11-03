import os
import sys
import io
import time
import socket
import random
import shutil
import threading
import subprocess
import urllib.request
import webbrowser
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml
import requests
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright, BrowserContext, Page

# =====================================================================
#                      BASE SETUP & PATHS
# =====================================================================

# Resolve base directory (handles running both from source and inside PyInstaller .exe)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR

CONFIG_PATH = BASE_DIR / "config.yaml"
SESSIONS_DIR = BASE_DIR / "sessions"
LOGS_DIR = BASE_DIR / "logs"
HISTORY_PATH = BASE_DIR / "history.json"
LAST_CHECKS_PATH = BASE_DIR / "last_checks.json"
UI_DIR = BUNDLE_DIR / "ui" if (BUNDLE_DIR / "ui").exists() else BASE_DIR / "ui"

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Enforce UTF-8 standard output and error on Windows
if sys.platform == "win32":
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    elif hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def set_low_process_priority():
    """Set process priority to BELOW_NORMAL_PRIORITY_CLASS on Windows so games/apps have full priority."""
    if sys.platform == "win32":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            pid = os.getpid()
            handle = k32.OpenProcess(0x0200 | 0x0400, False, pid)
            if handle:
                k32.SetPriorityClass(handle, 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
                k32.CloseHandle(handle)
        except Exception:
            pass

# =====================================================================
#                      LOGGING & IN-MEMORY CONSOLE
# =====================================================================

LOG_BUFFER: List[Dict[str, Any]] = []
LOG_LOCK = threading.Lock()

def add_log(level: str, message: str):
    """Print log to stdout and append to in-memory buffer for GUI."""
    t_str = time.strftime("%H:%M:%S")
    lvl = level.upper()
    print(f"[{t_str}] {lvl:<7} | {message}")
    with LOG_LOCK:
        LOG_BUFFER.append({"time": t_str, "level": lvl, "message": message})
        if len(LOG_BUFFER) > 500:
            LOG_BUFFER.pop(0)


# =====================================================================
#                      CONFIGURATION
# =====================================================================

DEFAULT_CONFIG = {
    "app": {
        "headless": True,
        "daemon_enabled": False,
        "action_delay_ms": 1500,
        "screenshot_on_error": True,
        "check_interval_hours": 12
    },
    "notifications": {
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "discord": {"enabled": False, "webhook_url": ""}
    },
    "games": {
        "war_robots": {
            "enabled": True,
            "player_id": "",
            "platform": "crossplay",
            "market_url": "https://shop.warrobots.com/"
        }
    }
}

def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Guard against missing configuration sections
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if sub_k not in cfg[k]:
                    cfg[k][sub_k] = sub_v
    return cfg

def save_config(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# =====================================================================
#                      HISTORY PERSISTENCE
# =====================================================================

def load_history() -> List[Dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history_entry(entry: Dict[str, Any]):
    history = load_history()
    history.insert(0, entry)
    history = history[:100]  # Keep the last 100 entries
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_log("DEBUG", f"Could not save history: {e}")

def load_last_checks() -> Dict[str, Any]:
    if not LAST_CHECKS_PATH.exists():
        return {}
    try:
        with open(LAST_CHECKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_last_check(game: str, status_type: str, message: str, items: list = None):
    checks = load_last_checks()
    checks[game] = {
        "status_type": status_type,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "items": items or []
    }
    try:
        with open(LAST_CHECKS_PATH, "w", encoding="utf-8") as f:
            json.dump(checks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_log("DEBUG", f"Could not save last checks: {e}")

CLAIMS_LOG_PATH = LOGS_DIR / "claims.log"
CLAIMS_JSONL_PATH = LOGS_DIR / "claims.jsonl"

def log_claim_event(game: str, pilot_id: str, status_type: str, item_name: str, message: str, trigger_source: str = "manual"):
    """Appends claim events with timestamps to logs/claims.log and claims.jsonl for reset timing analysis."""
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    unix_ts = int(time.time())

    line = f"[{now_str} | unix:{unix_ts}] [{status_type.upper()}] [{game}] Pilot: {pilot_id} | Item: {item_name} | Trigger: {trigger_source} | Message: {message}\n"
    try:
        with open(CLAIMS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        add_log("DEBUG", f"Could not write to claims.log: {e}")

    try:
        entry = {
            "timestamp": now_str,
            "unix_timestamp": unix_ts,
            "game": game,
            "pilot_id": pilot_id,
            "status_type": status_type,
            "item_name": item_name,
            "trigger_source": trigger_source,
            "message": message
        }
        with open(CLAIMS_JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        add_log("DEBUG", f"Could not write to claims.jsonl: {e}")


# =====================================================================
#                      DYNAMIC BROWSER FINDER
# =====================================================================

def find_browser_for_app_window() -> Optional[str]:
    """Dynamic 4-level Chromium-based browser discovery without hardcoded paths."""
    # 1. Windows Registry (Chrome, Edge, Brave)
    if sys.platform == "win32":
        try:
            import winreg
            for exe_name in ["chrome.exe", "msedge.exe", "brave.exe"]:
                for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
                    try:
                        with winreg.OpenKey(root, key_path) as k:
                            val, _ = winreg.QueryValueEx(k, "")
                            if val and os.path.exists(val):
                                return str(Path(val).resolve())
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. System PATH
    for cmd in ["chrome", "msedge", "brave", "chromium"]:
        p = shutil.which(cmd)
        if p and os.path.exists(p):
            return str(Path(p).resolve())

    # 3. Playwright Chromium executable
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if exe and os.path.exists(exe):
                return str(Path(exe).resolve())
    except Exception:
        pass

    # 4. File system globbing fallback
    base_dirs = [
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
    ]
    for b in base_dirs:
        if b and os.path.exists(b):
            for match in Path(b).glob("**/chrome.exe"):
                if match.is_file():
                    return str(match.resolve())
            for match in Path(b).glob("**/msedge.exe"):
                if match.is_file():
                    return str(match.resolve())

    return None


# =====================================================================
#                      BROWSER MANAGER (STEALTH & SESSION)
# =====================================================================

class BrowserManager:
    def __init__(self, headless: bool = True, session_name: str = "mygames_main"):
        self.headless = headless
        self.session_name = session_name
        self.profile_dir = SESSIONS_DIR / session_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self.context: Optional[BrowserContext] = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def clean_stale_locks(self):
        """Cleans up browser singleton locks left behind by interrupted or crashed instances."""
        lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]
        for lock_name in lock_files:
            p = self.profile_dir / lock_name
            if p.exists():
                try:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                    add_log("DEBUG", f"Removed stale browser lock: {lock_name}")
                except Exception as e:
                    add_log("DEBUG", f"Could not remove lock {lock_name}: {e}")

    def start(self) -> BrowserContext:
        self.clean_stale_locks()
        set_low_process_priority()
        self._playwright = sync_playwright().start()
        browser_exe = find_browser_for_app_window()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage"
        ]
        if self.headless:
            args.extend(["--disable-gpu", "--renderer-process-limit=2"])

        kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "args": args,
            "viewport": {"width": 1366, "height": 768},
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        if browser_exe and os.path.exists(browser_exe):
            kwargs["executable_path"] = browser_exe

        self.context = self._playwright.chromium.launch_persistent_context(**kwargs)
        self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        return self.context

    def new_page(self) -> Page:
        if not self.context:
            raise RuntimeError("Browser is not running.")
        return self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self):
        try:
            if self.context:
                self.context.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass


# =====================================================================
#                      NOTIFIER (TELEGRAM / DISCORD)
# =====================================================================

class Notifier:
    def __init__(self, config: Dict[str, Any]):
        self.tg = config.get("notifications", {}).get("telegram", {})
        self.dc = config.get("notifications", {}).get("discord", {})

    def send(self, message: str):
        if self.tg.get("enabled"):
            token = self.tg.get("bot_token")
            chat_id = self.tg.get("chat_id")
            if token and chat_id:
                try:
                    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
                    add_log("INFO", "Notification sent to Telegram.")
                except Exception as e:
                    add_log("ERROR", f"Telegram error: {e}")

        if self.dc.get("enabled"):
            wh = self.dc.get("webhook_url")
            if wh:
                try:
                    requests.post(wh, json={"content": message}, timeout=10)
                    add_log("INFO", "Notification sent to Discord.")
                except Exception as e:
                    add_log("ERROR", f"Discord error: {e}")


# =====================================================================
#                      GAME REWARD COLLECTORS
# =====================================================================

class WarRobotsCollector:
    def __init__(self, game_cfg: Dict[str, Any], app_cfg: Dict[str, Any]):
        self.name = "War Robots"
        self.cfg = game_cfg
        self.player_id = str(self.cfg.get("player_id", "")).strip()
        self.platform = self.cfg.get("platform", "crossplay").lower()
        self.shop_url = self.cfg.get("market_url", "https://shop.warrobots.com/")
        if "market.my.games" in self.shop_url:
            self.shop_url = "https://shop.warrobots.com/"

    def _dismiss_overlays(self, page: Page):
        try:
            accept_btn = page.query_selector('.cmpboxbtnyes, button:has-text("Accept all"), button:has-text("Принять все")')
            if accept_btn and accept_btn.is_visible():
                accept_btn.click()
                time.sleep(0.8)
        except Exception:
            pass

        try:
            page.evaluate("""() => {
                document.querySelector('#cmpbox')?.remove();
                document.querySelector('.cmpstyleroot')?.remove();
                document.querySelector('.styles_vpnDisclaimer__s6IdF')?.remove();
                document.querySelectorAll('.cookie-banner, [class*="cookie"]').forEach(e => e.remove());
            }""")
        except Exception:
            pass

    def _ensure_logged_in(self, page: Page):
        """Ensures the player ID is set in the official shop."""
        self._dismiss_overlays(page)

        account_chip = page.query_selector('.shop-account-chip, .shop-account-chip__trigger')
        chip_text = (account_chip.inner_text() or "").strip() if account_chip else ""

        if not account_chip or "ENTER YOUR GAME ID" in chip_text.upper():
            id_btn = page.query_selector('.shop-account-chip__no-account, button:has-text("ENTER YOUR GAME ID"), [class*="no-account"]')
            if id_btn and id_btn.is_visible():
                add_log("INFO", f"[{self.name}] Entering Game ID: {self.player_id}...")
                id_btn.click()
                time.sleep(1.5)

                inp = page.query_selector('input[placeholder*="account ID"], input[placeholder*="game account"], input[placeholder*="ID"]')
                if inp and inp.is_visible():
                    inp.fill(self.player_id)
                    time.sleep(0.5)
                    cont = page.query_selector('button:has-text("CONTINUE"), button:has-text("Continue"), button:has-text("Продолжить")')
                    if cont and cont.is_visible():
                        cont.click()
                        time.sleep(2.5)
                        add_log("SUCCESS", f"[{self.name}] Player account linked successfully!")

    def collect(self, page: Page) -> Dict[str, Any]:
        result = {"game": self.name, "success": False, "items_collected": [], "message": ""}
        if not self.player_id:
            msg = "Pilot ID not specified! Please enter your ID in War Robots card."
            add_log("WARNING", f"[{self.name}] {msg}")
            result["message"] = msg
            return result

        add_log("INFO", f"[{self.name}] Navigating to War Robots Web Shop: {self.shop_url}")
        try:
            page.goto(self.shop_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4.0)
            self._ensure_logged_in(page)

            # Check Free Daily Gift section
            claim_btn = page.query_selector('.shop-free-daily-gift__cta, button:has-text("CLAIM")')

            if not claim_btn:
                free_btns = page.query_selector_all('button:has-text("CLAIM"), button:has-text("Free"), button:has-text("Бесплатно")')
                if free_btns:
                    claim_btn = free_btns[0]

            if not claim_btn or not claim_btn.is_visible():
                result["success"] = True
                result["status_type"] = "no_rewards"
                result["message"] = "No free daily gift available at this time."
                add_log("INFO", f"[{self.name}] {result['message']}")
                return result

            # Determine item name from gift section
            item_name = "Common Data Pad (Silver)"
            try:
                title_el = page.query_selector('.shop-free-daily-gift__item-title, .shop-free-daily-gift strong, [class*="daily-gift"] h3, [class*="daily-gift"] [class*="title"]')
                if title_el and title_el.inner_text().strip():
                    item_name = title_el.inner_text().strip()
            except Exception:
                pass

            add_log("INFO", f"[{self.name}] Found Free Daily Gift: '{item_name}'. Claiming...")
            claim_btn.scroll_into_view_if_needed()
            time.sleep(0.5)
            claim_btn.click()
            time.sleep(2.0)

            # Modal confirmation step
            modal_btn = page.query_selector('.product-info-step__buy, [role="dialog"] button:has-text("CLAIM"), button:has-text("CLAIM").ui-button-primary--large')
            if modal_btn and modal_btn.is_visible():
                modal_btn.click()
                time.sleep(4.0)

            # Check purchase modal response
            text_after = page.inner_text('body').lower()
            if "thank you for your purchase" in text_after or "has been sent to your in-game account" in text_after or "успешно" in text_after:
                result["success"] = True
                result["status_type"] = "collected"
                result["items_collected"].append(item_name)
                result["message"] = f"Successfully claimed: {item_name}!"
                add_log("SUCCESS", f"[{self.name}] {result['message']}")
            elif "purchase limit exceeded" in text_after or "limit exceeded" in text_after or "something went wrong" in text_after:
                result["success"] = True
                result["status_type"] = "already_claimed"
                result["message"] = "Daily free gift has already been claimed for today."
                add_log("INFO", f"[{self.name}] {result['message']}")
            else:
                try:
                    close_btn = page.query_selector('.ui-close-button, button:has-text("DONE"), button:has-text("CLOSE")')
                    if close_btn and close_btn.is_visible():
                        close_btn.click()
                except Exception:
                    pass
                result["success"] = True
                result["status_type"] = "already_claimed"
                result["message"] = "Daily gift already claimed or limit reached."
                add_log("INFO", f"[{self.name}] {result['message']}")

        except Exception as e:
            result["success"] = False
            result["status_type"] = "error"
            result["message"] = f"Collection error: {e}"
            add_log("ERROR", f"[{self.name}] {result['message']}")

        return result


# =====================================================================
#                      FASTAPI WEB SERVER
# =====================================================================

app = FastAPI(title="Auto Collect MyGames")

STATE = {
    "is_running": False,
    "current_action": "idle",
    "stop_login": False,
    "last_result": None,
    "last_run_summary_ru": None,
    "last_run_summary_en": None,
    "last_run_status": None
}

def init_last_run_state():
    checks = load_last_checks()
    if checks:
        latest_ts = ""
        for c in checks.values():
            ts = c.get("timestamp", "")
            if ts > latest_ts:
                latest_ts = ts
        if latest_ts:
            try:
                t_obj = datetime.datetime.strptime(latest_ts, "%Y-%m-%d %H:%M:%S")
                time_str = t_obj.strftime("%H:%M")
                STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {time_str} (ПРОВЕРЕНО ✓)"
                STATE["last_run_summary_en"] = f"LAST RUN: {time_str} (VERIFIED ✓)"
                STATE["last_run_status"] = "success"
            except Exception:
                pass

init_last_run_state()

class ConfigModel(BaseModel):
    app: Dict[str, Any]
    notifications: Dict[str, Any]
    games: Dict[str, Any]

@app.get("/api/config")
def api_get_config():
    return load_config()

@app.post("/api/config")
def api_save_config(new_config: ConfigModel):
    try:
        save_config(new_config.model_dump())
        add_log("INFO", "Configuration saved.")
        return {"status": "ok", "message": "Settings saved!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
def api_get_status():
    sess_dir = SESSIONS_DIR / "mygames_main"
    has_session = sess_dir.exists() and any(sess_dir.iterdir()) if sess_dir.exists() else False
    cfg = load_config()
    daemon_enabled = cfg.get("app", {}).get("daemon_enabled", False)
    interval_sec = max(1, int(cfg.get("app", {}).get("check_interval_hours", 12))) * 3600
    last_daemon = STATE.get("last_daemon_run", 0)
    now = time.time()

    next_run_in = max(0, int(interval_sec - (now - last_daemon))) if (last_daemon > 0 and daemon_enabled) else (interval_sec if daemon_enabled else 0)

    return {
        "is_running": STATE["is_running"],
        "current_action": STATE["current_action"],
        "has_session": has_session,
        "last_result": STATE["last_result"],
        "last_run_summary_ru": STATE.get("last_run_summary_ru"),
        "last_run_summary_en": STATE.get("last_run_summary_en"),
        "last_run_status": STATE.get("last_run_status"),
        "daemon_enabled": daemon_enabled,
        "next_daemon_run_in": next_run_in
    }

@app.get("/api/logs")
def api_get_logs(after: int = 0):
    with LOG_LOCK:
        return {"logs": LOG_BUFFER[after:], "total": len(LOG_BUFFER)}

@app.post("/api/logs/clear")
def api_clear_logs():
    with LOG_LOCK:
        LOG_BUFFER.clear()
    return {"status": "ok"}

@app.get("/api/history")
def api_get_history():
    return load_history()

@app.post("/api/history/clear")
def api_clear_history():
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception:
            pass
    return {"status": "ok", "message": "History cleared!"}

@app.post("/api/daemon/toggle")
def api_daemon_toggle():
    cfg = load_config()
    current = cfg.get("app", {}).get("daemon_enabled", False)
    new_state = not current
    cfg["app"]["daemon_enabled"] = new_state
    save_config(cfg)
    if new_state:
        STATE["last_daemon_run"] = time.time()
    status_str = "ENABLED" if new_state else "DISABLED"
    add_log("INFO", f"[Daemon] Auto-collection scheduler {status_str}.")
    return {"status": "ok", "daemon_enabled": new_state}

@app.get("/api/rewards/cooldowns")
def api_get_cooldowns():
    history = load_history()
    last_checks = load_last_checks()
    now = datetime.datetime.now()

    # War Robots check: daily reset at midnight
    wr_claimed_today = False
    wr_status_type = "ready"
    today_str = now.strftime("%Y-%m-%d")

    for h in history:
        if h.get("game") == "War Robots" and h.get("status") == "success":
            if str(h.get("timestamp", "")).startswith(today_str):
                wr_claimed_today = True
                wr_status_type = "collected"
                break

    wr_check = last_checks.get("War Robots", {})
    if wr_check and str(wr_check.get("timestamp", "")).startswith(today_str):
        if wr_check.get("status_type") == "collected":
            wr_claimed_today = True
            wr_status_type = "collected"
        elif wr_check.get("status_type") == "no_rewards":
            wr_claimed_today = True
            wr_status_type = "no_rewards"
        elif wr_check.get("status_type") == "already_claimed":
            wr_claimed_today = True
            wr_status_type = "already_claimed"

    tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    wr_seconds = int((tomorrow - now).total_seconds()) if wr_claimed_today else 0

    return {
        "war_robots": {
            "status": wr_status_type,
            "claimed": wr_claimed_today,
            "seconds_left": wr_seconds,
            "title": "Daily Free Gift (Data Pad / Resources)",
            "image_url": "https://market.my.games/s3/media/2026/10/22/9b21a096c25aaa56c9bdfad9106e7c86.png"
        }
    }

def verify_mygames_session() -> Dict[str, Any]:
    """Actively checks if saved cookies in sessions/mygames_main are authorized on MY.GAMES."""
    sess_dir = SESSIONS_DIR / "mygames_main"
    if not sess_dir.exists() or not any(sess_dir.iterdir()):
        return {"authenticated": False, "reason": "No session profile found"}

    try:
        with BrowserManager(headless=True, session_name="mygames_main") as bm:
            page = bm.new_page()
            page.goto("https://market.my.games/", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2.0)

            login_el = page.query_selector('a[href*="login"], button:has-text("Войти"), button:has-text("Log in"), button:has-text("Sign in")')
            avatar_el = page.query_selector('.styles_avatarWrapper__Jh7Lq, a[href*="profile"], [class*="avatar"], [class*="userProfile"]')

            is_authed = avatar_el is not None or (login_el is None and "market.my.games" in page.url)
            return {
                "authenticated": is_authed,
                "reason": "Active session verified" if is_authed else "Session expired or logged out"
            }
    except Exception as e:
        return {"authenticated": False, "reason": f"Verification error: {e}"}

@app.get("/api/session/check")
def api_session_check():
    return verify_mygames_session()

@app.post("/api/session/logout")
def api_session_logout():
    sess_dir = SESSIONS_DIR / "mygames_main"
    if sess_dir.exists():
        try:
            shutil.rmtree(sess_dir, ignore_errors=True)
            sess_dir.mkdir(parents=True, exist_ok=True)
            add_log("INFO", "Session cleared. Account logged out.")
            return {"status": "ok", "message": "Logged out successfully!"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"message": f"Logout error: {e}"})
    return {"status": "ok", "message": "No active session."}

def _run_collection_task(target: str = "all", force_head: bool = False, trigger_source: str = "manual"):
    STATE["is_running"] = True
    STATE["current_action"] = f"Collecting rewards ({target})"
    add_log("INFO", f"=== STARTING REWARD COLLECTION ({target}) ===")

    try:
        config = load_config()
        headless = not force_head if force_head else config["app"].get("headless", True)
        notifier = Notifier(config)
        results = []

        with BrowserManager(headless=headless, session_name="mygames_main") as bm:
            page = bm.new_page()

            if target in ("all", "war_robots"):
                wr_cfg = config.get("games", {}).get("war_robots", {})
                if wr_cfg.get("enabled"):
                    r = WarRobotsCollector(wr_cfg, config.get("app", {})).collect(page)
                    results.append(r)

        # Save history for each collected reward
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        for r in results:
            if r.get("success") and r.get("items_collected"):
                for itm in r["items_collected"]:
                    save_history_entry({
                        "id": int(time.time() * 1000),
                        "timestamp": now_str,
                        "game": r["game"],
                        "item_name": itm if isinstance(itm, str) else itm.get("name", "Reward"),
                        "image_url": "https://market.my.games/s3/media/2026/10/22/9b21a096c25aaa56c9bdfad9106e7c86.png",
                        "status": "success",
                        "message": r["message"]
                    })

        # Save last checks for each game and log exact timestamps for analysis
        pilot_id = config.get("games", {}).get("war_robots", {}).get("player_id", "")
        for r in results:
            st = r.get("status_type", "collected" if r.get("items_collected") else ("already_claimed" if r.get("success") else "error"))
            save_last_check(
                game=r["game"],
                status_type=st,
                message=r.get("message", ""),
                items=r.get("items_collected", [])
            )
            items_str = ", ".join(r.get("items_collected", [])) if r.get("items_collected") else "None"
            log_claim_event(
                game=r["game"],
                pilot_id=pilot_id,
                status_type=st,
                item_name=items_str,
                message=r.get("message", ""),
                trigger_source=trigger_source
            )

        # Update last run summary for the top status pill
        total_collected = sum(len(r.get("items_collected", [])) for r in results)
        any_errors = any(not r.get("success", False) for r in results)
        now_time = datetime.datetime.now().strftime("%H:%M")

        if any_errors:
            STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {now_time} (ОШИБКА ⚠️)"
            STATE["last_run_summary_en"] = f"LAST RUN: {now_time} (ERROR ⚠️)"
            STATE["last_run_status"] = "error"
        elif total_collected > 0:
            STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {now_time} (СОБРАНО: {total_collected} ✓)"
            STATE["last_run_summary_en"] = f"LAST RUN: {now_time} (COLLECTED: {total_collected} ✓)"
            STATE["last_run_status"] = "success"
        else:
            all_no_rewards = all(r.get("status_type") == "no_rewards" for r in results)
            if all_no_rewards:
                STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {now_time} (НЕТ НАГРАД В МАГАЗИНЕ)"
                STATE["last_run_summary_en"] = f"LAST RUN: {now_time} (NO REWARDS IN STORE)"
                STATE["last_run_status"] = "idle"
            else:
                STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {now_time} (НАГРАДЫ УЖЕ ЗАБРАНЫ ✓)"
                STATE["last_run_summary_en"] = f"LAST RUN: {now_time} (ALL REWARDS CLAIMED ✓)"
                STATE["last_run_status"] = "success"

        # Send notification report
        lines = ["<b>🎁 Auto Collect MyGames: Report</b>\n"]
        for r in results:
            icon = "✅" if r["success"] else "❌"
            lines.append(f"{icon} <b>{r['game']}</b>: {r['message']}")
            for itm in r.get("items_collected", []):
                lines.append(f"   • {itm}")
        notifier.send("\n".join(lines))
        STATE["last_result"] = results
        STATE["last_daemon_run"] = time.time()
        
        if total_collected > 0:
            add_log("SUCCESS", f"Сбор наград завершён! Получено предметов: {total_collected}")
        elif any(r.get("status_type") == "no_rewards" for r in results):
            add_log("INFO", "Проверка завершена: в официальном магазине сейчас нет доступных бесплатных подарков.")
        else:
            add_log("INFO", "Проверка завершена: подарки уже были собраны за этот период.")
    except Exception as e:
        now_time = datetime.datetime.now().strftime("%H:%M")
        STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {now_time} (ОШИБКА ⚠️)"
        STATE["last_run_summary_en"] = f"LAST RUN: {now_time} (ERROR ⚠️)"
        STATE["last_run_status"] = "error"
        add_log("ERROR", f"Critical error during collection: {e}")
    finally:
        STATE["is_running"] = False
        STATE["current_action"] = "idle"

@app.post("/api/action/collect")
def api_action_collect(target: str = "all", force_head: bool = False):
    if STATE["is_running"]:
        return JSONResponse(status_code=400, content={"message": "Operation already in progress!"})
    threading.Thread(target=_run_collection_task, args=(target, force_head, "gui"), daemon=True).start()
    return {"status": "started", "message": "Reward collection started!"}

def _run_login_task(target: str):
    STATE["is_running"] = True
    STATE["stop_login"] = False
    STATE["current_action"] = "Browser Authentication"
    add_log("INFO", "=== STARTING AUTHENTICATION WINDOW ===")
    add_log("INFO", "Opening MY.GAMES login form...")

    try:
        url = "https://account.my.games/login/?continue=https://market.my.games/"
        with BrowserManager(headless=False, session_name="mygames_main") as bm:
            page = bm.new_page()
            page.goto(url, wait_until="domcontentloaded")

            while not STATE.get("stop_login", False):
                try:
                    if page.is_closed() or not bm.context or not bm.context.pages or all(p.is_closed() for p in bm.context.pages):
                        add_log("INFO", "Browser window closed.")
                        break

                    if "market.my.games" in page.url and "account.my.games/login" not in page.url:
                        add_log("SUCCESS", "Successful login detected! Saving session...")
                        time.sleep(2.0)
                        try:
                            bm.context.close()
                        except Exception:
                            pass
                        break

                    time.sleep(0.5)
                except Exception:
                    break

        add_log("SUCCESS", "MY.GAMES session saved successfully!")
    except Exception as e:
        add_log("ERROR", f"Authentication error: {e}")
    finally:
        STATE["is_running"] = False
        STATE["stop_login"] = False
        STATE["current_action"] = "idle"

@app.post("/api/action/login")
def api_action_login(target: str = "all"):
    if STATE["is_running"]:
        return JSONResponse(status_code=400, content={"message": "Operation already in progress!"})
    threading.Thread(target=_run_login_task, args=(target,), daemon=True).start()
    return {"status": "started", "message": "Opening login window..."}

@app.post("/api/action/login/finish")
def api_action_login_finish():
    STATE["stop_login"] = True
    add_log("INFO", "Finish login command received.")
    return {"status": "ok", "message": "Authentication finished!"}

@app.post("/api/action/test-notify")
def api_test_notify():
    Notifier(load_config()).send("🔔 <b>Auto Collect MyGames</b>: Test notification received!")
    add_log("INFO", "Test notification sent.")
    return {"status": "ok", "message": "Test notification sent!"}

def check_is_overdue(cfg: Dict[str, Any]) -> bool:
    """Checks whether War Robots has uncollected rewards that are overdue."""
    try:
        cd = api_get_cooldowns()
        games_cfg = cfg.get("games", {})

        # War Robots check: overdue if enabled and not claimed today
        if games_cfg.get("war_robots", {}).get("enabled", True):
            if not cd.get("war_robots", {}).get("claimed", False):
                return True

        return False
    except Exception as e:
        add_log("DEBUG", f"Error checking overdue state: {e}")
        return False

def daemon_worker():
    """Background scheduler running with Below Normal CPU priority.
    Only triggers after system reboot/start, or on PC wake-up IF rewards are overdue.
    """
    set_low_process_priority()
    last_heartbeat = time.time()

    # Initial check after full reboot / application start
    time.sleep(5)
    try:
        cfg = load_config()
        if cfg.get("app", {}).get("daemon_enabled", False):
            if check_is_overdue(cfg):
                add_log("INFO", "[Daemon] Запуск после старта системы: найдены несобранные награды (overdue). Сбор...")
                _run_collection_task(target="all", force_head=False, trigger_source="daemon_startup")
            else:
                add_log("INFO", "[Daemon] Запуск после старта системы: все награды за текущий период уже собраны. Ожидание.")
    except Exception as e:
        add_log("DEBUG", f"Daemon startup check exception: {e}")

    while True:
        try:
            time.sleep(60)  # Check once per minute with zero CPU impact
            now = time.time()
            gap = now - last_heartbeat
            last_heartbeat = now

            cfg = load_config()
            daemon_enabled = cfg.get("app", {}).get("daemon_enabled", False)
            if not daemon_enabled or STATE["is_running"]:
                continue

            # Detect wake-up from sleep or hibernate (gap > 3 minutes)
            is_wake_up = gap > 180

            if is_wake_up:
                # System just woke up from sleep or hibernate
                if check_is_overdue(cfg):
                    add_log("INFO", "[Daemon] Компьютер вышел из спящего режима: найдены доступные награды (overdue). Запуск сбора...")
                    _run_collection_task(target="all", force_head=False, trigger_source="daemon_wakeup")
                else:
                    add_log("DEBUG", "[Daemon] Компьютер вышел из спящего режима: награды уже собраны за этот период. Сбор не требуется.")
            else:
                # Periodic fallback check (e.g. 12h): only collect if overdue!
                interval_sec = max(1, int(cfg.get("app", {}).get("check_interval_hours", 12))) * 3600
                last_run = STATE.get("last_daemon_run", 0)
                if (now - last_run >= interval_sec):
                    if check_is_overdue(cfg):
                        add_log("INFO", "[Daemon] Плановый интервал: подошел срок сбора наград (overdue)...")
                        _run_collection_task(target="all", force_head=False, trigger_source="daemon_interval")
                    else:
                        STATE["last_daemon_run"] = now

        except Exception as e:
            add_log("DEBUG", f"Daemon scheduler loop exception: {e}")

# Mount UI static assets
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(UI_DIR / "index.html"))


# =====================================================================
#                      LAUNCHER & CLI ENTRYPOINT
# =====================================================================

def find_free_port(start_port: int = 18234) -> int:
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port

def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HealthCheck"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False

def run_daemon_service():
    """Runs pure background daemon scheduler without launching any GUI window."""
    set_low_process_priority()
    add_log("INFO", "Starting Auto Collect MyGames in Silent Daemon Mode (No GUI)...")
    port = find_free_port()
    server_cfg = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(server_cfg)
    threading.Thread(target=server.run, daemon=True).start()
    daemon_worker()

def start_gui():
    port = find_free_port()
    app_url = f"http://127.0.0.1:{port}"

    add_log("INFO", f"Starting UI server on {app_url}...")
    server_cfg = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(server_cfg)
    threading.Thread(target=server.run, daemon=True).start()
    threading.Thread(target=daemon_worker, daemon=True).start()

    if not wait_for_server(app_url, timeout=12.0):
        print("[!] Error: UI Server failed to start in time.")
        return

    browser_exe = find_browser_for_app_window()
    gui_profile = SESSIONS_DIR / "gui_window_profile"
    gui_profile.mkdir(parents=True, exist_ok=True)

    if browser_exe and os.path.exists(browser_exe):
        cmd = [
            browser_exe,
            f"--app={app_url}",
            "--window-size=1160,780",
            f"--user-data-dir={gui_profile}",
            "--disable-plugins",
            "--no-first-run",
            "--disable-default-apps"
        ]
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
            os._exit(0)
        except Exception:
            webbrowser.open(app_url)
    else:
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            os._exit(0)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto Collect MyGames")
    parser.add_argument("--run", choices=["all", "war_robots"], nargs="?", const="all", help="CLI: Claim rewards")
    parser.add_argument("--login", action="store_true", help="CLI: Authenticate account")
    parser.add_argument("--head", action="store_true", help="CLI: Run with visible browser window")
    parser.add_argument("--daemon", action="store_true", help="Run background scheduler service without GUI")
    args = parser.parse_args()

    if args.run:
        _run_collection_task(args.run, force_head=args.head, trigger_source="cli")
    elif args.login:
        _run_login_task("all")
    elif args.daemon:
        run_daemon_service()
    else:
        start_gui()

if __name__ == "__main__":
    main()
