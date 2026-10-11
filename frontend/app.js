// Reqnova - frontend (vanilla JS, no build step)
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tbd = (s) => esc(s).replace(/\[(TBD[^\]]*|benefit not stated)\]/g, '<span class="tbd">[$1]</span>');

let mode = "fast";
let lastResult = null;
let activeHistory = null;
let historyItems = [];

// ---------- boot ----------
fetch("/api/health").then((r) => r.json()).then((h) => {
  const el = $("#health");
  const ok = h.llm_key_set && h.parse_key_set;
  el.className = "health " + (ok ? "ok" : "bad");
  el.textContent = ok ? "connected" : "API keys missing in .env";
}).catch(() => { $("#health").textContent = "backend offline"; $("#health").className = "health bad"; });

fetch("/api/samples").then((r) => r.json()).then((list) => {
  const box = $("#samples");
  list.forEach((s) => {
    const b = document.createElement("button");
    b.className = "chip"; b.textContent = s.title;
    b.onclick = () => { $("#input").value = s.text; };
    box.appendChild(b);
  });
});

document.querySelectorAll(".seg button").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".seg button").forEach((x) => x.classList.remove("on"));
  b.classList.add("on"); mode = b.dataset.mode;
});

// Load a saved result for demos/screenshots: /?result=/examples/attendance_result.json
const pre = new URLSearchParams(location.search).get("result");
if (pre) fetch(pre).then((r) => r.json()).then((r) => { if (r.input) $("#input").value = r.input; render(r); });

// ---------- file upload ----------
const drop = $("#drop");
["dragover", "dragenter"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((e) => drop.addEventListener(e, () => drop.classList.remove("over")));
drop.addEventListener("drop", (ev) => { ev.preventDefault(); if (ev.dataTransfer.files[0]) upload(ev.dataTransfer.files[0]); });
$("#file").addEventListener("change", (e) => e.target.files[0] && upload(e.target.files[0]));

async function upload(file) {
  const info = $("#fileinfo");
  info.hidden = false; info.textContent = `Reading ${file.name}…`;
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await fetch("/api/extract", { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "extraction failed");
    $("#input").value = d.text;
    info.textContent = `${file.name} · ${d.pages} page(s)` + (d.warnings.length ? ` · ⚠ ${d.warnings.join(" ")}` : "");
  } catch (e) { info.textContent = `⚠ ${e.message}`; }
}

// ---------- run pipeline (SSE over fetch) ----------
$("#run").onclick = async () => {
  const text = $("#input").value.trim();
  const err = $("#error"); err.hidden = true;
  if (!text) { err.hidden = false; err.textContent = "Paste some customer text first."; return; }
  const btn = $("#run"); btn.disabled = true; btn.textContent = "Analysing…";
  const steps = $("#steps"); steps.hidden = false;
  steps.querySelectorAll("li").forEach((li) => { li.className = ""; li.querySelector(".t")?.remove(); });

  try {
    const resp = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, mode }) });
    const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!chunk.startsWith("data:")) continue;
        const ev = JSON.parse(chunk.slice(5));
        if (ev.type === "step") markStep(ev);
        else if (ev.type === "result") { ev.data.input = text; render(ev.data); activeHistory = ev.data.history_id; loadHistory(); }
        else if (ev.type === "error") { err.hidden = false; err.textContent = ev.message; }
      }
    }
  } catch (e) { err.hidden = false; err.textContent = "Request failed: " + e.message; }
  btn.disabled = false; btn.textContent = "Analyse requirements";
};

function markStep(ev) {
  const li = $(`#steps li[data-step="${ev.step}"]`); if (!li) return;
  li.className = ev.status;
  if (ev.status === "done") {
    const t = document.createElement("span"); t.className = "t";
    t.textContent = `${ev.data.seconds}s${ev.data.repaired ? " · repaired" : ""}${ev.data.fallback ? " · fallback" : ""}`;
    li.querySelector("b").after(t);
  }
}

// ---------- rendering ----------
const srcChips = (ids) => (ids || []).map((i) => `<span class="src" data-src="${esc(i)}">${esc(i)}</span>`).join(" ");
const tag = (cls, label) => `<span class="tag ${esc(cls)}">${esc(label ?? cls)}</span>`;
const section = (title, n, body) => `<div class="sec"><h3>${title}${n != null ? `<span class="count">${n}</span>` : ""}</h3>${body}</div>`;
const none = (msg) => `<p class="hint">${msg}</p>`;

function reqCard(r) {
  return `<div class="card"><div class="row"><span class="rid">${esc(r.id)}</span><span class="rtext">${tbd(r.text)}</span></div>
    <div class="meta">${tag(r.origin)}${tag(r.support)}${r.priority_hint !== "unknown" ? tag("neutral", r.priority_hint) : ""}
    ${r.actor ? tag("neutral", r.actor) : ""} ${srcChips(r.source_ids)}</div>
    ${(r.validation_notes || []).map((n) => `<div class="note">⚠ ${esc(n)}</div>`).join("")}</div>`;
}

function render(r) {
  lastResult = r;
  $("#empty").hidden = true;
  const out = $("#result"); out.hidden = false;
  document.querySelectorAll("#steps li").forEach((li) => { if (!li.className && r.status === "rejected") li.className = "skipped"; });

  if (r.status === "rejected") {
    out.innerHTML = `<div class="rejected"><h2>Not analysed</h2>
      <p>The intake gate classified this input as <b>${esc(r.gate.input_kind)}</b>: ${esc(r.gate.reason)}</p>
      <p class="hint">The system refuses to fabricate requirements from text that doesn't describe software.</p></div>`;
    return;
  }
  const q = r.quality;
  const warns = r.warnings || [];

  out.innerHTML = `
  <div class="rhead"><h2>Requirements draft · ${esc(r.gate.domain || "")}</h2>
    <div class="actions"><button class="ghost" id="dl-md">Download Markdown</button><button class="ghost" id="dl-json">Download JSON</button></div></div>
  <div class="kpis">
    <div class="kpi"><b>${q.requirements}</b><span>requirements</span></div>
    <div class="kpi"><b>${q.cited_pct}%</b><span>cite a source sentence</span></div>
    <div class="kpi"><b>${q.supported_pct}%</b><span>verified as supported</span></div>
    <div class="kpi"><b>${q.flagged}</b><span>flagged by rules</span></div>
    <div class="kpi"><b>${r.missing_information.length}</b><span>gaps found</span></div>
    <div class="kpi"><b>${q.open_questions}</b><span>questions to ask</span></div>
  </div>
  ${warns.length ? `<div class="warnbox"><b>Warnings</b><ul>${warns.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}
  <div class="rgrid"><div>
    ${section("Problem statement", null, `<p class="problem">${tbd(r.problem_statement)}</p>`)}
    ${section("Actors / users", r.actors.length, r.actors.map((a) => `<div class="card"><div class="row"><b>${esc(a.name)}</b><span class="rtext">${esc(a.description)}</span>${srcChips(a.source_ids)}</div></div>`).join(""))}
    ${section("Functional requirements", r.functional_requirements.length, r.functional_requirements.map(reqCard).join("") || none("None."))}
    ${section("Non-functional requirements", r.non_functional_requirements.length, r.non_functional_requirements.map(reqCard).join("") || none("The customer stated no quality requirements - see Missing information."))}
    ${section("User stories & acceptance criteria", r.user_stories.length, r.user_stories.map((u) => `<div class="card story">
        <div class="row"><span class="rid">${esc(u.id)}</span><h4>As a <b>${esc(u.as_a)}</b>, I want ${tbd(u.i_want)}, <em>so that ${tbd(u.so_that)}</em></h4></div>
        <div class="meta">${u.requirement_ids.map((i) => tag("neutral", i)).join("")}</div>
        <ul>${u.acceptance_criteria.map((c) => `<li>${tbd(c)}</li>`).join("")}</ul></div>`).join(""))}
    <div class="cols2">
      ${section("Missing information", r.missing_information.length, r.missing_information.map((m) => `<div class="card"><div class="row"><b>${esc(m.topic)}</b>${tag(m.impact)}</div><div>${esc(m.detail)}</div><div class="meta">${srcChips(m.related_ids)}</div></div>`).join("") || none("Nothing missing detected."))}
      ${section("Clarifying questions", r.clarifying_questions.length, r.clarifying_questions.map((x, i) => `<div class="card"><div class="row"><span class="rid">Q${i + 1}</span><span class="rtext">${esc(x.question)}</span>${tag(x.priority)}</div><div class="hint" style="margin:4px 0 0">${esc(x.why_it_matters)}</div></div>`).join(""))}
    </div>
    ${section("Potential edge cases", r.edge_cases.length, r.edge_cases.map((e) => `<div class="card"><div class="row"><span class="rtext">${esc(e.scenario)}</span>${srcChips(e.source_ids)}</div><div class="hint" style="margin:4px 0 0">→ ${esc(e.expected_handling)}</div></div>`).join(""))}
    ${section("Assumptions to confirm", r.assumptions.length, r.assumptions.map((a) => `<div class="card"><div>${tag("assumption")} ${esc(a.statement)}</div>${a.reason ? `<div class="hint" style="margin:4px 0 0">${esc(a.reason)}</div>` : ""}</div>`).join("") || none("None."))}
  </div>
  <aside class="sources"><h3>Source sentences</h3>${r.sentences.map((s) => `<div class="sent" id="sent-${esc(s.id)}"><code>${esc(s.id)}</code>${esc(s.text)}</div>`).join("")}</aside>
  </div>`;

  // hover a citation chip -> highlight the customer sentence it points to
  out.querySelectorAll(".src").forEach((c) => {
    const s = $(`#sent-${c.dataset.src}`);
    if (s) c.title = s.textContent.replace(/^S\d+/, "");
    c.onmouseenter = () => s?.classList.add("hl");
    c.onmouseleave = () => s?.classList.remove("hl");
  });
  $("#dl-json").onclick = () => save(JSON.stringify(lastResult, null, 2), "requirements.json", "application/json");
  $("#dl-md").onclick = async () => {
    const md = await (await fetch("/api/export/markdown", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lastResult) })).text();
    save(md, "requirements.md", "text/markdown");
  };
}

function save(content, name, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
}


// ---------- history tab ----------
document.querySelectorAll(".tab").forEach((t) => t.onclick = () => showView(t.dataset.view));

function showView(view) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.view === view));
  $("#view-new").hidden = view !== "new";
  $("#view-history").hidden = view !== "history";
  if (view === "history") loadHistory();
}

async function loadHistory() {
  try {
    historyItems = await (await fetch("/api/history")).json();
  } catch { historyItems = []; }
  $("#hist-count").textContent = historyItems.length || "";
  renderHistory();
}

function timeAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function renderHistory() {
  const q = $("#hist-search").value.trim().toLowerCase();
  const items = historyItems.filter((h) => !q || `${h.title} ${h.domain}`.toLowerCase().includes(q));
  const list = $("#hist-list");
  if (!items.length) {
    list.innerHTML = `<li class="hist-empty">${historyItems.length ? "No matches." : "No previous analyses yet. Run one from <b>New analysis</b> and it will appear here."}</li>`;
    return;
  }
  list.innerHTML = items.map((h) => `
    <li class="hist-item ${h.id === activeHistory ? "active" : ""}" data-id="${esc(h.id)}">
      <div class="ht">${esc(h.title)}</div>
      <div class="hm">
        <span>${esc(timeAgo(h.created))}</span>
        ${h.status === "ok"
          ? `${h.domain ? tag("neutral", h.domain) : ""}${tag("stated", `${h.n_requirements ?? 0} req.`)}${tag("medium", `${h.n_questions ?? 0} questions`)}`
          : tag("unsupported", "not analysed")}
      </div>
      <button class="del" title="Delete" aria-label="Delete">×</button>
    </li>`).join("");
  list.querySelectorAll(".hist-item").forEach((li) => {
    li.onclick = () => openHistory(li.dataset.id);
    li.querySelector(".del").onclick = async (e) => {
      e.stopPropagation();
      await fetch(`/api/history/${li.dataset.id}`, { method: "DELETE" });
      if (activeHistory === li.dataset.id) activeHistory = null;
      loadHistory();
    };
  });
}

async function openHistory(id) {
  const r = await fetch(`/api/history/${id}`);
  if (!r.ok) return loadHistory();
  const item = await r.json();
  activeHistory = id;
  $("#input").value = item.input;
  item.result.input = item.input;
  $("#steps").hidden = true;
  $("#error").hidden = true;
  render(item.result);
  renderHistory();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("#hist-search").addEventListener("input", renderHistory);
$("#hist-clear").onclick = () => { if (historyItems.length) $("#hist-confirm").hidden = false; };
$("#hist-clear-no").onclick = () => { $("#hist-confirm").hidden = true; };
$("#hist-clear-yes").onclick = async () => {
  await fetch("/api/history", { method: "DELETE" });
  $("#hist-confirm").hidden = true; activeHistory = null; loadHistory();
};
loadHistory();
if (new URLSearchParams(location.search).get("view") === "history") showView("history");

// ---------- theme (system / light / dark) ----------
function applyTheme(choice) {
  if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
  else delete document.documentElement.dataset.theme;            // follow the OS
  document.querySelectorAll("[data-theme-choice]").forEach((b) => {
    b.classList.toggle("on", b.dataset.themeChoice === choice);
    b.setAttribute("aria-checked", b.dataset.themeChoice === choice);
  });
  try { choice === "system" ? localStorage.removeItem("reqnova-theme") : localStorage.setItem("reqnova-theme", choice); } catch (e) {}
}
document.querySelectorAll("[data-theme-choice]").forEach((b) => b.onclick = () => applyTheme(b.dataset.themeChoice));
const themeParam = new URLSearchParams(location.search).get("theme");
let savedTheme = "system";
try { savedTheme = localStorage.getItem("reqnova-theme") || "system"; } catch (e) {}
applyTheme(themeParam || savedTheme);
