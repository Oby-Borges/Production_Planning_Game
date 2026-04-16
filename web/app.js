const summaryPanel = document.getElementById("summary-panel");
const strategyPanel = document.getElementById("strategy-panel");
const hybridPanel = document.getElementById("hybrid-panel");
const finalRankingPanel = document.getElementById("final-ranking-panel");
const mpsStagePanel = document.getElementById("mps-stage-panel");
const mrpStagePanel = document.getElementById("mrp-stage-panel");
const requestedAggregatePanel = document.getElementById("requested-aggregate-panel");
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
        <p class="metric-label">Best Final Plan</p>
        <p class="metric-value">${escapeHtml(data.summary.best_strategy)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Final Cost</p>
        <p class="metric-value">${currency.format(data.summary.best_total_cost)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Best Aggregate Plan</p>
        <p class="metric-value">${escapeHtml(data.summary.cheapest_aggregate_plan)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Aggregate Benchmark</p>
        <p class="metric-value">${currency.format(data.summary.cheapest_aggregate_cost)}</p>
      </article>
      <article class="metric-card">
        <p class="metric-label">Selected Aggregate Cost</p>
        <p class="metric-value">${currency.format(data.summary.aggregate_cost)}</p>
      </article>
    </div>
    <div style="margin-top:16px;">${warningsBadge}</div>
  `;
}

function renderStrategies(data) {
  const rows = data.aggregate_stage_summary;
  const maxCost = Math.max(...rows.map((row) => row.total_cost), 1);

  strategyPanel.innerHTML = `
    <h2>Aggregate Stage Summary</h2>
    <div class="strategy-grid">
      ${rows.map((row) => {
        const selected = row.candidate_id === data.summary.cheapest_aggregate_candidate_id ? `<span class="selected-badge">Cheapest Aggregate</span>` : "";
        const feasibleClass = row.aggregate_feasible ? "ok" : "no";
        return `
          <article class="strategy-card">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
              <div>
                <p class="strategy-label">${escapeHtml(row.strategy)}</p>
                <p class="strategy-value">${currency.format(row.total_cost)}</p>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
                <span class="feasible-badge ${feasibleClass}">${row.aggregate_feasible ? "Feasible" : "Infeasible"}</span>
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
            <p class="subtle" style="margin:14px 0 0;">Rank: ${row.aggregate_rank} | ${escapeHtml(row.display_name)} | Initial inventory: ${number.format(row.initial_inventory)}</p>
            <p class="subtle" style="margin:8px 0 0;">Regular hours: ${number.format(row.regular_hours_q1)}, ${number.format(row.regular_hours_q2)}, ${number.format(row.regular_hours_q3)} | Overtime: ${number.format(row.overtime_hours_q1)}, ${number.format(row.overtime_hours_q2)}, ${number.format(row.overtime_hours_q3)}</p>
            <p class="subtle" style="margin:8px 0 0;">Inventory OK: ${row.inventory_constraints_satisfied ? "Yes" : "No"} | Overtime OK: ${row.overtime_constraints_satisfied ? "Yes" : "No"} | Divisibility OK: ${row.divisibility_rules_satisfied ? "Yes" : "No"}</p>
            ${row.warnings ? `<p class="subtle" style="margin-top:10px;color:#a8572d;">${escapeHtml(row.warnings)}</p>` : ""}
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderRequestedAggregate(data) {
  const outcomes = data.requested_aggregate_outcomes;
  const renderCostList = (costs) => `
    <div class="mini-grid">
      <article class="mini-card"><p class="mini-label">Material</p><p class="mini-value">${currency.format(costs.material_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Regular Labor</p><p class="mini-value">${currency.format(costs.regular_labor_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Training</p><p class="mini-value">${currency.format(costs.training_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Relocation</p><p class="mini-value">${currency.format(costs.relocation_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Inventory Holding</p><p class="mini-value">${currency.format(costs.inventory_holding_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Total</p><p class="mini-value">${currency.format(costs.total_cost)}</p></article>
    </div>
  `;

  requestedAggregatePanel.innerHTML = `
    <h2>Requested Aggregate Outcomes</h2>
    <p class="subtle">These two tables follow your simplified aggregate-only instructions exactly: chase and level only, no overtime, no hybrid, no MPS/MRP adjustments.</p>
    <div class="fruit-grid">
      <article class="fruit-card">
        <h3 style="margin:0 0 12px;font-size:1.2rem;">Chase Strategy</h3>
        ${renderTable(["Quarter", "Demand", "Production", "Total Labor Hours", "Ending Inventory"], outcomes.chase.plan_rows)}
        <div style="margin-top:16px;">${renderTable(["Quarter", "Regular Hours", "Overtime Hours"], outcomes.chase.labor_rows)}</div>
        <div style="margin-top:16px;">${renderCostList(outcomes.chase.costs)}</div>
      </article>
      <article class="fruit-card">
        <h3 style="margin:0 0 12px;font-size:1.2rem;">Level Strategy</h3>
        <p class="subtle">Constant production: ${number.format(outcomes.level.constant_production)} units per quarter.</p>
        ${renderTable(["Quarter", "Demand", "Production", "Total Labor Hours", "Ending Inventory"], outcomes.level.plan_rows)}
        <div style="margin-top:16px;">${renderTable(["Quarter", "Regular Hours", "Overtime Hours"], outcomes.level.labor_rows)}</div>
        <div style="margin-top:16px;">${renderCostList(outcomes.level.costs)}</div>
      </article>
    </div>
  `;
}

function renderHybridSelector(data) {
  const hybrid = data.plans.hybrid_benchmark || data.plans.hybrid_1;
  const decisionRows = [
    {
      "Initial Inventory": hybrid.initial_inventory,
      "Regular Hours Q1": hybrid.regular_hours[0],
      "Regular Hours Q2": hybrid.regular_hours[1],
      "Regular Hours Q3": hybrid.regular_hours[2],
      "OT Hours Q1": hybrid.overtime_hours[0],
      "OT Hours Q2": hybrid.overtime_hours[1],
      "OT Hours Q3": hybrid.overtime_hours[2],
    },
  ];
  const resultRows = hybrid.production.map((_, index) => ({
    Quarter: `Q${index + 1}`,
    Demand: hybrid.demand[index],
    Production: hybrid.production[index],
    "Ending Inventory": hybrid.ending_inventory[index],
  }));
  const feasibility = hybrid.feasibility_summary || {};
  const costs = hybrid.cost_breakdown;

  hybridPanel.innerHTML = `
    <h2>Hybrid Selector</h2>
    <p class="subtle">This panel shows the app's bounded feasible-search hybrid aggregate plan using explicit initial inventory, regular hours, and overtime decisions.</p>
    <div class="fruit-grid">
      <article class="fruit-card">
        <h3 style="margin:0 0 12px;font-size:1.2rem;">Decision Variables</h3>
        ${renderTable(["Initial Inventory", "Regular Hours Q1", "Regular Hours Q2", "Regular Hours Q3", "OT Hours Q1", "OT Hours Q2", "OT Hours Q3"], decisionRows)}
      </article>
      <article class="fruit-card">
        <h3 style="margin:0 0 12px;font-size:1.2rem;">Computed Results</h3>
        ${renderTable(["Quarter", "Demand", "Production", "Ending Inventory"], resultRows)}
      </article>
    </div>
    <div class="mini-grid" style="margin-top:16px;">
      <article class="mini-card"><p class="mini-label">Aggregate Feasible</p><p class="mini-value">${feasibility.aggregate_feasible ? "Yes" : "No"}</p></article>
      <article class="mini-card"><p class="mini-label">Inventory OK</p><p class="mini-value">${feasibility.inventory_constraints_satisfied ? "Yes" : "No"}</p></article>
      <article class="mini-card"><p class="mini-label">Overtime OK</p><p class="mini-value">${feasibility.overtime_constraints_satisfied ? "Yes" : "No"}</p></article>
      <article class="mini-card"><p class="mini-label">Divisibility OK</p><p class="mini-value">${feasibility.divisibility_rules_satisfied ? "Yes" : "No"}</p></article>
    </div>
    <div class="mini-grid" style="margin-top:16px;">
      <article class="mini-card"><p class="mini-label">Initial Inventory</p><p class="mini-value">${currency.format(costs.initial_inventory_acquisition_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Material</p><p class="mini-value">${currency.format(costs.material_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Regular Labor</p><p class="mini-value">${currency.format(costs.regular_labor_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Overtime</p><p class="mini-value">${currency.format(costs.overtime_labor_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Training</p><p class="mini-value">${currency.format(costs.training_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Relocation</p><p class="mini-value">${currency.format(costs.relocation_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Holding</p><p class="mini-value">${currency.format(costs.aggregate_inventory_holding_cost)}</p></article>
      <article class="mini-card"><p class="mini-label">Total</p><p class="mini-value">${currency.format(costs.total_cost)}</p></article>
    </div>
  `;
}

function renderFinalRanking(data) {
  const rows = data.final_ranking;
  finalRankingPanel.innerHTML = `
    <h2>Final Ranking</h2>
    <p class="subtle">Only plans that are aggregate-feasible, MPS-feasible, and MRP-feasible are eligible to win.</p>
    ${renderTable(
      ["display_name", "strategy", "aggregate_rank", "aggregate_cost", "mps_feasible", "mrp_feasible", "full_feasible", "setup_cost", "mrp_chosen_cost", "final_total_cost"],
      rows.map((row) => ({
        display_name: row.display_name,
        strategy: row.strategy,
        aggregate_rank: row.aggregate_rank,
        aggregate_cost: currency.format(row.aggregate_cost),
        mps_feasible: row.mps_feasible ? "Yes" : "No",
        mrp_feasible: row.mrp_feasible ? "Yes" : "No",
        full_feasible: row.full_feasible ? "Yes" : "No",
        setup_cost: currency.format(row.setup_cost),
        mrp_chosen_cost: currency.format(row.mrp_chosen_cost),
        final_total_cost: currency.format(row.final_total_cost),
      }))
    )}
  `;
}

function renderMpsStage(data) {
  const rows = data.mps_stage_summary.map((row) => ({
    display_name: row.display_name,
    strategy: row.strategy,
    aggregate_rank: row.aggregate_rank,
    mps_feasible: row.mps_feasible ? "Yes" : "No",
    setup_switches: row.setup_switches,
    setup_cost: currency.format(row.setup_cost),
    warnings: row.warnings.join(" | "),
  }));
  mpsStagePanel.innerHTML = `
    <h2>MPS Stage Summary</h2>
    ${renderTable(["display_name", "strategy", "aggregate_rank", "mps_feasible", "setup_switches", "setup_cost", "warnings"], rows)}
  `;
}

function renderMrpStage(data) {
  const rows = data.mrp_stage_summary.map((row) => ({
    display_name: row.display_name,
    strategy: row.strategy,
    mps_feasible: row.mps_feasible ? "Yes" : "No",
    mrp_feasible: row.mrp_feasible ? "Yes" : "No",
    chosen_mrp_cost: currency.format(row.chosen_mrp_cost),
    fruit_methods: row.fruit_methods.map((item) => `${item.fruit}: ${item.chosen_method}`).join(" | "),
    warnings: row.warnings.join(" | "),
  }));
  mrpStagePanel.innerHTML = `
    <h2>MRP Stage Summary</h2>
    ${renderTable(["display_name", "strategy", "mps_feasible", "mrp_feasible", "chosen_mrp_cost", "fruit_methods", "warnings"], rows)}
  `;
}

function renderAggregate(data) {
  const rows = data.aggregate_best_table || [];
  const headers = ["Quarter", "Demand", "Production", "Regular Hours", "Overtime Hours", "Regular Units", "Overtime Units", "Ending Inventory"];

  aggregatePanel.innerHTML = `
    <h2>Selected Final Plan</h2>
    <p class="subtle">Quarter-level aggregate plan for the lowest-cost candidate that survives all stages.</p>
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
  renderHybridSelector(data);
  renderFinalRanking(data);
  renderMpsStage(data);
  renderMrpStage(data);
  renderRequestedAggregate(data);
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
