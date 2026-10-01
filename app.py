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
        "rush_royale": {
            "enabled": True,
            "player_id": "",
            "platform": "android",
            "market_url": "https://market.my.games/rush_royale?content=items"
        },
        "war_robots": {
            "enabled": True,
            "player_id": "",
            "platform": "android",
            "market_url": "https://market.my.games/war_robots/"
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
        self._playwright = sync_playwright().start()
        browser_exe = find_browser_for_app_window()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage"
        ]

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

class RushRoyaleCollector:
    def __init__(self, game_cfg: Dict[str, Any], app_cfg: Dict[str, Any]):
        self.name = "Rush Royale"
        self.cfg = game_cfg
        self.player_id = str(self.cfg.get("player_id", "")).strip()
        self.platform = self.cfg.get("platform", "Android").capitalize()
        self.market_url = self.cfg.get("market_url", "https://market.my.games/rush_royale?content=items")

    def _clear_overlays(self, page: Page):
        try:
            page.evaluate("""() => {
                document.querySelector('#cmpbox')?.remove();
                document.querySelector('.cmpstyleroot')?.remove();
                document.querySelector('.styles_vpnDisclaimer__s6IdF')?.remove();
                document.querySelectorAll('.cookie-banner, [class*="cookie"]').forEach(e => e.remove());
            }""")
        except Exception:
            pass

    def _handle_enter_details(self, page: Page):
        time.sleep(1.0)
        self._clear_overlays(page)

        # 1. Platform selection
        try:
            plat_btn = page.query_selector(f'button:has-text("{self.platform}")')
            if plat_btn and plat_btn.is_visible():
                plat_btn.click()
                time.sleep(0.5)
        except Exception:
            pass

        # 2. Player ID
        if self.player_id:
            try:
                chip = page.query_selector(f'span:has-text("{self.player_id}"), div:has-text("{self.player_id}")')
                if chip and chip.is_visible():
                    chip.click()
                else:
                    inp = page.query_selector('input[type="text"], input:not([type="hidden"])')
                    if inp and inp.is_visible():
                        if inp.input_value().strip() != self.player_id:
                            inp.fill(self.player_id)
                time.sleep(1.0)
            except Exception:
                pass

        # 3. Continue button
        try:
            cnt_btn = page.query_selector('button:has-text("Continue"), button:has-text("Продолжить")')
            if cnt_btn and cnt_btn.is_visible():
                cnt_btn.click()
                time.sleep(3.0)
        except Exception:
            pass

    def collect(self, page: Page) -> Dict[str, Any]:
        result = {"game": self.name, "success": False, "items_collected": [], "message": ""}
        if not self.player_id:
            msg = "Player ID not specified! Please enter your ID in Rush Royale card."
            add_log("WARNING", f"[{self.name}] {msg}")
            result["message"] = msg
            return result

        # 1. Permanent free items (ID 24420: 10 Summoning Bells)
        prod_url = "https://market.my.games/rush_royale?content=items&product_id=24420"
        try:
            add_log("INFO", f"[{self.name}] Checking '10 Summoning Bells'...")
            page.goto(prod_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(2.5)
            self._clear_overlays(page)

            btn = page.query_selector('button:has-text("Получить"), button:has-text("Бесплатно"), button:has-text("Claim"), button:has-text("Free")')
            if btn and btn.is_visible():
                btn_text = btn.inner_text().strip().lower()
                if "получено" not in btn_text and "claimed" not in btn_text:
                    btn.click()
                    time.sleep(1.5)
                    self._handle_enter_details(page)
                    result["items_collected"].append("10 Summoning Bells (Limited Edition)")
                    add_log("SUCCESS", f"[{self.name}] Claimed: 10 Summoning Bells!")
                else:
                    add_log("INFO", f"[{self.name}] 10 Summoning Bells already claimed previously.")
        except Exception as e:
            add_log("DEBUG", f"Error checking product 24420: {e}")

        # 2. Scan store showcase for other promotional items
        try:
            page.goto("https://market.my.games/rush_royale?content=items", wait_until="domcontentloaded", timeout=45000)
            time.sleep(2.5)
            self._clear_overlays(page)
            page.evaluate("window.scrollTo(0, 700)")
            time.sleep(1.0)

            free_btns = page.query_selector_all('button:has-text("Бесплатно"), button:has-text("Free"), button:has-text("0 ₽"), button:has-text("0,00 €")')
            for b in free_btns:
                try:
                    if b.is_visible() and b.is_enabled():
                        if "получено" in b.inner_text().lower() or "claimed" in b.inner_text().lower():
                            continue
                        b.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        b.click()
                        time.sleep(2.0)

                        modal_get = page.query_selector('.styles_modalWrapper__Jh7Lq button:has-text("Получить"), .styles_modalWrapper__Jh7Lq button:has-text("Claim")')
                        if modal_get and modal_get.is_visible():
                            modal_get.click()
                            time.sleep(1.5)

                        self._handle_enter_details(page)
                        result["items_collected"].append("Market Promo Item")
                except Exception:
                    pass

            result["success"] = True
            if result["items_collected"]:
                result["message"] = f"Successfully collected rewards: {len(result['items_collected'])}"
                result["status_type"] = "collected"
            else:
                result["message"] = "All available free rewards have already been collected."
                result["status_type"] = "already_claimed"
            add_log("SUCCESS" if result["items_collected"] else "INFO", f"[{self.name}] {result['message']}")
        except Exception as e:
            result["success"] = False
            result["status_type"] = "error"
            result["message"] = f"Collection error: {e}"
            add_log("ERROR", f"[{self.name}] {result['message']}")

        return result


class WarRobotsCollector:
    def __init__(self, game_cfg: Dict[str, Any], app_cfg: Dict[str, Any]):
        self.name = "War Robots"
        self.cfg = game_cfg
        self.player_id = str(self.cfg.get("player_id", "")).strip()
        self.platform = self.cfg.get("platform", "android").lower()
        self.market_url = self.cfg.get("market_url", "https://market.my.games/war_robots/")

    def _clear_overlays(self, page: Page):
        try:
            page.evaluate("""() => {
                document.querySelector('#cmpbox')?.remove();
                document.querySelector('.cmpstyleroot')?.remove();
                document.querySelector('.styles_vpnDisclaimer__s6IdF')?.remove();
                document.querySelectorAll('.cookie-banner, [class*="cookie"]').forEach(e => e.remove());
            }""")
        except Exception:
            pass

    def collect(self, page: Page) -> Dict[str, Any]:
        result = {"game": self.name, "success": False, "items_collected": [], "message": ""}
        if not self.player_id:
            msg = "Pilot ID not specified! Please enter your ID in War Robots card."
            add_log("WARNING", f"[{self.name}] {msg}")
            result["message"] = msg
            return result

        add_log("INFO", f"[{self.name}] Navigating to market: {self.market_url}")
        try:
            page.goto(self.market_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3.0)
            self._clear_overlays(page)

            # Platform selection (Android / iOS / PC / Steam)
            target_plat = self.platform.lower()
            try:
                for btn in page.query_selector_all('button, [role="tab"], [role="radio"], label, .platform-button'):
                    txt = (btn.inner_text() or "").strip().lower()
                    if target_plat in txt or (target_plat == "pc" and "steam" in txt):
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        time.sleep(0.8)
                        break
            except Exception:
                pass

            # Enter Pilot ID if input field is present
            id_input = page.query_selector('input[placeholder*="ID"], input[placeholder*="Pilot"], input[name*="user_id"], input[type="text"]')
            if id_input and id_input.is_visible():
                if id_input.input_value().strip() != self.player_id:
                    id_input.fill(self.player_id)
                    sub = page.query_selector('button:has-text("Войти"), button:has-text("Применить"), button:has-text("Submit"), button:has-text("Confirm")')
                    if sub and sub.is_visible():
                        sub.click()
                        time.sleep(1.5)

            # Search and claim free rewards
            free_keywords = ["бесплатно", "0 ₽", "free", "0$", "подарок", "gift"]
            claimed = 0
            for btn in page.query_selector_all('button, a, div[role="button"]'):
                try:
                    text = (btn.inner_text() or "").strip().lower()
                    if any(kw in text for kw in free_keywords) and btn.is_visible() and btn.is_enabled():
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        btn.click()
                        claimed += 1
                        result["items_collected"].append("War Robots Supply Gift")
                        time.sleep(2.0)
                except Exception:
                    pass

            result["success"] = True
            if claimed > 0:
                result["message"] = f"Successfully collected gifts: {claimed}"
                result["status_type"] = "collected"
            else:
                result["message"] = "No free rewards available at this time (or already collected)."
                result["status_type"] = "no_rewards"
            add_log("SUCCESS" if claimed > 0 else "INFO", f"[{self.name}] {result['message']}")
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

    next_run_in = 0
    if daemon_enabled:
        interval_rem = max(0, int(interval_sec - (now - last_daemon))) if last_daemon > 0 else interval_sec
        candidates = [interval_rem] if interval_rem > 0 else []
        try:
            cd = api_get_cooldowns()
            rr_cfg = cfg.get("games", {}).get("rush_royale", {})
            wr_cfg = cfg.get("games", {}).get("war_robots", {})
            if rr_cfg.get("enabled", True) and not cd["rush_royale"]["claimed"]:
                candidates.append(0)
            elif rr_cfg.get("enabled", True) and cd["rush_royale"]["seconds_left"] > 0:
                candidates.append(cd["rush_royale"]["seconds_left"])

            if wr_cfg.get("enabled", True) and not cd["war_robots"]["claimed"]:
                candidates.append(0)
            elif wr_cfg.get("enabled", True) and cd["war_robots"]["seconds_left"] > 0:
                candidates.append(cd["war_robots"]["seconds_left"])
        except Exception:
            pass

        next_run_in = min(candidates) if candidates else interval_sec

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
    cfg["app"]["daemon_enabled"] = not current
    save_config(cfg)
    status_str = "ENABLED" if not current else "DISABLED"
    add_log("INFO", f"[Daemon] Auto-collection scheduler {status_str}.")
    return {"status": "ok", "daemon_enabled": not current}

@app.get("/api/rewards/cooldowns")
def api_get_cooldowns():
    history = load_history()
    last_checks = load_last_checks()
    now = datetime.datetime.now()

    # Rush Royale check: reset on 1st of next month
    rr_claimed_this_month = False
    for h in history:
        if h.get("game") == "Rush Royale" and h.get("status") == "success":
            try:
                h_date = datetime.datetime.strptime(h.get("timestamp", "")[:10], "%Y-%m-%d")
                if h_date.year == now.year and h_date.month == now.month:
                    rr_claimed_this_month = True
                    break
            except Exception:
                pass

    rr_check = last_checks.get("Rush Royale", {})
    if not rr_claimed_this_month and rr_check:
        try:
            c_date = datetime.datetime.strptime(rr_check.get("timestamp", "")[:10], "%Y-%m-%d")
            if c_date.year == now.year and c_date.month == now.month:
                if rr_check.get("status_type") in ("collected", "already_claimed"):
                    rr_claimed_this_month = True
        except Exception:
            pass

    if now.month == 12:
        next_month = datetime.datetime(now.year + 1, 1, 1, 0, 0, 0)
    else:
        next_month = datetime.datetime(now.year, now.month + 1, 1, 0, 0, 0)
    rr_seconds = int((next_month - now).total_seconds()) if rr_claimed_this_month else 0

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
        "rush_royale": {
            "status": "already_claimed" if rr_claimed_this_month else "ready",
            "claimed": rr_claimed_this_month,
            "seconds_left": rr_seconds,
            "title": "10 Summoning Bells",
            "image_url": "https://static.my.games/market/images/products/24420.png"
        },
        "war_robots": {
            "status": wr_status_type,
            "claimed": wr_claimed_today,
            "seconds_left": wr_seconds,
            "title": "Daily Supply Gifts",
            "image_url": "https://market.my.games/favicon.ico"
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

def _run_collection_task(target: str = "all", force_head: bool = False):
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

            if target in ("all", "rush_royale"):
                rr_cfg = config.get("games", {}).get("rush_royale", {})
                if rr_cfg.get("enabled"):
                    r = RushRoyaleCollector(rr_cfg, config.get("app", {})).collect(page)
                    results.append(r)

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
                        "image_url": "https://market.my.games/favicon.ico" if r["game"] == "War Robots" else "https://static.my.games/market/images/products/24420.png",
                        "status": "success",
                        "message": r["message"]
                    })

        # Save last checks for each game (tracks cooldowns even when 0 gifts available or already claimed)
        for r in results:
            st = r.get("status_type", "collected" if r.get("items_collected") else ("already_claimed" if r.get("success") else "error"))
            save_last_check(
                game=r["game"],
                status_type=st,
                message=r.get("message", ""),
                items=r.get("items_collected", [])
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
        add_log("SUCCESS", "Reward collection finished!")
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
    threading.Thread(target=_run_collection_task, args=(target, force_head), daemon=True).start()
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

def daemon_worker():
    """Lightweight background thread that executes smart rewards collection (on cooldown expiry + scheduled interval)."""
    while True:
        try:
            time.sleep(20)
            cfg = load_config()
            daemon_enabled = cfg.get("app", {}).get("daemon_enabled", False)
            if not daemon_enabled or STATE["is_running"]:
                continue

            now = time.time()
            interval_sec = max(1, int(cfg.get("app", {}).get("check_interval_hours", 12))) * 3600
            last_run = STATE.get("last_daemon_run", 0)

            # Check if any enabled game reward cooldown has just expired (ready for collection)
            cd_data = api_get_cooldowns()
            rr_ready = cfg.get("games", {}).get("rush_royale", {}).get("enabled", True) and not cd_data["rush_royale"]["claimed"]
            wr_ready = cfg.get("games", {}).get("war_robots", {}).get("enabled", True) and not cd_data["war_robots"]["claimed"]

            # Guard against rapid retry loops: wait at least 10 minutes between runs
            min_cooldown_gap = 600
            should_run_cooldown = (rr_ready or wr_ready) and (now - last_run >= min_cooldown_gap)

            # Scheduled interval fallback (e.g. check every 12 hours)
            should_run_interval = (now - last_run >= interval_sec)

            if should_run_cooldown or should_run_interval:
                reason = "Reward cooldown expired" if should_run_cooldown else "Scheduled interval"
                add_log("INFO", f"[Daemon] Triggering auto-collection ({reason})...")
                STATE["last_daemon_run"] = now
                _run_collection_task(target="all", force_head=False)
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
        except Exception:
            webbrowser.open(app_url)
    else:
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto Collect MyGames")
    parser.add_argument("--run", choices=["all", "rush_royale", "war_robots"], nargs="?", const="all", help="CLI: Claim rewards")
    parser.add_argument("--login", action="store_true", help="CLI: Authenticate account")
    parser.add_argument("--head", action="store_true", help="CLI: Run with visible browser window")
    args = parser.parse_args()

    if args.run:
        _run_collection_task(args.run, force_head=args.head)
    elif args.login:
        _run_login_task("all")
    else:
        start_gui()

if __name__ == "__main__":
    main()
