// TAB 3 — Alert Triage: legacy rule alerts vs agent disposition (explainable auto-closure, zero missed mules)
import { $, api, esc, pct, DECISION_EN } from "./core.js";

let data = null;

export async function initTriage() {
  if (!data) data = await api("/api/triage");
  const m = data.metrics;
  const k = (v, l, c = "text-ink") => `<div class="kpi"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`;
  $("#triage-kpis").innerHTML = k(m.alerts_total, "Legacy rule alerts") + k(pct(m.legacy_false_positive_rate), "Are false positives", "text-rose-700")
    + k(m.auto_closed, `Auto-closed (${m.auto_closed_correct} correct)`, "text-emerald-700") + k(m.escalated, `Escalated (${m.escalated_true} true mules)`, "text-amber-700")
    + k(m.victim_protection, "Routed to victim protection", "text-sky-700") + k(m.missed_mules, "Mules missed", m.missed_mules ? "text-rose-700" : "text-emerald-700")
    + k("−" + pct(m.workload_reduction), "Manual review workload", "text-emerald-700") + k(Math.round(m.analyst_minutes_saved / 60) + " h", "Analyst hours saved (25 min/alert)");
  const decs = [...new Set(data.alerts.map((a) => a.decision))];
  $("#triage-filter").innerHTML = `<option value="">All dispositions</option>` + decs.map((d) => `<option value="${esc(d)}">${esc((DECISION_EN[d] || [d])[0])}</option>`).join("");
  $("#triage-filter").onchange = draw;
  draw();
}

function draw() {
  const f = $("#triage-filter").value;
  const rows = data.alerts.filter((a) => !f || a.decision === f).slice(0, 400);
  $("#triage-table").innerHTML = `<tr><th>Alert</th><th>Account</th><th>Rules fired</th><th>Risk</th><th>Agent disposition</th><th>Explanation (Vietnamese, audit-ready)</th><th>Ground truth</th></tr>` +
    rows.map((a) => { const [label, cls] = DECISION_EN[a.decision] || [a.decision, "b-slate"]; return `<tr>
      <td class="font-mono">${esc(a.alert_id)}</td><td class="font-mono">${esc(a.account_id)}<div class="font-sans text-[11px] text-muted">${esc(a.holder)} · ${esc(a.segment)}</div></td>
      <td class="text-[11.5px] text-muted">${a.rules.map(esc).join("<br>")}</td><td class="font-mono ${a.score >= 0.5 ? "text-rose-700" : "text-emerald-700"}">${pct(a.score)}</td>
      <td><span class="badge ${cls}">${esc(label)}</span></td><td class="text-[12px] text-ink">${esc(a.reason)}</td>
      <td>${a.truth === "mule" ? '<span class="badge b-rose">mule</span>' : '<span class="badge b-slate">legitimate</span>'}</td></tr>`; }).join("");
}
