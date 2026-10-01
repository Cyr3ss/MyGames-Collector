// ==========================================================================
// Auto Collect MyGames - Modern Desktop Client
// ==========================================================================

let currentConfig = null;
let lastLogIndex = 0;
let isPolling = true;
let currentLanguage = localStorage.getItem("app_lang") || "ru";

let rrCooldownData = null;
let wrCooldownData = null;
let rrCooldownSec = 0;
let wrCooldownSec = 0;
let wasRunning = false;

// ==========================================================================
//                           LOCALIZATION (I18N)
// ==========================================================================

const TRANSLATIONS = {
  ru: {
    nav_label: "Навигация",
    tab_dashboard: "Дашборд",
    tab_history: "История сборов",
    tab_promocodes: "Промокоды",
    tab_auth: "Авторизация",
    tab_settings: "Настройки",
    tab_console: "Живая консоль",
    session_title: "MY.GAMES Профиль",
    dash_title: "Центр управления наградами",
    dash_sub: "Автоматический сбор ежедневных подарков и бесплатных наборов из магазинов",
    btn_visible: "Запустить с окном",
    btn_claim_all: "ЗАБРАТЬ ВСЕ НАГРАДЫ",
    btn_claim_rr: "Забрать только Rush Royale",
    btn_claim_wr: "Забрать только War Robots",
    lbl_game_id: "Игровой ID (Game ID)",
    lbl_platform: "Платформа",
    lbl_recent_events: "Последние события",
    btn_full_console: "Вся консоль →",
    hist_title: "Журнал собранных наград",
    hist_sub: "История всех успешных сборов, подарков и акций с прямыми ссылками на предметы",
    btn_refresh: "Обновить",
    btn_clear_history: "Очистить историю",
    col_date: "Дата и время",
    col_game: "Игра",
    col_item: "Награда / Предмет",
    col_status: "Статус",
    hist_empty_title: "Наград пока не собрано",
    hist_empty_desc: "Нажмите «Забрать все награды» на главной панели, чтобы пополнить журнал!",
    promo_title: "Активация промокодов",
    promo_sub: "Автоматический ввод промо-кодов для ваших игр в один клик",
    promo_badge: "СКОРО В ОБНОВЛЕНИИ V2.0",
    promo_card_title: "Универсальный активатор промокодов",
    promo_card_desc: "Мы разрабатываем модуль автоматического распознавания и применения секретных промокодов для Rush Royale и War Robots без необходимости открывать игру.",
    promo_lbl_game: "Выберите игру",
    promo_lbl_code: "Промокод",
    promo_btn_submit: "Активировать промокод (В разработке)",
    auth_title: "Авторизация в MY.GAMES",
    auth_sub: "Безопасный вход через браузер без передачи паролей сторонним скриптам",
    btn_check_session: "Проверить сессию",
    btn_logout: "Выйти из аккаунта",
    auth_how_title: "Как это работает:",
    auth_step_1: "Нажмите кнопку <b>«Открыть окно входа»</b> ниже.",
    auth_step_2: "В открывшемся окне официального браузера выполните вход (VK ID, логин/пароль, почта или Google).",
    auth_step_3: "После успешного входа на сайт окно само закроется или нажмите «Я вошёл».",
    auth_step_4: "Сессия сохраняется на несколько месяцев (Sliding Session) — повторно входить не придётся!",
    btn_open_login: "Открыть форму входа в MY.GAMES",
    btn_finish_login: "Я вошёл в аккаунт (Завершить и сохранить)",
    cfg_title: "Параметры и Настройки",
    cfg_sub: "Редактируйте параметры прямо в окне без ручной правки файлов конфигурации",
    btn_save_cfg: "Сохранить настройки",
    cfg_section_app: "Параметры приложения",
    cfg_daemon_title: "Автоматический сбор по расписанию",
    cfg_daemon_desc: "Регулярно собирать подарки в фоне каждые N часов без вашего участия",
    cfg_lbl_interval: "Интервал проверки (в часах)",
    cfg_headless_title: "Скрытый режим браузера (Headless)",
    cfg_headless_desc: "Браузер работает невидимо в памяти без всплывающих окон на экране",
    cfg_shot_title: "Скриншот при ошибке",
    cfg_shot_desc: "Сохранять снимок экрана в папку logs/screenshots",
    cfg_section_games: "Игровые профили",
    cfg_notify_title: "Оповещения в мессенджеры",
    btn_test_notify: "Отправить тест",
    console_title: "Живая консоль (Live Logs)",
    console_sub: "Мониторинг событий, статусов сбора и системных сообщений в реальном времени",
    btn_copy_logs: "Скопировать логи",
    btn_clear_logs: "Очистить",
    status_ready: "СИСТЕМА ГОТОВА",
    status_collecting: "ИДЕТ СБОР НАГРАД...",
    status_auth_waiting: "ОЖИДАНИЕ ВХОДА В БРАУЗЕРЕ...",
    status_authed: "Авторизован ✅",
    status_need_auth: "Требуется вход ⚠️",
    daemon_on: "ДЕМОН: ВКЛ",
    daemon_off: "ДЕМОН: ВЫКЛ",
    ready_to_claim: "Готово к сбору! 🎁",
    badge_claimed: "Собрано ✓",
    badge_no_rewards: "Нет наград",
    cooldown_word: "Откат: ",
    cooldown_prefix: "Доступно через: ",
    ph_dash_rr_id: "Введите ваш Player ID",
    ph_dash_wr_id: "Введите ваш Pilot ID",
    ph_cfg_rr_id: "Введите Player ID",
    ph_cfg_wr_id: "Введите Pilot ID"
  },
  en: {
    nav_label: "Navigation",
    tab_dashboard: "Dashboard",
    tab_history: "Reward History",
    tab_promocodes: "Promo Codes",
    tab_auth: "Authentication",
    tab_settings: "Settings",
    tab_console: "Live Console",
    session_title: "MY.GAMES Profile",
    dash_title: "Rewards Control Center",
    dash_sub: "Automated daily gifts and free bundle collector for game stores",
    btn_visible: "Run with Window",
    btn_claim_all: "CLAIM ALL REWARDS",
    btn_claim_rr: "Claim Rush Royale Only",
    btn_claim_wr: "Claim War Robots Only",
    lbl_game_id: "Player ID (Game ID)",
    lbl_platform: "Platform",
    lbl_recent_events: "Recent Events",
    btn_full_console: "Full Console →",
    hist_title: "Collected Rewards Log",
    hist_sub: "History of all claimed gifts and promotional items with direct image previews",
    btn_refresh: "Refresh",
    btn_clear_history: "Clear History",
    col_date: "Date & Time",
    col_game: "Game",
    col_item: "Reward / Item",
    col_status: "Status",
    hist_empty_title: "No rewards collected yet",
    hist_empty_desc: "Click 'Claim All Rewards' on the dashboard to populate your history log!",
    promo_title: "Promo Code Redemption",
    promo_sub: "Automated one-click promo code activator across games",
    promo_badge: "COMING IN V2.0",
    promo_card_title: "Universal Promo Code Activator",
    promo_card_desc: "We are developing an automated code redemption module for Rush Royale and War Robots without launching the games.",
    promo_lbl_game: "Select Game",
    promo_lbl_code: "Promo Code",
    promo_btn_submit: "Redeem Promo Code (In Development)",
    auth_title: "MY.GAMES Authentication",
    auth_sub: "Secure login via standard browser window without sharing credentials",
    btn_check_session: "Verify Session",
    btn_logout: "Log Out Account",
    auth_how_title: "How it works:",
    auth_step_1: "Click the <b>'Open Login Window'</b> button below.",
    auth_step_2: "In the browser window, log in to your account (VK ID, password, email, or Google).",
    auth_step_3: "Once signed in, the window closes automatically or click 'I am logged in'.",
    auth_step_4: "Sessions stay valid for months (Sliding Session) — no need to log in repeatedly!",
    btn_open_login: "Open MY.GAMES Login Window",
    btn_finish_login: "I am Logged In (Finish & Save)",
    cfg_title: "Preferences & Settings",
    cfg_sub: "Configure options in GUI without editing configuration files manually",
    btn_save_cfg: "Save Settings",
    cfg_section_app: "Application Settings",
    cfg_daemon_title: "Scheduled Auto-Collection",
    cfg_daemon_desc: "Periodically check and claim rewards in background without manual interaction",
    cfg_lbl_interval: "Check Interval (hours)",
    cfg_headless_title: "Silent Browser Mode (Headless)",
    cfg_headless_desc: "Browser runs silently in memory without popping up windows on screen",
    cfg_shot_title: "Screenshot on Failure",
    cfg_shot_desc: "Save debug screenshot to logs/screenshots on error",
    cfg_section_games: "Game Profiles",
    cfg_notify_title: "Messenger Notifications",
    btn_test_notify: "Send Test Message",
    console_title: "Live Console Logs",
    console_sub: "Real-time event monitoring, collection statuses, and system messages",
    btn_copy_logs: "Copy Logs",
    btn_clear_logs: "Clear",
    status_ready: "SYSTEM READY",
    status_collecting: "COLLECTING REWARDS...",
    status_auth_waiting: "AWAITING BROWSER LOGIN...",
    status_authed: "Authorized ✅",
    status_need_auth: "Login Required ⚠️",
    daemon_on: "DAEMON: ON",
    daemon_off: "DAEMON: OFF",
    ready_to_claim: "Ready to Claim! 🎁",
    badge_claimed: "Claimed ✓",
    badge_no_rewards: "No gifts",
    cooldown_word: "Cooldown: ",
    cooldown_prefix: "Available in: ",
    ph_dash_rr_id: "Enter your Player ID",
    ph_dash_wr_id: "Enter your Pilot ID",
    ph_cfg_rr_id: "Enter Player ID",
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
  showToast(currentLanguage === "ru" ? "Язык переключен на Русский" : "Language set to English", "info");
});

// Toast helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  if (type === "success") toast.style.borderLeftColor = "#10b981";
  if (type === "error") toast.style.borderLeftColor = "#f43f5e";
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
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
//                           CONFIG & SYNC
// ==========================================================================

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error("Could not load configuration");
    currentConfig = await res.json();

    // Populate Settings Fields
    document.getElementById("cfg-interval").value = currentConfig.app?.check_interval_hours || 12;
    document.getElementById("cfg-headless").checked = currentConfig.app?.headless ?? true;
    document.getElementById("cfg-screenshot").checked = currentConfig.app?.screenshot_on_error ?? true;
    document.getElementById("cfg-daemon-enabled").checked = currentConfig.app?.daemon_enabled ?? false;

    // Rush Royale
    const rr = currentConfig.games?.rush_royale || {};
    const rrId = rr.player_id || "";
    const rrPlat = (rr.platform || "android").toLowerCase();
    document.getElementById("cfg-rr-player-id").value = rrId;
    document.getElementById("dash-rr-player-id").value = rrId;
    document.getElementById("dash-rr-platform").value = rrPlat;
    document.getElementById("dash-rr-enabled").checked = rr.enabled ?? true;

    // War Robots
    const wr = currentConfig.games?.war_robots || {};
    const wrId = wr.player_id || "";
    const wrPlat = (wr.platform || "android").toLowerCase();
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

  currentConfig.games = currentConfig.games || {};
  currentConfig.games.rush_royale = currentConfig.games.rush_royale || {};
  currentConfig.games.rush_royale.player_id = document.getElementById("dash-rr-player-id").value.trim();
  currentConfig.games.rush_royale.platform = document.getElementById("dash-rr-platform").value;
  currentConfig.games.rush_royale.enabled = document.getElementById("dash-rr-enabled").checked;

  currentConfig.games.war_robots = currentConfig.games.war_robots || {};
  currentConfig.games.war_robots.player_id = document.getElementById("dash-wr-player-id").value.trim();
  currentConfig.games.war_robots.platform = document.getElementById("dash-wr-platform").value;
  currentConfig.games.war_robots.enabled = document.getElementById("dash-wr-enabled").checked;

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
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentConfig)
    });
    if (!res.ok) throw new Error("Failed to save settings");
    showToast(currentLanguage === "ru" ? "Настройки успешно сохранены!" : "Settings saved successfully!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

document.getElementById("btn-save-settings")?.addEventListener("click", saveFullConfig);

// Two-way sync on dashboard inputs
["dash-rr-player-id", "dash-rr-platform", "dash-rr-enabled", "dash-wr-player-id", "dash-wr-platform", "dash-wr-enabled"].forEach(id => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("change", saveFullConfig);
    if (el.tagName === "INPUT" && el.type === "text") {
      el.addEventListener("blur", saveFullConfig);
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
      const imgUrl = item.image_url || (item.game === "War Robots" ? "https://market.my.games/favicon.ico" : "https://static.my.games/market/images/products/24420.png");

      tr.innerHTML = `
        <td style="color: var(--text-muted); font-size: 12px;">${escapeHtml(item.timestamp || "")}</td>
        <td><b style="color: ${item.game === 'Rush Royale' ? '#c084fc' : '#38bdf8'};">${escapeHtml(item.game)}</b></td>
        <td>
          <img src="${escapeHtml(imgUrl)}" class="history-thumb" alt="Item" onerror="this.src='https://market.my.games/favicon.ico'">
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
  showToast(currentLanguage === "ru" ? "Функция промокодов появится в версии 2.0!" : "Promo codes module coming in v2.0!", "info");
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
  const rrBadge = document.getElementById("rr-cooldown-badge");
  const wrBadge = document.getElementById("wr-cooldown-badge");

  if (rrBadge) {
    if (rrCooldownSec <= 0 || !rrCooldownData?.claimed) {
      rrBadge.innerText = t("ready_to_claim");
      rrBadge.className = "cooldown-badge ready";
    } else {
      const cdStr = formatTime(rrCooldownSec, true);
      rrBadge.innerText = `${t("badge_claimed")} (${t("cooldown_word")}${cdStr})`;
      rrBadge.className = "cooldown-badge claimed";
    }
  }

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
      rrCooldownData = data.rush_royale || null;
      wrCooldownData = data.war_robots || null;
      rrCooldownSec = data.rush_royale?.seconds_left || 0;
      wrCooldownSec = data.war_robots?.seconds_left || 0;
      updateCooldownDisplay();
    }
  } catch (e) {
    console.debug("Cooldown fetch error:", e);
  }
}

setInterval(() => {
  if (rrCooldownSec > 0) rrCooldownSec--;
  if (wrCooldownSec > 0) wrCooldownSec--;
  updateCooldownDisplay();
}, 1000);

// ==========================================================================
//                           ACTIONS: COLLECT & LOGIN
// ==========================================================================

async function triggerCollect(target = "all", forceHead = false) {
  const rrId = document.getElementById("dash-rr-player-id").value.trim();
  const wrId = document.getElementById("dash-wr-player-id").value.trim();
  const rrEnabled = document.getElementById("dash-rr-enabled").checked;
  const wrEnabled = document.getElementById("dash-wr-enabled").checked;

  if (target === "rush_royale" || (target === "all" && rrEnabled)) {
    if (!rrId && target === "rush_royale") {
      showToast(currentLanguage === "ru" ? "Пожалуйста, введите ваш ID в карточке Rush Royale!" : "Please enter your Player ID in Rush Royale card!", "error");
      document.getElementById("dash-rr-player-id").focus();
      return;
    }
  }

  if (target === "war_robots" || (target === "all" && wrEnabled)) {
    if (!wrId && target === "war_robots") {
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
document.getElementById("btn-collect-rr")?.addEventListener("click", () => triggerCollect("rush_royale", false));
document.getElementById("btn-collect-wr")?.addEventListener("click", () => triggerCollect("war_robots", false));

// Action: Login
document.getElementById("btn-launch-login")?.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/action/login?target=all", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "Error");
    showToast(currentLanguage === "ru" ? "Браузер запускается с формой входа MY.GAMES!" : "Browser launching with MY.GAMES login form!", "info");
    document.getElementById("btn-top-finish-login").style.display = "inline-flex";
    document.getElementById("btn-finish-login").style.display = "block";
    document.getElementById("btn-launch-login").style.display = "none";
    document.querySelector('.nav-item[data-tab="console"]')?.click();
  } catch (err) {
    showToast(err.message, "error");
  }
});

async function finishLogin() {
  try {
    const res = await fetch("/api/action/login/finish", { method: "POST" });
    const data = await res.json();
    showToast(currentLanguage === "ru" ? "Сессия сохранена! Авторизация завершена." : "Session saved! Authentication finished.", "success");
    document.getElementById("btn-top-finish-login").style.display = "none";
    document.getElementById("btn-finish-login").style.display = "none";
    document.getElementById("btn-launch-login").style.display = "block";
  } catch (err) {
    showToast(err.message, "error");
  }
}

document.getElementById("btn-top-finish-login")?.addEventListener("click", finishLogin);
document.getElementById("btn-finish-login")?.addEventListener("click", finishLogin);

// Action: Check & Logout Session
document.getElementById("btn-check-session")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-check-session");
  btn.style.opacity = "0.5";
  btn.innerText = "⏳ Checking...";
  try {
    const res = await fetch("/api/session/check");
    const data = await res.json();
    if (data.authenticated) {
      showToast(currentLanguage === "ru" ? "Сессия подтверждена: Аккаунт активен! ✅" : "Session verified: Account is active! ✅", "success");
    } else {
      showToast(currentLanguage === "ru" ? `Сессия недействительна: ${data.reason}` : `Session invalid: ${data.reason}`, "error");
    }
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.style.opacity = "1";
    btn.innerHTML = `<span>🔄</span> <span>${t("btn_check_session")}</span>`;
  }
});

document.getElementById("btn-logout-session")?.addEventListener("click", async () => {
  if (!confirm(currentLanguage === "ru" ? "Вы уверены, что хотите выйти из аккаунта и удалить сохранённую сессию?" : "Are you sure you want to log out and clear the saved session?")) return;
  try {
    const res = await fetch("/api/session/logout", { method: "POST" });
    const data = await res.json();
    showToast(data.message, "info");
  } catch (err) {
    showToast(err.message, "error");
  }
});

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
    showToast(data.daemon_enabled ? (currentLanguage === "ru" ? "Демон включен!" : "Daemon enabled!") : (currentLanguage === "ru" ? "Демон выключен" : "Daemon disabled"), "info");
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
      const sidebarAuth = document.getElementById("sidebar-auth-status");
      const authIcon = document.getElementById("auth-status-icon");
      const authTitle = document.getElementById("auth-status-title");
      const authDesc = document.getElementById("auth-status-desc");
      const daemonPill = document.getElementById("daemon-status-pill");
      const daemonText = document.getElementById("daemon-status-text");

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
        if ((status.current_action || "").toLowerCase().includes("auth")) {
          statusText.innerText = t("status_auth_waiting");
        } else if ((status.current_action || "").toLowerCase().includes("collect")) {
          statusText.innerText = t("status_collecting");
        } else {
          statusText.innerText = status.current_action.toUpperCase();
        }
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
          statusPill.style.background = "rgba(16, 185, 129, 0.1)";
          statusPill.style.borderColor = "rgba(16, 185, 129, 0.25)";
          statusPill.style.color = "#6ee7b7";
          statusText.innerText = t("status_ready");
        }
      }

      // Daemon status
      if (status.daemon_enabled) {
        daemonPill.className = "daemon-pill active";
        if (status.next_daemon_run_in > 0) {
          const totM = Math.floor(status.next_daemon_run_in / 60);
          const h = Math.floor(totM / 60);
          const m = totM % 60;
          const timeStr = h > 0 ? `${h}h ${m}m` : `${m}m`;
          daemonText.innerText = `${t("daemon_on")} (${timeStr})`;
        } else {
          daemonText.innerText = t("daemon_on");
        }
      } else {
        daemonPill.className = "daemon-pill";
        daemonText.innerText = t("daemon_off");
      }

      const isLoggingIn = status.is_running && (status.current_action || "").toLowerCase().includes("auth");
      const topBtnFinish = document.getElementById("btn-top-finish-login");
      const btnFinish = document.getElementById("btn-finish-login");
      const btnLaunch = document.getElementById("btn-launch-login");

      if (topBtnFinish) topBtnFinish.style.display = isLoggingIn ? "inline-flex" : "none";
      if (btnFinish) btnFinish.style.display = isLoggingIn ? "block" : "none";
      if (btnLaunch) btnLaunch.style.display = isLoggingIn ? "none" : "block";

      if (status.has_session) {
        sidebarAuth.innerText = t("status_authed");
        sidebarAuth.style.color = "#10b981";
        authIcon.innerText = "🔓";
        authTitle.innerText = `${currentLanguage === 'ru' ? 'Статус: Аккаунт привязан' : 'Status: Account Linked'} ✅`;
        authTitle.style.color = "#10b981";
        authDesc.innerText = currentLanguage === 'ru' ? "Сессия активна. Коллектор может собирать награды в фоновом режиме." : "Session active. Collector can claim rewards in background.";
      } else {
        sidebarAuth.innerText = t("status_need_auth");
        sidebarAuth.style.color = "#f59e0b";
        authIcon.innerText = "🔒";
        authTitle.innerText = `${currentLanguage === 'ru' ? 'Статус: Требуется вход' : 'Status: Login Required'} ⚠️`;
        authTitle.style.color = "#f59e0b";
        authDesc.innerText = currentLanguage === 'ru' ? "Для получения наград необходимо один раз авторизоваться в магазине MY.GAMES." : "You must log in to MY.GAMES once to claim free rewards.";
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
        miniLog.innerText = `[${lastLog.time}] ${lastLog.message}`;

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
