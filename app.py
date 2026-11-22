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

import re
import yaml
import requests
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright, BrowserContext, Page

import winreg
import pystray
from PIL import Image, ImageDraw

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
    """Set process priority to BELOW_NORMAL_PRIORITY_CLASS on Windows so games/apps (e.g. osu!) have full priority."""
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

set_low_process_priority()


# =====================================================================
#                      WINDOWS AUTOSTART REGISTRY
# =====================================================================

AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_APP_NAME = "WR_Rewards_Toolkit"

def get_windows_autostart() -> bool:
    """Checks whether the application is set to start with Windows in HKCU\\...\\Run."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, AUTOSTART_APP_NAME)
            return bool(val)
    except OSError:
        return False

def set_windows_autostart(enable: bool) -> bool:
    """Enables or disables Windows autostart without requiring administrator rights."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                if getattr(sys, 'frozen', False):
                    # Running as compiled standalone AutoCollect.exe
                    exe_path = Path(sys.executable).resolve()
                    cmd_str = f'"{exe_path}" --minimized'
                else:
                    # Running from source / Python / VBS
                    base_dir = Path(__file__).resolve().parent
                    dist_exe = base_dir / "dist" / "AutoCollect" / "AutoCollect.exe"
                    vbs_path = base_dir / "WR_Toolkit.vbs"
                    if dist_exe.exists():
                        cmd_str = f'"{dist_exe.resolve()}" --minimized'
                    elif vbs_path.exists():
                        cmd_str = f'wscript.exe "{vbs_path.resolve()}"'
                    else:
                        venv_pythonw = base_dir / ".venv" / "Scripts" / "pythonw.exe"
                        pythonw_exe = str(venv_pythonw) if venv_pythonw.exists() else sys.executable.replace("python.exe", "pythonw.exe")
                        cmd_str = f'"{pythonw_exe}" "{base_dir / "app.py"}" --minimized'

                winreg.SetValueEx(key, AUTOSTART_APP_NAME, 0, winreg.REG_SZ, cmd_str)
                add_log("INFO", f"Windows autostart registered: {cmd_str}")
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_APP_NAME)
                    add_log("INFO", "Windows autostart entry removed.")
                except FileNotFoundError:
                    pass
            return True
    except Exception as e:
        add_log("ERROR", f"Failed to set Windows autostart: {e}")
        return False


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
        "check_interval_hours": 12,
        "minimize_to_tray": True,
        "start_minimized": False
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
#                      HISTORY PERSISTENCE & AUDIT LOGS
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

def parse_cooldown_text(text: str) -> Optional[int]:
    """Parses live countdown strings like '21h 47m', '45m', '1d 2h' into exact seconds."""
    if not text:
        return None
    text = text.lower().strip()
    days = 0
    hours = 0
    mins = 0
    d_match = re.search(r'(\d+)\s*d', text)
    if d_match:
        days = int(d_match.group(1))
    h_match = re.search(r'(\d+)\s*h', text)
    if h_match:
        hours = int(h_match.group(1))
    m_match = re.search(r'(\d+)\s*m', text)
    if m_match:
        mins = int(m_match.group(1))
    s_match = re.search(r'(\d+)\s*s', text)
    secs = int(s_match.group(1)) if s_match else 0
    total = days * 86400 + hours * 3600 + mins * 60 + secs
    return total if total > 0 else None

def save_last_check(game: str, status_type: str, message: str, items: list = None, exact_seconds_left: int = None, timer_str: str = None):
    checks = load_last_checks()
    existing = checks.get(game, {})
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # If already successfully collected or claimed today, don't let a subsequent error overwrite success
    if status_type == "error" and existing.get("timestamp", "").startswith(today_str):
        if existing.get("status_type") in ("collected", "already_claimed"):
            add_log("DEBUG", f"Preserving today's successful status for {game} instead of overwriting with error.")
            return

    checks[game] = {
        "status_type": status_type,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "unix_timestamp": int(time.time()),
        "message": message,
        "items": items or [],
        "exact_seconds_left": exact_seconds_left if exact_seconds_left is not None else existing.get("exact_seconds_left"),
        "timer_str": timer_str if timer_str is not None else existing.get("timer_str")
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
        for fname in lock_files:
            target = self.profile_dir / fname
            if target.exists():
                try:
                    if target.is_file() or target.is_symlink():
                        target.unlink(missing_ok=True)
                    elif target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                except Exception:
                    pass

    def start(self) -> BrowserContext:
        self.clean_stale_locks()
        self._playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--window-size=1366,768"
        ]

        browser_exe = find_browser_for_app_window()
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
        self.cfg = config.get("notifications", {})

    def send(self, message: str):
        tg = self.cfg.get("telegram", {})
        if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
            self._send_telegram(tg["bot_token"], tg["chat_id"], message)

        dc = self.cfg.get("discord", {})
        if dc.get("enabled") and dc.get("webhook_url"):
            self._send_discord(dc["webhook_url"], message)

    def _send_telegram(self, token: str, chat_id: str, text: str):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=8)
        except Exception as e:
            add_log("DEBUG", f"Telegram error: {e}")

    def _send_discord(self, webhook_url: str, text: str):
        clean_text = text.replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*")
        payload = {"content": clean_text}
        try:
            requests.post(webhook_url, json=payload, timeout=8)
        except Exception as e:
            add_log("DEBUG", f"Discord error: {e}")


# =====================================================================
#                      WAR ROBOTS COLLECTOR
# =====================================================================

class WarRobotsCollector:
    def __init__(self, game_cfg: Dict[str, Any], app_cfg: Dict[str, Any]):
        self.name = "War Robots"
        self.player_id = game_cfg.get("player_id", "").strip()
        self.platform = game_cfg.get("platform", "crossplay").lower()
        self.delay = app_cfg.get("action_delay_ms", 1500) / 1000.0
        self.shop_url = game_cfg.get("market_url", "https://shop.warrobots.com/")
        if not self.shop_url or not self.shop_url.startswith("http"):
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

            # Check official website live countdown timer
            countdown_el = page.query_selector('.shop-countdown-badge__label, .shop-free-daily-gift__next-timer, .shop-countdown-badge')
            timer_text = countdown_el.inner_text().strip() if countdown_el else ""
            exact_sec = parse_cooldown_text(timer_text) if timer_text else None

            # Check if button is disabled (already claimed)
            btn_text = (claim_btn.inner_text() or "").lower()
            is_disabled = (
                not claim_btn.is_enabled()
                or claim_btn.get_attribute("disabled") is not None
                or "disabled" in (claim_btn.get_attribute("class") or "").lower()
                or claim_btn.get_attribute("aria-disabled") == "true"
                or (timer_text != "" and "next reward" in btn_text)
            )
            if is_disabled:
                result["success"] = True
                result["status_type"] = "already_claimed"
                result["exact_seconds_left"] = exact_sec
                result["timer_str"] = timer_text
                result["message"] = f"Daily free gift has already been claimed for today (Next in {timer_text or '24h'})."
                add_log("INFO", f"[{self.name}] {result['message']}")
                return result

            add_log("INFO", f"[{self.name}] Found Free Daily Gift: '{item_name}'. Claiming...")
            try:
                claim_btn.scroll_into_view_if_needed()
                time.sleep(0.5)
                claim_btn.click(timeout=5000)
                time.sleep(2.0)
            except Exception as click_err:
                err_text = str(click_err).lower()
                if "not enabled" in err_text or "disabled" in err_text or "timeout" in err_text:
                    result["success"] = True
                    result["status_type"] = "already_claimed"
                    result["message"] = "Daily free gift has already been claimed for today."
                    add_log("INFO", f"[{self.name}] {result['message']}")
                    return result
                raise click_err

            # Modal confirmation step
            modal_btn = page.query_selector('.product-info-step__buy, [role="dialog"] button:has-text("CLAIM"), button:has-text("CLAIM").ui-button-primary--large')
            if modal_btn and modal_btn.is_visible():
                if not modal_btn.is_enabled() or modal_btn.get_attribute("disabled") is not None:
                    result["success"] = True
                    result["status_type"] = "already_claimed"
                    result["message"] = "Daily free gift has already been claimed for today."
                    add_log("INFO", f"[{self.name}] {result['message']}")
                    return result
                try:
                    modal_btn.click(timeout=5000)
                    time.sleep(4.0)
                except Exception as modal_err:
                    err_text = str(modal_err).lower()
                    if "not enabled" in err_text or "disabled" in err_text or "timeout" in err_text:
                        result["success"] = True
                        result["status_type"] = "already_claimed"
                        result["message"] = "Daily free gift has already been claimed for today."
                        add_log("INFO", f"[{self.name}] {result['message']}")
                        return result
                    raise modal_err

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

app = FastAPI(title="WR Rewards Toolkit")

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
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Check if War Robots was collected today in history
    claimed_in_history = False
    for h in load_history():
        if h.get("game") == "War Robots" and h.get("status") == "success":
            if (h.get("timestamp") or "").startswith(today_str):
                claimed_in_history = True
                break

    if checks:
        latest_ts = ""
        latest_check = None
        for c in checks.values():
            ts = c.get("timestamp", "")
            if ts > latest_ts:
                latest_ts = ts
                latest_check = c
        if latest_ts and latest_check:
            try:
                t_obj = datetime.datetime.strptime(latest_ts, "%Y-%m-%d %H:%M:%S")
                time_str = t_obj.strftime("%H:%M")
                st = latest_check.get("status_type", "")
                if st == "error" and not claimed_in_history:
                    STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {time_str} (ОШИБКА ⚠️)"
                    STATE["last_run_summary_en"] = f"LAST RUN: {time_str} (ERROR ⚠️)"
                    STATE["last_run_status"] = "error"
                elif st == "collected" or claimed_in_history:
                    STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {time_str} (СОБРАНО ✓)"
                    STATE["last_run_summary_en"] = f"LAST RUN: {time_str} (COLLECTED ✓)"
                    STATE["last_run_status"] = "success"
                elif st == "no_rewards":
                    STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {time_str} (НЕТ НАГРАД В МАГАЗИНЕ)"
                    STATE["last_run_summary_en"] = f"LAST RUN: {time_str} (NO REWARDS IN STORE)"
                    STATE["last_run_status"] = "idle"
                else:
                    STATE["last_run_summary_ru"] = f"ПОСЛЕДНИЙ СБОР: {time_str} (НАГРАДЫ УЖЕ ЗАБРАНЫ ✓)"
                    STATE["last_run_summary_en"] = f"LAST RUN: {time_str} (ALL REWARDS CLAIMED ✓)"
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
        return JSONResponse(status_code=500, content={"message": f"Save error: {e}"})

@app.get("/api/system/settings")
def api_get_system_settings():
    cfg = load_config()
    app_cfg = cfg.get("app", {})
    return {
        "autostart_windows": get_windows_autostart(),
        "minimize_to_tray": app_cfg.get("minimize_to_tray", True),
        "start_minimized": app_cfg.get("start_minimized", False)
    }

class SystemSettingsModel(BaseModel):
    autostart_windows: Optional[bool] = None
    minimize_to_tray: Optional[bool] = None
    start_minimized: Optional[bool] = None

@app.post("/api/system/settings")
def api_save_system_settings(settings: SystemSettingsModel):
    cfg = load_config()
    if settings.autostart_windows is not None:
        set_windows_autostart(settings.autostart_windows)
    if settings.minimize_to_tray is not None:
        cfg["app"]["minimize_to_tray"] = settings.minimize_to_tray
    if settings.start_minimized is not None:
        cfg["app"]["start_minimized"] = settings.start_minimized
    save_config(cfg)
    return {"status": "ok", "message": "System settings saved successfully!"}

@app.get("/api/status")
def api_get_status():
    cfg = load_config()
    daemon_enabled = cfg.get("app", {}).get("daemon_enabled", False)
    
    # Calculate next collection time based on actual reward cooldown
    cooldowns = api_get_cooldowns()
    wr_cd = cooldowns.get("war_robots", {})
    wr_sec_left = wr_cd.get("seconds_left", 0)

    now = time.time()
    last_run = STATE.get("last_daemon_run", 0)

    if daemon_enabled:
        if wr_sec_left > 0:
            next_run_in = wr_sec_left
        elif wr_cd.get("claimed", False):
            interval_sec = max(1, int(cfg.get("app", {}).get("check_interval_hours", 12))) * 3600
            next_run_in = max(0, int(interval_sec - (now - last_run))) if last_run > 0 else 0
        else:
            # Overdue / ready right now!
            next_run_in = 0
    else:
        next_run_in = 0

    return {
        "is_running": STATE["is_running"],
        "current_action": STATE["current_action"],
        "last_result": STATE["last_result"],
        "last_run_summary_ru": STATE["last_run_summary_ru"],
        "last_run_summary_en": STATE["last_run_summary_en"],
        "last_run_status": STATE["last_run_status"],
        "has_session": True,
        "daemon_enabled": daemon_enabled,
        "next_daemon_run_in": next_run_in
    }

@app.post("/api/daemon/toggle")
def api_daemon_toggle():
    cfg = load_config()
    current = cfg.get("app", {}).get("daemon_enabled", False)
    cfg["app"]["daemon_enabled"] = not current
    save_config(cfg)
    status_str = "включен" if cfg["app"]["daemon_enabled"] else "выключен"
    add_log("INFO", f"Фоновый демон сбора наград {status_str}.")
    return {"status": "ok", "daemon_enabled": cfg["app"]["daemon_enabled"]}

@app.get("/api/logs")
def api_get_logs(after: int = 0):
    with LOG_LOCK:
        logs_slice = LOG_BUFFER[after:]
        return {"logs": logs_slice, "total": len(LOG_BUFFER)}

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
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        return {"status": "ok", "message": "History cleared"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"Clear history error: {e}"})

@app.get("/api/rewards/cooldowns")
def api_get_cooldowns():
    checks = load_last_checks()
    now = datetime.datetime.now()

    wr_check = checks.get("War Robots", {})
    wr_claimed_today = False
    wr_status_type = "ready"
    wr_seconds = 0

    # 0. Check live countdown timer from the official game shop
    exact_sec = wr_check.get("exact_seconds_left")
    unix_ts = wr_check.get("unix_timestamp", 0)
    if exact_sec is not None and unix_ts > 0:
        elapsed = int(time.time() - unix_ts)
        remaining = max(0, int(exact_sec - elapsed))
        if remaining > 0:
            return {
                "war_robots": {
                    "status": "already_claimed",
                    "claimed": True,
                    "seconds_left": remaining,
                    "title": "Daily Free Gift (Data Pad / Resources)",
                    "image_url": "https://market.my.games/s3/media/2026/10/22/9b21a096c25aaa56c9bdfad9106e7c86.png"
                }
            }
        else:
            # Exact cooldown from official store has elapsed -> ready to collect now!
            return {
                "war_robots": {
                    "status": "ready",
                    "claimed": False,
                    "seconds_left": 0,
                    "title": "Daily Free Gift (Data Pad / Resources)",
                    "image_url": "https://market.my.games/s3/media/2026/10/22/9b21a096c25aaa56c9bdfad9106e7c86.png"
                }
            }

    # 1. Determine latest claim timestamp from last_checks
    last_ts_str = wr_check.get("timestamp", "")
    last_claim_dt = None
    if last_ts_str:
        try:
            last_claim_dt = datetime.datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # 2. Also check history for the latest successful collection
    for h in load_history():
        if h.get("game") == "War Robots" and h.get("status") == "success":
            h_ts_str = h.get("timestamp", "")
            if h_ts_str:
                try:
                    fmt = "%Y-%m-%d %H:%M:%S" if len(h_ts_str) > 16 else "%Y-%m-%d %H:%M"
                    h_dt = datetime.datetime.strptime(h_ts_str, fmt)
                    if last_claim_dt is None or h_dt > last_claim_dt:
                        last_claim_dt = h_dt
                        wr_check["status_type"] = "collected"
                except Exception:
                    pass
            break

    # 3. Check elapsed time from latest claim
    if last_claim_dt:
        elapsed_sec = (now - last_claim_dt).total_seconds()
        # Cooldown is 20 hours minimum (daily reset cycle)
        if elapsed_sec < 20 * 3600:
            st = wr_check.get("status_type", "already_claimed")
            if st in ("collected", "already_claimed"):
                wr_claimed_today = True
                wr_status_type = st
                wr_seconds = max(0, int(24 * 3600 - elapsed_sec))
            elif st == "no_rewards":
                wr_claimed_today = True
                wr_status_type = "no_rewards"
                wr_seconds = max(0, int(24 * 3600 - elapsed_sec))

    return {
        "war_robots": {
            "status": wr_status_type,
            "claimed": wr_claimed_today,
            "seconds_left": wr_seconds,
            "title": "Daily Free Gift (Data Pad / Resources)",
            "image_url": "https://market.my.games/s3/media/2026/10/22/9b21a096c25aaa56c9bdfad9106e7c86.png"
        }
    }

# Stub backward-compatible session check
@app.get("/api/session/check")
def api_session_check():
    return {"authenticated": True, "reason": "War Robots uses direct Pilot ID"}

@app.post("/api/session/logout")
def api_session_logout():
    return {"status": "ok", "message": "Ready"}

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
                items=r.get("items_collected", []),
                exact_seconds_left=r.get("exact_seconds_left"),
                timer_str=r.get("timer_str")
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

        # Update last run summary for the status pill
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
        lines = ["<b>🎁 WR Rewards Toolkit: Report</b>\n"]
        for r in results:
            icon = "✅" if r["success"] else "❌"
            lines.append(f"{icon} <b>{r['game']}</b>: {r['message']}")
            for itm in r.get("items_collected", []):
                lines.append(f"   • {itm}")
        notifier.send("\n".join(lines))
        STATE["last_result"] = results
        STATE["last_daemon_run"] = time.time()
        
        if any_errors:
            add_log("WARNING", "Проверка завершена: возникла ошибка при обращении к магазину.")
        elif total_collected > 0:
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

@app.post("/api/action/test-notify")
def api_test_notify():
    Notifier(load_config()).send("🔔 <b>WR Rewards Toolkit</b>: Test notification received!")
    add_log("INFO", "Test notification sent.")
    return {"status": "ok", "message": "Test notification sent!"}

def check_is_overdue(cfg: Dict[str, Any]) -> bool:
    """Checks whether War Robots has uncollected rewards that are overdue."""
    try:
        cd = api_get_cooldowns()
        games_cfg = cfg.get("games", {})

        # War Robots check: overdue if enabled and not claimed today or cooldown reached 0
        if games_cfg.get("war_robots", {}).get("enabled", True):
            wr = cd.get("war_robots", {})
            if not wr.get("claimed", False):
                return True
            if wr.get("seconds_left", 0) <= 0:
                return True

        return False
    except Exception as e:
        add_log("DEBUG", f"Error checking overdue state: {e}")
        return False

COOLDOWN_SAFETY_MARGIN_SEC = 5  # 5-second buffer after cooldown ends to guarantee store server reset

def daemon_worker():
    """Background scheduler running with Below Normal CPU priority.
    Trusts the game website timer completely. Zero network polling or browser launches
    during cooldown. Collects rewards exactly when the cooldown timer expires (+5s buffer).
    """
    set_low_process_priority()
    last_heartbeat = time.time()

    # Initial check after full reboot / application start
    time.sleep(5)
    try:
        cfg = load_config()
        if cfg.get("app", {}).get("daemon_enabled", False):
            if check_is_overdue(cfg):
                add_log("INFO", "[Daemon] Старт приложения: таймер наград уже истек. Запуск сбора...")
                _run_collection_task(target="all", force_head=False, trigger_source="daemon_startup")
            else:
                cd = api_get_cooldowns()
                sec_left = cd.get("war_robots", {}).get("seconds_left", 0)
                h = sec_left // 3600
                m = (sec_left % 3600) // 60
                s = sec_left % 60
                time_str = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
                add_log("INFO", f"[Daemon] Старт приложения: награды на откате (еще {time_str}). Фоновое ожидание без лишних проверок.")
    except Exception as e:
        add_log("DEBUG", f"Daemon startup check exception: {e}")

    while True:
        try:
            # Low-overhead sleep: 15-second slices to gracefully handle PC sleep/wake and shutdown
            # ZERO network requests, ZERO browser calls during this sleep!
            time.sleep(15)
            now = time.time()
            gap = now - last_heartbeat
            last_heartbeat = now

            cfg = load_config()
            daemon_enabled = cfg.get("app", {}).get("daemon_enabled", False)
            if not daemon_enabled or STATE["is_running"]:
                continue

            last_run = STATE.get("last_daemon_run", 0)
            # Minimum 5-minute debounce between automatic collection attempts to prevent retry spam on errors
            if now - last_run < 300:
                continue

            # Detect wake-up from sleep or hibernate (gap > 3 minutes)
            is_wake_up = gap > 180

            # Check website cooldown timestamp
            checks = load_last_checks()
            wr_check = checks.get("War Robots", {})
            exact_sec = wr_check.get("exact_seconds_left")
            unix_ts = wr_check.get("unix_timestamp", 0)

            should_collect = False
            trigger_reason = ""

            if exact_sec is not None and unix_ts > 0:
                # Trust website data! Target time is unix_ts + exact_sec + 5s buffer
                target_time = unix_ts + exact_sec + COOLDOWN_SAFETY_MARGIN_SEC
                if now >= target_time:
                    should_collect = True
                    trigger_reason = "daemon_cooldown_expired"
            elif is_wake_up:
                if check_is_overdue(cfg):
                    should_collect = True
                    trigger_reason = "daemon_wakeup"
            else:
                # Fallback: interval check if no exact timer was available from shop
                interval_sec = max(1, int(cfg.get("app", {}).get("check_interval_hours", 12))) * 3600
                if (now - last_run >= interval_sec) and check_is_overdue(cfg):
                    should_collect = True
                    trigger_reason = "daemon_interval"

            if should_collect:
                add_log("INFO", f"[Daemon] Таймер отката наград истек (+{COOLDOWN_SAFETY_MARGIN_SEC}с запас для надежности). Запуск сбора...")
                _run_collection_task(target="all", force_head=False, trigger_source=trigger_reason)

        except Exception as e:
            add_log("DEBUG", f"Daemon scheduler loop exception: {e}")

# Mount UI static assets
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(UI_DIR / "index.html"))


# =====================================================================
#                      LAUNCHER, SYSTEM TRAY & WINDOW LIFECYCLE
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

def open_app_window(app_url: str) -> Optional[subprocess.Popen]:
    """Launches the app window using an installed Chromium browser or system default browser."""
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
            return subprocess.Popen(cmd)
        except Exception:
            webbrowser.open(app_url)
            return None
    else:
        webbrowser.open(app_url)
        return None

class TrayManager:
    """Manages the Windows notification area (System Tray) icon and context menu."""
    def __init__(self, app_url: str):
        self.app_url = app_url
        self.gui_process: Optional[subprocess.Popen] = None
        self.icon: Optional[pystray.Icon] = None
        self.first_minimize_notified = False

    def get_icon_image(self) -> Image.Image:
        icon_path = BASE_DIR / "ui" / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                return Image.open(icon_path)
            except Exception:
                pass
        png_path = BASE_DIR / "ui" / "assets" / "icon.png"
        if png_path.exists():
            try:
                return Image.open(png_path)
            except Exception:
                pass
        # Dynamic fallback
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([2, 2, 62, 62], radius=14, fill="#1e1e1e", outline="#0078d4", width=2)
        draw.polygon([(32, 12), (50, 22), (50, 42), (32, 52), (14, 42), (14, 22)], fill="#262626", outline="#0078d4", width=2)
        draw.polygon([(34, 18), (22, 33), (30, 33), (28, 46), (42, 30), (34, 30)], fill="#4cc2ff")
        return img

    def show_window(self, icon=None, item=None):
        if self.gui_process and self.gui_process.poll() is None:
            return
        self.gui_process = open_app_window(self.app_url)

    def claim_now(self, icon=None, item=None):
        if STATE["is_running"]:
            if self.icon:
                try:
                    self.icon.notify("Сбор уже выполняется...", "WR Rewards Toolkit")
                except Exception:
                    pass
            return
        add_log("INFO", "[Tray] Запуск сбора наград по команде из трея...")
        threading.Thread(target=_run_collection_task, args=("war_robots", False, "tray"), daemon=True).start()
        if self.icon:
            try:
                self.icon.notify("Запущен фоновый сбор наград War Robots...", "WR Rewards Toolkit")
            except Exception:
                pass

    def exit_app(self, icon=None, item=None):
        add_log("INFO", "[Tray] Завершение работы приложения...")
        if self.gui_process and self.gui_process.poll() is None:
            try:
                self.gui_process.terminate()
            except Exception:
                pass
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        os._exit(0)

    def setup_and_run(self):
        img = self.get_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("⚡ WR Rewards Toolkit", self.show_window, default=True),
            pystray.MenuItem("🎁 Забрать награду сейчас", self.claim_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("✕ Выход", self.exit_app)
        )
        self.icon = pystray.Icon("WR_Rewards_Toolkit", img, "WR Rewards Toolkit", menu)
        self.icon.run_detached()

def run_daemon_service():
    """Runs pure background daemon scheduler without launching any GUI window."""
    set_low_process_priority()
    add_log("INFO", "Starting WR Rewards Toolkit in Silent Daemon Mode (No GUI)...")
    port = find_free_port()
    server_cfg = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(server_cfg)
    threading.Thread(target=server.run, daemon=True).start()
    daemon_worker()

def start_gui(start_minimized: bool = False):
    set_low_process_priority()
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

    cfg = load_config()
    app_cfg = cfg.get("app", {})
    should_minimize = start_minimized or app_cfg.get("start_minimized", False)

    tray_mgr = TrayManager(app_url)
    tray_mgr.setup_and_run()

    if not should_minimize:
        tray_mgr.show_window()

    # Main thread handles window lifecycle and minimize-to-tray logic
    while True:
        time.sleep(0.8)
        if tray_mgr.gui_process is not None:
            if tray_mgr.gui_process.poll() is not None:
                # Browser window was closed by user
                tray_mgr.gui_process = None
                current_cfg = load_config()
                min_to_tray = current_cfg.get("app", {}).get("minimize_to_tray", True)
                if not min_to_tray:
                    add_log("INFO", "Window closed and minimize_to_tray is disabled. Exiting...")
                    tray_mgr.exit_app()
                    break
                else:
                    add_log("INFO", "Window closed. Application continues running silently in system tray.")
                    if not tray_mgr.first_minimize_notified and tray_mgr.icon:
                        tray_mgr.first_minimize_notified = True
                        try:
                            tray_mgr.icon.notify("Приложение свёрнуто в системный трей.", "WR Rewards Toolkit")
                        except Exception:
                            pass

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WR Rewards Toolkit")
    parser.add_argument("--run", choices=["all", "war_robots"], nargs="?", const="all", help="CLI: Claim rewards")
    parser.add_argument("--head", action="store_true", help="CLI: Run with visible browser window")
    parser.add_argument("--daemon", action="store_true", help="Run background scheduler service without GUI")
    parser.add_argument("--minimized", action="store_true", help="Start directly minimized to system tray")
    args = parser.parse_args()

    if args.run:
        _run_collection_task(args.run, force_head=args.head, trigger_source="cli")
    elif args.daemon:
        run_daemon_service()
    else:
        start_gui(start_minimized=args.minimized)

if __name__ == "__main__":
    main()
