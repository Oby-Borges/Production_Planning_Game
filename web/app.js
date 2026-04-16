const summaryPanel = document.getElementById("summary-panel");
const strategyPanel = document.getElementById("strategy-panel");
const aggregatePanel = document.getElementById("aggregate-panel");
const mpsPanel = document.getElementById("mps-panel");
const mrpPanel = document.getElementById("mrp-panel");
const reportPanel = document.getElementById("report-panel");
const downloadsPanel = document.getElementById("downloads-panel");
const rerunButton = document.getElementById("rerun-button");
const statusText = document.getElementById("status-text");

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const number = new Intl.NumberFormat("en-US");

function setStatus(message) {
  statusText.textContent = message;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? number.format(value) : value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return escapeHtml(value ?? "");
}

function renderSummary(data) {
  const warningsBadge = data.summary.warnings_count
    ? `<span class="warning-badge">${data.summary.warnings_count} warning(s)</span>`
    : `<span class="selected-badge">No warnings</span>`;

  summaryPanel.innerHTML = `
    <h2>Executive View</h2>
    <p class="subtle">Generated ${new Date(data.generated_at).toLocaleString()}</p>
    <div class="metric-grid">
      <article class="metric-card">
        <p class="metric-label">Best Strategy</p>
        <p class="metric-value">${escapeHtml(data.summary.best_strategy)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Planned Cost</p>
        <p class="metric-value">${currency.format(data.summary.best_total_cost)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Setup Cost</p>
        <p class="metric-value">${currency.format(data.summary.setup_cost)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Setup Switches</p>
        <p class="metric-value">${number.format(data.summary.setup_switches)}</p>
      </article>
    </div>
    <div style="margin-top:16px;">${warningsBadge}</div>
  `;
}

function renderStrategies(data) {
  const rows = data.strategy_comparison;
  const maxCost = Math.max(...rows.map((row) => row.total_cost), 1);

  strategyPanel.innerHTML = `
    <h2>Aggregate Strategy Comparison</h2>
    <div class="strategy-grid">
      ${rows.map((row) => {
        const selected = row.strategy === data.best_strategy ? `<span class="selected-badge">Selected</span>` : "";
        const feasibleClass = row.feasible ? "ok" : "no";
        return `
          <article class="strategy-card">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
              <div>
                <p class="strategy-label">${escapeHtml(row.strategy)}</p>
                <p class="strategy-value">${currency.format(row.total_cost)}</p>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
                <span class="feasible-badge ${feasibleClass}">${row.feasible ? "Feasible" : "Infeasible"}</span>
                ${selected}
              </div>
            </div>
            <div class="bar-stack">
              <div class="bar-row">
                <span>Cost</span>
                <div class="bar-track"><div class="bar-fill" style="width:${(row.total_cost / maxCost) * 100}%"></div></div>
                <strong>${currency.format(row.total_cost)}</strong>
              </div>
            </div>
            <p class="subtle" style="margin:14px 0 0;">Initial inventory: ${number.format(row.initial_inventory)} | Regular hours: ${number.format(row.regular_hours_q1)}, ${number.format(row.regular_hours_q2)}, ${number.format(row.regular_hours_q3)}</p>
            ${row.warnings ? `<p class="subtle" style="margin-top:10px;color:#a8572d;">${escapeHtml(row.warnings)}</p>` : ""}
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderAggregate(data) {
  const rows = data.aggregate_tables[data.best_strategy] || [];
  const headers = ["Quarter", "Demand", "Production", "Regular Hours", "Overtime Hours", "Regular Units", "Overtime Units", "Ending Inventory"];

  aggregatePanel.innerHTML = `
    <h2>Best Aggregate Plan</h2>
    <p class="subtle">Quarter-level production and labor plan for the selected strategy.</p>
    ${renderTable(headers, rows)}
  `;
}

function renderMps(data) {
  const rows = data.mps.rows;
  const periods = data.summary.regular_by_period.map((regular, index) => ({
    label: `P${index + 1}`,
    regular,
    overtime: data.summary.overtime_by_period[index],
  }));
  const maxHours = Math.max(...periods.map((item) => item.regular + item.overtime), 1);

  mpsPanel.innerHTML = `
    <h2>MPS and Labor Rhythm</h2>
    <div class="mini-grid">
      <article class="mini-card">
        <p class="mini-label">Periods</p>
        <p class="mini-value">${number.format(rows.length)}</p>
      </article>
      <article class="mini-card">
        <p class="mini-label">Products</p>
        <p class="mini-value">${number.format(Object.keys(data.inputs.products).length)}</p>
      </article>
      <article class="mini-card">
        <p class="mini-label">Overtime Hours</p>
        <p class="mini-value">${number.format(data.summary.overtime_by_period.reduce((sum, value) => sum + value, 0))}</p>
      </article>
    </div>
    <div class="period-bars">
      ${periods.map((item) => `
        <div class="period-row">
          <span class="period-label">${item.label}</span>
          <div class="period-track">
            <div class="period-regular" style="width:${(item.regular / maxHours) * 100}%"></div>
            <div class="period-overtime" style="width:${(item.overtime / maxHours) * 100}%"></div>
          </div>
          <strong>${number.format(item.regular + item.overtime)}h</strong>
        </div>
      `).join("")}
    </div>
    <div style="margin-top:18px;">
      ${renderTable(
        ["Period", "Quarter", "Regular Labor Hours", "Overtime Labor Hours", "Total Labor Hours Used", "Setup Sequence", "Setup Switches", "Feasible Labor?\n"],
        rows
      )}
    </div>
  `;
}

function renderMrp(data) {
  const fruitCards = data.mrp_summary.map((row) => {
    const table = data.mrp_tables[row.fruit];
    const chosenKey = row.chosen_method === "L4L" ? "l4l" : "silver_meal";
    const altKey = chosenKey === "l4l" ? "silver_meal" : "l4l";
    return `
      <article class="fruit-card">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
          <h3 style="margin:0;font-size:1.2rem;">${escapeHtml(row.fruit)}</h3>
          <span class="selected-badge">${escapeHtml(row.chosen_method)}</span>
        </div>
        <p class="subtle">Initial inventory: ${number.format(row.initial_inventory)}</p>
        <div class="mini-grid">
          <article class="mini-card">
            <p class="mini-label">Chosen Cost</p>
            <p class="mini-value">${currency.format(row.chosen_total_cost)}</p>
          </article>
          <article class="mini-card">
            <p class="mini-label">Alternative</p>
            <p class="mini-value">${currency.format(row[`${altKey}_total_cost`] ?? 0)}</p>
          </article>
        </div>
        <div style="margin-top:16px;">
          <p class="mini-label">Chosen Method Snapshot</p>
          ${renderTable(
            ["Period", "Gross Requirements", "Net Requirements", "Planned Order Release", "Planned Order Delivery", "Projected Ending Inventory"],
            table[chosenKey].rows
          )}
        </div>
      </article>
    `;
  }).join("");

  mrpPanel.innerHTML = `
    <h2>MRP Decisions</h2>
    <p class="subtle">Each fruit shows the selected lot-sizing rule and a live table snapshot from the current planning run.</p>
    <div class="fruit-grid">${fruitCards}</div>
  `;
}

function renderReport(data) {
  reportPanel.innerHTML = `
    <h2>Summary Report</h2>
    <pre class="report-box">${escapeHtml(data.summary_report)}</pre>
  `;
}

function renderDownloads(data) {
  downloadsPanel.innerHTML = `
    <h2>Output Files</h2>
    <div class="download-grid">
      ${data.summary.output_files.map((file) => `
        <article class="download-card">
          <a href="/outputs/${encodeURIComponent(file)}" target="_blank" rel="noreferrer">${escapeHtml(file)}</a>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTable(headers, rows) {
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>${headers.map((header) => `<td>${formatValue(row[header])}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDashboard(data) {
  renderSummary(data);
  renderStrategies(data);
  renderAggregate(data);
  renderMps(data);
  renderMrp(data);
  renderReport(data);
  renderDownloads(data);
}

async function loadDashboard(endpoint = "/api/dashboard", method = "GET") {
  rerunButton.disabled = true;
  setStatus(method === "POST" ? "Running planning model..." : "Loading dashboard...");
  try {
    const response = await fetch(endpoint, { method });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    const data = await response.json();
    renderDashboard(data);
    setStatus(`Updated ${new Date(data.generated_at).toLocaleTimeString()}`);
  } catch (error) {
    setStatus(`Unable to load dashboard: ${error.message}`);
  } finally {
    rerunButton.disabled = false;
  }
}

rerunButton.addEventListener("click", () => {
  loadDashboard("/api/run", "POST");
});

loadDashboard();
