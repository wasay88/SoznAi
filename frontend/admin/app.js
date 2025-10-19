const state = {
  token: localStorage.getItem("soznai_admin_token") || "",
  charts: {},
};

const toast = document.getElementById("toast");

function showToast(message, kind = "info") {
  toast.textContent = message;
  toast.dataset.kind = kind;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 3000);
}

async function fetchAdmin(path, options = {}) {
  if (!state.token) {
    throw new Error("Требуется токен администратора");
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${state.token}`,
      ...(options.headers || {}),
    },
  });
  if (response.status === 401) {
    showToast("Токен отклонён", "error");
    return null;
  }
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Запрос не выполнен");
  }
  return response.status === 204 ? null : response.json();
}

function renderOverview(data) {
  const container = document.getElementById("overview-metrics");
  const overview = data.overview;
  document.getElementById("soft-limit").value = overview.soft_limit.toFixed(2);
  document.getElementById("hard-limit").value = overview.hard_limit.toFixed(2);
  document.getElementById("mode-select").value = data.overview.mode;
  document.getElementById("batch-toggle").checked = overview.batch_enabled;

  container.innerHTML = `
    <div class="metric">
      <span class="label">Расход сегодня</span>
      <span class="value">$${overview.today_spend.toFixed(3)}</span>
    </div>
    <div class="metric">
      <span class="label">Режим</span>
      <span class="value">${overview.mode} / ${overview.limiter_mode}</span>
    </div>
    <div class="metric">
      <span class="label">Запросы</span>
      <span class="value">${overview.requests}</span>
    </div>
    <div class="metric">
      <span class="label">Tokens (in/out)</span>
      <span class="value">${overview.tokens_in}/${overview.tokens_out}</span>
    </div>
    <div class="metric">
      <span class="label">Cache hit</span>
      <span class="value">${Math.round(overview.cache_hit_rate * 100)}% (${overview.cache_hits})</span>
    </div>
  `;
}

function ensureChart(id, type, options) {
  if (state.charts[id]) {
    state.charts[id].destroy();
  }
  const ctx = document.getElementById(id);
  state.charts[id] = new Chart(ctx, { type, ...options });
}

function renderCharts(data) {
  ensureChart("cost-chart", "line", {
    data: {
      labels: data.cost_per_day.map((item) => item.label),
      datasets: [
        {
          label: "USD",
          data: data.cost_per_day.map((item) => item.value),
          borderColor: "#4b7bec",
          backgroundColor: "rgba(75, 123, 236, 0.2)",
          fill: true,
        },
      ],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });

  ensureChart("tokens-chart", "bar", {
    data: {
      labels: data.tokens_per_model.map((item) => item.label),
      datasets: [
        {
          label: "Tokens",
          data: data.tokens_per_model.map((item) => item.value),
          backgroundColor: "#20bf6b",
        },
      ],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });

  ensureChart("requests-chart", "doughnut", {
    data: {
      labels: data.requests_by_kind.map((item) => item.label),
      datasets: [
        {
          data: data.requests_by_kind.map((item) => item.value),
          backgroundColor: ["#4b7bec", "#a55eea", "#fd9644", "#26de81", "#778ca3"],
        },
      ],
    },
    options: { responsive: true },
  });
}

function renderHistory(items) {
  const body = document.getElementById("history-body");
  body.innerHTML = items
    .map((item) => {
      const tokens = `${item.tokens_in}/${item.tokens_out}`;
      const sourceIcon =
        item.source === "cache"
          ? "♻️"
          : item.source === "turbo"
          ? "✨"
          : item.source === "mini"
          ? "⚡"
          : item.source === "template"
          ? "💡"
          : "🔹";
      return `
        <tr>
          <td>${new Date(item.ts).toLocaleString()}</td>
          <td>${item.model}</td>
          <td>${sourceIcon} ${item.source}</td>
          <td>${item.kind}</td>
          <td>${tokens}</td>
          <td>$${item.usd_cost.toFixed(4)}</td>
          <td>${item.user_hash ?? "—"}</td>
        </tr>
      `;
    })
    .join("");
}

async function refreshDashboard() {
  try {
    const stats = await fetchAdmin("/admin/ai/stats?range=7");
    if (!stats) return;
    renderOverview(stats);
    renderCharts(stats);

    const history = await fetchAdmin("/admin/ai/history?limit=50");
    if (history) {
      renderHistory(history.items);
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindAuthControls() {
  const input = document.getElementById("admin-token");
  input.value = state.token;

  document.getElementById("apply-token").addEventListener("click", () => {
    state.token = input.value.trim();
    if (!state.token) {
      showToast("Введите токен", "error");
      return;
    }
    localStorage.setItem("soznai_admin_token", state.token);
    showToast("Токен сохранён");
    refreshDashboard();
  });

  document.getElementById("clear-token").addEventListener("click", () => {
    state.token = "";
    localStorage.removeItem("soznai_admin_token");
    showToast("Токен очищен", "info");
  });
}

function bindControls() {
  document.getElementById("limits-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = {
        soft: parseFloat(document.getElementById("soft-limit").value),
        hard: parseFloat(document.getElementById("hard-limit").value),
      };
      await fetchAdmin("/admin/ai/limits", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Лимиты обновлены", "success");
      refreshDashboard();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  document.getElementById("update-mode").addEventListener("click", async () => {
    try {
      const mode = document.getElementById("mode-select").value;
      await fetchAdmin("/admin/ai/mode", {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
      showToast(`Режим ${mode} применён`, "success");
      refreshDashboard();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  document.getElementById("stop-gpt").addEventListener("click", async () => {
    try {
      await fetchAdmin("/admin/ai/mode", {
        method: "POST",
        body: JSON.stringify({ mode: "local_only" }),
      });
      showToast("GPT отключён (local)", "success");
      refreshDashboard();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  document.getElementById("batch-toggle").addEventListener("change", async (event) => {
    try {
      await fetchAdmin("/admin/ai/batch", {
        method: "POST",
        body: JSON.stringify({ enabled: event.target.checked }),
      });
      showToast("Настройка батча обновлена", "success");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

bindAuthControls();
bindControls();

if (state.token) {
  refreshDashboard();
}
