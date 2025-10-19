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
  weeklyInsights: [],
  weeklyInsightsRange: 4,
  weeklyInsightsLoading: true,
  weeklyInsightsLoaded: false,
  companion: {
    kind: "quick_tip",
    loading: false,
    lastResponse: null,
  },
};

const lazyChartObservers = new WeakMap();
const CHART_PALETTE = ["#4c78a8", "#f58518", "#72b7b2", "#e45756", "#54a24b"];

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
  renderWeeklyInsights();
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

function clearCanvas(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawLineChart(canvas, points, options = {}) {
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
  const strokeColor = options.color || "#4c78a8";
  const fillColor = options.fill || "rgba(76, 120, 168, 0.25)";

  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.fillStyle = fillColor;
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
    const baseColor = item.color || "#54a24b";
    const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
    gradient.addColorStop(0, baseColor);
    gradient.addColorStop(1, `${baseColor}33`);
    ctx.fillStyle = gradient;
    ctx.fillRect(x, y, barWidth, barHeight);
  });

  ctx.restore();
}

function drawDonutChart(canvas, items) {
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

  const total = items.reduce((acc, item) => acc + item.count, 0);
  if (!total) {
    ctx.restore();
    return;
  }

  const radius = Math.min(width, height) / 2 - 16;
  const centerX = width / 2;
  const centerY = height / 2;
  let startAngle = -Math.PI / 2;

  items.forEach((item) => {
    const sliceAngle = (item.count / total) * Math.PI * 2;
    const endAngle = startAngle + sliceAngle;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);
    ctx.closePath();
    ctx.fillStyle = item.color;
    ctx.fill();
    startAngle = endAngle;
  });

  ctx.globalCompositeOperation = "destination-out";
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius * 0.55, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalCompositeOperation = "source-over";

  ctx.restore();
}

function lazyDraw(canvas, draw) {
  if (!canvas) return;
  const run = () => {
    draw();
    canvas.dataset.lazyReady = "true";
  };
  if (canvas.dataset.lazyReady === "true") {
    run();
    return;
  }
  if ("IntersectionObserver" in window) {
    let observer = lazyChartObservers.get(canvas);
    if (!observer) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            observer.disconnect();
            lazyChartObservers.delete(canvas);
            run();
          }
        });
      }, { rootMargin: "0px 0px 120px 0px" });
      lazyChartObservers.set(canvas, observer);
    }
    observer.observe(canvas);
  } else {
    requestAnimationFrame(run);
  }
}

function setInsightCardLoading(cardId, isLoading) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const skeleton = card.querySelector(".insight-card__skeleton");
  const content = card.querySelector(".insight-card__content");
  if (skeleton) {
    skeleton.classList.toggle("hidden", !isLoading);
  }
  if (content) {
    content.classList.toggle("hidden", isLoading);
  }
}

function formatWeekday(index) {
  const locale = state.locale === "ru" ? "ru-RU" : "en-US";
  const base = new Date(Date.UTC(2023, 0, 2 + index));
  return base.toLocaleDateString(locale, { weekday: "short" });
}

function aggregateDayCounts(items) {
  const totals = Array.from({ length: 7 }, () => 0);
  items.forEach((item) => {
    (item.entries_by_day || []).forEach((entry) => {
      if (typeof entry.day === "number") {
        totals[entry.day] += entry.count ?? 0;
      }
    });
  });
  return totals.map((count, index) => ({
    label: formatWeekday(index),
    count,
    color: "#54a24b",
  }));
}

function aggregateTopEmotions(items) {
  const totals = new Map();
  items.forEach((item) => {
    (item.top_emotions || []).forEach((emotion) => {
      const current = totals.get(emotion.code) || 0;
      totals.set(emotion.code, current + (emotion.count || 0));
    });
  });
  return Array.from(totals.entries())
    .map(([code, count], index) => {
      const rawLabel = t(`emotions.options.${code}`);
      const label = rawLabel.startsWith("emotions.") ? code : rawLabel;
      return {
        code,
        label,
        count,
        color: CHART_PALETTE[index % CHART_PALETTE.length],
      };
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

function renderWeeklyOverview(items) {
  const summaryText = document.getElementById("weekly-summary-text");
  const moodCanvas = document.getElementById("weekly-mood-chart");
  const entriesCanvas = document.getElementById("weekly-entries-chart");
  const habitCurrent = document.getElementById("weekly-habit-current");
  const habitLongest = document.getElementById("weekly-habit-longest");
  const emotionCanvas = document.getElementById("weekly-emotion-donut");
  const emotionList = document.getElementById("weekly-emotion-list");
  const emotionMessage = document.getElementById("weekly-emotion-message");

  if (!items.length) {
    renderWeeklyOverviewEmpty();
    return;
  }

  const chronological = [...items].reverse();
  const latest = items[0];
  const moodPoints = chronological.map((item) => ({
    label: formatWeekRange(item.week_start, item.week_end),
    value: typeof item.mood_avg === "number" ? item.mood_avg : null,
  }));
  const hasMood = moodPoints.some((point) => typeof point.value === "number");
  if (summaryText) {
    summaryText.textContent = t("insights.summaryDescription", {
      mood: formatMoodValue(latest.mood_avg),
      volatility: formatVolatility(latest.mood_volatility),
      entries: latest.entries_count ?? 0,
    });
  }
  if (moodCanvas) {
    if (hasMood) {
      moodCanvas.classList.remove("chart--empty");
      lazyDraw(moodCanvas, () => drawLineChart(moodCanvas, moodPoints));
    } else {
      moodCanvas.classList.add("chart--empty");
      clearCanvas(moodCanvas);
    }
  }

  const dayCounts = aggregateDayCounts(items);
  const hasEntries = dayCounts.some((entry) => entry.count > 0);
  if (habitCurrent) {
    habitCurrent.textContent = latest.days_with_entries ?? 0;
  }
  if (habitLongest) {
    const longest = Math.max(
      0,
      ...items.map((item) => item.longest_streak ?? 0),
    );
    habitLongest.textContent = longest;
  }
  if (entriesCanvas) {
    if (hasEntries) {
      entriesCanvas.classList.remove("chart--empty");
      lazyDraw(entriesCanvas, () => drawBarChart(entriesCanvas, dayCounts));
    } else {
      entriesCanvas.classList.add("chart--empty");
      clearCanvas(entriesCanvas);
    }
  }

  if (emotionList) {
    emotionList.innerHTML = "";
  }
  if (emotionMessage) {
    emotionMessage.classList.add("hidden");
  }
  const emotionData = aggregateTopEmotions(items);
  const hasEmotions = emotionData.some((item) => item.count > 0);
  if (emotionCanvas) {
    if (hasEmotions) {
      emotionCanvas.classList.remove("chart--empty");
      lazyDraw(emotionCanvas, () => drawDonutChart(emotionCanvas, emotionData));
    } else {
      emotionCanvas.classList.add("chart--empty");
      clearCanvas(emotionCanvas);
    }
  }
  if (emotionData.length && emotionList) {
    emotionData.forEach((item) => {
      const li = document.createElement("li");
      li.setAttribute("role", "listitem");
      li.textContent = `${item.label} • ${item.count}`;
      li.style.setProperty("--accent-color", item.color);
      emotionList.appendChild(li);
    });
    emotionList.classList.remove("hidden");
  } else {
    if (emotionList) {
      emotionList.classList.add("hidden");
    }
    if (emotionMessage) {
      emotionMessage.textContent = t("insights.emotionsEmpty");
      emotionMessage.classList.remove("hidden");
    }
  }
}

function renderWeeklyOverviewEmpty() {
  const summaryText = document.getElementById("weekly-summary-text");
  const moodCanvas = document.getElementById("weekly-mood-chart");
  const entriesCanvas = document.getElementById("weekly-entries-chart");
  const habitCurrent = document.getElementById("weekly-habit-current");
  const habitLongest = document.getElementById("weekly-habit-longest");
  const emotionCanvas = document.getElementById("weekly-emotion-donut");
  const emotionList = document.getElementById("weekly-emotion-list");
  const emotionMessage = document.getElementById("weekly-emotion-message");
  if (summaryText) {
    summaryText.textContent = t("insights.summaryEmpty");
  }
  if (habitCurrent) {
    habitCurrent.textContent = "0";
  }
  if (habitLongest) {
    habitLongest.textContent = "0";
  }
  clearCanvas(moodCanvas);
  clearCanvas(entriesCanvas);
  clearCanvas(emotionCanvas);
  moodCanvas?.classList.add("chart--empty");
  entriesCanvas?.classList.add("chart--empty");
  emotionCanvas?.classList.add("chart--empty");
  if (emotionList) {
    emotionList.innerHTML = "";
    emotionList.classList.add("hidden");
  }
  if (emotionMessage) {
    emotionMessage.textContent = t("insights.emotionsEmpty");
    emotionMessage.classList.remove("hidden");
  }
}

function renderWeeklyList(items, container) {
  container.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "insight-item";
    card.setAttribute("role", "listitem");

    const header = document.createElement("div");
    header.className = "insight-item__header";
    const title = document.createElement("h4");
    title.className = "insight-item__title";
    title.textContent = formatWeekRange(item.week_start, item.week_end);
    header.appendChild(title);
    const entriesBadge = document.createElement("span");
    entriesBadge.className = "insight-pill";
    entriesBadge.textContent = t("insights.entries", { count: item.entries_count ?? 0 });
    header.appendChild(entriesBadge);
    card.appendChild(header);

    const stats = document.createElement("div");
    stats.className = "insight-item__stats";
    stats.appendChild(buildInsightStat(t("insights.moodAvgShort"), formatMoodValue(item.mood_avg)));
    stats.appendChild(buildInsightStat(t("insights.volatility"), formatVolatility(item.mood_volatility)));
    stats.appendChild(buildInsightStat(t("insights.daysActive"), item.days_with_entries ?? 0));
    stats.appendChild(buildInsightStat(t("insights.longestStreak"), item.longest_streak ?? 0));
    card.appendChild(stats);

    if (item.top_emotions && item.top_emotions.length) {
      const badges = document.createElement("div");
      badges.className = "insight-item__badges";
      badges.setAttribute("aria-label", t("insights.topEmotions"));
      item.top_emotions.slice(0, 3).forEach((emotion) => {
        const pill = document.createElement("span");
        pill.className = "insight-pill";
        const rawLabel = t(`emotions.options.${emotion.code}`);
        const label = rawLabel.startsWith("emotions.") ? emotion.code : rawLabel;
        pill.textContent = `${label} • ${emotion.count}`;
        badges.appendChild(pill);
      });
      card.appendChild(badges);
    }

    if (item.wordcloud && item.wordcloud.length) {
      const words = document.createElement("div");
      words.className = "insight-item__badges";
      words.setAttribute("aria-label", t("insights.keywordsLabel"));
      item.wordcloud.slice(0, 5).forEach((entry) => {
        const pill = document.createElement("span");
        pill.className = "insight-pill";
        pill.textContent = `${entry.word} • ${entry.count}`;
        words.appendChild(pill);
      });
      card.appendChild(words);
    }

    const summary = document.createElement("p");
    summary.className = "insight-summary";
    summary.textContent = item.summary ?? t("insights.summaryFallback");
    card.appendChild(summary);

    if (item.summary_model) {
      const meta = document.createElement("span");
      meta.className = "muted";
      meta.textContent = t("insights.summarySource", {
        source: item.summary_source ?? item.summary_model,
      });
      card.appendChild(meta);
    }

    container.appendChild(card);
  });
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

function formatWeekRange(start, end) {
  const locale = state.locale === "ru" ? "ru-RU" : "en-US";
  const startDate = new Date(start);
  const endDate = new Date(end);
  const opts = { day: "2-digit", month: "short" };
  return `${startDate.toLocaleDateString(locale, opts)} — ${endDate.toLocaleDateString(locale, opts)}`;
}

function formatMoodValue(value) {
  return typeof value === "number" ? value.toFixed(2) : "–";
}

function formatVolatility(value) {
  return typeof value === "number" ? value.toFixed(2) : "–";
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

function buildInsightStat(label, value) {
  const span = document.createElement("span");
  span.textContent = `${label}: ${value}`;
  return span;
}

function renderWeeklyInsights() {
  const container = document.getElementById("weekly-insights-grid");
  const empty = document.getElementById("weekly-insights-empty");
  const rangeLabel = document.getElementById("weekly-insights-range");
  const summaryCardId = "weekly-summary-card";
  const streakCardId = "weekly-streak-card";
  const emotionsCardId = "weekly-emotions-card";
  const items = state.weeklyInsights ?? [];
  if (!container || !empty || !rangeLabel) {
    return;
  }
  rangeLabel.textContent = t("insights.rangeLabel", { weeks: state.weeklyInsightsRange });
  if (state.weeklyInsightsLoading) {
    setInsightCardLoading(summaryCardId, true);
    setInsightCardLoading(streakCardId, true);
    setInsightCardLoading(emotionsCardId, true);
    empty.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  setInsightCardLoading(summaryCardId, false);
  setInsightCardLoading(streakCardId, false);
  setInsightCardLoading(emotionsCardId, false);

  if (!items.length) {
    empty.classList.remove("hidden");
    renderWeeklyOverviewEmpty();
    container.innerHTML = "";
    return;
  }

  empty.classList.add("hidden");
  renderWeeklyOverview(items);
  renderWeeklyList(items, container);
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
    await loadWeeklyInsights({ range: 4, silent: true }).catch((error) => {
      if (!(error instanceof AuthError)) {
        console.warn("Weekly insights skipped", error);
      }
    });
  } catch (error) {
    if (error instanceof AuthError) {
      setAuthenticated(false);
      state.analyticsSummary = null;
      renderSummary(null);
      setChartEmpty("line-chart", "line-chart-empty", true);
      setChartEmpty("bar-chart", "bar-chart-empty", true);
      state.weeklyInsights = [];
      state.weeklyInsightsLoading = false;
      state.weeklyInsightsLoaded = true;
      renderWeeklyInsights();
      return;
    }
    console.error("Analytics load failed", error);
    if (!silent) {
      showToast("dashboard.analyticsError", "error");
    }
    state.weeklyInsightsLoading = false;
    renderWeeklyInsights();
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

async function loadWeeklyInsights({ range = state.weeklyInsightsRange, silent = false } = {}) {
  state.weeklyInsightsLoading = true;
  state.weeklyInsightsLoaded = false;
  renderWeeklyInsights();
  try {
    const response = await authFetch(
      `${API_BASE}/api/v1/insights/weekly?range=${range}&locale=${state.locale}`,
      {},
      { requireAuth: true },
    );
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    const payload = await response.json();
    state.weeklyInsights = payload.items ?? [];
    state.weeklyInsightsRange = payload.range_weeks ?? range;
    state.weeklyInsightsLoaded = true;
    return state.weeklyInsights;
  } catch (error) {
    if (error instanceof AuthError) {
      state.weeklyInsights = [];
      state.weeklyInsightsLoaded = true;
      if (!silent) {
        showToast("toast.authRequired", "warning");
      }
      throw error;
    }
    console.error("Weekly insights load failed", error);
    if (!silent) {
      showToast("insights.error", "error");
    }
    state.weeklyInsights = [];
    state.weeklyInsightsLoaded = true;
    return [];
  } finally {
    state.weeklyInsightsLoading = false;
    renderWeeklyInsights();
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
