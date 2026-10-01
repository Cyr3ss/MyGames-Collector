// ==========================================================================
// Auto Collect MyGames - Modern Desktop Client
// ==========================================================================

let currentConfig = null;
let lastLogIndex = 0;
let isPolling = true;

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
  });
});

document.getElementById("btn-to-console")?.addEventListener("click", () => {
  document.querySelector('.nav-item[data-tab="console"]')?.click();
});

// Load Config from Backend
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error("Ошибка получения конфигурации");
    currentConfig = await res.json();

    // Populate Settings Fields
    document.getElementById("cfg-interval").value = currentConfig.app?.check_interval_hours || 12;
    document.getElementById("cfg-headless").checked = currentConfig.app?.headless ?? true;
    document.getElementById("cfg-screenshot").checked = currentConfig.app?.screenshot_on_error ?? true;

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

// Synchronize inputs between Dashboard and Settings
document.getElementById("dash-rr-player-id")?.addEventListener("input", (e) => {
  document.getElementById("cfg-rr-player-id").value = e.target.value;
});
document.getElementById("cfg-rr-player-id")?.addEventListener("input", (e) => {
  document.getElementById("dash-rr-player-id").value = e.target.value;
});

document.getElementById("dash-wr-player-id")?.addEventListener("input", (e) => {
  document.getElementById("cfg-wr-player-id").value = e.target.value;
});
document.getElementById("cfg-wr-player-id")?.addEventListener("input", (e) => {
  document.getElementById("dash-wr-player-id").value = e.target.value;
});

document.getElementById("dash-wr-platform")?.addEventListener("change", (e) => {
  document.getElementById("cfg-wr-platform").value = e.target.value;
});
document.getElementById("cfg-wr-platform")?.addEventListener("change", (e) => {
  document.getElementById("dash-wr-platform").value = e.target.value;
});

// Auto-save on blur of ID inputs
["dash-rr-player-id", "dash-wr-player-id", "dash-rr-platform", "dash-wr-platform"].forEach(id => {
  document.getElementById(id)?.addEventListener("blur", () => saveConfig(false));
  document.getElementById(id)?.addEventListener("change", () => saveConfig(false));
});

// Save Config to Backend
async function saveConfig(showNotification = true) {
  if (!currentConfig) return;

  const rrId = (document.getElementById("dash-rr-player-id")?.value || document.getElementById("cfg-rr-player-id")?.value || "").trim();
  const rrPlat = document.getElementById("dash-rr-platform")?.value || "android";
  const wrId = (document.getElementById("dash-wr-player-id")?.value || document.getElementById("cfg-wr-player-id")?.value || "").trim();
  const wrPlat = document.getElementById("dash-wr-platform")?.value || document.getElementById("cfg-wr-platform")?.value || "android";

  const updated = {
    app: {
      ...currentConfig.app,
      check_interval_hours: parseInt(document.getElementById("cfg-interval").value, 10) || 12,
      headless: document.getElementById("cfg-headless").checked,
      screenshot_on_error: document.getElementById("cfg-screenshot").checked
    },
    notifications: {
      telegram: {
        enabled: document.getElementById("cfg-tg-enabled").checked,
        bot_token: document.getElementById("cfg-tg-token").value.trim(),
        chat_id: document.getElementById("cfg-tg-chat").value.trim()
      },
      discord: {
        enabled: document.getElementById("cfg-dc-enabled").checked,
        webhook_url: document.getElementById("cfg-dc-webhook").value.trim()
      }
    },
    games: {
      rush_royale: {
        ...currentConfig.games?.rush_royale,
        enabled: document.getElementById("dash-rr-enabled").checked,
        player_id: rrId,
        platform: rrPlat
      },
      war_robots: {
        ...currentConfig.games?.war_robots,
        enabled: document.getElementById("dash-wr-enabled").checked,
        player_id: wrId,
        platform: wrPlat
      }
    }
  };

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated)
    });
    if (!res.ok) throw new Error("Не удалось сохранить конфигурацию");
    currentConfig = updated;
    if (showNotification) {
      showToast("Настройки успешно сохранены!", "success");
    }
  } catch (err) {
    if (showNotification) showToast(err.message, "error");
  }
}

document.getElementById("btn-save-settings")?.addEventListener("click", () => saveConfig(true));

// Switch triggers on dashboard
document.getElementById("dash-rr-enabled")?.addEventListener("change", () => saveConfig(false));
document.getElementById("dash-wr-enabled")?.addEventListener("change", () => saveConfig(false));

// Actions: Collect
async function triggerCollect(target = "all", forceHead = false) {
  // Always save before collecting
  await saveConfig(false);

  // Validate ID if specific or all
  const rrEnabled = document.getElementById("dash-rr-enabled").checked;
  const rrId = (document.getElementById("dash-rr-player-id").value || "").trim();
  const wrEnabled = document.getElementById("dash-wr-enabled").checked;
  const wrId = (document.getElementById("dash-wr-player-id").value || "").trim();

  if (target === "rush_royale" || (target === "all" && rrEnabled)) {
    if (!rrId) {
      showToast("Пожалуйста, введите ваш игровой ID в карточке Rush Royale!", "error");
      document.getElementById("dash-rr-player-id").focus();
      return;
    }
  }

  if (target === "war_robots" || (target === "all" && wrEnabled && target !== "rush_royale")) {
    if (!wrId && target === "war_robots") {
      showToast("Пожалуйста, введите ваш Pilot ID в карточке War Robots!", "error");
      document.getElementById("dash-wr-player-id").focus();
      return;
    }
  }

  try {
    const res = await fetch(`/api/action/collect?target=${target}&force_head=${forceHead}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "Ошибка запуска");
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
    if (!res.ok) throw new Error(data.message || "Ошибка");
    showToast("Браузер запускается с формой входа MY.GAMES!", "info");
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
    showToast("Сессия сохранена! Авторизация завершена.", "success");
    document.getElementById("btn-top-finish-login").style.display = "none";
    document.getElementById("btn-finish-login").style.display = "none";
    document.getElementById("btn-launch-login").style.display = "block";
  } catch (err) {
    showToast(err.message, "error");
  }
}

document.getElementById("btn-top-finish-login")?.addEventListener("click", finishLogin);
document.getElementById("btn-finish-login")?.addEventListener("click", finishLogin);

// Action: Test Notification
document.getElementById("btn-test-notification")?.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/action/test-notify", { method: "POST" });
    const data = await res.json();
    showToast("Тестовое уведомление отправлено!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
});

// Action: Clear & Copy Logs
document.getElementById("btn-clear-logs")?.addEventListener("click", async () => {
  await fetch("/api/logs/clear", { method: "POST" });
  document.getElementById("terminal-output").innerHTML = "";
  lastLogIndex = 0;
  showToast("Логи очищены", "info");
});

document.getElementById("btn-copy-logs")?.addEventListener("click", () => {
  const terminal = document.getElementById("terminal-output");
  navigator.clipboard.writeText(terminal.innerText).then(() => {
    showToast("Логи скопированы в буфер обмена!", "success");
  });
});

// Status & Logs Polling Loop
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

      if (status.is_running) {
        statusPill.style.background = "rgba(245, 158, 11, 0.15)";
        statusPill.style.borderColor = "rgba(245, 158, 11, 0.4)";
        statusPill.style.color = "#fde047";
        statusText.innerText = status.current_action.toUpperCase();
      } else {
        statusPill.style.background = "rgba(16, 185, 129, 0.1)";
        statusPill.style.borderColor = "rgba(16, 185, 129, 0.25)";
        statusPill.style.color = "#6ee7b7";
        statusText.innerText = "СИСТЕМА ГОТОВА";
      }

      const isLoggingIn = status.is_running && (status.current_action || "").includes("Авторизация");
      const topBtnFinish = document.getElementById("btn-top-finish-login");
      const btnFinish = document.getElementById("btn-finish-login");
      const btnLaunch = document.getElementById("btn-launch-login");

      if (topBtnFinish) topBtnFinish.style.display = isLoggingIn ? "inline-flex" : "none";
      if (btnFinish) btnFinish.style.display = isLoggingIn ? "block" : "none";
      if (btnLaunch) btnLaunch.style.display = isLoggingIn ? "none" : "block";

      if (status.has_session) {
        sidebarAuth.innerText = "Авторизован ✅";
        sidebarAuth.style.color = "#10b981";
        authIcon.innerText = "🔓";
        authTitle.innerText = "Статус: Аккаунт привязан ✅";
        authTitle.style.color = "#10b981";
        authDesc.innerText = "Сессия активна. Коллектор может собирать награды в фоновом режиме.";
      } else {
        sidebarAuth.innerText = "Требуется вход ⚠️";
        sidebarAuth.style.color = "#f59e0b";
        authIcon.innerText = "🔒";
        authTitle.innerText = "Статус: Требуется вход ⚠️";
        authTitle.style.color = "#f59e0b";
        authDesc.innerText = "Для получения наград необходимо один раз авторизоваться в магазине MY.GAMES.";
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

        // Update mini log preview
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
  await loadConfig();
  pollStatusAndLogs();
});
