async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {"X-Requested-With": "webui"},
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${url} ${response.status}`);
  }
  return response.json();
}

function statusClass(status) {
  if (["failed", "disabled", "rolled_back"].includes(status)) {
    return "status status-danger";
  }
  return "status";
}

function renderTaskRows(table, items) {
  const tbody = table.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = items.map((task) => `
    <tr>
      <td><a href="/tasks/${task.task_id}">${task.task_id}</a></td>
      <td>${task.business_context ?? ""}</td>
      <td>${task.host ?? ""}</td>
      <td><span class="${statusClass(task.status)}">${task.status}</span></td>
      <td>${task.url_count ?? 0}</td>
      <td>${task.raw_count ?? 0}</td>
      <td>${task.created_by ?? "—"}</td>
    </tr>
  `).join("");
}

function renderBars(target, labels, values) {
  const max = Math.max(...values, 1);
  target.innerHTML = values.map((value, index) => {
    const height = Math.max(8, Math.round((value / max) * 180));
    const label = labels[index] ?? "";
    return `<div class="bar" title="${label}: ${value}" style="height:${height}px"></div>`;
  }).join("") || "<p class='empty'>暂无时序数据。</p>";
}

async function hydrateTaskTables() {
  const tables = document.querySelectorAll('[data-api-table="tasks"]');
  if (!tables.length) return;
  const data = await fetchJson("/api/tasks");
  tables.forEach((table) => renderTaskRows(table, data.items));
  const summary = document.querySelector("[data-monitor-summary]");
  if (summary) {
    const running = data.items.filter((i) => i.status === "running").length;
    const completed = data.items.filter((i) => i.status === "completed").length;
    const failed = data.items.filter((i) => ["failed", "disabled"].includes(i.status)).length;
    summary.querySelector("[data-summary-running]").textContent = running;
    summary.querySelector("[data-summary-completed]").textContent = completed;
    summary.querySelector("[data-summary-failed]").textContent = failed;
  }
}

async function hydrateTimeseries() {
  const charts = document.querySelectorAll("[data-timeseries-task]");
  for (const chart of charts) {
    const taskId = chart.dataset.timeseriesTask;
    const data = await fetchJson(`/api/tasks/${taskId}/timeseries`);
    renderBars(chart, data.labels, data.series[0]?.values ?? []);
  }
}

async function hydrateStatusChart() {
  const target = document.querySelector("[data-status-chart]");
  if (!target) return;
  const data = await fetchJson("/api/tasks");
  const counts = new Map();
  for (const task of data.items) {
    counts.set(task.status, (counts.get(task.status) ?? 0) + 1);
  }
  const labels = Array.from(counts.keys());
  const values = labels.map((label) => counts.get(label));
  renderBars(target, labels, values);
}

function bindCancelButtons() {
  document.querySelectorAll("[data-cancel-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskId = button.dataset.cancelTask;
      button.disabled = true;
      await fetchJson(`/api/tasks/${taskId}/cancel`, {method: "POST"});
      window.location.reload();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  hydrateTaskTables().catch(console.error);
  hydrateTimeseries().catch(console.error);
  hydrateStatusChart().catch(console.error);
  bindCancelButtons();
});
