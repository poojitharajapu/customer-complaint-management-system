/**
 * Vanilla JavaScript client for the existing FastAPI service.
 * Views call only routes present in backend/routers; empty states are API-derived.
 */

const API_BASE_URL = "http://127.0.0.1:8000";
const API = `${API_BASE_URL}/api/v1`;
const state = { view: "dashboard", complaintPage: 1, complaintSearch: "", customerSearch: "", complaints: [], customers: [], agents: [] };
const root = document.getElementById("view-root");
const modal = document.getElementById("modal");

const VIEW_META = {
  dashboard: ["Overview", "SERVICE SNAPSHOT", "Monitor customer issues, service health, and team activity."],
  complaints: ["Complaints", "CASE MANAGEMENT", "Review and manage customer-reported issues."],
  customers: ["Customers", "CUSTOMER DIRECTORY", "Find customer records and keep contact details current."],
  agents: ["Agents", "SUPPORT TEAM", "Manage support agent records and active status."],
  assignments: ["Assignments", "CASE ROUTING", "Assign and reassign complaints to the right support team."],
  messages: ["Messages", "CONVERSATIONS", "Review and add messages to complaint threads."],
  slas: ["SLA Monitoring", "SERVICE LEVELS", "Track response deadlines, pauses, and escalations."],
  resolutions: ["Resolutions", "CASE OUTCOMES", "Record a resolution, reopen a case, and review prior attempts."],
  feedback: ["Customer Feedback", "VOICE OF CUSTOMER", "Review post-closure surveys and satisfaction metrics."],
};

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response;
  try {
    response = await fetch(`${API}${path}`, { ...options, headers });
  } catch (error) {
    throw new Error(`Could not reach the API at ${API_BASE_URL}. Start the backend and check its readiness.`);
  }
  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : null;
    const message = Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail;
    throw new Error(message || `Request failed (${response.status}).`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function formatDate(value, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(date);
}

function badge(value) {
  const text = String(value || "Unknown");
  const key = text.toLowerCase().replaceAll(" ", "-");
  const className = ["critical", "high", "medium", "low", "closed", "resolved", "active", "open", "pending", "running", "breached", "reopened"].includes(key) ? key : "";
  return `<span class="badge ${className}">${escapeHtml(text)}</span>`;
}

function heading(view, actions = "") {
  const [title, eyebrow, description] = VIEW_META[view];
  document.getElementById("page-crumb").textContent = title;
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div><div class="heading-actions">${actions}</div></div>`;
}

function loading(message = "Loading live data…") {
  root.innerHTML = `<div class="loading-state"><span class="spinner"></span><span>${escapeHtml(message)}</span></div>`;
}

function showError(error, container = root) {
  const node = document.createElement("div");
  node.className = "notice error";
  node.setAttribute("role", "alert");
  node.textContent = error.message || String(error);
  container.prepend(node);
}

function toast(message, kind = "success") {
  const region = document.getElementById("toast-region");
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  region.append(item);
  window.setTimeout(() => item.remove(), 3600);
}

async function checkConnection() {
  const label = document.getElementById("connection-label");
  const dot = document.getElementById("connection-dot");
  const pill = document.querySelector(".api-pill");
  const status = document.getElementById("api-status");
  try {
    await fetch(`${API_BASE_URL}/ready`).then(async (response) => {
      if (!response.ok) throw new Error("Not ready");
      return response.json();
    });
    label.textContent = "API connected"; status.textContent = "online";
    dot.className = "connection-dot online"; pill.className = "api-pill online";
  } catch {
    label.textContent = "API unavailable"; status.textContent = "offline";
    dot.className = "connection-dot offline"; pill.className = "api-pill offline";
  }
}

function emptyState(title, message) {
  return `<div class="empty-state"><div><span class="empty-icon">⌁</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(message)}</p></div></div>`;
}

function metricCard(label, value, note, icon, tone = "") {
  return `<article class="metric-card ${tone}"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${icon}</span></div><div class="metric-value">${escapeHtml(value)}</div><div class="metric-note">${note}</div></article>`;
}

function barRows(entries, colors = {}) {
  const values = Object.entries(entries || {});
  const max = Math.max(1, ...values.map(([, value]) => Number(value) || 0));
  if (!values.length) return emptyState("No records yet", "Counts will appear here when the API has matching records.");
  return `<div class="status-list">${values.map(([label, count]) => {
    const key = label.toLowerCase();
    const color = colors[key] || "var(--blue)";
    return `<div class="bar-row"><span class="bar-label">${escapeHtml(label)}</span><span class="bar-track"><span class="bar-fill" style="display:block;width:${Math.max(count ? 3 : 0, (Number(count) / max) * 100)}%;background:${color}"></span></span><span class="bar-value">${escapeHtml(count)}</span></div>`;
  }).join("")}</div>`;
}

function complaintRows(rows) {
  if (!rows.length) return `<tr><td colspan="7">${emptyState("No complaints found", "Try changing your filters, or register a complaint.")}</td></tr>`;
  return rows.map((item) => `<tr>
    <td><span class="primary-cell">${escapeHtml(item.id)}</span><span class="secondary-cell">${escapeHtml(item.title)}</span></td>
    <td>${escapeHtml(item.customer_id)}</td><td>${escapeHtml(item.category_name)}</td>
    <td>${badge(item.priority)}</td><td>${badge(item.status)}</td><td>${formatDate(item.created_at)}</td>
    <td><button class="table-action" data-action="complaint-detail" data-id="${escapeHtml(item.id)}">View details →</button></td>
  </tr>`).join("");
}

async function renderDashboard() {
  loading();
  try {
    const [summary, latest] = await Promise.all([api("/dashboard/summary"), api("/complaints?page=1&page_size=6")]);
    const statuses = summary.complaints_by_status || {};
    const priorities = summary.complaints_by_priority || {};
    root.innerHTML = `${heading("dashboard", `<span class="date-chip">◷ &nbsp;Live database metrics</span>`)}
      <section class="metric-grid">
        ${metricCard("Total complaints", summary.total_complaints ?? 0, "All recorded cases", "▤")}
        ${metricCard("Open complaints", summary.open_complaints ?? 0, "Awaiting completion", "◷", "tone-amber")}
        ${metricCard("Resolved & closed", summary.resolved_closed_complaints ?? 0, `${Number(summary.total_complaints || 0) ? (summary.resolved_closed_complaints / summary.total_complaints * 100).toFixed(1) : "0.0"}% of total`, "✓", "tone-green")}
        ${metricCard("Critical priority", priorities.Critical ?? 0, "Cases needing urgent attention", "!", "tone-red")}
        ${metricCard("SLA breaches", summary.sla_breach_count ?? 0, `${Number(summary.sla_compliance_percent || 0).toFixed(1)}% SLA compliance`, "◴", "tone-teal")}
      </section>
      <section class="dashboard-grid">
        <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Complaint status</h2><p class="panel-subtitle">Current cases grouped by workflow state</p></div><button class="text-link" data-nav="complaints">View complaints →</button></div><div class="panel-body">${barRows(statuses, { "closed": "var(--green)", "resolved": "var(--green)", "reopened": "var(--purple)", "pending customer": "var(--amber)", "pending vendor": "var(--amber)" })}</div></article>
        <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Priority overview</h2><p class="panel-subtitle">Active and completed cases by priority</p></div></div><div class="panel-body">${barRows(priorities, { critical: "var(--red)", high: "#e59050", medium: "#d4ad45", low: "var(--green)" })}</div></article>
      </section>
      <section class="dashboard-bottom">
        <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Recently updated complaints</h2><p class="panel-subtitle">Latest records returned by the service</p></div><button class="text-link" data-nav="complaints">All complaints →</button></div>
          <div class="table-scroll"><table><thead><tr><th>Complaint</th><th>Customer</th><th>Category</th><th>Priority</th><th>Status</th><th></th></tr></thead><tbody>${complaintRows(latest.items || [])}</tbody></table></div></article>
        <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Service quality</h2><p class="panel-subtitle">Outcome and customer feedback</p></div></div><div class="panel-body"><div class="detail-list">
          <div class="detail-item"><label>Average resolution</label><span>${Number(summary.average_resolution_time_hours || 0).toFixed(2)} hrs</span></div>
          <div class="detail-item"><label>Reopened cases</label><span>${escapeHtml(summary.reopened_complaint_count ?? 0)}</span></div>
          <div class="detail-item"><label>Customer satisfaction</label><span>${Number(summary.customer_satisfaction_average || 0).toFixed(2)} / 5</span></div>
          <div class="detail-item"><label>Refund total</label><span>$${Number(summary.refund_total || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></div>
        </div><button class="btn btn-secondary btn-small" data-nav="feedback">View feedback</button></div></article>
      </section>`;
  } catch (error) { root.innerHTML = heading("dashboard") + `<div class="panel panel-section">${emptyState("Dashboard unavailable", "The dashboard could not load from the API.")}</div>`; showError(error); }
}

function complaintTablePage(data) {
  const pages = Math.max(1, data.pages || 1);
  return `<article class="panel"><div class="toolbar"><div class="toolbar-left"><label class="search-box"><span>⌕</span><input id="complaint-search" placeholder="Search complaint ID, title, or customer" value="${escapeHtml(state.complaintSearch)}"></label>
      <select class="filter-select" id="complaint-status"><option value="">All statuses</option>${["New", "Assigned", "In Progress", "Pending Customer", "Pending Vendor", "Resolved", "Closed", "Reopened"].map((x) => `<option ${state.statusFilter === x ? "selected" : ""}>${x}</option>`).join("")}</select>
      <select class="filter-select" id="complaint-priority"><option value="">All priorities</option>${["Critical", "High", "Medium", "Low"].map((x) => `<option ${state.priorityFilter === x ? "selected" : ""}>${x}</option>`).join("")}</select>
    </div><div class="toolbar-right"><button class="btn btn-primary" data-action="new-complaint">＋ Register complaint</button></div></div>
    <div class="table-scroll"><table><thead><tr><th>Complaint</th><th>Customer ID</th><th>Category</th><th>Priority</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody>${complaintRows(data.items || [])}</tbody></table></div>
    <div class="table-footer"><span>Showing ${data.items?.length || 0} of ${data.total || 0} complaints</span><div class="pager"><button data-action="complaint-page" data-page="${state.complaintPage - 1}" ${state.complaintPage <= 1 ? "disabled" : ""} aria-label="Previous page">‹</button><span class="date-chip">${state.complaintPage} / ${pages}</span><button data-action="complaint-page" data-page="${state.complaintPage + 1}" ${state.complaintPage >= pages ? "disabled" : ""} aria-label="Next page">›</button></div></div></article>`;
}

async function findComplaints() {
  const term = state.complaintSearch.trim();
  const filters = new URLSearchParams({ page: String(state.complaintPage), page_size: "25" });
  if (state.statusFilter) filters.set("status", state.statusFilter);
  if (state.priorityFilter) filters.set("priority", state.priorityFilter);
  if (!term) return api(`/complaints?${filters}`);
  if (/^CMP-/i.test(term)) {
    try {
      const item = await api(`/complaints/${encodeURIComponent(term)}`);
      const matches = (!state.statusFilter || item.status === state.statusFilter) && (!state.priorityFilter || item.priority === state.priorityFilter);
      return { items: matches ? [item] : [], total: matches ? 1 : 0, page: 1, pages: 1 };
    }
    catch (error) { if (error.message.includes("not found")) return { items: [], total: 0, page: 1, pages: 1 }; throw error; }
  }
  if (/^CUS-/i.test(term)) {
    try {
      const customer = await api(`/customers/${encodeURIComponent(term)}`);
      const result = await api(`/complaints?${new URLSearchParams({ customer_id: customer.id, page_size: "100" })}`);
      const rows = (result.items || []).filter((x) => (!state.statusFilter || x.status === state.statusFilter) && (!state.priorityFilter || x.priority === state.priorityFilter));
      return { items: rows, total: rows.length, page: 1, pages: 1 };
    } catch (error) { if (error.message.includes("not found")) return { items: [], total: 0, page: 1, pages: 1 }; throw error; }
  }
  const [textMatches, customers] = await Promise.all([
    api(`/complaints?${new URLSearchParams({ ...Object.fromEntries(filters), search: term, page_size: "100" })}`),
    api(`/customers?${new URLSearchParams({ search: term, page_size: "100" })}`),
  ]);
  const customerIds = (customers.items || []).slice(0, 25).map((x) => x.id);
  const byCustomer = await Promise.all(customerIds.map((id) => api(`/complaints?${new URLSearchParams({ customer_id: id, page_size: "100" })}`)));
  const unique = new Map();
  [...(textMatches.items || []), ...byCustomer.flatMap((page) => page.items || [])].forEach((row) => unique.set(row.id, row));
  const rows = [...unique.values()].filter((x) => (!state.statusFilter || x.status === state.statusFilter) && (!state.priorityFilter || x.priority === state.priorityFilter));
  return { items: rows, total: rows.length, page: 1, pages: 1 };
}

async function renderComplaints() {
  loading();
  try { const data = await findComplaints(); root.innerHTML = heading("complaints", `<span class="date-chip">${data.total} matching</span>`) + complaintTablePage(data); }
  catch (error) { root.innerHTML = heading("complaints") + `<div class="panel panel-section">${emptyState("Complaints unavailable", "Could not load complaint records.")}</div>`; showError(error); }
}

async function openComplaintDetail(id) {
  setModal("Complaint details", id, `<div class="loading-state"><span class="spinner"></span>Loading complaint…</div>`);
  try {
    const [item, history] = await Promise.all([api(`/complaints/${encodeURIComponent(id)}`), api(`/complaints/${encodeURIComponent(id)}/history`)]);
    setModal(`${item.id}`, item.title, `<div class="detail-list">
      <div class="detail-item"><label>Customer</label><span>${escapeHtml(item.customer_id)}</span></div><div class="detail-item"><label>Category</label><span>${escapeHtml(item.category_name)}</span></div>
      <div class="detail-item"><label>Priority</label><span>${badge(item.priority)}</span></div><div class="detail-item"><label>Status</label><span>${badge(item.status)}</span></div>
      <div class="detail-item"><label>Channel</label><span>${escapeHtml(item.channel)}</span></div><div class="detail-item"><label>Created</label><span>${formatDate(item.created_at, true)}</span></div>
      <div class="detail-item detail-wide"><label>Description</label><span>${escapeHtml(item.description)}</span></div>
    </div><div class="panel-section"><h3>Update complaint details</h3><form id="complaint-update-form" data-id="${escapeHtml(item.id)}" class="form-grid">
      <div class="field full"><label for="update-title">Title</label><input id="update-title" name="title" required maxlength="255" value="${escapeHtml(item.title)}"></div>
      <div class="field full"><label for="update-description">Description</label><textarea id="update-description" name="description" required>${escapeHtml(item.description)}</textarea></div>
      <div class="field"><label for="update-channel">Channel</label><select id="update-channel" name="channel">${["Web", "Email", "Phone", "Chat", "Mobile"].map((x) => `<option ${x === item.channel ? "selected" : ""}>${x}</option>`).join("")}</select></div>
      <div class="field full"><div class="form-actions"><button class="btn btn-primary">Save changes</button></div></div>
    </form></div><div class="panel-section"><h3>Complaint history</h3>${history.length ? `<div class="timeline">${history.map((h) => `<div class="timeline-item"><span class="timeline-rail"><i class="timeline-dot"></i></span><div><div class="timeline-title">${escapeHtml(h.from_status || "Submitted")} → ${escapeHtml(h.to_status)}</div><div class="timeline-meta">${formatDate(h.changed_at, true)} · ${escapeHtml(h.changed_by)}${h.reason ? ` · ${escapeHtml(h.reason)}` : ""}</div></div></div>`).join("")}</div>` : emptyState("No history", "No status events were returned.")}</div>`);
  } catch (error) { setModal(id, "Complaint details", `<div class="notice error">${escapeHtml(error.message)}</div>`); }
}

async function renderCustomers() {
  loading();
  try {
    const params = new URLSearchParams({ page: "1", page_size: "50" });
    if (state.customerSearch) params.set("search", state.customerSearch);
    const result = await api(`/customers?${params}`);
    state.customers = result.items || [];
    root.innerHTML = `${heading("customers", `<button class="btn btn-primary" data-action="new-customer">＋ Add customer</button>`)}<article class="panel">
      <div class="toolbar"><div class="toolbar-left"><label class="search-box"><span>⌕</span><input id="customer-search" value="${escapeHtml(state.customerSearch)}" placeholder="Search name, email, or company"></label></div><div class="toolbar-right"><span class="date-chip">${result.total || 0} records</span></div></div>
      <div class="table-scroll"><table><thead><tr><th>Customer</th><th>Email</th><th>Company</th><th>Tier</th><th>Status</th><th>Vulnerable</th><th></th></tr></thead><tbody>${state.customers.length ? state.customers.map((x) => `<tr><td><span class="primary-cell">${escapeHtml(x.first_name)} ${escapeHtml(x.last_name)}</span><span class="secondary-cell">${escapeHtml(x.id)}</span></td><td>${escapeHtml(x.email)}</td><td>${escapeHtml(x.company_name || "—")}</td><td>${escapeHtml(x.tier)}</td><td>${badge(x.status)}</td><td>${x.is_vulnerable ? "Yes" : "No"}</td><td><button class="table-action" data-action="edit-customer" data-id="${escapeHtml(x.id)}">Edit</button></td></tr>`).join("") : `<tr><td colspan="7">${emptyState("No customers found", "Customer records will appear here when available.")}</td></tr>`}</tbody></table></div>
      <div class="table-footer"><span>Showing ${state.customers.length} of ${result.total || 0} customers</span><span>Use search to narrow the directory.</span></div></article>`;
  } catch (error) { root.innerHTML = heading("customers") + `<div class="panel panel-section">${emptyState("Customer directory unavailable", "Could not load customer records.")}</div>`; showError(error); }
}

function customerForm(customer = {}) {
  return `<form id="customer-form" data-id="${escapeHtml(customer.id || "")}" class="form-grid">
    <div class="field"><label>First name</label><input name="first_name" required maxlength="100" value="${escapeHtml(customer.first_name || "")}"></div>
    <div class="field"><label>Last name</label><input name="last_name" required maxlength="100" value="${escapeHtml(customer.last_name || "")}"></div>
    <div class="field full"><label>Email</label><input name="email" type="email" required maxlength="255" value="${escapeHtml(customer.email || "")}"></div>
    <div class="field"><label>Phone</label><input name="phone" maxlength="30" value="${escapeHtml(customer.phone || "")}"></div>
    <div class="field"><label>Company</label><input name="company_name" maxlength="150" value="${escapeHtml(customer.company_name || "")}"></div>
    <div class="field"><label>Tier</label><select name="tier">${["Standard", "Premium", "Enterprise", "VIP"].map((x) => `<option ${x === (customer.tier || "Standard") ? "selected" : ""}>${x}</option>`).join("")}</select></div>
    <div class="field"><label>Status</label><select name="status">${["Active", "Inactive", "Suspended"].map((x) => `<option ${x === (customer.status || "Active") ? "selected" : ""}>${x}</option>`).join("")}</select></div>
    <div class="field full"><label><input style="width:auto;min-height:0" name="is_vulnerable" type="checkbox" ${customer.is_vulnerable ? "checked" : ""}> Mark as vulnerable customer</label></div>
    <div class="field full"><div class="form-actions"><button type="button" class="btn btn-secondary" data-action="close-modal">Cancel</button><button class="btn btn-primary">${customer.id ? "Save changes" : "Create customer"}</button></div></div>
  </form>`;
}

async function openCustomerForm(id = null) {
  let customer = {};
  if (id) { try { customer = await api(`/customers/${encodeURIComponent(id)}`); } catch (error) { toast(error.message, "error"); return; } }
  setModal(id ? "Update customer" : "New customer", id || "Customer details", customerForm(customer));
}

async function renderAgents() {
  loading();
  try {
    const data = await api("/agents?page=1&page_size=100");
    state.agents = data.items || [];
    root.innerHTML = `${heading("agents", `<button class="btn btn-primary" data-action="new-agent">＋ Add agent</button>`)}<article class="panel"><div class="toolbar"><span class="date-chip">${data.total || 0} agent records</span><span class="field-hint">Availability and skills are not persisted by the current API schema.</span></div>
      <div class="table-scroll"><table><thead><tr><th>Agent</th><th>Email</th><th>Team</th><th>Role</th><th>Ticket capacity</th><th>Status</th></tr></thead><tbody>${state.agents.length ? state.agents.map((x) => `<tr><td><span class="primary-cell">${escapeHtml(x.first_name)} ${escapeHtml(x.last_name)}</span><span class="secondary-cell">${escapeHtml(x.id)}</span></td><td>${escapeHtml(x.email)}</td><td>${escapeHtml(x.team)}</td><td>${escapeHtml(x.role)}</td><td>${escapeHtml(x.max_active_tickets)}</td><td>${badge(x.is_active ? "Active" : "Inactive")}</td></tr>`).join("") : `<tr><td colspan="6">${emptyState("No agents found", "Add an agent when the API is ready to accept one.")}</td></tr>`}</tbody></table></div></article>`;
  } catch (error) { root.innerHTML = heading("agents") + `<div class="panel panel-section">${emptyState("Agent list unavailable", "Could not load agent records.")}</div>`; showError(error); }
}

function agentForm() {
  return `<form id="agent-form" class="form-grid"><div class="field"><label>First name</label><input name="first_name" required maxlength="100"></div><div class="field"><label>Last name</label><input name="last_name" required maxlength="100"></div><div class="field full"><label>Email</label><input name="email" type="email" required maxlength="255"></div><div class="field"><label>Phone</label><input name="phone" maxlength="30"></div><div class="field"><label>Team</label><input name="team" required maxlength="100" placeholder="General Support"></div><div class="field"><label>Role</label><select name="role"><option>Support Agent</option><option>Senior Specialist</option><option>Team Lead</option><option>Manager</option></select></div><div class="field"><label>Ticket capacity</label><input name="max_active_tickets" type="number" min="1" max="500" value="10" required></div><div class="field full"><label><input name="is_active" type="checkbox" checked style="width:auto;min-height:0"> Active</label></div><div class="field full"><div class="form-actions"><button class="btn btn-primary">Create agent</button></div></div></form>`;
}

async function loadCustomerOptions() {
  const data = await api("/customers?page=1&page_size=100");
  return data.items || [];
}

async function loadComplaintOptions() {
  const data = await api("/complaints?page=1&page_size=100");
  return data.items || [];
}

async function renderNewComplaintForm() {
  loading();
  try {
    const customers = await loadCustomerOptions();
    root.innerHTML = `${heading("complaints")}<article class="panel form-panel"><div class="panel-header" style="padding:0 0 18px"><div><h2 class="panel-title">Register a complaint</h2><p class="panel-subtitle">The API classifies the description and applies configured priority rules.</p></div></div>
      ${customers.length ? `<form id="complaint-form" class="form-grid"><div class="field full"><label>Customer</label><input name="customer_id" required list="customer-options" placeholder="Search or enter customer ID"><datalist id="customer-options">${customers.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.first_name)} ${escapeHtml(x.last_name)} · ${escapeHtml(x.email)}</option>`).join("")}</datalist><span class="field-hint">Type an ID directly if the customer is not in the first 100 suggestions.</span></div>
        <div class="field full"><label>Complaint title</label><input name="title" required minlength="3" maxlength="255" placeholder="Briefly describe the issue"></div>
        <div class="field full"><label>Description</label><textarea name="description" required minlength="5" placeholder="Include what happened and when"></textarea></div>
        <div class="field"><label>Channel</label><select name="channel"><option>Web</option><option>Email</option><option>Phone</option><option>Chat</option><option>Mobile</option></select></div>
        <div class="field"><label>Category override <span class="field-hint">Optional</span></label><input name="category_name" maxlength="100" placeholder="Leave blank for automatic classification"></div>
        <div class="field"><label>Order ID <span class="field-hint">Optional</span></label><input name="order_id" placeholder="ORD-2026-000001"></div>
        <div class="field"><label>Product ID <span class="field-hint">Optional</span></label><input name="product_id" placeholder="PRD-000001"></div>
        <div class="field full"><div class="form-actions"><button type="button" class="btn btn-secondary" data-nav="complaints">Cancel</button><button class="btn btn-primary">Submit complaint</button></div></div>
      </form>` : `${emptyState("No customers available", "Create or import customer records before registering a complaint.")}`}</article>`;
  } catch (error) { root.innerHTML = heading("complaints"); showError(error); }
}

async function renderAssignments() {
  loading();
  try {
    const [complaints, agents] = await Promise.all([loadComplaintOptions(), api("/agents?active_only=true&page=1&page_size=100")]);
    state.agents = agents.items || [];
    root.innerHTML = `${heading("assignments")}<section class="section-grid"><article class="panel form-panel"><h2 class="panel-title">Route a complaint</h2><p class="panel-subtitle" style="margin:5px 0 17px">Safety complaints must be assigned to an active Safety team agent.</p>
      ${complaints.length && state.agents.length ? `<form id="assignment-form" class="form-grid"><div class="field full"><label>Complaint</label><select name="complaint_id" required><option value="">Select a complaint</option>${complaints.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)} (${escapeHtml(x.status)})</option>`).join("")}</select></div><div class="field full"><label>Active agent</label><select name="agent_id" required><option value="">Select an agent</option>${state.agents.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.first_name)} ${escapeHtml(x.last_name)} · ${escapeHtml(x.team)}</option>`).join("")}</select></div><div class="field full"><button class="btn btn-primary">Assign / reassign</button></div></form>` : emptyState("Records required", "Create an active agent and a complaint before assigning.")}</article>
      <article class="panel form-panel"><h2 class="panel-title">Assignment history</h2><p class="panel-subtitle" style="margin:5px 0 17px">Select a case to inspect its current and previous owners.</p><form id="assignment-history-form" class="select-row"><select name="complaint_id" required><option value="">Select complaint</option>${complaints.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)}</option>`).join("")}</select><button class="btn btn-secondary">Load</button></form><div id="assignment-history-result" class="panel-section" style="padding-left:0;padding-right:0">${emptyState("No case selected", "Assignment history appears here.")}</div></article></section>`;
  } catch (error) { root.innerHTML = heading("assignments"); showError(error); }
}

async function renderMessages() {
  loading();
  try {
    const [complaints, agents] = await Promise.all([loadComplaintOptions(), api("/agents?active_only=true&page=1&page_size=100")]);
    state.agents = agents.items || [];
    root.innerHTML = `${heading("messages")}<article class="panel form-panel"><h2 class="panel-title">Complaint conversation</h2><p class="panel-subtitle" style="margin:5px 0 16px">Messages are displayed in chronological order.</p><form id="message-load-form" class="select-row"><select name="complaint_id" required><option value="">Select complaint</option>${complaints.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)}</option>`).join("")}</select><button class="btn btn-secondary">Load conversation</button></form><div id="conversation-result" class="panel-section" style="padding-left:0;padding-right:0">${emptyState("Select a complaint", "The conversation will load from the API.")}</div></article>`;
  } catch (error) { root.innerHTML = heading("messages"); showError(error); }
}

async function loadConversation(id) {
  const target = document.getElementById("conversation-result");
  target.innerHTML = `<div class="loading-state"><span class="spinner"></span>Loading messages…</div>`;
  try {
    const [messages, complaint] = await Promise.all([api(`/complaints/${encodeURIComponent(id)}/messages`), api(`/complaints/${encodeURIComponent(id)}`)]);
    const history = messages.length ? `<div class="timeline">${messages.map((m) => `<div class="timeline-item"><span class="timeline-rail"><i class="timeline-dot"></i></span><div><div class="timeline-title">${escapeHtml(m.sender_name)} · ${escapeHtml(m.sender_type)}</div><div class="timeline-meta">${formatDate(m.created_at, true)}</div><p style="margin:7px 0 0;color:#59677b;font-size:11px">${escapeHtml(m.message_body)}</p></div></div>`).join("")}</div>` : emptyState("No messages yet", "Add the first message to this complaint thread.");
    target.innerHTML = `${history}<form id="message-form" class="form-grid" data-complaint="${escapeHtml(id)}" data-customer="${escapeHtml(complaint.customer_id)}" style="margin-top:18px"><div class="field"><label>Sender type</label><select name="sender_type"><option>Customer</option><option>Agent</option></select></div><div class="field"><label>Sender</label><select name="sender_id"><option value="${escapeHtml(complaint.customer_id)}">Customer · ${escapeHtml(complaint.customer_id)}</option>${state.agents.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.first_name)} ${escapeHtml(x.last_name)} · Agent</option>`).join("")}</select></div><div class="field full"><label>Message</label><textarea name="message_body" required maxlength="10000"></textarea></div><div class="field full"><label><input type="checkbox" name="is_internal_note" style="width:auto;min-height:0"> Internal note</label><div class="form-actions"><button class="btn btn-primary">Add message</button></div></div></form>`;
  } catch (error) { target.replaceChildren(); showError(error, target); }
}

async function renderSlas() {
  loading();
  try {
    const [breached, risk, complaints] = await Promise.all([api("/slas/breached"), api("/slas/at-risk?within_minutes=60"), loadComplaintOptions()]);
    root.innerHTML = `${heading("slas")}<section class="metric-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));max-width:520px">${metricCard("Breached SLAs", breached.length, "Returned by the breach endpoint", "!", "tone-red")}${metricCard("At-risk · next hour", risk.length, "Running clocks near deadline", "◷", "tone-amber")}</section>
      <section class="section-grid"><article class="panel"><div class="panel-header"><div><h2 class="panel-title">Breached clocks</h2><p class="panel-subtitle">SLAs explicitly marked as breached</p></div></div>${slaTable(breached)}</article><article class="panel"><div class="panel-header"><div><h2 class="panel-title">At-risk clocks</h2><p class="panel-subtitle">Running clocks due within 60 minutes</p></div></div>${slaTable(risk)}</article></section>
      <article class="panel form-panel" style="margin-top:16px"><h2 class="panel-title">Manage an SLA clock</h2><p class="panel-subtitle" style="margin:5px 0 14px">Pause time is excluded from active SLA time and added to the deadline when resumed.</p><form id="sla-load-form" class="select-row"><select name="complaint_id" required><option value="">Select complaint</option>${complaints.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)}</option>`).join("")}</select><button class="btn btn-secondary">Load SLA</button></form><div id="sla-detail-result" class="panel-section" style="padding-left:0;padding-right:0">${emptyState("Select a complaint", "Clock details and controls appear here.")}</div></article>`;
  } catch (error) { root.innerHTML = heading("slas"); showError(error); }
}

function slaTable(rows) {
  if (!rows.length) return emptyState("No matching SLAs", "No clocks currently match this view.");
  return `<div class="table-scroll"><table><thead><tr><th>Complaint</th><th>State</th><th>Deadline</th><th>Target</th></tr></thead><tbody>${rows.slice(0, 8).map((x) => `<tr><td><button class="table-action" data-action="sla-load" data-id="${escapeHtml(x.complaint_id)}">${escapeHtml(x.complaint_id)}</button></td><td>${badge(x.is_breached ? "Breached" : x.clock_state)}</td><td>${formatDate(x.deadline, true)}</td><td>${escapeHtml(x.target_duration_minutes)} min</td></tr>`).join("")}</tbody></table></div>`;
}

async function loadSla(id) {
  const target = document.getElementById("sla-detail-result");
  target.innerHTML = `<div class="loading-state"><span class="spinner"></span>Loading SLA…</div>`;
  try {
    const [clock, events] = await Promise.all([api(`/slas/${encodeURIComponent(id)}`), api(`/slas/${encodeURIComponent(id)}/events`)]);
    const action = clock.clock_state === "Paused" ? "resume" : clock.clock_state === "Running" ? "pause" : null;
    target.innerHTML = `<div class="detail-list"><div class="detail-item"><label>State</label><span>${badge(clock.is_breached ? "Breached" : clock.clock_state)}</span></div><div class="detail-item"><label>Target</label><span>${clock.target_duration_minutes} minutes</span></div><div class="detail-item"><label>Deadline</label><span>${formatDate(clock.deadline, true)}</span></div><div class="detail-item"><label>Elapsed</label><span>${clock.elapsed_active_minutes} active · ${clock.elapsed_paused_minutes} paused min</span></div></div>
      <div class="inline-actions">${action ? `<button class="btn btn-secondary" data-action="sla-${action}" data-id="${escapeHtml(id)}">${action === "pause" ? "Pause clock" : "Resume clock"}</button>` : ""}<button class="btn btn-secondary" data-action="sla-escalate" data-id="${escapeHtml(id)}">Escalate</button></div>
      <div class="panel-section" style="padding-left:0;padding-right:0"><h3>SLA events</h3>${events.length ? `<div class="timeline">${events.map((x) => `<div class="timeline-item"><span class="timeline-rail"><i class="timeline-dot"></i></span><div><div class="timeline-title">${escapeHtml(x.event_type)}</div><div class="timeline-meta">${formatDate(x.event_time, true)} · ${escapeHtml(x.reason || "")}</div></div></div>`).join("")}</div>` : emptyState("No events", "No clock events were returned.")}</div>`;
  } catch (error) { target.replaceChildren(); showError(error, target); }
}

async function renderResolutions() {
  loading();
  try {
    const [complaints, agents] = await Promise.all([loadComplaintOptions(), api("/agents?active_only=true&page=1&page_size=100")]);
    state.agents = agents.items || [];
    root.innerHTML = `${heading("resolutions")}<section class="section-grid"><article class="panel form-panel"><h2 class="panel-title">Resolution history</h2><form id="resolution-load-form" class="select-row" style="margin-top:14px"><select name="complaint_id" required><option value="">Select complaint</option>${complaints.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)} (${escapeHtml(x.status)})</option>`).join("")}</select><button class="btn btn-secondary">Load</button></form><div id="resolution-history-result" class="panel-section" style="padding-left:0;padding-right:0">${emptyState("Select a complaint", "Resolution attempts appear here.")}</div></article>
      <article class="panel form-panel"><h2 class="panel-title">Record a resolution</h2><p class="panel-subtitle" style="margin:5px 0 15px">Recording a resolution closes the complaint. Refunds require an order and an explicit amount.</p>${complaints.length && state.agents.length ? `<form id="resolution-form" class="form-grid"><div class="field full"><label>Complaint</label><select name="complaint_id" required><option value="">Select complaint</option>${complaints.map((x) => `<option value="${escapeHtml(x.id)}" data-order="${escapeHtml(x.order_id || "")}">${escapeHtml(x.id)} · ${escapeHtml(x.title)} (${escapeHtml(x.status)})</option>`).join("")}</select></div><div class="field"><label>Resolving agent</label><select name="resolved_by_agent_id" required>${state.agents.map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.first_name)} ${escapeHtml(x.last_name)}</option>`).join("")}</select></div><div class="field"><label>Resolution type</label><select id="resolution-type" name="resolution_type"><option>Explanation Provided</option><option>Refund</option><option>Replacement</option><option>Configuration Fix</option><option>Credit Issued</option><option>Bug Fix</option><option>Account Update</option></select></div><div class="field"><label>Root cause</label><input name="root_cause" required maxlength="255"></div><div class="field"><label>Refund amount</label><input id="refund-amount" name="refund_amount" type="number" min="0.01" step="0.01"><span class="field-hint" id="refund-hint">Only used for Refund; a linked order is required.</span></div><div class="field full"><label>Action taken</label><textarea name="action_taken" required></textarea></div><div class="field full"><label>Customer notes</label><textarea name="customer_notes"></textarea></div><div class="field full"><div class="form-actions"><button class="btn btn-primary">Record and close</button></div></div></form>` : emptyState("Records required", "An active agent and complaint are needed to record a resolution.")}</article></section>
      <article class="panel form-panel" style="margin-top:16px"><h2 class="panel-title">Reopen a closed complaint</h2><form id="reopen-form" class="select-row" style="margin-top:13px"><select name="complaint_id" required><option value="">Select closed complaint</option>${complaints.filter((x) => x.status === "Closed").map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)}</option>`).join("")}</select><input name="reason" required minlength="3" placeholder="Why is the case reopening?"><button class="btn btn-secondary">Reopen</button></form></article>`;
  } catch (error) { root.innerHTML = heading("resolutions"); showError(error); }
}

async function loadResolutionHistory(id) {
  const target = document.getElementById("resolution-history-result");
  target.innerHTML = `<div class="loading-state"><span class="spinner"></span>Loading history…</div>`;
  try {
    const [items, complaint] = await Promise.all([api(`/complaints/${encodeURIComponent(id)}/resolutions`), api(`/complaints/${encodeURIComponent(id)}`)]);
    target.innerHTML = `<p class="panel-subtitle">Current status: ${badge(complaint.status)}</p>${items.length ? `<div class="timeline">${items.map((x) => `<div class="timeline-item"><span class="timeline-rail"><i class="timeline-dot"></i></span><div><div class="timeline-title">Attempt ${x.attempt_number} · ${escapeHtml(x.resolution_type)}</div><div class="timeline-meta">${formatDate(x.resolved_at, true)} · ${escapeHtml(x.resolved_by_agent_id)}</div><p style="margin:6px 0 0;color:#68768a;font-size:10px">${escapeHtml(x.action_taken)}</p></div></div>`).join("")}</div>` : emptyState("No resolutions yet", "This complaint has no recorded resolution attempts.")}`;
  } catch (error) { target.replaceChildren(); showError(error, target); }
}

async function renderFeedback() {
  loading();
  try {
    const [metrics, surveys, complaints] = await Promise.all([api("/metrics/customer-satisfaction"), api("/surveys"), loadComplaintOptions()]);
    const closed = complaints.filter((item) => item.status === "Closed");
    root.innerHTML = `${heading("feedback")}<section class="metric-grid four">${metricCard("Average satisfaction", `${Number(metrics.average_customer_satisfaction_rating || 0).toFixed(2)} / 5`, "From submitted surveys", "☆", "tone-amber")}${metricCard("Survey responses", metrics.survey_response_count ?? 0, "Post-closure feedback", "▤")}${metricCard("Positive feedback", metrics.positive_feedback_count ?? 0, "Ratings of 4 or 5", "↑", "tone-green")}${metricCard("Negative feedback", metrics.negative_feedback_count ?? 0, "Ratings of 1 or 2", "↓", "tone-red")}</section>
      <article class="panel form-panel" style="margin-bottom:16px"><h2 class="panel-title">Submit customer feedback</h2><p class="panel-subtitle" style="margin:5px 0 14px">The API accepts a survey only after a complaint is closed.</p>${closed.length ? `<form id="survey-form" class="form-grid"><div class="field full"><label>Closed complaint</label><select name="complaint_id" required><option value="">Select complaint</option>${closed.map((x) => `<option value="${escapeHtml(x.id)}" data-customer="${escapeHtml(x.customer_id)}">${escapeHtml(x.id)} · ${escapeHtml(x.title)}</option>`).join("")}</select></div><div class="field"><label>Customer ID</label><input id="survey-customer-id" name="customer_id" readonly required></div><div class="field"><label>Rating</label><select name="rating"><option value="5">5 · Very satisfied</option><option value="4">4 · Satisfied</option><option value="3">3 · Neutral</option><option value="2">2 · Dissatisfied</option><option value="1">1 · Very dissatisfied</option></select></div><div class="field"><label>NPS score</label><input name="nps_score" type="number" min="0" max="10"></div><div class="field"><label>Timeliness (1–5)</label><input name="timeliness_rating" type="number" min="1" max="5"></div><div class="field"><label>Agent helpfulness (1–5)</label><input name="agent_helpfulness_rating" type="number" min="1" max="5"></div><div class="field full"><label>Comments</label><textarea name="feedback_comments" maxlength="5000"></textarea></div><div class="field full"><div class="form-actions"><button class="btn btn-primary">Submit feedback</button></div></div></form>` : emptyState("No closed complaints available", "Close a complaint through the resolution workflow before submitting a survey.")}</article>
      <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Customer surveys</h2><p class="panel-subtitle">Submitted feedback linked to closed complaints</p></div><span class="date-chip">${surveys.length} responses</span></div><div class="table-scroll"><table><thead><tr><th>Complaint</th><th>Customer</th><th>Rating</th><th>NPS</th><th>Satisfaction</th><th>Submitted</th></tr></thead><tbody>${surveys.length ? surveys.map((x) => `<tr><td class="primary-cell">${escapeHtml(x.complaint_id)}</td><td>${escapeHtml(x.customer_id)}</td><td><span class="star-rating">${"★".repeat(x.rating)}${"☆".repeat(5 - x.rating)}</span> ${x.rating}/5</td><td>${escapeHtml(x.nps_score ?? "—")}</td><td>${escapeHtml(x.satisfaction_level)}</td><td>${formatDate(x.submitted_at, true)}</td></tr>`).join("") : `<tr><td colspan="6">${emptyState("No survey responses", "Surveys submitted through the API will appear here.")}</td></tr>`}</tbody></table></div></article>`;
  } catch (error) { root.innerHTML = heading("feedback") + `<div class="panel panel-section">${emptyState("Feedback unavailable", "Could not load surveys or satisfaction metrics.")}</div>`; showError(error); }
}

async function renderView(view = state.view) {
  state.view = view;
  document.querySelectorAll(".nav-link").forEach((node) => node.classList.toggle("is-active", node.dataset.view === view));
  document.getElementById("sidebar").classList.remove("is-open");
  const renderers = { dashboard: renderDashboard, complaints: renderComplaints, customers: renderCustomers, agents: renderAgents, assignments: renderAssignments, messages: renderMessages, slas: renderSlas, resolutions: renderResolutions, feedback: renderFeedback };
  await renderers[view]();
}

function setModal(eyebrow, title, body) {
  document.getElementById("modal-eyebrow").textContent = eyebrow;
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = body;
  if (!modal.open) modal.showModal();
}

function closeModal() { if (modal.open) modal.close(); }

async function withSubmit(button, callback) {
  const original = button.textContent;
  button.disabled = true; button.textContent = "Saving…";
  try { await callback(); }
  catch (error) { showError(error, button.closest("form") || root); }
  finally { button.disabled = false; button.textContent = original; }
}

function formObject(form) {
  const data = new FormData(form);
  return Object.fromEntries(data.entries());
}

function omitEmpty(record) {
  Object.keys(record).forEach((key) => { if (record[key] === "") delete record[key]; });
  return record;
}

async function submitForm(event) {
  const form = event.target;
  const button = form.querySelector("button[type='submit'], button:not([type])");
  if (!button) return;

  if (form.id === "complaint-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = omitEmpty(formObject(form));
      const result = await api("/complaints", { method: "POST", body: JSON.stringify(payload) });
      toast(`Complaint ${result.id} registered`);
      state.complaintPage = 1; await renderView("complaints"); openComplaintDetail(result.id);
    });
  }
  if (form.id === "customer-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = formObject(form); payload.is_vulnerable = form.elements.is_vulnerable.checked;
      const id = form.dataset.id;
      const result = id ? await api(`/customers/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(omitEmpty(payload)) }) : await api("/customers", { method: "POST", body: JSON.stringify(omitEmpty(payload)) });
      closeModal(); toast(id ? "Customer updated" : `Customer ${result.id} created`); await renderCustomers();
    });
  }
  if (form.id === "agent-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = formObject(form); payload.is_active = form.elements.is_active.checked; payload.max_active_tickets = Number(payload.max_active_tickets);
      const result = await api("/agents", { method: "POST", body: JSON.stringify(omitEmpty(payload)) });
      closeModal(); toast(`Agent ${result.id} created`); await renderAgents();
    });
  }
  if (form.id === "complaint-update-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      await api(`/complaints/${encodeURIComponent(form.dataset.id)}`, { method: "PATCH", body: JSON.stringify(formObject(form)) });
      toast("Complaint updated"); await openComplaintDetail(form.dataset.id); await renderComplaints();
    });
  }
  if (form.id === "assignment-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const values = formObject(form); const id = values.complaint_id; delete values.complaint_id;
      await api(`/complaints/${encodeURIComponent(id)}/assignments`, { method: "POST", body: JSON.stringify(values) });
      toast("Complaint assigned"); await renderAssignments();
    });
  }
  if (form.id === "assignment-history-form") {
    event.preventDefault();
    const id = formObject(form).complaint_id;
    try {
      const rows = await api(`/complaints/${encodeURIComponent(id)}/assignments`);
      const target = document.getElementById("assignment-history-result");
      target.innerHTML = rows.length ? `<div class="timeline">${rows.map((x) => `<div class="timeline-item"><span class="timeline-rail"><i class="timeline-dot"></i></span><div><div class="timeline-title">${escapeHtml(x.agent_id)} ${x.is_current ? badge("Active") : ""}</div><div class="timeline-meta">Assignment ${x.sequence_number} · ${formatDate(x.assigned_at, true)}${x.unassigned_at ? ` · ended ${formatDate(x.unassigned_at, true)}` : ""}</div></div></div>`).join("")}</div>` : emptyState("No assignments", "This complaint has not been assigned.");
    } catch (error) { showError(error, document.getElementById("assignment-history-result")); }
  }
  if (form.id === "message-load-form") { event.preventDefault(); await loadConversation(formObject(form).complaint_id); }
  if (form.id === "message-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = formObject(form); payload.is_internal_note = form.elements.is_internal_note.checked;
      await api(`/complaints/${encodeURIComponent(form.dataset.complaint)}/messages`, { method: "POST", body: JSON.stringify(payload) });
      toast("Message added"); await loadConversation(form.dataset.complaint);
    });
  }
  if (form.id === "sla-load-form") { event.preventDefault(); await loadSla(formObject(form).complaint_id); }
  if (form.id === "resolution-load-form") { event.preventDefault(); await loadResolutionHistory(formObject(form).complaint_id); }
  if (form.id === "resolution-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = omitEmpty(formObject(form)); const id = payload.complaint_id; delete payload.complaint_id;
      if (payload.refund_amount) payload.refund_amount = Number(payload.refund_amount);
      await api(`/complaints/${encodeURIComponent(id)}/resolutions`, { method: "POST", body: JSON.stringify(payload) });
      toast("Resolution recorded and complaint closed"); await renderResolutions(); await loadResolutionHistory(id);
    });
  }
  if (form.id === "reopen-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = formObject(form); const id = payload.complaint_id; delete payload.complaint_id;
      payload.reopened_by = "API_OPERATOR";
      await api(`/complaints/${encodeURIComponent(id)}/reopen`, { method: "POST", body: JSON.stringify(payload) });
      toast("Complaint reopened"); await renderResolutions();
    });
  }
  if (form.id === "survey-form") {
    event.preventDefault();
    await withSubmit(button, async () => {
      const payload = formObject(form); const id = payload.complaint_id; delete payload.complaint_id;
      for (const key of ["rating", "nps_score", "timeliness_rating", "agent_helpfulness_rating"]) {
        if (payload[key] === "") delete payload[key]; else if (payload[key] !== undefined) payload[key] = Number(payload[key]);
      }
      await api(`/complaints/${encodeURIComponent(id)}/surveys`, { method: "POST", body: JSON.stringify(omitEmpty(payload)) });
      toast("Customer feedback submitted"); await renderFeedback();
    });
  }
}

document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => renderView(button.dataset.view)));
document.getElementById("view-root").addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-nav]");
  if (nav) { await renderView(nav.dataset.nav); return; }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const { action, id } = button.dataset;
  if (action === "complaint-detail") await openComplaintDetail(id);
  if (action === "new-complaint") await renderNewComplaintForm();
  if (action === "new-customer") setModal("CUSTOMER DIRECTORY", "Create customer", customerForm());
  if (action === "edit-customer") await openCustomerForm(id);
  if (action === "new-agent") setModal("SUPPORT TEAM", "Add agent", agentForm());
  if (action === "close-modal") closeModal();
  if (action === "complaint-page") { state.complaintPage = Number(button.dataset.page); await renderComplaints(); }
  if (action === "sla-load") await loadSla(id);
  if (action === "sla-pause" || action === "sla-resume") {
    try { await api(`/slas/${encodeURIComponent(id)}/${action.slice(4)}`, { method: "POST" }); toast(`SLA ${action.slice(4)}d`); await loadSla(id); }
    catch (error) { showError(error); }
  }
  if (action === "sla-escalate") {
    const reason = window.prompt("Reason for escalation");
    if (reason && reason.trim()) {
      try { await api(`/slas/${encodeURIComponent(id)}/escalate?${new URLSearchParams({ reason })}`, { method: "POST" }); toast("SLA escalation recorded"); await loadSla(id); }
      catch (error) { showError(error); }
    }
  }
});

document.getElementById("view-root").addEventListener("submit", submitForm);
modal.addEventListener("submit", submitForm);
modal.addEventListener("click", (event) => {
  if (event.target.closest('[data-action="close-modal"]')) closeModal();
});
document.getElementById("view-root").addEventListener("change", (event) => {
  if (event.target.id === "complaint-status") state.statusFilter = event.target.value;
  if (event.target.id === "complaint-priority") state.priorityFilter = event.target.value;
  if (event.target.id === "complaint-status" || event.target.id === "complaint-priority") { state.complaintPage = 1; renderComplaints(); }
  if (event.target.name === "sender_type" && event.target.form?.id === "message-form") {
    const sender = event.target.form.elements.sender_id;
    if (event.target.value === "Customer") sender.value = event.target.form.dataset.customer;
    else if (state.agents[0]) sender.value = state.agents[0].id;
  }
  if ((event.target.name === "resolution_type" || event.target.name === "complaint_id") && event.target.form?.id === "resolution-form") {
    const form = event.target.form;
    let isRefund = form.elements.resolution_type.value === "Refund";
    const selected = form.elements.complaint_id.selectedOptions[0];
    const hasOrder = Boolean(selected?.dataset.order);
    if (isRefund && !hasOrder) {
      form.elements.resolution_type.value = "Explanation Provided";
      isRefund = false;
    }
    form.elements.refund_amount.required = isRefund;
    form.elements.refund_amount.disabled = false;
    const hint = document.getElementById("refund-hint");
    if (hint) hint.textContent = isRefund ? (hasOrder ? `Refund is limited to the linked order ${selected.dataset.order}.` : "Select a complaint with a linked order to issue a refund.") : "Only used for Refund; a linked order is required.";
  }
  if (event.target.name === "complaint_id" && event.target.form?.id === "survey-form") {
    document.getElementById("survey-customer-id").value = event.target.selectedOptions[0]?.dataset.customer || "";
  }
});

document.getElementById("view-root").addEventListener("input", (event) => {
  if (event.target.id === "complaint-search") {
    state.complaintSearch = event.target.value;
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.complaintPage = 1; renderComplaints(); }, 320);
  }
  if (event.target.id === "customer-search") {
    state.customerSearch = event.target.value;
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(renderCustomers, 320);
  }
});

document.getElementById("refresh-view").addEventListener("click", () => renderView(state.view));
document.getElementById("mobile-menu").addEventListener("click", () => document.getElementById("sidebar").classList.toggle("is-open"));
document.getElementById("modal-close").addEventListener("click", closeModal);
modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });

checkConnection();
renderView("dashboard");
