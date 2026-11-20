// ==========================================================================
// WR Rewards Toolkit - Desktop UI Application
// ==========================================================================

let currentConfig = null;
let lastLogIndex = 0;
let isPolling = true;
let currentLanguage = localStorage.getItem("app_lang") || "ru";

let wrCooldownData = null;
let wrCooldownSec = 0;
let wasRunning = false;

// ==========================================================================
//                           LOCALIZATION (I18N)
// ==========================================================================

const TRANSLATIONS = {
  ru: {
    nav_label: "НАВИГАЦИЯ",
    tab_dashboard: "Дашборд",
    tab_promocodes: "Промокоды",
    tab_history: "История сборов",
    tab_settings: "Настройки",
    tab_console: "Живая консоль",
    tray_active: "Трей активен",
    dash_title: "Центр управления наградами",
    dash_sub: "Автоматический сбор ежедневных подарков и предметов из официального магазина",
    btn_visible: "Запустить с окном",
    btn_claim_all: "ЗАБРАТЬ НАГРАДЫ",
    btn_claim_wr: "Забрать",
    lbl_platform: "Платформа",
    lbl_recent_events: "Последние события",
    btn_full_console: "Вся консоль →",
    hist_title: "Журнал собранных наград",
    hist_sub: "История всех успешных сборов и бесплатных предметов из магазина",
    btn_refresh: "Обновить",
    btn_clear_history: "Очистить",
    col_date: "Дата и время",
    col_game: "Игра",
    col_item: "Награда / Предмет",
    col_status: "Статус",
    hist_empty_title: "Наград пока не собрано",
    hist_empty_desc: "Нажмите «Забрать награды» на дашборде, чтобы пополнить журнал!",
    promo_title: "Активация промокодов",
    promo_sub: "Быстрый ввод и применение официальных промокодов для War Robots",
    promo_lbl_code: "Промокод",
    promo_btn_submit: "Активировать промокод",
    cfg_title: "Параметры и Настройки",
    cfg_sub: "Интеграция с Windows, системный трей, параметры автосбора и оповещения",
    btn_save_cfg: "Сохранить настройки",
    cfg_group_windows: "ИНТЕГРАЦИЯ С WINDOWS & ТРЕЙ",
    cfg_autostart_title: "Запуск вместе с Windows",
    cfg_autostart_desc: "Автоматически запускать сборщик в фоне при старте системы (без открытия консоли)",
    cfg_tray_title: "Сворачивать в системный трей",
    cfg_tray_desc: "При нажатии на крестик [X] окно закрывается, а приложение продолжает тихо работать в трее",
    cfg_minimized_title: "Запускать свёрнутым",
    cfg_minimized_desc: "При автозапуске не открывать главное окно, а сразу прятать значок в трей",
    cfg_group_daemon: "АВТОМАТИЗАЦИЯ И СБОР",
    cfg_daemon_title: "Автоматический фоновый сбор",
    cfg_daemon_desc: "Фоновый планировщик проверяет магазин при старте ПК, выходе из сна и по расписанию",
    cfg_lbl_interval: "Интервал периодической проверки",
    cfg_desc_interval: "Периодичность фоновой проверки магазина (в часах)",
    cfg_headless_title: "Скрытый режим браузера (Headless)",
    cfg_headless_desc: "Браузер работает невидимо в памяти без всплывающих окон на рабочем столе",
    cfg_shot_title: "Скриншот при ошибке",
    cfg_shot_desc: "Сохранять снимок экрана в папку logs/screenshots в случае сбоя",
    cfg_section_games: "ИГРОВОЙ ПРОФИЛЬ",
    cfg_notify_title: "ОПОВЕЩЕНИЯ В МЕССЕНДЖЕРЫ",
    btn_test_notify: "Отправить тест",
    console_title: "Живая консоль (Live Logs)",
    console_sub: "События, статусы сбора и системные сообщения в реальном времени",
    btn_copy_logs: "Скопировать логи",
    btn_clear_logs: "Очистить",
    status_ready: "ГОТОВО К РАБОТЕ",
    status_collecting: "ИДЕТ СБОР НАГРАД...",
    daemon_on: "АВТОСБОР: ВКЛ",
    daemon_off: "АВТОСБОР: ВЫКЛ",
    ready_to_claim: "Готово к сбору! 🎁",
    badge_claimed: "Собрано ✓",
    badge_no_rewards: "Нет наград",
    cooldown_word: "Откат: ",
    cooldown_prefix: "Доступно через: ",
    ph_dash_wr_id: "Введите ваш Pilot ID",
    ph_cfg_wr_id: "Введите Pilot ID"
  },
  en: {
    nav_label: "NAVIGATION",
    tab_dashboard: "Dashboard",
    tab_promocodes: "Promo Codes",
    tab_history: "Reward History",
    tab_settings: "Settings",
    tab_console: "Live Console",
    tray_active: "Tray Active",
    dash_title: "Rewards Control Center",
    dash_sub: "Automated daily gifts and free items collector for War Robots shop",
    btn_visible: "Run with Window",
    btn_claim_all: "CLAIM REWARDS",
    btn_claim_wr: "Claim",
    lbl_platform: "Platform",
    lbl_recent_events: "Recent Events",
    btn_full_console: "Full Console →",
    hist_title: "Collected Rewards Log",
    hist_sub: "History of all claimed gifts and promotional items with direct image previews",
    btn_refresh: "Refresh",
    btn_clear_history: "Clear",
    col_date: "Date & Time",
    col_game: "Game",
    col_item: "Reward / Item",
    col_status: "Status",
    hist_empty_title: "No rewards collected yet",
    hist_empty_desc: "Click 'Claim Rewards' on the dashboard to populate your history log!",
    promo_title: "Promo Code Redemption",
    promo_sub: "Quick promo code activation for War Robots",
    promo_lbl_code: "Promo Code",
    promo_btn_submit: "Redeem Promo Code",
    cfg_title: "Preferences & Settings",
    cfg_sub: "Windows integration, system tray, scheduler automation and notifications",
    btn_save_cfg: "Save Settings",
    cfg_group_windows: "WINDOWS & SYSTEM TRAY INTEGRATION",
    cfg_autostart_title: "Start with Windows",
    cfg_autostart_desc: "Automatically launch the toolkit silently in the background on system boot",
    cfg_tray_title: "Minimize to System Tray",
    cfg_tray_desc: "Closing the window [X] keeps the toolkit running quietly in the system tray",
    cfg_minimized_title: "Start Minimized in Tray",
    cfg_minimized_desc: "Do not open the window on launch; keep it minimized in the tray",
    cfg_group_daemon: "AUTOMATION & SCHEDULER",
    cfg_daemon_title: "Scheduled Background Collector",
    cfg_daemon_desc: "Background scheduler checks store on boot, sleep wake-up, and periodic intervals",
    cfg_lbl_interval: "Check Interval",
    cfg_desc_interval: "Frequency of background store checks (in hours)",
    cfg_headless_title: "Silent Browser Mode (Headless)",
    cfg_headless_desc: "Browser runs silently in memory without popping up windows on screen",
    cfg_shot_title: "Screenshot on Failure",
    cfg_shot_desc: "Save debug screenshot to logs/screenshots on error",
    cfg_section_games: "GAME PROFILES",
    cfg_notify_title: "MESSENGER NOTIFICATIONS",
    btn_test_notify: "Send Test Message",
    console_title: "Live Console Logs",
    console_sub: "Real-time event monitoring, collection statuses, and system messages",
    btn_copy_logs: "Copy Logs",
    btn_clear_logs: "Clear",
    status_ready: "SYSTEM READY",
    status_collecting: "COLLECTING REWARDS...",
    daemon_on: "AUTO-COLLECT: ON",
    daemon_off: "AUTO-COLLECT: OFF",
    ready_to_claim: "Ready to Claim! 🎁",
    badge_claimed: "Claimed ✓",
    badge_no_rewards: "No gifts",
    cooldown_word: "Cooldown: ",
    cooldown_prefix: "Available in: ",
    ph_dash_wr_id: "Enter your Pilot ID",
    ph_cfg_wr_id: "Enter Pilot ID"
  }
};

function t(key) {
  return (TRANSLATIONS[currentLanguage] && TRANSLATIONS[currentLanguage][key]) || key;
}

function applyLanguage() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (key && TRANSLATIONS[currentLanguage][key]) {
      el.innerHTML = TRANSLATIONS[currentLanguage][key];
    }
  });

  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    const key = el.getAttribute("data-i18n-ph");
    if (key && TRANSLATIONS[currentLanguage][key]) {
      el.placeholder = TRANSLATIONS[currentLanguage][key];
    }
  });

  const langText = document.getElementById("current-lang-text");
  if (langText) langText.innerText = currentLanguage.toUpperCase();
}

document.getElementById("btn-toggle-lang")?.addEventListener("click", () => {
  currentLanguage = currentLanguage === "ru" ? "en" : "ru";
  localStorage.setItem("app_lang", currentLanguage);
  applyLanguage();
  updateCooldownDisplay();
  showToast(currentLanguage === "ru" ? "Язык интерфейса: Русский" : "Language set to English", "info");
});

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  if (type === "success") toast.style.borderLeftColor = "var(--accent-emerald)";
  if (type === "error") toast.style.borderLeftColor = "var(--accent-rose)";
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    toast.style.transition = "all 0.2s ease";
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// Navigation Tabs
document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));

    item.classList.add("active");
    const targetTab = item.getAttribute("data-tab");
    const tabEl = document.getElementById(`tab-${targetTab}`);
    if (tabEl) tabEl.classList.add("active");

    if (targetTab === "history") {
      loadHistory();
    }
  });
});

document.getElementById("btn-to-console")?.addEventListener("click", () => {
  document.querySelector('.nav-item[data-tab="console"]')?.click();
});

// ==========================================================================
//                           CONFIG & SYSTEM SETTINGS
// ==========================================================================

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error("Could not load configuration");
    currentConfig = await res.json();

    // App core fields
    document.getElementById("cfg-interval").value = currentConfig.app?.check_interval_hours || 12;
    document.getElementById("cfg-headless").checked = currentConfig.app?.headless ?? true;
    document.getElementById("cfg-screenshot").checked = currentConfig.app?.screenshot_on_error ?? true;
    document.getElementById("cfg-daemon-enabled").checked = currentConfig.app?.daemon_enabled ?? false;

    // War Robots fields
    const wr = currentConfig.games?.war_robots || {};
    const wrId = wr.player_id || "";
    const wrPlat = (wr.platform || "crossplay").toLowerCase();
    document.getElementById("cfg-wr-player-id").value = wrId;
    document.getElementById("dash-wr-player-id").value = wrId;
    document.getElementById("cfg-wr-platform").value = wrPlat;
    document.getElementById("dash-wr-platform").value = wrPlat;
    document.getElementById("dash-wr-enabled").checked = wr.enabled ?? true;

    // Notifications
    const tg = currentConfig.notifications?.telegram || {};
    document.getElementById("cfg-tg-enabled").checked = tg.enabled ?? false;
    document.getElementById("cfg-tg-token").value = tg.bot_token || "";
    document.getElementById("cfg-tg-chat").value = tg.chat_id || "";

    const dc = currentConfig.notifications?.discord || {};
    document.getElementById("cfg-dc-enabled").checked = dc.enabled ?? false;
    document.getElementById("cfg-dc-webhook").value = dc.webhook_url || "";

    // System Settings (Autostart & Tray)
    const sysRes = await fetch("/api/system/settings");
    if (sysRes.ok) {
      const sysData = await sysRes.json();
      document.getElementById("cfg-autostart").checked = sysData.autostart_windows ?? false;
      document.getElementById("cfg-minimize-to-tray").checked = sysData.minimize_to_tray ?? true;
      document.getElementById("cfg-start-minimized").checked = sysData.start_minimized ?? false;
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function saveFullConfig() {
  if (!currentConfig) return;

  currentConfig.app = currentConfig.app || {};
  currentConfig.app.check_interval_hours = parseInt(document.getElementById("cfg-interval").value, 10) || 12;
  currentConfig.app.headless = document.getElementById("cfg-headless").checked;
  currentConfig.app.screenshot_on_error = document.getElementById("cfg-screenshot").checked;
  currentConfig.app.daemon_enabled = document.getElementById("cfg-daemon-enabled").checked;

  currentConfig.games = {
    war_robots: {
      player_id: document.getElementById("dash-wr-player-id").value.trim(),
      platform: document.getElementById("dash-wr-platform").value,
      enabled: document.getElementById("dash-wr-enabled").checked
    }
  };

  currentConfig.notifications = currentConfig.notifications || {};
  currentConfig.notifications.telegram = {
    enabled: document.getElementById("cfg-tg-enabled").checked,
    bot_token: document.getElementById("cfg-tg-token").value.trim(),
    chat_id: document.getElementById("cfg-tg-chat").value.trim()
  };
  currentConfig.notifications.discord = {
    enabled: document.getElementById("cfg-dc-enabled").checked,
    webhook_url: document.getElementById("cfg-dc-webhook").value.trim()
  };

  try {
    const res1 = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentConfig)
    });
    if (!res1.ok) throw new Error("Failed to save config settings");

    const sysPayload = {
      autostart_windows: document.getElementById("cfg-autostart").checked,
      minimize_to_tray: document.getElementById("cfg-minimize-to-tray").checked,
      start_minimized: document.getElementById("cfg-start-minimized").checked
    };
    await fetch("/api/system/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sysPayload)
    });

    showToast(currentLanguage === "ru" ? "Настройки успешно сохранены!" : "Settings saved successfully!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

document.getElementById("btn-save-settings")?.addEventListener("click", saveFullConfig);

// Two-way sync on dashboard inputs
["dash-wr-player-id", "dash-wr-platform", "dash-wr-enabled"].forEach(id => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("change", () => {
      if (id === "dash-wr-player-id") {
        document.getElementById("cfg-wr-player-id").value = el.value;
      }
      saveFullConfig();
    });
    if (el.tagName === "INPUT" && el.type === "text") {
      el.addEventListener("blur", () => {
        document.getElementById("cfg-wr-player-id").value = el.value;
        saveFullConfig();
      });
    }
  }
});

// ==========================================================================
//                           HISTORY LOGIC
// ==========================================================================

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    if (!res.ok) throw new Error("Could not fetch history");
    const history = await res.json();

    const tbody = document.getElementById("history-tbody");
    const emptyState = document.getElementById("history-empty");
    tbody.innerHTML = "";

    if (!history || history.length === 0) {
      emptyState.style.display = "block";
      return;
    }

    emptyState.style.display = "none";
    history.forEach(item => {
      const tr = document.createElement("tr");
      const imgUrl = item.image_url || "https://market.my.games/s3/media/2026/10/22/9b21a096c25aaa56c9bdfad9106e7c86.png";

      tr.innerHTML = `
        <td style="color: var(--text-muted); font-size: 12px;">${escapeHtml(item.timestamp || "")}</td>
        <td><b style="color: var(--accent-cyan);">${escapeHtml(item.game)}</b></td>
        <td>
          <img src="${escapeHtml(imgUrl)}" class="history-thumb" alt="Item" onerror="this.src='/static/assets/icon.png'">
          <span>${escapeHtml(item.item_name || "Reward Item")}</span>
        </td>
        <td>
          <span class="history-status-badge history-status-success">
            ✓ ${currentLanguage === 'ru' ? 'Забрано' : 'Claimed'}
          </span>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.debug("History fetch error:", err);
  }
}

document.getElementById("btn-refresh-history")?.addEventListener("click", loadHistory);
document.getElementById("btn-clear-history")?.addEventListener("click", async () => {
  try {
    await fetch("/api/history/clear", { method: "POST" });
    loadHistory();
    showToast(currentLanguage === "ru" ? "История очищена" : "History cleared", "info");
  } catch (err) {
    showToast(err.message, "error");
  }
});

// Promo codes submit
document.getElementById("btn-promo-submit")?.addEventListener("click", () => {
  const code = document.getElementById("promo-input-code")?.value.trim();
  if (!code) {
    showToast(currentLanguage === "ru" ? "Введите промокод!" : "Please enter a promo code!", "error");
    return;
  }
  showToast(currentLanguage === "ru" ? "Активация промокодов в процессе интеграции..." : "Promo code redemption integration in progress...", "info");
});

// ==========================================================================
//                           COOLDOWNS & TIMERS
// ==========================================================================

function formatTime(seconds, short = false) {
  if (seconds <= 0) return t("ready_to_claim");
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;

  const prefix = short ? "" : t("cooldown_prefix");
  if (d > 0) return `${prefix}${d}d ${h}h`;
  if (h > 0) return `${prefix}${h}h ${m}m`;
  return `${prefix}${m}m ${s}s`;
}

function updateCooldownDisplay() {
  const wrBadge = document.getElementById("wr-cooldown-badge");
  if (wrBadge) {
    if (wrCooldownSec <= 0 || !wrCooldownData?.claimed) {
      wrBadge.innerText = t("ready_to_claim");
      wrBadge.className = "cooldown-badge ready";
    } else {
      const cdStr = formatTime(wrCooldownSec, true);
      if (wrCooldownData?.status === "no_rewards") {
        wrBadge.innerText = `${t("badge_no_rewards")} (${t("cooldown_word")}${cdStr})`;
        wrBadge.className = "cooldown-badge no-rewards";
      } else {
        wrBadge.innerText = `${t("badge_claimed")} (${t("cooldown_word")}${cdStr})`;
        wrBadge.className = "cooldown-badge claimed";
      }
    }
  }
}

async function fetchCooldowns() {
  try {
    const res = await fetch("/api/rewards/cooldowns");
    if (res.ok) {
      const data = await res.json();
      wrCooldownData = data.war_robots || null;
      wrCooldownSec = data.war_robots?.seconds_left || 0;
      updateCooldownDisplay();
    }
  } catch (e) {
    console.debug("Cooldown fetch error:", e);
  }
}

setInterval(() => {
  if (wrCooldownSec > 0) wrCooldownSec--;
  updateCooldownDisplay();
}, 1000);

// ==========================================================================
//                           ACTIONS: REWARD COLLECTION
// ==========================================================================

async function triggerCollect(target = "all", forceHead = false) {
  const wrId = document.getElementById("dash-wr-player-id").value.trim();
  const wrEnabled = document.getElementById("dash-wr-enabled").checked;

  if (target === "war_robots" || (target === "all" && wrEnabled)) {
    if (!wrId) {
      showToast(currentLanguage === "ru" ? "Пожалуйста, введите ваш Pilot ID в карточке War Robots!" : "Please enter your Pilot ID in War Robots card!", "error");
      document.getElementById("dash-wr-player-id").focus();
      return;
    }
  }

  try {
    const res = await fetch(`/api/action/collect?target=${target}&force_head=${forceHead}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "Launch failed");
    showToast(data.message, "success");
    document.querySelector('.nav-item[data-tab="console"]')?.click();
  } catch (err) {
    showToast(err.message, "error");
  }
}

document.getElementById("btn-collect-all")?.addEventListener("click", () => triggerCollect("all", false));
document.getElementById("btn-collect-head")?.addEventListener("click", () => triggerCollect("all", true));
document.getElementById("btn-collect-wr")?.addEventListener("click", () => triggerCollect("war_robots", false));

// Action: Test Notification
document.getElementById("btn-test-notification")?.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/action/test-notify", { method: "POST" });
    const data = await res.json();
    showToast(currentLanguage === "ru" ? "Тестовое уведомление отправлено!" : "Test notification sent!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
});

// Action: Clear & Copy Logs
document.getElementById("btn-clear-logs")?.addEventListener("click", async () => {
  await fetch("/api/logs/clear", { method: "POST" });
  document.getElementById("terminal-output").innerHTML = "";
  lastLogIndex = 0;
  showToast(currentLanguage === "ru" ? "Логи очищены" : "Logs cleared", "info");
});

document.getElementById("btn-copy-logs")?.addEventListener("click", () => {
  const terminal = document.getElementById("terminal-output");
  navigator.clipboard.writeText(terminal.innerText).then(() => {
    showToast(currentLanguage === "ru" ? "Логи скопированы в буфер обмена!" : "Logs copied to clipboard!", "success");
  });
});

// Daemon Toggle Pill
document.getElementById("daemon-status-pill")?.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/daemon/toggle", { method: "POST" });
    const data = await res.json();
    document.getElementById("cfg-daemon-enabled").checked = data.daemon_enabled;
    showToast(data.daemon_enabled ? (currentLanguage === "ru" ? "Автосбор включен!" : "Auto-collect enabled!") : (currentLanguage === "ru" ? "Автосбор выключен" : "Auto-collect disabled"), "info");
  } catch (err) {
    showToast(err.message, "error");
  }
});

document.getElementById("cfg-daemon-enabled")?.addEventListener("change", async () => {
  try {
    await fetch("/api/daemon/toggle", { method: "POST" });
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ==========================================================================
//                           STATUS & LOGS POLLING LOOP
// ==========================================================================

async function pollStatusAndLogs() {
  try {
    // 1. Status
    const sRes = await fetch("/api/status");
    if (sRes.ok) {
      const status = await sRes.json();
      
      const statusPill = document.getElementById("system-status");
      const statusText = document.getElementById("status-text");
      const daemonPill = document.getElementById("daemon-status-pill");
      const daemonDot = daemonPill?.querySelector(".status-dot");
      const daemonText = document.getElementById("daemon-status-text");
      const sidebarDaemon = document.getElementById("sidebar-daemon-status");

      // Auto-refresh badges & history when a background run finishes
      if (wasRunning && !status.is_running) {
        fetchCooldowns();
        loadHistory();
      }
      wasRunning = status.is_running;

      // System running status
      if (status.is_running) {
        statusPill.style.background = "rgba(245, 158, 11, 0.15)";
        statusPill.style.borderColor = "rgba(245, 158, 11, 0.4)";
        statusPill.style.color = "#fde047";
        statusText.innerText = t("status_collecting");
      } else {
        const summary = currentLanguage === "ru" ? status.last_run_summary_ru : status.last_run_summary_en;
        if (summary) {
          statusText.innerText = summary;
          if (status.last_run_status === "error") {
            statusPill.style.background = "rgba(239, 68, 68, 0.15)";
            statusPill.style.borderColor = "rgba(239, 68, 68, 0.35)";
            statusPill.style.color = "#fca5a5";
          } else {
            statusPill.style.background = "rgba(16, 185, 129, 0.12)";
            statusPill.style.borderColor = "rgba(16, 185, 129, 0.28)";
            statusPill.style.color = "#6ee7b7";
          }
        } else {
          statusPill.style.background = "rgba(255, 255, 255, 0.05)";
          statusPill.style.borderColor = "var(--border-subtle)";
          statusPill.style.color = "var(--text-secondary)";
          statusText.innerText = t("status_ready");
        }
      }

      // Daemon status
      if (status.daemon_enabled) {
        if (daemonDot) daemonDot.className = "status-dot dot-daemon active";
        if (status.next_daemon_run_in > 0) {
          const totM = Math.floor(status.next_daemon_run_in / 60);
          const h = Math.floor(totM / 60);
          const m = totM % 60;
          const timeStr = h > 0 ? `${h}h ${m}m` : `${m}m`;
          daemonText.innerText = `${t("daemon_on")} (${timeStr})`;
          if (sidebarDaemon) sidebarDaemon.innerText = `${currentLanguage === 'ru' ? 'Автосбор: Вкл' : 'Auto-collect: On'} (${timeStr})`;
        } else {
          daemonText.innerText = t("daemon_on");
          if (sidebarDaemon) sidebarDaemon.innerText = currentLanguage === 'ru' ? 'Автосбор: Вкл' : 'Auto-collect: On';
        }
      } else {
        if (daemonDot) daemonDot.className = "status-dot dot-daemon";
        daemonText.innerText = t("daemon_off");
        if (sidebarDaemon) sidebarDaemon.innerText = currentLanguage === 'ru' ? 'Автосбор: Выкл' : 'Auto-collect: Off';
      }
    }

    // 2. Logs
    const lRes = await fetch(`/api/logs?after=${lastLogIndex}`);
    if (lRes.ok) {
      const lData = await lRes.json();
      if (lData.logs && lData.logs.length > 0) {
        const terminal = document.getElementById("terminal-output");
        const miniLog = document.getElementById("mini-log");
        
        lData.logs.forEach(log => {
          const line = document.createElement("div");
          line.className = "log-line";
          line.innerHTML = `
            <span class="log-time">[${log.time}]</span>
            <span class="log-tag tag-${log.level}">${log.level}</span>
            <span class="log-msg">${escapeHtml(log.message)}</span>
          `;
          terminal.appendChild(line);
        });

        const lastLog = lData.logs[lData.logs.length - 1];
        if (miniLog) miniLog.innerText = `[${lastLog.time}] ${lastLog.message}`;

        terminal.scrollTop = terminal.scrollHeight;
        lastLogIndex += lData.logs.length;
      }
    }
  } catch (e) {
    console.debug("Polling error:", e);
  }

  if (isPolling) {
    setTimeout(pollStatusAndLogs, 1500);
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.innerText = text;
  return div.innerHTML;
}

// Initial Boot
window.addEventListener("DOMContentLoaded", async () => {
  applyLanguage();
  await loadConfig();
  await fetchCooldowns();
  await loadHistory();
  pollStatusAndLogs();
});
