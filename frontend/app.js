const API_BASE = window.location.origin;
const EMOTION_CODES = [
  "calm",
  "joy",
  "gratitude",
  "focus",
  "energy",
  "love",
  "sadness",
  "anxiety",
  "anger",
];
const BREATHING_STEPS = [
  { key: "resource.phase.one", duration: 4000, progress: 33 },
  { key: "resource.phase.two", duration: 4000, progress: 66 },
  { key: "resource.phase.three", duration: 5000, progress: 100 },
];
const BREATHING_CYCLES = 3;

const COMPANION_SOURCE_ICONS = {
  template: "💡",
  rule_based: "💡",
  cache: "♻️",
  mini: "⚡",
  turbo: "✨",
  local: "🌱",
};

const COMPANION_CHIPS = [
  { id: "breath", kind: "breathing_hint", labelKey: "companion.quick.breathe", promptKey: "companion.prompt.breathe" },
  { id: "anxiety", kind: "mood_reply", labelKey: "companion.quick.anxiety", promptKey: "companion.prompt.anxiety" },
  { id: "focus", kind: "quick_tip", labelKey: "companion.quick.focus", promptKey: "companion.prompt.focus" },
];

const state = {
  locale: "ru",
  locales: {},
  selectedEmotion: null,
  breathingTimeout: null,
  breathingActive: false,
  breathingCycle: 0,
  breathingStepIndex: 0,
  hapticsAvailable: false,
  user: null,
  authenticated: false,
  analyticsRange: "7d",
  lastEmotionItems: [],
  lastJournalItems: [],
  analyticsSummary: null,
  companion: {
    kind: "quick_tip",
    loading: false,
    lastResponse: null,
  },
};

class AuthError extends Error {}

function telegramReady() {
  if (window.Telegram?.WebApp) {
    try {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
      state.hapticsAvailable = Boolean(window.Telegram.WebApp.HapticFeedback);
    } catch (error) {
      console.warn("Telegram WebApp init failed", error);
    }
  }
  if (!state.hapticsAvailable && "vibrate" in navigator) {
    state.hapticsAvailable = true;
  }
}

function resolveUser() {
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  if (tgUser?.id) {
    state.user = {
      tg_id: Number(tgUser.id),
      username: tgUser.username ?? null,
      firstName: tgUser.first_name ?? null,
    };
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const manualTg = params.get("tg_id");
  if (manualTg) {
    const parsed = Number(manualTg);
    if (!Number.isNaN(parsed)) {
      state.user = { tg_id: parsed, username: null, firstName: null };
      return;
    }
  }
  state.user = null;
}

function t(key, replacements = {}) {
  const dict = state.locales[state.locale] || {};
  const template = dict[key];
  if (!template) {
    return key;
  }
  return Object.entries(replacements).reduce(
    (acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

async function loadLocales() {
  const [ru, en] = await Promise.all([
    fetch("/static/locales/ru.json").then((res) => res.json()),
    fetch("/static/locales/en.json").then((res) => res.json()),
  ]);
  state.locales = { ru, en };
  applyLocale(state.locale);
}

function refreshAuthLocks() {
  document.querySelectorAll('[data-auth-required="true"]').forEach((node) => {
    if (node.getAttribute("data-auth-locked") === "true") {
      node.setAttribute("data-auth-hint", t("dashboard.hintLocked"));
    }
  });
}

function applyLocale(locale) {
  const dict = state.locales[locale];
  if (!dict) return;
  state.locale = locale;
  document.documentElement.lang = locale;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.dataset.i18n;
    if (dict[key]) {
      node.textContent = dict[key];
    }
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const key = node.dataset.i18nPlaceholder;
    if (dict[key]) {
      node.setAttribute("placeholder", dict[key]);
    }
  });
  const switchBtn = document.getElementById("lang-switch");
  if (switchBtn) {
    switchBtn.textContent = dict.switch ?? (locale === "ru" ? "EN" : "RU");
  }
  renderEmotionGrid();
  updateIntensityLabel(document.getElementById("emotion-intensity")?.value ?? 3);
  updateBreathingLabels();
  updateListsPlaceholders();
  renderCompanionChips();
  if (!state.companion.lastResponse) {
    const container = document.getElementById("companion-response");
    if (container) {
      container.textContent = t("companion.noResponse");
      container.classList.add("muted");
    }
  }
  updateCompanionMeta();
  updateUserIndicator();
  refreshAuthLocks();
  updateCompanionAvailability();
}

function toggleLocale() {
  const next = state.locale === "ru" ? "en" : "ru";
  applyLocale(next);
}

function updateUserIndicator() {
  const indicator = document.getElementById("user-indicator");
  if (!indicator) return;
  if (state.user?.username) {
    indicator.textContent = t("user.logged", { username: state.user.username });
  } else if (state.user?.tg_id) {
    indicator.textContent = t("user.loggedAnon", { id: state.user.tg_id });
  } else if (state.authenticated) {
    indicator.textContent = t("user.guest");
  } else {
    indicator.textContent = t("user.guest");
  }
}

function setAuthenticated(value) {
  state.authenticated = value;
  const guest = document.getElementById("dashboard-guest");
  const content = document.getElementById("dashboard-content");
  if (guest) {
    guest.classList.toggle("hidden", value);
  }
  if (content) {
    content.classList.toggle("hidden", !value);
  }
  document.querySelectorAll('[data-auth-required="true"]').forEach((node) => {
    if (value) {
      node.removeAttribute("data-auth-locked");
      node.removeAttribute("data-auth-hint");
    } else {
      node.setAttribute("data-auth-locked", "true");
      node.setAttribute("data-auth-hint", t("dashboard.hintLocked"));
    }
  });
  updateUserIndicator();
  updateCompanionAvailability();
}

function showToast(messageKey, type = "info", { translate = true, replacements = {} } = {}) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  const message = translate ? t(messageKey, replacements) : messageKey;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("toast--visible"));
  setTimeout(() => {
    toast.classList.remove("toast--visible");
    setTimeout(() => toast.remove(), 250);
  }, 2500);
}

function triggerHaptic(intensity = "light") {
  if (!state.hapticsAvailable) {
    return;
  }
  try {
    if (window.Telegram?.WebApp?.HapticFeedback) {
      if (intensity === "medium") {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
      } else {
        window.Telegram.WebApp.HapticFeedback.impactOccurred("light");
      }
    } else if (navigator.vibrate) {
      navigator.vibrate(intensity === "medium" ? 40 : 20);
    }
  } catch (error) {
    console.warn("Haptic feedback failed", error);
  }
}

async function fetchMode() {
  const modeValue = document.getElementById("mode-value");
  const modeReason = document.getElementById("mode-reason");

  try {
    const response = await fetch(`${API_BASE}/api/v1/mode`);
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    const data = await response.json();
    modeValue.textContent = `${data.mode}`.toUpperCase();
    modeValue.dataset.state = data.mode;
    modeReason.textContent = data.reason || "";
    modeReason.classList.toggle("muted", !data.reason);
  } catch (error) {
    console.warn("Failed to fetch mode", error);
    modeValue.textContent = "OFFLINE";
    modeReason.textContent = t("statusOffline");
  }
}

function renderList(container, items = [], mapFn) {
  if (!container) return;
  container.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = t("empty");
    container.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const mapped = mapFn(item);
    const node = document.createElement("div");
    node.className = "list-item";
    const title = document.createElement("h3");
    title.textContent = mapped.title;
    node.appendChild(title);
    if (mapped.body) {
      const body = document.createElement("p");
      body.textContent = mapped.body;
      node.appendChild(body);
    }
    container.appendChild(node);
  });
}

function renderCompanionChips() {
  const container = document.getElementById("companion-chips");
  if (!container) return;
  container.innerHTML = "";
  COMPANION_CHIPS.forEach((chip) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip-button";
    button.dataset.companionChip = chip.id;
    button.dataset.kind = chip.kind;
    const label = t(chip.labelKey);
    button.textContent = label.startsWith("companion") ? chip.id : label;
    button.title = t("companion.chipHint", { label: button.textContent });
    button.addEventListener("click", () => applyCompanionChip(chip));
    if (state.companion.loading || !state.authenticated) {
      button.disabled = true;
    }
    container.appendChild(button);
  });
}

function applyCompanionChip(chip) {
  const textarea = document.getElementById("companion-text");
  if (!textarea) return;
  const prompt = t(chip.promptKey);
  textarea.value = prompt.startsWith("companion") ? "" : prompt;
  state.companion.kind = chip.kind;
  textarea.focus();
  triggerHaptic();
}

function renderEmotionGrid() {
  const container = document.getElementById("emotion-grid");
  if (!container) return;
  container.innerHTML = "";
  EMOTION_CODES.forEach((code) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "emotion-cell";
    if (state.selectedEmotion === code) {
      button.classList.add("emotion-cell--active");
    }
    button.dataset.code = code;
    const label = t(`emotions.options.${code}`);
    button.textContent = label.startsWith("emotions") ? code : label;
    button.addEventListener("click", () => selectEmotion(code));
    container.appendChild(button);
  });
}

function selectEmotion(code) {
  state.selectedEmotion = code;
  document.querySelectorAll(".emotion-cell").forEach((node) => {
    node.classList.toggle("emotion-cell--active", node.dataset.code === code);
  });
  triggerHaptic();
}

function updateIntensityLabel(value) {
  const label = document.getElementById("emotion-intensity-label");
  if (label) {
    label.textContent = t("emotions.intensityLabel", { value });
  }
}

function updateListsPlaceholders() {
  renderList(
    document.getElementById("emotion-list"),
    state.lastEmotionItems || [],
    (item) => {
      const rawLabel = t(`emotions.options.${item.emotion_code}`);
      const label = rawLabel.startsWith("emotions") ? item.emotion_code : rawLabel;
      return {
        title: `${label} • ${item.intensity}/5`,
        body: item.note || "",
      };
    },
  );
  renderList(
    document.getElementById("journal-list"),
    state.lastJournalItems || [],
    (item) => ({
      title: formatDateTime(item.created_at),
      body: item.text,
    }),
  );
}

function updateCompanionAvailability() {
  const locked = !state.authenticated;
  const form = document.getElementById("companion-form");
  const textarea = document.getElementById("companion-text");
  const submit = document.getElementById("companion-submit");
  const clearButton = document.getElementById("companion-clear");
  const lockedBanner = document.getElementById("companion-locked");
  const chipButtons = document.querySelectorAll("[data-companion-chip]");
  const disabled = locked || state.companion.loading;

  if (textarea) textarea.disabled = disabled;
  if (submit) submit.disabled = disabled;
  if (clearButton) clearButton.disabled = disabled;
  if (form) form.setAttribute("aria-disabled", String(disabled));
  chipButtons.forEach((button) => {
    button.disabled = disabled;
  });
  if (lockedBanner) {
    lockedBanner.classList.toggle("hidden", !locked);
  }
  const card = document.getElementById("companion-card");
  if (card) {
    card.classList.toggle("companion--disabled", disabled);
  }
}

function setCompanionLoading(value) {
  state.companion.loading = value;
  const submit = document.getElementById("companion-submit");
  if (submit) {
    submit.classList.toggle("loading", value);
    submit.disabled = value || !state.authenticated;
  }
  const textarea = document.getElementById("companion-text");
  if (textarea) {
    textarea.readOnly = value;
  }
  document
    .querySelectorAll("[data-companion-chip]")
    .forEach((button) => button.classList.toggle("chip-button--loading", value));
  updateCompanionAvailability();
}

function updateCompanionMeta() {
  const meta = document.getElementById("companion-meta");
  const label = document.getElementById("companion-source-label");
  const icon = document.getElementById("companion-source-icon");
  const response = state.companion.lastResponse;
  if (!meta || !label || !icon) return;
  if (!response) {
    meta.classList.add("hidden");
    label.textContent = "";
    icon.textContent = "";
    return;
  }
  const iconSymbol = COMPANION_SOURCE_ICONS[response.source] ?? "💡";
  const sourceLabel = t(`companion.source.${response.source}`);
  const fallback = sourceLabel.startsWith("companion") ? response.source : sourceLabel;
  const parts = [t("companion.sourceLabel", { source: fallback })];
  if (response.cost && response.cost > 0) {
    parts.push(t("companion.cost", { value: response.cost.toFixed(4) }));
  }
  icon.textContent = iconSymbol;
  label.textContent = parts.join(" • ");
  meta.classList.remove("hidden");
}

function renderCompanionResponse(result) {
  const container = document.getElementById("companion-response");
  if (!container) return;
  state.companion.lastResponse = result;
  container.textContent = result?.text ?? t("companion.noResponse");
  container.classList.toggle("muted", !result?.text);
  updateCompanionMeta();
}

function clearCompanionResponse() {
  state.companion.lastResponse = null;
  const container = document.getElementById("companion-response");
  if (container) {
    container.textContent = t("companion.noResponse");
    container.classList.add("muted");
  }
  updateCompanionMeta();
}

async function authFetch(url, options = {}, { requireAuth = true } = {}) {
  const init = { ...options };
  const headers = new Headers(options?.headers || {});
  if (state.user?.tg_id) {
    headers.set("X-Soznai-Tg-Id", String(state.user.tg_id));
  }
  init.headers = headers;
  const response = await fetch(url, init);
  if (response.status === 401 && requireAuth) {
    throw new AuthError("unauthorized");
  }
  return response;
}

async function loadJournal({ limit = 20, silent = false } = {}) {
  try {
    const response = await authFetch(`${API_BASE}/api/v1/journal?limit=${limit}`, {}, { requireAuth: false });
    if (response.status === 401) {
      setAuthenticated(false);
      state.lastJournalItems = [];
      if (!silent) updateListsPlaceholders();
      return [];
    }
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    const payload = await response.json();
    setAuthenticated(true);
    state.lastJournalItems = payload.items ?? [];
    if (!silent) updateListsPlaceholders();
    return state.lastJournalItems;
  } catch (error) {
    if (!silent) {
      console.warn("Unable to load journal", error);
      showToast("toast.network", "error");
    }
    return [];
  }
}

async function loadEmotions({ limit = 20, silent = false } = {}) {
  try {
    const response = await authFetch(`${API_BASE}/api/v1/emotions?limit=${limit}`, {}, { requireAuth: false });
    if (response.status === 401) {
      setAuthenticated(false);
      state.lastEmotionItems = [];
      if (!silent) updateListsPlaceholders();
      return [];
    }
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    const payload = await response.json();
    setAuthenticated(true);
    state.lastEmotionItems = payload.items ?? [];
    if (!silent) updateListsPlaceholders();
    return state.lastEmotionItems;
  } catch (error) {
    if (!silent) {
      console.warn("Unable to load emotions", error);
      showToast("toast.network", "error");
    }
    return [];
  }
}

function setupTabs() {
  const tabs = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".panel");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.target;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      panels.forEach((panel) => panel.classList.toggle("active", panel.id === target));
      if (target === "journal") loadJournal();
      if (target === "emotions") loadEmotions();
      if (target === "dashboard") refreshAnalytics(state.analyticsRange);
      if (target === "companion") {
        const textarea = document.getElementById("companion-text");
        if (textarea && !textarea.disabled) {
          textarea.focus();
        }
      }
    });
  });
}

function updateBreathingLabels() {
  const label = document.getElementById("breathing-progress-label");
  if (label) {
    label.textContent = state.breathingActive
      ? t("resource.progress", { current: state.breathingCycle, total: BREATHING_CYCLES })
      : t("resource.progressIdle", { total: BREATHING_CYCLES });
  }
}

function updateBreathingProgress(percent) {
  const progress = document.getElementById("breathing-progress");
  const container = document.querySelector(".breathing-progress");
  if (progress && container) {
    progress.style.width = `${percent}%`;
    container.setAttribute("aria-valuenow", String(percent));
  }
}

function stopBreathingSequence({ completed }) {
  clearTimeout(state.breathingTimeout);
  state.breathingTimeout = null;
  state.breathingActive = false;
  state.breathingCycle = 0;
  state.breathingStepIndex = 0;
  const button = document.getElementById("breathing-start");
  if (button) {
    button.textContent = t("resource.start");
    button.disabled = false;
  }
  const stepLabel = document.getElementById("breathing-step");
  if (stepLabel) {
    stepLabel.textContent = completed ? t("resource.complete") : t("resource.ready");
  }
  updateBreathingProgress(0);
  updateBreathingLabels();
  if (completed) {
    showToast("resource.completeToast", "success");
    triggerHaptic("medium");
  }
}

function runBreathingStep() {
  if (!state.breathingActive) {
    return;
  }
  if (state.breathingStepIndex >= BREATHING_STEPS.length) {
    if (state.breathingCycle >= BREATHING_CYCLES) {
      stopBreathingSequence({ completed: true });
      return;
    }
    state.breathingStepIndex = 0;
    state.breathingCycle += 1;
    updateBreathingProgress(0);
    updateBreathingLabels();
  }
  const step = BREATHING_STEPS[state.breathingStepIndex];
  state.breathingStepIndex += 1;
  const stepLabel = document.getElementById("breathing-step");
  if (stepLabel) {
    stepLabel.textContent = t(step.key);
  }
  updateBreathingProgress(step.progress);
  if (document.getElementById("breathing-vibration")?.checked) {
    triggerHaptic("medium");
  }
  state.breathingTimeout = window.setTimeout(runBreathingStep, step.duration);
}

function startBreathingSequence() {
  if (state.breathingActive) {
    stopBreathingSequence({ completed: false });
    return;
  }
  state.breathingActive = true;
  state.breathingCycle = 1;
  state.breathingStepIndex = 0;
  const button = document.getElementById("breathing-start");
  if (button) {
    button.textContent = t("resource.stop");
    button.disabled = false;
  }
  updateBreathingProgress(0);
  updateBreathingLabels();
  runBreathingStep();
}

async function handleCompanionSubmit(event) {
  event.preventDefault();
  const textarea = document.getElementById("companion-text");
  if (!textarea) return;
  const text = textarea.value.trim();
  if (!text) {
    showToast("companion.toast.empty", "warning");
    return;
  }

  try {
    setCompanionLoading(true);
    const response = await authFetch(
      `${API_BASE}/api/v1/ai/ask`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Soznai-Locale": state.locale,
        },
        body: JSON.stringify({
          kind: state.companion.kind ?? "quick_tip",
          text,
          locale: state.locale,
        }),
      },
      { requireAuth: true },
    );

    if (response.status === 429) {
      const payload = await response.json().catch(() => null);
      showToast(payload?.detail ?? "companion.toast.rate", "warning", {
        translate: !payload?.detail,
      });
      return;
    }

    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      if (detail?.detail === "over budget") {
        showToast("companion.toast.limit", "warning");
      } else {
        showToast(detail?.detail ?? "companion.toast.error", "error", {
          translate: !detail?.detail,
        });
      }
      return;
    }

    const data = await response.json();
    renderCompanionResponse(data);
    textarea.focus();
    triggerHaptic();
    showToast("companion.toast.success", "success");
  } catch (error) {
    if (error instanceof AuthError) {
      showToast("toast.authRequired", "warning");
    } else {
      console.error("Companion request failed", error);
      showToast("companion.toast.error", "error");
    }
  } finally {
    setCompanionLoading(false);
    updateCompanionAvailability();
  }
}

function handleCompanionClear() {
  const textarea = document.getElementById("companion-text");
  if (textarea) {
    textarea.value = "";
  }
  state.companion.kind = "quick_tip";
  clearCompanionResponse();
}

async function handleEmotionSubmit(event) {
  event.preventDefault();
  if (!state.selectedEmotion) {
    showToast("toast.selectEmotion", "warning");
    return;
  }
  const intensity = Number(document.getElementById("emotion-intensity").value);
  const note = document.getElementById("emotion-note").value.trim();

  try {
    const response = await authFetch(
      `${API_BASE}/api/v1/emotions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          emotion_code: state.selectedEmotion,
          intensity,
          note: note || undefined,
          source: "mini-app",
        }),
      },
      { requireAuth: true },
    );
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      showToast(detail?.detail ?? "toast.error", "error", { translate: !detail?.detail });
      return;
    }
    await response.json();
    showToast("toast.saved", "success");
    triggerHaptic();
    document.getElementById("emotion-note").value = "";
    await refreshAnalytics(state.analyticsRange, { silent: true });
    await loadEmotions();
  } catch (error) {
    if (error instanceof AuthError) {
      showToast("toast.authRequired", "warning");
      return;
    }
    console.error("Emotion save failed", error);
    showToast("toast.network", "error");
  }
}

async function handleJournalSubmit(event) {
  event.preventDefault();
  const text = document.getElementById("journal-text").value.trim();
  if (text.length < 10) {
    showToast("toast.journalHint", "warning");
    return;
  }
  try {
    const response = await authFetch(
      `${API_BASE}/api/v1/journal`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source: "mini-app" }),
      },
      { requireAuth: true },
    );
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      showToast(detail?.detail ?? "toast.error", "error", { translate: !detail?.detail });
      return;
    }
    await response.json();
    document.getElementById("journal-text").value = "";
    showToast("toast.saved", "success");
    triggerHaptic();
    await refreshAnalytics(state.analyticsRange, { silent: true });
    await loadJournal();
  } catch (error) {
    if (error instanceof AuthError) {
      showToast("toast.authRequired", "warning");
      return;
    }
    console.error("Journal save failed", error);
    showToast("toast.network", "error");
  }
}

async function sendJournalToBot() {
  const text = document.getElementById("journal-text").value.trim();
  if (text.length < 3) {
    showToast("toast.journalHint", "warning");
    return;
  }
  try {
    const response = await fetch(`${API_BASE}/webhook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        update_id: Date.now(),
        message: { message_id: Date.now(), text, chat: { id: Date.now() } },
      }),
    });
    if (response.status === 401) {
      showToast("toast.botProtected", "warning");
      return;
    }
    if (response.status === 503) {
      showToast("toast.botOffline", "warning");
      return;
    }
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      showToast(detail?.detail ?? "toast.error", "error", { translate: !detail?.detail });
      return;
    }
    const payload = await response.json();
    showToast(payload.response ?? t("toast.saved"), "success", { translate: false });
    triggerHaptic();
  } catch (error) {
    console.error("Webhook send failed", error);
    showToast("toast.network", "error");
  }
}

function updateRangeButtons() {
  document.querySelectorAll(".range-switch__button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.range === state.analyticsRange);
  });
}

function setChartEmpty(chartId, emptyId, isEmpty) {
  const empty = document.getElementById(emptyId);
  if (empty) {
    empty.classList.toggle("hidden", !isEmpty);
  }
  const canvas = document.getElementById(chartId);
  if (canvas) {
    canvas.classList.toggle("chart--empty", isEmpty);
  }
}

function drawLineChart(canvas, points) {
  if (!canvas) return;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const values = points.filter((p) => typeof p.value === "number");
  if (!values.length) {
    ctx.restore();
    return;
  }
  const margin = 24;
  const chartWidth = width - margin * 2;
  const chartHeight = height - margin * 2;
  const maxValue = 5;
  const count = points.length;
  const step = count > 1 ? chartWidth / (count - 1) : 0;

  ctx.beginPath();
  ctx.moveTo(margin, margin + chartHeight);
  points.forEach((point, index) => {
    const x = margin + step * index;
    const value = typeof point.value === "number" ? point.value : null;
    const y = value === null ? margin + chartHeight : margin + chartHeight * (1 - value / maxValue);
    if (value === null) {
      ctx.lineTo(x, margin + chartHeight);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.strokeStyle = "rgba(77, 123, 255, 0.9)";
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.fillStyle = "rgba(77, 123, 255, 0.2)";
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = margin + step * index;
    const value = typeof point.value === "number" ? point.value : null;
    const y = value === null ? margin + chartHeight : margin + chartHeight * (1 - value / maxValue);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.lineTo(margin + step * (count - 1), margin + chartHeight);
  ctx.lineTo(margin, margin + chartHeight);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

function drawBarChart(canvas, items) {
  if (!canvas) return;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  if (!items.length) {
    ctx.restore();
    return;
  }

  const margin = 32;
  const chartWidth = width - margin * 2;
  const chartHeight = height - margin * 2;
  const maxValue = Math.max(...items.map((item) => item.count));
  const gap = 24;
  const barWidth = (chartWidth - gap * (items.length - 1)) / items.length;

  items.forEach((item, index) => {
    const x = margin + index * (barWidth + gap);
    const barHeight = maxValue ? (item.count / maxValue) * chartHeight : 0;
    const y = margin + chartHeight - barHeight;
    const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
    gradient.addColorStop(0, "rgba(77, 123, 255, 0.9)");
    gradient.addColorStop(1, "rgba(108, 205, 255, 0.6)");
    ctx.fillStyle = gradient;
    ctx.fillRect(x, y, barWidth, barHeight);
  });

  ctx.restore();
}

function renderTopEmotions(items) {
  const container = document.getElementById("metric-top-emotions");
  if (!container) return;
  container.innerHTML = "";
  if (!items.length) {
    container.classList.add("muted");
    container.textContent = t("dashboard.noData");
    return;
  }
  container.classList.remove("muted");
  items.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const rawLabel = t(`emotions.options.${item.code}`);
    const label = rawLabel.startsWith("emotions") ? item.code : rawLabel;
    chip.textContent = `${label} • ${item.count}`;
    container.appendChild(chip);
  });
}

function formatDateTime(value) {
  if (!value) {
    return t("dashboard.lastNone");
  }
  const date = new Date(value);
  const locale = state.locale === "ru" ? "ru-RU" : "en-US";
  return date.toLocaleString(locale, {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short",
  });
}

function renderSummary(summary) {
  const streakNode = document.getElementById("metric-streak");
  const entriesNode = document.getElementById("metric-entries");
  const moodNode = document.getElementById("metric-mood");
  const lastNode = document.getElementById("metric-last");
  streakNode.textContent = summary?.streak_days ?? 0;
  entriesNode.textContent = summary?.entries_count ?? 0;
  moodNode.textContent = summary?.mood_avg ? Number(summary.mood_avg).toFixed(2) : t("dashboard.lastNone");
  lastNode.textContent = summary?.last_entry_ts ? formatDateTime(summary.last_entry_ts) : t("dashboard.lastNone");
  renderTopEmotions(summary?.top_emotions ?? []);
}

function computeDailyPoints(emotions, rangeDays) {
  const dailyMap = new Map();
  emotions.forEach((item) => {
    const key = item.created_at.slice(0, 10);
    const current = dailyMap.get(key) ?? { total: 0, count: 0 };
    current.total += item.intensity;
    current.count += 1;
    dailyMap.set(key, current);
  });

  const points = [];
  const today = new Date();
  for (let offset = rangeDays - 1; offset >= 0; offset -= 1) {
    const day = new Date(today);
    day.setHours(0, 0, 0, 0);
    day.setDate(today.getDate() - offset);
    const key = day.toISOString().slice(0, 10);
    const entry = dailyMap.get(key);
    points.push({
      label: key,
      value: entry && entry.count ? entry.total / entry.count : null,
    });
  }
  return points;
}

async function refreshAnalytics(range = state.analyticsRange, { silent = false } = {}) {
  state.analyticsRange = range;
  updateRangeButtons();
  const rangeDays = range === "30d" ? 30 : 7;
  const rangeLabel = document.getElementById("line-chart-range");
  if (rangeLabel) {
    rangeLabel.textContent = t("dashboard.rangeLabel", { days: rangeDays });
  }

  try {
    const summaryResponse = await authFetch(`${API_BASE}/api/v1/analytics/summary?range=${range}`);
    if (!summaryResponse.ok) {
      throw new Error(`status ${summaryResponse.status}`);
    }
    const summary = await summaryResponse.json();
    setAuthenticated(true);
    state.analyticsSummary = summary;
    renderSummary(summary);
  } catch (error) {
    if (error instanceof AuthError) {
      setAuthenticated(false);
      state.analyticsSummary = null;
      renderSummary(null);
      setChartEmpty("line-chart", "line-chart-empty", true);
      setChartEmpty("bar-chart", "bar-chart-empty", true);
      return;
    }
    console.error("Analytics load failed", error);
    if (!silent) {
      showToast("dashboard.analyticsError", "error");
    }
    return;
  }

  const limit = range === "30d" ? 120 : 60;
  const [emotionItems] = await Promise.all([
    loadEmotions({ limit, silent: true }),
    loadJournal({ limit, silent: true }),
  ]);

  updateListsPlaceholders();

  const points = computeDailyPoints(emotionItems, rangeDays);
  const hasMoodData = points.some((point) => typeof point.value === "number");
  setChartEmpty("line-chart", "line-chart-empty", !hasMoodData);
  if (hasMoodData) {
    drawLineChart(document.getElementById("line-chart"), points);
  }

  const topEmotions = state.analyticsSummary?.top_emotions ?? [];
  setChartEmpty("bar-chart", "bar-chart-empty", !topEmotions.length);
  if (topEmotions.length) {
    drawBarChart(document.getElementById("bar-chart"), topEmotions);
  }
}

function setupRangeSwitch() {
  document.querySelectorAll(".range-switch__button").forEach((button) => {
    button.addEventListener("click", () => {
      const { range } = button.dataset;
      if (range && range !== state.analyticsRange) {
        refreshAnalytics(range);
      }
    });
  });
}

function setupCompanion() {
  renderCompanionChips();
  const form = document.getElementById("companion-form");
  if (form) {
    form.addEventListener("submit", handleCompanionSubmit);
  }
  const clearButton = document.getElementById("companion-clear");
  if (clearButton) {
    clearButton.addEventListener("click", handleCompanionClear);
  }
  const textarea = document.getElementById("companion-text");
  if (textarea) {
    textarea.addEventListener("input", () => {
      if (!textarea.value.trim()) {
        state.companion.kind = "quick_tip";
        if (!state.companion.lastResponse) {
          const container = document.getElementById("companion-response");
          if (container) {
            container.textContent = t("companion.noResponse");
            container.classList.add("muted");
          }
        }
      }
    });
  }
  updateCompanionAvailability();
}

function initEvents() {
  document.getElementById("lang-switch").addEventListener("click", toggleLocale);
  document.getElementById("breathing-start").addEventListener("click", startBreathingSequence);
  document.getElementById("emotion-form").addEventListener("submit", handleEmotionSubmit);
  document.getElementById("journal-form").addEventListener("submit", handleJournalSubmit);
  document.getElementById("journal-send").addEventListener("click", sendJournalToBot);
  document.getElementById("emotion-intensity").addEventListener("input", (event) => {
    updateIntensityLabel(event.target.value);
  });
  setupRangeSwitch();
  setupCompanion();
}

async function bootstrap() {
  telegramReady();
  await loadLocales();
  resolveUser();
  updateUserIndicator();
  setupTabs();
  initEvents();
  fetchMode();
  await Promise.all([loadEmotions({ silent: true }), loadJournal({ silent: true })]);
  await refreshAnalytics(state.analyticsRange, { silent: true });
  setInterval(fetchMode, 15000);
}

bootstrap().catch((error) => {
  console.error("SoznAi init failed", error);
});
