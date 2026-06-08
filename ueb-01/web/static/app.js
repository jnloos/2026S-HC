// DigSig debug UI. Groups events by request_id; renders Swagger-styled cards.

const eventsEl = document.getElementById("events");
const emptyEl = document.getElementById("empty-state");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");

// request_id -> { cardEl, request: Event | null, selections: Event[] }
const groups = new Map();

function statusClass(s) {
  if (!s) return "";
  if (s >= 200 && s < 300) return "s2xx";
  if (s >= 400 && s < 500) return "s4xx";
  if (s >= 500) return "s5xx";
  return "";
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function tryPrettyJson(s) {
  if (s == null) return "";
  try {
    const parsed = JSON.parse(s);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return s;
  }
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderCard(group) {
  const req = group.request;
  const sel = group.selections;
  const method = req?.method ?? "···";
  const path = req?.path ?? (sel[0] ? `(variant ${sel[0].variant})` : "(pending)");
  const status = req?.status;
  const duration = req?.duration_ms;
  const variant = req?.variant ?? sel[0]?.variant ?? null;

  const cardEl = group.cardEl;
  const wasOpen = cardEl.classList.contains("open");

  // Reset method-tint class, reapply current one.
  cardEl.classList.remove("method-get", "method-post", "method-put", "method-delete");
  if (method && method !== "···") {
    cardEl.classList.add(`method-${method.toLowerCase()}`);
  }

  cardEl.innerHTML = `
    <div class="card-head">
      <span class="pill ${method === "···" ? "PENDING" : method}">${escapeHtml(method)}</span>
      <span class="path">${escapeHtml(path)}</span>
      ${variant ? `<span class="variant-tag ${variant}">${variant.toUpperCase()}</span>` : ""}
      ${status ? `<span class="status-badge ${statusClass(status)}">${status}</span>` : ""}
      ${duration != null ? `<span class="duration">${duration.toFixed(1)} ms</span>` : ""}
      <span class="caret">▶</span>
    </div>
    <div class="card-body">
      ${renderBody(group)}
    </div>
  `;
  if (wasOpen) cardEl.classList.add("open");

  cardEl.querySelector(".card-head").addEventListener("click", () => {
    cardEl.classList.toggle("open");
  });
}

function renderBody(group) {
  const req = group.request;
  const parts = [];

  parts.push(`
    <div class="meta">
      <span class="request-id">${escapeHtml(group.requestId)}</span>
      ${req ? ` · ${formatTime(req.timestamp)}` : ""}
    </div>
  `);

  for (const sel of group.selections) {
    const variantClass = sel.variant ?? "v2";
    parts.push(`
      <div class="selection-block ${variantClass}">
        <div class="selection-block-title">${(sel.variant || "").toUpperCase()} — Mistral selection</div>
        ${sel.error ? `<div class="section"><div class="section-title">Error</div><div class="error">${escapeHtml(sel.error)}</div></div>` : ""}
        ${sel.chosen_id != null ? `
          <dl class="kv section">
            <dt>chosen_id</dt><dd>${sel.chosen_id}</dd>
            <dt>reasoning</dt><dd>${escapeHtml(sel.reasoning ?? "")}</dd>
          </dl>` : ""}
        ${sel.image_meta ? `
          <div class="section">
            <div class="section-title">Image</div>
            <dl class="kv">
              <dt>hash</dt><dd>${escapeHtml(sel.image_meta.hash)}</dd>
              <dt>mime</dt><dd>${escapeHtml(sel.image_meta.mime)}</dd>
              <dt>size</dt><dd>${sel.image_meta.size_bytes} bytes</dd>
            </dl>
          </div>` : ""}
        ${sel.system_prompt ? `
          <div class="section">
            <div class="section-title">System prompt</div>
            <pre class="code">${escapeHtml(sel.system_prompt)}</pre>
          </div>` : ""}
        ${sel.user_prompt ? `
          <div class="section">
            <div class="section-title">User prompt</div>
            <pre class="code">${escapeHtml(sel.user_prompt)}</pre>
          </div>` : ""}
        ${sel.raw_response ? `
          <div class="section">
            <div class="section-title">Raw response</div>
            <pre class="code dark">${escapeHtml(tryPrettyJson(sel.raw_response))}</pre>
          </div>` : ""}
      </div>
    `);
  }

  if (parts.length === 1) {
    parts.push(`<div class="section"><em>No selection events for this request.</em></div>`);
  }

  return parts.join("");
}

function ensureGroup(requestId) {
  let group = groups.get(requestId);
  if (group) return group;

  const cardEl = document.createElement("div");
  cardEl.className = "card";
  // Newest on top.
  eventsEl.prepend(cardEl);
  group = { cardEl, request: null, selections: [], requestId };
  groups.set(requestId, group);
  emptyEl.classList.add("hidden");
  return group;
}

function handleEvent(ev) {
  const requestId = ev.request_id ?? `orphan-${ev.id}`;
  const group = ensureGroup(requestId);
  const wasNew = !group.request && group.selections.length === 0;

  if (ev.kind === "request") {
    group.request = ev;
  } else if (ev.kind === "selection") {
    group.selections.push(ev);
  }

  renderCard(group);
  if (wasNew) {
    group.cardEl.classList.add("new");
    setTimeout(() => group.cardEl.classList.remove("new"), 700);
  }
}

async function loadBackfill() {
  try {
    const r = await fetch("/debug/recent?limit=200");
    if (!r.ok) return;
    const events = await r.json();
    // Sort by timestamp ascending so the rebuild matches the live order.
    events.sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1));
    for (const ev of events) handleEvent(ev);
  } catch (e) {
    console.warn("backfill failed", e);
  }
}

function connect() {
  const es = new EventSource("/debug/stream");
  es.onopen = () => {
    statusEl.classList.add("live");
    statusText.textContent = "LIVE";
  };
  es.onerror = () => {
    statusEl.classList.remove("live");
    statusText.textContent = "OFFLINE";
  };
  es.onmessage = (msg) => {
    try {
      handleEvent(JSON.parse(msg.data));
    } catch (e) {
      console.warn("bad event", e, msg.data);
    }
  };
}

loadBackfill().then(connect);
