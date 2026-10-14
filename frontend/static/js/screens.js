// screens.js - Renderers for all 5 screens + demo case seeder

import { api } from './api.js?v=9';
import { cloudSvg } from './cloud.js?v=7';

// Async loaders can resolve after the user has navigated away; never crash.
function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
  return el;
}

// A case whose audit chain fails verification is frozen server-side (423).
// Show that up front and hide every control that would only be refused.
function frozenWrap(s, html, esc) {
  const hold = s.sentinel_hold || {};
  if (hold.active) {
    return `<div class="banner banner-error" role="alert"><p><strong>Stopped by the sentinel:</strong> ${(hold.findings || []).map(esc).join('; ')}. What it saw has been kept, the reason is on the case's audit trail, and an auditor decides on Governance whether to release or quarantine it.</p></div>
    <div class="case-frozen">${html}</div>`;
  }
  if (s.audit_chain_valid !== false) return html;
  return `<div class="banner banner-error"><p><strong>Case frozen:</strong> the audit chain for ${esc(s.case_id)} failed verification, so it can be read but not advanced, decided or closed until an auditor reviews it.</p></div>
    <div class="case-frozen">${html}</div>`;
}

// Tabs: one card group at a time instead of a long page. Every panel is
// rendered (screens fill their cards by id); only the chosen one shows, and
// the choice is remembered per screen for the session.
function tabbed(key, tabs, first = tabs[0].id) {
  let active = null;
  try { active = sessionStorage.getItem(`tbc_tab_${key}`); } catch (_) { /* first tab */ }
  if (!tabs.some(t => t.id === active)) active = first;
  return `<div class="tabs" role="tablist" data-tabs="${key}">${tabs.map(t => `<button type="button" role="tab" class="tab" id="tab-${key}-${t.id}"
      aria-selected="${t.id === active}" aria-controls="tp-${key}-${t.id}" tabindex="${t.id === active ? 0 : -1}"
      data-key="${key}" data-tab="${t.id}">${t.label}${tabNote(t.note)}</button>`).join('')}</div>`
    + tabs.map(t => `<div class="tab-panel" role="tabpanel" id="tp-${key}-${t.id}" aria-labelledby="tab-${key}-${t.id}" ${t.id === active ? '' : 'hidden'}>${t.html}</div>`).join('');
}
// A count shows as a number in a bubble; anything else as a short word.
function tabNote(note) {
  if (note === undefined || note === null || note === '' || note === 0) return '';
  return /^\d+$/.test(String(note))
    ? ` <span class="tab-count">${note}</span>`
    : ` <span class="tab-note">${note}</span>`;
}
function openTab(key, id) {
  const list = document.querySelector(`[data-tabs="${key}"]`);
  if (!list || !document.getElementById(`tab-${key}-${id}`)) return;
  list.querySelectorAll('.tab').forEach(b => {
    const on = b.dataset.tab === id;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
    document.getElementById(b.getAttribute('aria-controls')).hidden = !on;
  });
  try { sessionStorage.setItem(`tbc_tab_${key}`, id); } catch (_) { /* not remembered */ }
}
document.addEventListener('click', e => {
  const b = e.target.closest('.tab[data-key]');
  if (b) openTab(b.dataset.key, b.dataset.tab);
});
document.addEventListener('keydown', e => {
  const b = e.target.closest?.('.tab[data-key]');
  if (!b || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
  const all = [...b.parentElement.querySelectorAll('.tab')];
  const i = all.indexOf(b);
  const next = e.key === 'Home' ? all[0] : e.key === 'End' ? all.at(-1)
    : all[(i + (e.key === 'ArrowRight' ? 1 : -1) + all.length) % all.length];
  e.preventDefault(); openTab(next.dataset.key, next.dataset.tab); next.focus();
});
// A tab's small status note ("2 pending", "action needed"), set after load.
function setTabNote(key, id, text) {
  const b = document.getElementById(`tab-${key}-${id}`);
  if (!b) return;
  b.querySelectorAll('.tab-note, .tab-count').forEach(x => x.remove());
  if (!text) return;
  const n = document.createElement('span');
  n.className = /^\d+$/.test(String(text)) ? 'tab-count' : 'tab-note';
  n.textContent = text;
  b.append(' ', n);
}
window.__tabs__ = { open: openTab };

const isForbidden = e => e?.status === 403 || /403|lacks capability|forbidden/i.test(e?.message || '');
const rbacNote = (what, roles) => `<div class="banner banner-info"><p><strong>Role-based access:</strong> ${what} is limited to ${roles}. Switch role in the top bar to see it.</p></div>`;

// A one-line orientation cue at the top of every screen, so someone who
// just landed on it (or is watching over a shoulder) knows what to do or
// expect next without reading the whole card stack first.
const nextHint = text => `<p class="next-hint">${_esc(text)}</p>`;
// Who raises the work order depends on the role: a technician is told the AOM does it.
const workOrderNext = () => (api.can('approve_reject_modify') ? 'raise the work order' : 'the AOM raises the work order');

// local HTML-escape for module-level helper (render functions receive `esc` via helpers)
function _esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Causes: canonical IDs with plain-English labels, from /causes ──
// One source of truth for every cause dropdown and cause label on screen.
let _causes = null;
async function loadCauses() {
  if (_causes) return _causes;
  try { _causes = (await api.get('/causes')).causes || []; }
  catch (_) { _causes = []; }
  return _causes;
}
const ALIASES = { comm_bus_failure: 'communication_bus_controller_failure', config_drift: 'configuration_drift', loose_wiring: 'loose_wiring_after_service' };
function causeLabel(id) {
  if (!id) return 'Unknown cause';
  if (id.startsWith('new:')) return 'Proposed new cause: ' + id.slice(4).replace(/_/g, ' ');
  const c = (_causes || []).find(x => x.id === (ALIASES[id] || id));
  return c ? c.label : id.replace(/_/g, ' ');
}
// <option>s grouped by asset type; `selected` is pre-selected.
function causeOptions(causes, selected = '') {
  const groups = {};
  causes.forEach(c => (groups[c.asset_type] = groups[c.asset_type] || []).push(c));
  return Object.entries(groups).map(([at, cs]) =>
    `<optgroup label="${_esc(at)}">${cs.map(c => `<option value="${_esc(c.id)}" ${c.id === (ALIASES[selected] || selected) ? 'selected' : ''}>${_esc(c.label)}</option>`).join('')}</optgroup>`).join('');
}

const plain = v => String(v || '').replace(/_/g, ' ');
// What the sensor reported, in words: "invalid" covers a vibration that is
// too high as much as a temperature that cannot be right.
const readingText = r => ({ absent: 'no reading', invalid: 'out of range', ok: 'normal' }[r] || r || 'unknown');
// Model-written prose can carry internal ids ("temperature_measurement_missing");
// show those words, not the identifier.
const prose = v => String(v || '').replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, m => m.replace(/_/g, ' '));
// "kb:technical_services:pump_tree:v1:Q2" -> "Pump tree v1, Q2"; the full
// reference stays in the tooltip.
const kbRef = r => {
  const parts = String(r).split(':');
  // Words for an AOM: "Pump decision tree (v1), question 2", "site heuristic H3".
  const step = x => x.replace(/^Q(\d+)$/, 'question $1');
  const label = parts.length >= 4
    ? `${plain(parts[2]).replace(/^\w/, c => c.toUpperCase()).replace(/^(Ups|Crah)\b/, m => m.toUpperCase()).replace(/ tree$/, ' decision tree')} (${parts[3]})${parts.length > 4 ? ', ' + parts.slice(4).map(step).join(', ') : ''}`
    : String(r).replace(/^KB-H(\d+)$/, 'site heuristic H$1').replace(/^KB-(CH|UPS|PMP)(\d+)$/, 'site heuristic $1-$2');
  return `<span class="kb-ref" title="${_esc(r)}">${_esc(label)}</span>`;
};
// A symptom is shown after a "When" label; drop only a repeated leading
// "When"/"Whenever" so it never reads "When When the supply air...". Any
// other wording ("If the axial vibration...") is the expert's own sentence
// and is shown exactly as they said it.
const whenText = t => {
  const s = String(t || '').trim().replace(/^(when|whenever)\s+/i, '');
  return s.charAt(0).toUpperCase() + s.slice(1);
};

// Model calls make the on-screen cloud "think" while they run.
const thinking = p => (window.__cloud__ ? window.__cloud__.cloudThinking(p) : p);
const cloudMood = m => window.__cloud__ && window.__cloud__.setCloudMood(m);

// What the AOM is actually approving: the diagnosed cause, how confident
// the engine is, the readings that drove it, and the AI's advisory view.
function decisionFacts(s, esc, confBand) {
  const diag = s.diagnosis || {};
  const cb = confBand(s.confidence, s.current_state);
  const obs = s.observation || {};
  const abnormal = [`Trigger: ${plain(obs.type)} (${readingText(obs.reading_status)})`];
  (s.evidence || []).forEach(ev => {
    (ev.abnormal || []).forEach(k => {
      abnormal.push(`${_humaniseKey(k, ev.labels)}: ${_formatValue(k, ev.payload[k], true)}`);
    });
  });
  const hyp = s.ai_hypothesis;
  const ai = !hyp ? 'Not run' : hyp.status === 'unavailable' ? 'AI offline'
    : !hyp.hypothesis ? 'No opinion (evidence too thin)'
    : hyp.agrees_with_rules ? 'Agrees' : `Disagrees: ${causeLabel(hyp.hypothesis)}`;
  return `<div class="decision-facts">
      <div class="decision-fact"><div class="lbl">Diagnosed cause</div><div class="val">${esc(causeLabel(diag.top_cause_id))}</div></div>
      <div class="decision-fact"><div class="lbl">Confidence</div><div class="val"><span class="badge ${cb.cls}">${esc(cb.label)}</span></div></div>
      <div class="decision-fact"><div class="lbl">AI second opinion (advisory)</div><div class="val">${esc(ai)}</div></div>
    </div>
    <div style="margin-bottom:12px"><strong>Readings behind this diagnosis:</strong> ${abnormal.map(a => `<span class="badge badge-yellow" style="margin:2px">${esc(a)}</span>`).join(' ')}</div>`;
}

function corroboration(m, esc) {
  if (m.guidance_only) {
    return `<div class="muted" style="margin:4px 0"><span class="badge badge-yellow">Protective device or work on equipment</span> Safety-reviewed by ${esc(m.safety_reviewed_by)}. Guidance for a person only: it never raises confidence.</div>`;
  }
  return m.matched_terms && m.matched_terms.length
    ? `<div class="muted" style="margin:4px 0"><span class="badge badge-green">Seen in this case's abnormal readings</span> The expert's words ${(() => { const w = m.matched_terms.map(t => `“${esc(t)}”`); return w.length > 1 ? `${w.slice(0, -1).join(', ')} and ${w.at(-1)}` : w[0]; })()} also describe a reading flagged on this case.</div>`
    : `<div class="muted" style="margin:4px 0"><span class="badge badge-grey">Not seen in this case's abnormal readings</span> Shown as guidance; it does not raise confidence.</div>`;
}

// Approved expert know-how for this cause, shown where the decision is made.
function expertChecks(ek, esc) {
  if ((!ek.matches || !ek.matches.length) && (ek.withheld || []).length) {
    return `<div class="banner banner-warn mt-16"><p>${ek.withheld.length} approved expert heuristic(s) for this cause are withheld: ${esc(ek.withheld[0].reason)}.</p></div>`;
  }
  if (!ek.matches || !ek.matches.length) {
    return `<p class="muted" style="margin-top:8px">No approved expert knowledge matches this cause yet.</p>`;
  }
  const list = (title, items) => items && items.length ? `<div><strong>${title}:</strong><ul class="expert-list">${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : '';
  return `<div class="mt-16"><span class="tier-label tier-advisory">Expert knowledge to apply (approved by a knowledge steward)</span>
    ${ek.matches.map(m => `<article class="expert-match">
      <div><strong>${esc(m.expert_name)}</strong> <span class="muted">— ${esc(m.expert_role)} · ${esc(m.kb_version_label)} · approved by ${esc(m.approved_by)}</span></div>
      ${corroboration(m, esc)}
      ${list(`Checks (safety-reviewed by ${esc(m.safety_reviewed_by || m.approved_by)})`, m.checks)}${list('Never', m.do_not)}${list('Escalate when', m.escalate_when)}
      <blockquote class="expert-quote">“${esc(m.evidence_quote)}”</blockquote>
    </article>`).join('')}</div>`;
}

// ── Guardrail definitions for G1-G9 grid ───────────────────
const GUARDRAILS = [
  { id: 'G1', desc: 'BMS setpoint/interlock block' },
  { id: 'G2', desc: 'Safety-critical escalate' },
  { id: 'G3', desc: 'Cross-domain coordinate' },
  { id: 'G4', desc: 'Low confidence escalate' },
  { id: 'G5', desc: 'Unknown asset escalate' },
  { id: 'G6', desc: 'Force approval' },
  { id: 'G7', desc: 'Sanitize injection' },
  { id: 'G8', desc: 'Ungrounded reject' },
  { id: 'G9', desc: 'AI disagreement flag (advisory)' },
];

// ── Confidence weights for W1-W5 breakdown ────────────────
const WEIGHTS = [
  { id: 'W1', val: 0.30, key: 'evidence_coverage', label: 'Evidence Coverage', sign: '+' },
  { id: 'W2', val: 0.20, key: 'peer_agreement', label: 'Peer Agreement', sign: '+' },
  { id: 'W3', val: 0.25, key: 'kb_match', label: 'KB Match', sign: '+' },
  { id: 'W4', val: 0.10, key: 'data_staleness', label: 'Data Staleness', sign: '-' },
  { id: 'W5', val: 0.15, key: 'conflict_penalty', label: 'Conflict Penalty', sign: '-' },
];

// Evidence display toggle state (plain English vs raw JSON)
let _evidenceRawMode = false;
// The timeline opens on abnormal readings only; "show all" lists every item.
let _evidenceShowAll = false;



// Field names come from the server (evidence_flags.FIELD_LABELS, sent with
// each evidence item as ``labels``); this only covers anything it lacks.
function _humaniseKey(key, labels = {}) {
  if (labels[key]) return labels[key];
  const t = key.replace(/_/g, ' ');
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// Which fields are abnormal comes from the server (evidence_flags.py), which
// uses the decision trees' own thresholds; this only formats values.
function _formatValue(key, val, abnormal) {
  if (typeof val === 'boolean') return abnormal && key.endsWith('_switch') ? 'TRIPPED' : (val ? 'Yes' : 'No');
  if (key === 'alarms' && Array.isArray(val)) return val.length ? val.map(plain).join(', ') : 'None';
  if (val !== null && typeof val === 'object') return JSON.stringify(val);
  return String(val);
}

function renderEvidencePlain(payload, abnormalKeys = [], labels = {}) {
  if (!payload || typeof payload !== 'object') {
    return '<span class="muted">—</span>';
  }
  const entries = Object.entries(payload);
  return `<div class="evidence-plain">` + entries.map(([key, val]) => {
    const label = _humaniseKey(key, labels);
    const abnormal = abnormalKeys.includes(key);
    const displayVal = _formatValue(key, val, abnormal);
    const cls = abnormal ? 'evidence-abnormal' : 'evidence-normal';
    return `<div class="evidence-field ${cls}">
      <span class="evidence-field-label">${_esc(label)}</span>
      <span class="evidence-field-value">${_esc(String(displayVal))}</span>
    </div>`;
  }).join('') + `</div>`;
}

// ═══════════════════════════════════════════════════════════
// Screen 1: Dashboard
// ═══════════════════════════════════════════════════════════
// The stat cards double as filters. Each count and its filter use the
// same test, so the number on a card is always the number of rows shown.
const STAT_FILTERS = [
  { id: 'all',       label: 'Total Cases',       cls: '',            match: () => true },
  { id: 'approval',  label: 'Awaiting Approval', cls: 'stat-yellow', match: c => c.current_state === 'AWAITING_APPROVAL' },
  { id: 'escalated', label: 'Escalated',         cls: 'stat-red',    match: c => c.current_state === 'ESCALATED' },
  { id: 'resolved',  label: 'Resolved',          cls: 'stat-green',  match: c => c.current_state === 'CLOSED' && !c.quarantined },
];

// Status sorts in lifecycle order, not alphabetically; an undiagnosed
// case sorts below every diagnosed one on confidence.
const STATE_ORDER = ['TRIGGERED', 'GATHERING_EVIDENCE', 'DIAGNOSING', 'RECOMMENDING', 'AWAITING_APPROVAL',
  'EXECUTING', 'MONITORING_OUTCOME', 'RECORDING_OUTCOME', 'FEEDBACK_QUEUED', 'ESCALATED', 'CLOSED'];
const CASE_COLUMNS = [
  { id: 'case',       label: 'Case ID',    key: c => c.case_id || '' },
  { id: 'asset',      label: 'Asset',      key: c => c.asset_id || '' },
  { id: 'fault',      label: 'Fault',      key: c => (c.observation || {}).type || '' },
  { id: 'sensor',     label: 'Sensor',     key: c => (c.observation || {}).sensor_id || '' },
  { id: 'reading',    label: 'Reading',    key: c => (c.observation || {}).reading_status || '' },
  { id: 'status',     label: 'Status',     key: c => { const i = STATE_ORDER.indexOf(c.current_state); return i < 0 ? STATE_ORDER.length : i; } },
  { id: 'confidence', label: 'Confidence', key: c => (c.diagnosis ? Number(c.confidence) || 0 : -1) },
];
const dashView = { filter: 'all', sortKey: null, sortDir: 'asc' };

export function renderDashboard(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate } = h;
  const isAdmin = api.role() === 'admin';

  el.innerHTML = `
    <h2 class="sr-only">Cases</h2>
    <div id="integrity-banner"></div>
    <div class="dash-toolbar">
      ${nextHint('click a case to see its diagnosis, or create a new one to get started.')}
      <div class="flex gap-8">
        <button class="btn btn-secondary" id="btn-seed" ${isAdmin ? '' : 'disabled title="Seeding demo cases is limited to the Admin role"'}>Seed Demo Cases</button>
        ${api.can('open_case') ? '<button class="btn btn-primary" id="btn-new">New Case</button>' : ''}
      </div>
    </div>
    <div class="stats-row" id="stats-row" role="group" aria-label="Filter cases by status"></div>
    <div class="table-filter-note" id="cases-filter-note" hidden aria-live="polite"></div>
    <div class="card">
      <div class="table-wrap">
        <table id="cases-table">
          <thead><tr id="cases-head"></tr></thead>
          <tbody id="cases-tbody"><tr><td colspan="8" class="skeleton-row">
            <div class="skeleton skeleton-line" style="width:80%"></div>
            <div class="skeleton skeleton-line" style="width:60%"></div>
            <div class="skeleton skeleton-line"></div>
          </td></tr></tbody>
        </table>
      </div>
    </div>
    <div id="new-case-form" style="display:none" class="card">
      <div class="card-header"><h3>Create New Case</h3></div>
      <div class="card-body">
        <div class="grid-2">
          <div class="form-group"><label for="nc-asset">Asset ID</label><select id="nc-asset">
            <option value="__other__">Other / unregistered asset (demonstrates G5 escalation)</option>
          </select>
          <input id="nc-asset-other" type="text" placeholder="e.g. NOPE-999" style="display:none;margin-top:8px">
          </div>
          <div class="form-group"><label for="nc-sensor">Sensor ID</label><select id="nc-sensor"><option value="SA-TEMP-01">SA-TEMP-01</option></select>
          <input id="nc-sensor-other" type="text" placeholder="e.g. NOPE-SENSOR" aria-label="Sensor ID on the unregistered asset" style="display:none;margin-top:8px"></div>
          <div class="form-group"><label>Fault Type</label><select id="nc-fault">
            <option value="temperature_measurement_missing">temperature measurement missing</option>
            <option value="chiller_compressor_trip">chiller compressor trip</option>
            <option value="ups_battery_fault">ups battery fault</option>
            <option value="pump_vibration_high">pump vibration high</option>
          </select></div>
          <div class="form-group"><label for="nc-reading">Reading Status</label><select id="nc-reading">
            <option value="absent">no reading (absent)</option>
            <option value="invalid">out of range or implausible</option>
          </select></div>
        </div>
        <button class="btn btn-primary" id="btn-create">Create Case</button>
      </div>
    </div>
    <details class="card why-panel about-card" id="how-it-works">
      <summary><h3 style="display:inline">How this pill works</h3> <span class="muted">where AI is used · why it exists · illustrative value · deployment path</span></summary>
      <div class="card-body">
        <div class="ai-flow-row ai-flow" role="group" aria-label="Where AI is used and what governs it">
        <div class="ai-flow-step"><div class="ai-flow-k">AI</div><div class="ai-flow-v" id="ai-flow-provider">Tencent Cloud ADP</div><div class="ai-flow-d">Drafts knowledge, second opinion</div></div>
        <div class="ai-flow-arrow" aria-hidden="true">→</div>
        <div class="ai-flow-step"><div class="ai-flow-k">Governance</div><div class="ai-flow-v">Checks every AI output</div><div class="ai-flow-d">Grounding, safety, guardrails, sentinel</div></div>
        <div class="ai-flow-arrow" aria-hidden="true">→</div>
        <div class="ai-flow-step"><div class="ai-flow-k">Diagnosis</div><div class="ai-flow-v">Decision tree</div><div class="ai-flow-d">Same evidence, same answer</div></div>
        <div class="ai-flow-arrow" aria-hidden="true">→</div>
        <div class="ai-flow-step"><div class="ai-flow-k">Decision</div><div class="ai-flow-v">A person approves</div><div class="ai-flow-d">Nothing runs without a manager</div></div>
      </div>
            ${tabbed('about', [
        { id: 'why', label: 'Why this exists', html: `<p><strong>Problem:</strong> fault diagnosis know-how lives in individual technicians' heads. When an experienced tech is unavailable or retires, that judgement isn't captured anywhere a new case can reuse it.</p>
        <p><strong>Users:</strong> technicians trigger and work cases; Asset Ops Managers approve every recommendation before anything happens; Knowledge Stewards review and govern what the pill learns from interviews and closed cases.</p>
        <p><strong>Value:</strong> a rule-based diagnosis plus any matching approved expert knowledge appears in seconds (see the Diagnosis screen), and a validated fix measurably raises confidence on the next identical fault (see Governance, and <code>make demo</code>). For what that could be worth, use the Illustrative value tab with your own figures.</p>` },
        { id: 'value', label: 'Illustrative value', note: 'not Keppel actuals', html: `<p class="muted" style="margin-bottom:10px">Your inputs, not Keppel data.</p>
        <div class="roi-grid">
          <label>Cases a year<input id="roi-cases" type="number" min="0" step="10" value="500"></label>
          <label>Minutes per case today<input id="roi-now" type="number" min="0" step="5" value="60"></label>
          <label>Minutes with TBC<input id="roi-with" type="number" min="0" step="5" value="30"></label>
          <label>Cost per hour<input id="roi-rate" type="number" min="0" step="5" value="60"></label>
        </div>
        <div class="roi-out" id="roi-out" aria-live="polite"></div>` },
        { id: 'path', label: 'Deployment path', html: `<p><strong>Stage 1 -- Pilot:</strong> the decision tree, guardrails, governance loop, audit trail and RBAC in this repo are real and tested today; telemetry is a static mock registry pending a real BMS/SCADA feed.</p>
        <p><strong>Stage 2 -- Production on Tencent Cloud:</strong> containerised deploy (the repo's own Dockerfile), SQLite swapped for a managed database, secrets moved to Tencent Cloud's secret manager, real CMMS work-order integration.</p>
        <p><strong>Stage 3 -- Scale:</strong> additional asset types and sites, per-site knowledge-base governance, the steward roster set per site (it is already configurable with TBC_PILL_OWNERS).</p>
        <p class="muted">Full detail, including exactly what's real versus stubbed at each stage: <code>docs/IMPLEMENTATION_PATH.md</code>.</p>` },
      ])}
    </div></details>
  `;

  // Illustrative value: simple arithmetic on the viewer's own inputs.
  const roiIds = ['roi-cases', 'roi-now', 'roi-with', 'roi-rate'];
  try {
    const saved = JSON.parse(localStorage.getItem('tbc_roi') || 'null');
    if (Array.isArray(saved)) roiIds.forEach((id, i) => { if (Number.isFinite(saved[i])) document.getElementById(id).value = saved[i]; });
  } catch (_) { /* defaults */ }
  const roi = () => {
    const [cases, now, withPill, rate] = roiIds.map(id => Math.max(0, Number(document.getElementById(id).value) || 0));
    const saved = Math.max(0, now - withPill);
    const hours = cases * saved / 60;
    try { localStorage.setItem('tbc_roi', JSON.stringify([cases, now, withPill, rate])); } catch (_) { /* not remembered */ }
    setHTML('roi-out', `
      <div class="stat"><div class="stat-val">${saved} min</div><div class="stat-lbl">Saved per case</div></div>
      <div class="stat stat-green"><div class="stat-val">${Math.round(hours).toLocaleString()} h</div><div class="stat-lbl">Hours saved a year</div></div>
      <div class="stat stat-blue"><div class="stat-val">${Math.round(hours * rate).toLocaleString()}</div><div class="stat-lbl">Saved a year</div></div>
      <p class="muted roi-formula">${cases} × ${saved} min ÷ 60 × ${rate}/h</p>`);
  };
  roiIds.forEach(id => document.getElementById(id).addEventListener('input', roi));
  roi();
  api.get('/system/info').then(info => {
    setHTML('ai-flow-provider', esc(info.llm_provider === 'adp' ? 'Tencent Cloud ADP' : 'Offline models'));
  }).catch(() => {});

  document.getElementById('btn-seed').onclick = async () => {
    try {
      const r = await api.post('/demo/seed');
      showToast(`Seeded ${r.seeded.length} cases (recorded as ${r.actor})`, 'success');
      loadCases();
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
  };

  // Any case chain or the governance ledger failing verification is shown
  // to every role here, not only on the auditor's Governance table.
  (async () => {
    try {
      const [st, sen] = await Promise.all([api.get('/audit/status'), api.get('/sentinel')]);
      if (st.ok && !sen.held.length) return;
      const parts = [];
      // A tamper recorded on load or save stays open until an auditor
      // acknowledges it, even though the clean state has been restored.
      const open = st.unacknowledged_tamper_events || [];
      if (open.length) parts.push(`${open.length} saved copy change(s) recorded outside the app and not yet acknowledged (latest: ${esc(open[open.length - 1].detail)}; the changed copy was archived and the last verified state restored)`);
      if (sen.held.length) parts.push(`the sentinel stopped ${sen.held.map(x => esc(x.case_id)).join(', ')} (held for an auditor's decision)`);
      if (st.broken_cases.length) parts.push(`case audit chain failed for ${st.broken_cases.map(esc).join(', ')} (frozen: no further actions allowed)`);
      if (!st.ledger_valid) parts.push('the knowledge governance ledger failed verification');
      if (!st.registry_valid) parts.push('the set of cases does not match its seal (a case was added or removed outside the app)');
      if (!st.tool_log_valid) parts.push('the tool audit log failed verification');
      setHTML('integrity-banner', `<div class="banner banner-error" role="alert"><p><strong>Audit integrity alert:</strong> ${parts.join('; ')}. An auditor reviews it on Governance before anyone relies on it.</p></div>`);
    } catch (_) { /* banner is best-effort */ }
  })();
  const btnNew = document.getElementById('btn-new');
  if (btnNew) btnNew.onclick = () => {
    const f = document.getElementById('new-case-form');
    const opening = f.style.display === 'none';
    f.style.display = opening ? 'block' : 'none';
    if (opening) f.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  const assetSelect = document.getElementById('nc-asset');
  const assetOther = document.getElementById('nc-asset-other');
  // The asset list, each asset's fault type and default sensor come from
  // the registry (/assets); only the fault an asset's pill diagnoses is
  // offered, and the server rejects a mismatch too.
  let registry = [];
  const syncFault = () => {
    const other = assetSelect.value === '__other__';
    assetOther.style.display = other ? 'block' : 'none';
    const a = registry.find(x => x.asset_id === assetSelect.value);
    const sel = document.getElementById('nc-fault');
    [...sel.options].forEach(o => { o.disabled = !other && (!a || o.value !== a.fault_type); });
    if (a) sel.value = a.fault_type;
    // A missing temperature is "no reading"; a trip or a vibration alarm is
    // a reading out of range.
    if (a) document.getElementById('nc-reading').value = a.fault_type === 'temperature_measurement_missing' ? 'absent' : 'invalid';
    // A registered asset offers only its own sensors; the server refuses
    // any other, so evidence is never filed under the wrong sensor.
    const sensorSel = document.getElementById('nc-sensor');
    const sensorOther = document.getElementById('nc-sensor-other');
    sensorSel.style.display = other ? 'none' : '';
    sensorOther.style.display = other ? 'block' : 'none';
    sensorSel.innerHTML = (a ? a.sensors : []).map(sid => `<option value="${esc(sid)}">${esc(sid)}</option>`).join('');
    if (a) sensorSel.value = a.default_sensor;
  };
  assetSelect.addEventListener('change', syncFault);
  api.get('/assets').then(({ assets }) => {
    registry = assets;
    assetSelect.insertAdjacentHTML('afterbegin', assets.map(a =>
      `<option value="${esc(a.asset_id)}">${esc(a.asset_id)} (${esc(a.type)})</option>`).join(''));
    assetSelect.selectedIndex = 0;
    syncFault();
  }).catch(() => {});
  document.getElementById('btn-create').onclick = async () => {
    const assetId = assetSelect.value === '__other__' ? assetOther.value.trim() : assetSelect.value;
    if (!assetId) { showToast('Enter an asset ID', 'error'); assetOther.focus(); return; }
    try {
      const r = await api.post('/cases', {
        asset_id: assetId,
        sensor_id: assetSelect.value === '__other__'
          ? (document.getElementById('nc-sensor-other').value.trim() || 'UNKNOWN-SENSOR')
          : document.getElementById('nc-sensor').value,
        observation_type: document.getElementById('nc-fault').value,
        reading_status: document.getElementById('nc-reading').value,
      });
      showToast(`Case created: ${r.case_id} (${r.evidence_count} evidence items gathered). Opening it.`, 'success');
      window.__app__.navigate('diagnosis', r.case_id);
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
  };

  let allCases = [];
  async function loadCases() {
    try {
      const data = await api.get('/cases');
      const ids = data.cases || [];
      const snapshots = await Promise.all(ids.map(id => api.get(`/cases/${id}`).catch(() => null)));
      allCases = snapshots.filter(s => s);
      renderView();
    } catch (e) {
      renderHead();
      setHTML('cases-tbody', `<tr><td colspan="8" class="muted">Error: ${esc(e.message)}</td></tr>`);
    }
  }

  // The stat cards filter the table and the column headers sort it.
  // Both survive a refresh and a trip to another screen (dashView).
  function renderView() {
    const filter = STAT_FILTERS.find(f => f.id === dashView.filter) || STAT_FILTERS[0];
    const shown = allCases.filter(filter.match);
    const col = CASE_COLUMNS.find(c => c.id === dashView.sortKey);
    if (col) {
      const dir = dashView.sortDir === 'desc' ? -1 : 1;
      shown.sort((a, b) => {
        const x = col.key(a), y = col.key(b);
        return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'en', { numeric: true })) * dir;
      });
    }
    renderStats(allCases);
    renderHead();
    renderTable(shown);
    const note = document.getElementById('cases-filter-note');
    if (note) {
      note.hidden = filter.id === 'all';
      note.innerHTML = filter.id === 'all' ? '' :
        `Showing ${shown.length} of ${allCases.length} cases: ${esc(filter.label.toLowerCase())}. <button class="btn btn-secondary btn-sm" id="cases-filter-clear">Show all</button>`;
      document.getElementById('cases-filter-clear')?.addEventListener('click', () => setFilter('all'));
    }
  }

  function setFilter(id) {
    // Clicking the active card again goes back to all cases.
    dashView.filter = (id === dashView.filter || id === 'all') ? 'all' : id;
    renderView();
    document.querySelector(`#stats-row [data-filter="${dashView.filter}"]`)?.focus();
  }

  function renderStats(cases) {
    setHTML('stats-row', STAT_FILTERS.map(f => {
      const on = (dashView.filter || 'all') === f.id;
      return `<button type="button" class="stat ${f.cls}" data-filter="${f.id}" aria-pressed="${on}" title="${f.id === 'all' || on ? 'Show all cases' : `Show ${esc(f.label.toLowerCase())} only`}">
        <div class="stat-val">${f.id === 'all' ? cases.length : cases.filter(f.match).length}</div><div class="stat-lbl">${f.label}</div></button>`;
    }).join(''));
    document.getElementById('stats-row')?.classList.toggle('filtering', (dashView.filter || 'all') !== 'all');
    document.querySelectorAll('#stats-row [data-filter]').forEach(b => b.addEventListener('click', () => setFilter(b.dataset.filter)));
  }

  function renderHead() {
    const head = document.getElementById('cases-head');
    if (!head) return;
    head.innerHTML = CASE_COLUMNS.map(c => {
      const sorted = dashView.sortKey === c.id;
      const aria = sorted ? (dashView.sortDir === 'desc' ? 'descending' : 'ascending') : 'none';
      const arrow = sorted ? (dashView.sortDir === 'desc' ? '▼' : '▲') : '↕';
      return `<th aria-sort="${aria}"><button type="button" class="th-sort" data-sort="${c.id}" title="Sort by ${c.label.toLowerCase()}">${c.label}<span class="sort-arrow" aria-hidden="true">${arrow}</span></button></th>`;
    }).join('') + '<th>Action</th>';
    head.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () => {
      // First click sorts ascending, second descending, third back to the server order.
      const id = b.dataset.sort;
      if (dashView.sortKey !== id) { dashView.sortKey = id; dashView.sortDir = 'asc'; }
      else if (dashView.sortDir === 'asc') dashView.sortDir = 'desc';
      else dashView.sortKey = null;
      renderView();
      document.querySelector(`#cases-head [data-sort="${id}"]`)?.focus();
    }));
  }

  function renderTable(cases) {
    const tbody = document.getElementById('cases-tbody');
    if (!cases.length && allCases.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted">No cases match this filter.</td></tr>`;
      return;
    }
    if (!cases.length) {
      tbody.innerHTML = `<tr><td colspan="8">
        <div class="empty-state">
          <div class="empty-state-icon">[ ]</div>
          <div class="empty-state-title">No cases found</div>
          <div class="empty-state-desc">The server seeds the demo scenarios when it starts with no cases; an Admin can also click "Seed Demo Cases". Or click "New Case" to raise one.</div>
        </div>
      </td></tr>`;
      return;
    }
    tbody.innerHTML = cases.map(c => {
      const obs = c.observation || {};
      // Confidence is 0.0 by default before a diagnosis exists -- showing
      // that as a confidence band would read as "Escalate" for a case
      // that was never diagnosed at all, contradicting the status column.
      // A record that failed verification, or that an auditor quarantined,
      // has no trustworthy score or status: say so instead of showing one.
      const frozen = c.audit_chain_valid === false || (c.sentinel_hold || {}).active;
      const untrusted = frozen || c.quarantined;
      const confCell = untrusted
        ? `<span class="badge badge-red">${c.quarantined ? 'not trusted (quarantined)' : 'not trusted until reviewed'}</span>`
        : c.knowledge_withdrawn
        ? `<span class="badge badge-red" title="${esc(c.knowledge_withdrawn)}">${(c.confidence * 100).toFixed(0)}% · knowledge withdrawn</span>`
        : c.diagnosis
        ? (() => {
            // "Escalated" only when the latest diagnosis ended in escalation
            // (still escalated, or closed from escalation). A case re-diagnosed
            // and approved since then reads as its current score.
            const hist = c.history || [];
            const lastIdx = states => hist.map(x => states.includes(x.to_state)).lastIndexOf(true);
            const escalatedLast = lastIdx(['ESCALATED']) > lastIdx(['RECOMMENDING', 'AWAITING_APPROVAL']);
            // Closed from escalation: a person resolved it, so it is not a
            // live red alarm next to "Resolved".
            if (escalatedLast && c.current_state === 'CLOSED') return `<span class="badge badge-grey">${(c.confidence * 100).toFixed(0)}% · resolved by an expert</span>`;
            const cb = confBand(c.confidence, escalatedLast ? 'ESCALATED' : c.current_state);
            return `<span class="badge ${cb.cls}">${cb.label}</span>`;
          })()
        : '<span class="muted">Not yet diagnosed</span>';
      const canAdv = c.current_state === 'GATHERING_EVIDENCE' && !untrusted;
      // The next step for this role, so nobody has to open the case to find it.
      const next = untrusted ? null
        : c.current_state === 'AWAITING_APPROVAL' && api.can('approve_reject_modify') ? ['decision', 'Decide']
        : c.current_state === 'ESCALATED' && api.can('approve_reject_modify') ? ['decision', 'Resolve']
        : ['MONITORING_OUTCOME', 'RECORDING_OUTCOME'].includes(c.current_state) && api.can('record_outcome') && (c.human_decision || {}).decided_by !== api.user() ? ['outcome', 'Record outcome']
        : c.current_state === 'EXECUTING' && api.can('approve_reject_modify') ? ['outcome', 'Work order']
        : null;
      return `<tr class="clickable" tabindex="0" role="link" aria-label="Open case ${c.case_id} on ${c.asset_id}" onclick="window.__app__.navigate('diagnosis', '${c.case_id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();window.__app__.navigate('diagnosis', '${c.case_id}')}">
        <td><code>${esc(c.case_id)}</code></td>
        <td><strong>${esc(c.asset_id)}</strong></td>
        <td>${esc((obs.type || '-').replace(/_/g, ' '))}</td>
        <td>${esc(obs.sensor_id || '-')}</td>
        <td>${esc(obs.reading_status ? readingText(obs.reading_status) : '-')}</td>
        <td>${c.quarantined ? '<span class="badge badge-red">Quarantined</span>'
          : c.audit_chain_valid === false ? '<span class="badge badge-red">Frozen: record failed verification</span>'
          : statePill(c.current_state)}${(c.sentinel_hold || {}).active ? ' <span class="badge badge-red">Stopped by sentinel</span>' : ''}</td>
        <td>${confCell}</td>
        <td onclick="event.stopPropagation()">
          ${canAdv && api.can('open_case') ? `<button class="btn btn-sm btn-primary" onclick="advCase('${c.case_id}', this)">Advance</button>`
            : next ? `<button class="btn btn-sm btn-primary" onclick="window.__app__.navigate('${next[0]}', '${c.case_id}')">${next[1]}</button>`
            : '<span class="muted">-</span>'}
        </td>
      </tr>`;
    }).join('');
  }

  window.advCase = async (id, btn) => {
    if (btn) { btn.disabled = true; btn.setAttribute('aria-busy', 'true'); btn.textContent = 'Running…'; }
    try {
      await thinking(api.post(`/cases/${id}/advance`));
      showToast('Agent advanced', 'success');
      window.__app__?.refreshSystemInfo?.();
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
    loadCases();
  };

  loadCases();
}

// ═══════════════════════════════════════════════════════════
// Screen 2: Diagnosis and Recommendation
// ═══════════════════════════════════════════════════════════
export function renderDiagnosis(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate } = h;
  const cid = state.caseId;
  // While the agent is diagnosing (possibly started from another screen or
  // session), poll until it finishes, then re-render: no "refresh" needed.
  let pollTimer = null;
  let diagnosingSince = null;
  const pollWhileDiagnosing = () => {
    if (pollTimer || state.screen !== 'diagnosis') return;
    pollTimer = setTimeout(() => { pollTimer = null; if (state.screen === 'diagnosis') load(); }, 2000);
  };

  el.innerHTML = '<div class="card skeleton-card"><div class="skeleton skeleton-line" style="width:30%"></div><div class="skeleton skeleton-line" style="width:50%"></div><div class="skeleton skeleton-line" style="width:80%"></div><div class="skeleton skeleton-line" style="width:40%"></div></div>';

  async function load() {
    try {
      const [s, expertKnowledge, sysInfo] = await Promise.all([
        api.get(`/cases/${cid}`),
        api.get(`/cases/${cid}/expert-knowledge`),
        api.get('/system/info'),
        loadCauses(),
      ]);
      if (s.current_state === 'DIAGNOSING') {
        diagnosingSince = diagnosingSince || Date.now();
        pollWhileDiagnosing();
      } else {
        diagnosingSince = null;
      }
      const obs = s.observation || {};
      const cb = s.diagnosis ? confBand(s.confidence, s.current_state) : { cls: 'badge-grey', label: 'Not yet diagnosed' };

      const nextHintText = (s.audit_chain_valid === false || (s.sentinel_hold || {}).active)
        ? 'this case is frozen: an auditor must review it on Governance.'
        : {
        GATHERING_EVIDENCE: api.can('open_case') ? 'click Advance Agent to run the decision tree.' : 'a technician or AOM runs the agent on this case next.',
        DIAGNOSING: `the agent is diagnosing (${Math.max(0, Math.floor((Date.now() - (diagnosingSince || Date.now())) / 1000))} s so far). This screen updates when it finishes.`,
        RECOMMENDING: 'a recommendation is being prepared.',
        AWAITING_APPROVAL: s.ledger_valid === false
          ? 'the knowledge ledger failed verification: approval waits for an auditor review on Governance.'
          : s.knowledge_withdrawn
          ? 'knowledge this diagnosis used was withdrawn: re-score it on AOM Decision before anyone approves it.'
          : api.can('approve_reject_modify')
          ? 'move to AOM Decision to approve, reject or modify it.'
          : 'an Asset Operations Manager reviews it on AOM Decision; you can follow it there.',
        EXECUTING: `approved: ${workOrderNext()} on the Outcome screen.`,
        MONITORING_OUTCOME: 'record the outcome once work is complete, on the Outcome screen.',
        RECORDING_OUTCOME: 'outcome recording is in progress.',
        FEEDBACK_QUEUED: 'feedback is queued for a knowledge steward to review.',
        ESCALATED: api.can('approve_reject_modify')
          ? 'move to AOM Decision to see why, and to resolve it.'
          : 'escalated to a person: an Asset Operations Manager resolves it on AOM Decision.',
        CLOSED: 'this case is closed; nothing further is needed.',
      }[s.current_state] || 'check back as the case progresses.';

      // Header
      let html = `${nextHint(nextHintText)}<div class="flex justify-between align-center" style="margin-bottom:16px">
        <div>
          <h2 style="font-size:20px;font-weight:700">${esc(s.case_id)}</h2>
          <div class="flex gap-8 flex-wrap" style="margin-top:6px;font-size:15px;color:var(--text-dim)">
            <span><strong>Asset:</strong> ${esc(s.asset_id)}</span>
            <span><strong>Sensor:</strong> ${esc(obs.sensor_id || '-')}</span>
            <span><strong>Fault:</strong> ${esc((obs.type || '-').replace(/_/g,' '))}</span>
            <span><strong>Detected:</strong> ${fmtTime(obs.detected_at)}</span>
            ${statePill(s.current_state)} <span class="badge ${cb.cls}">${cb.label}</span>
          </div>
        </div>
        <div>${s.current_state === 'GATHERING_EVIDENCE' && api.can('open_case') ? `<button class="btn btn-primary" id="btn-adv">Advance Agent</button>` : ''}</div>
      </div>`;

      if (s.knowledge_withdrawn) {
        html += `<div class="banner banner-error"><p><strong>Knowledge withdrawn:</strong> ${esc(s.knowledge_withdrawn)}. The confidence below may no longer hold; re-score on AOM Decision before approval.</p></div>`;
      }

      const T = { summary: '', evidence: '', ai: '', expert: '', scoring: '' };
      // Summary first: what the agent concluded and what happens next, so the
      // detail below is there to check, not to read through.
      const evsAll = s.evidence || [];
      const abnormalReadings = evsAll.flatMap(ev => (ev.abnormal || [])
        .filter(k => ev.payload && k in ev.payload)
        .map(k => `${_humaniseKey(k, ev.labels)}: ${_formatValue(k, ev.payload[k], true)}`));
      if (s.diagnosis) {
        const hypS = s.ai_hypothesis;
        const aiLine = !hypS ? 'not run'
          : hypS.status === 'unavailable' ? 'AI offline'
          : !hypS.hypothesis ? 'no independent opinion'
          : hypS.agrees_with_rules ? `agrees (${causeLabel(hypS.hypothesis)})`
          : `disagrees: suggests ${causeLabel(hypS.hypothesis)} (G9, advisory)`;
        const firstAction = s.recommendation && (s.recommendation.actions || [])[0];
        T.summary += `<div class="card summary-card"><div class="card-body">
          <div class="summary-grid">
            <div><div class="summary-lbl">Likely cause</div><div class="summary-val">${esc(causeLabel(s.diagnosis.top_cause_id))}</div></div>
            <div><div class="summary-lbl">Confidence</div><div class="summary-val"><span class="badge ${cb.cls}">${cb.label}</span></div></div>
            <div><div class="summary-lbl">AI second opinion</div><div class="summary-val">${esc(aiLine)}</div></div>
            <div><div class="summary-lbl">Recommendation</div><div class="summary-val">${firstAction ? esc(firstAction.detail) : '<span class="muted">none: a person decides</span>'}</div></div>
          </div>
          <div class="summary-row"><span class="summary-lbl">Abnormal readings</span> ${abnormalReadings.length ? abnormalReadings.map(r => `<span class="badge badge-red">${esc(r)}</span>`).join(' ') : '<span class="muted">none flagged</span>'}</div>
        </div></div>`;
      }

      // Two-column: evidence + diagnosis
      const abnormalCount = evsAll.filter(ev => (ev.abnormal || []).length).length;
      T.evidence += `<div class="grid-2">
        <div class="card"><div class="card-header"><h3>Evidence Timeline</h3><div class="flex align-center gap-8"><span class="muted">${abnormalCount && !_evidenceShowAll ? `${abnormalCount} of ${evsAll.length} abnormal` : `${evsAll.length} items`}</span>${abnormalCount && abnormalCount < evsAll.length ? `<button class="evidence-toggle" id="btn-ev-all">${_evidenceShowAll ? 'Abnormal only' : 'Show all'}</button>` : ''}<button class="evidence-toggle" id="btn-ev-toggle">${_evidenceRawMode ? 'Plain English' : 'Raw JSON'}</button></div></div><div class="card-body">
          <span class="tier-label tier-fact">Sensor readings (facts)</span>
          <div id="ev-body"></div>
        </div></div>
        <div class="card"><div class="card-header"><h3>Decision-Tree Diagnosis</h3></div><div class="card-body">
          <span class="tier-label tier-fact">Deterministic — rule-based diagnosis (expert decision tree)</span>
          <div id="diag-body"></div>
        </div></div>
      </div>`;

      T.ai += `<div class="card"><div class="card-header">
          <div class="flex align-center gap-8">
            <span class="card-cloud" id="ai-avatar"></span>
            <h3>AI Second Opinion</h3>
          </div>
          <span class="badge badge-purple">AI HARVEST</span>
        </div><div class="card-body" id="ai-opinion-body"></div></div>`;

      // Recommendation
      T.summary += `<div class="card"><div class="card-header"><h3>Recommended Action</h3></div><div class="card-body">
        <span class="tier-label tier-action">Recommended action (from approved knowledge)</span>
        <div id="rec-body"></div>
      </div></div>`;

      T.expert += `<div class="card"><div class="card-header"><h3>Expert Knowledge Reused</h3><span class="badge badge-purple">AI HARVEST</span></div><div class="card-body" id="expert-knowledge-body"></div></div>`;

      // The working behind the summary: its own tab.
      const firedCount = ((s.guardrail_result || {}).rule_ids || []).length;
      T.scoring += `<div class="card"><div class="card-header"><h3>Confidence breakdown (W1-W5)</h3></div><div class="card-body" id="conf-body"></div></div>`;
      T.scoring += `<div class="card"><div class="card-header"><h3>Guardrail engine (G1-G9)</h3><span class="muted">${s.guardrail_result ? (firedCount ? `${firedCount} rule(s) fired` : 'no rule fired') : 'not run yet'}</span></div><div class="card-body" id="gr-body"></div></div>`;

      const hypT = s.ai_hypothesis || {};
      html += tabbed('diag', [
        { id: 'summary', label: 'Summary', html: T.summary || '<div class="banner banner-info"><p>Not yet diagnosed.</p></div>' },
        { id: 'evidence', label: 'Evidence', note: abnormalCount ? `${abnormalCount} abnormal` : '', html: T.evidence },
        { id: 'ai', label: 'AI second opinion', note: hypT.status === 'ok' && hypT.hypothesis && !hypT.agrees_with_rules ? 'disagrees' : '', html: T.ai },
        { id: 'expert', label: 'Expert knowledge', html: T.expert },
        { id: 'scoring', label: 'Scoring', html: T.scoring },
      ]);

      el.innerHTML = frozenWrap(s, html, esc);

      // Render evidence
      const evBody = document.getElementById('ev-body');
      const evs = abnormalCount && !_evidenceShowAll ? evsAll.filter(ev => (ev.abnormal || []).length) : evsAll;
      if (!evs.length) {
        evBody.innerHTML = s.current_state === 'GATHERING_EVIDENCE'
          ? `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No evidence gathered yet</div><div class="empty-state-desc">Click "Advance Agent" to collect sensor readings, BMS data and history.</div></div>`
          : `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No evidence</div><div class="empty-state-desc">Nothing was gathered: this asset is not in the registry, so the pill has no data source for it and escalated it to a human (G5).</div></div>`;
      } else {
        evBody.innerHTML = evs.map(ev => {
          const src = ev.source || 'unknown';
          const payload = JSON.stringify(ev.payload, null, 2);
          const payloadHtml = _evidenceRawMode
            ? `<pre class="evidence-payload">${esc(payload)}</pre>`
            : renderEvidencePlain(ev.payload, ev.abnormal || [], ev.labels || {});
          return `<div class="evidence-item">
            <div class="evidence-dot dot-${src}"></div>
            <div style="flex:1;min-width:0">
              <div class="evidence-head">
                <span class="evidence-src src-${src}">${esc(src)}</span>
                <span class="muted">${esc(ev.type || '')}</span>
                <span class="evidence-meta">${fmtTime(ev.retrieved_at)}</span>
              </div>
              ${payloadHtml}
            </div>
          </div>`;
        }).join('');
      }

      // Render diagnosis
      const diagBody = document.getElementById('diag-body');
      if (!s.diagnosis) {
        diagBody.innerHTML = `<div class="banner banner-info"><p>The agent has not yet produced a diagnosis.</p>${s.current_state === 'GATHERING_EVIDENCE' ? '<p>Click <strong>Advance Agent</strong> to run the decision tree.</p>' : ''}</div>`;
      } else {
        const diag = s.diagnosis;
        const causes = (diag.candidate_causes || []).map(c => {
          const top = c.id === diag.top_cause_id;
          const evRefs = (c.evidence_refs || []).map(kbRef).join(', ') || '—';
          return `<div style="padding:10px;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;${top ? 'border-color:var(--green);background:var(--green-bg);' : ''}">
            ${top ? '<span class="badge badge-green">Top</span> ' : ''}<strong>${esc(causeLabel(c.id))}</strong>
            <span class="muted" style="margin-left:auto;font-size:14px">Evidence: ${evRefs}</span>
          </div>`;
        }).join('');
        diagBody.innerHTML = `
          <div style="font-size:16px;margin-bottom:8px"><span class="muted">Root Cause:</span> <strong style="color:var(--blue-text)">${esc(causeLabel(diag.top_cause_id))}</strong></div>
          ${diag.kb_refs && diag.kb_refs.length ? `<div class="muted" style="margin-bottom:8px">Knowledge used: ${diag.kb_refs.map(kbRef).join(', ')}</div>` : ''}
          <h4 style="margin:14px 0 8px">Candidate Causes</h4>
          ${causes}
        `;
      }

      // Render AI second opinion (advisory, never affects routing)
      const aiBody = document.getElementById('ai-opinion-body');
      const aiAvatar = document.getElementById('ai-avatar');
      const hyp = s.ai_hypothesis;
      if (!hyp) {
        aiBody.innerHTML = `<div class="banner banner-info"><p>No AI second opinion yet. It runs alongside the decision tree when the agent is advanced.</p></div>`;
        if (aiAvatar) aiAvatar.innerHTML = cloudSvg('ready', 34);
      } else {
        const modelLabel = hyp.status === 'unavailable' ? 'AI offline' : (sysInfo.llm_label || 'AI model');
        const agrees = hyp.agrees_with_rules;
        const mood = hyp.status === 'unavailable' ? 'offline' : !hyp.hypothesis ? 'ready' : agrees ? 'online' : 'alert';
        if (aiAvatar) aiAvatar.innerHTML = cloudSvg(mood, 34);
        if (mood === 'alert') cloudMood('alert');
        aiBody.innerHTML = `
          <span class="tier-label tier-ai">AI hypothesis — advisory only, does not affect routing</span>
          <div class="flex gap-8 align-center flex-wrap" style="margin:8px 0">
            <span class="badge ${hyp.status === 'unavailable' ? 'badge-red' : 'badge-purple'}">${esc(modelLabel)}</span>
            ${hyp.status === 'ok' ? (hyp.hypothesis
              ? `<span class="badge ${agrees ? 'badge-green' : 'badge-yellow'}">${agrees ? 'Agrees with rule-based diagnosis' : 'Disagrees with rule-based diagnosis (G9)'}</span>`
              : '<span class="badge badge-grey">No independent opinion</span>') : ''}
          </div>
          ${hyp.hypothesis ? `<div style="margin-bottom:8px"><span class="muted">AI hypothesis:</span> <strong>${esc(causeLabel(hyp.hypothesis))}</strong></div>` : ''}
          <p class="muted" style="margin-bottom:8px">${esc(prose(hyp.summary || ''))}</p>
          ${hyp.supporting_evidence && hyp.supporting_evidence.length ? `<div><strong>Supporting:</strong><ul class="expert-list">${hyp.supporting_evidence.map(e => `<li>${esc(prose(e))}</li>`).join('')}</ul></div>` : ''}
          ${hyp.conflicting_evidence && hyp.conflicting_evidence.length ? `<div><strong>Conflicting:</strong><ul class="expert-list">${hyp.conflicting_evidence.map(e => `<li>${esc(prose(e))}</li>`).join('')}</ul></div>` : ''}
          ${hyp.missing_evidence && hyp.missing_evidence.length ? `<div><strong>Would help:</strong><ul class="expert-list">${hyp.missing_evidence.map(e => `<li>${esc(prose(e))}</li>`).join('')}</ul></div>` : ''}
          ${hyp.recommended_next_check ? `<div class="muted" style="margin-top:8px"><strong>Suggested next check:</strong> ${esc(prose(hyp.recommended_next_check))}</div>` : ''}
          <div class="muted" style="margin-top:10px">The AOM decides. This card never approves, executes or changes the case.</div>
        `;
      }

      const expertBody = document.getElementById('expert-knowledge-body');
      if (!s.diagnosis) {
        expertBody.innerHTML = `<div class="banner banner-info"><p>Approved expert heuristics will appear here when they match the diagnosed cause and asset type.</p></div>`;
      } else if (!expertKnowledge.matches.length && (expertKnowledge.withheld || []).length) {
        expertBody.innerHTML = `<div class="banner banner-warn"><p>${expertKnowledge.withheld.length} approved heuristic(s) for this cause were withheld: ${esc(expertKnowledge.withheld[0].reason)}. A steward should revoke them on Governance.</p></div>`;
      } else if (!expertKnowledge.matches.length) {
        expertBody.innerHTML = `<div class="banner banner-info"><p>No approved expert heuristic matches this asset type and the diagnosed cause (${esc(causeLabel(expertKnowledge.cause_id))}).</p><p>The diagnosis and recommendation remain governed by the deterministic decision tree.</p></div>`;
      } else {
        expertBody.innerHTML = `
          <p class="muted expert-reuse-intro">Supporting knowledge from a steward-approved expert interview. Match basis: ${esc(expertKnowledge.match_basis)}. The decision tree remains authoritative.</p>
          ${expertKnowledge.matches.map(item => `
            <article class="expert-match">
              <div class="flex justify-between align-center flex-wrap gap-8">
                <div><strong>${esc(item.expert_name)}</strong> <span class="muted">— ${esc(item.expert_role)}</span></div>
                <span class="badge badge-green">Cause + asset matched</span>
              </div>
              <div class="expert-meta">
                <span><strong>Knowledge ID:</strong> <code>${esc(item.knowledge_id)}</code></span>
                <span><strong>Knowledge version:</strong> ${esc(item.kb_version_label)}</span>
                <span><strong>Approved by:</strong> ${esc(item.approved_by)}${item.safety_reviewed_by ? ' (safety-reviewed)' : ''}</span>
                <span><strong>Cause:</strong> ${esc(causeLabel(item.likely_cause))}</span>
              </div>
              <p><strong>When:</strong> ${esc(whenText(item.symptom_pattern))}</p>
              ${corroboration(item, esc)}
              ${item.checks.length ? `<div><strong>Expert checks:</strong><ul class="expert-list">${item.checks.map(check => `<li>${esc(check)}</li>`).join('')}</ul></div>` : ''}
              ${item.do_not.length ? `<div><strong>Never:</strong><ul class="expert-list">${item.do_not.map(caution => `<li>${esc(caution)}</li>`).join('')}</ul></div>` : ''}
              ${(item.escalate_when || []).length ? `<div><strong>Escalate when:</strong><ul class="expert-list">${item.escalate_when.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
              <blockquote class="expert-quote">“${esc(item.evidence_quote)}”</blockquote>
            </article>
          `).join('')}
          ${(expertKnowledge.withheld || []).length ? `<div class="banner banner-warn" style="margin-top:10px"><p>${expertKnowledge.withheld.length} more heuristic(s) withheld: ${esc(expertKnowledge.withheld[0].reason)}.</p></div>` : ''}
          <div class="muted" style="margin-top:10px">Current KB: ${esc(expertKnowledge.kb_version)} · Expert knowledge informs context; it does not override the deterministic diagnosis or guardrails.</div>
        `;
      }

      // Render confidence breakdown
      const confBody = document.getElementById('conf-body');
      if (!s.diagnosis) {
        // Confidence defaults to 0.0 before any diagnosis runs; showing a
        // band for that reads as "Escalate" for a case nothing has judged
        // yet, contradicting a status column that says "Not yet diagnosed".
        confBody.innerHTML = `<div class="banner banner-info"><p>Not yet diagnosed. Confidence appears once the decision tree produces a diagnosis.</p></div>`;
      } else {
      const confVal = s.confidence !== null && s.confidence !== undefined ? (s.confidence * 100).toFixed(1) + '%' : 'N/A';
      const confPct = (s.confidence * 100).toFixed(1);
      const confCls = s.confidence < 0.35 ? 'low' : (s.confidence < 0.55 ? 'medium' : 'high');
      const confBandLabel = s.confidence < 0.35 ? 'Escalate' : (s.confidence < 0.55 ? 'Medium / Needs scrutiny' : 'Recommendable');
      confBody.innerHTML = `
        <div style="font-size:18px;margin-bottom:8px"><strong>Confidence: ${confVal}</strong> <span class="badge badge-${s.confidence < 0.35 ? 'red' : (s.confidence < 0.55 ? 'yellow' : 'green')}">${confBandLabel}</span></div>
        <div class="conf-meter-wrap">
          <div class="conf-meter-track">
            <div class="conf-meter-thresholds">
              <div class="conf-threshold-mark" style="left:35%"></div>
              <div class="conf-threshold-mark" style="left:55%"></div>
            </div>
            <div class="conf-meter-fill ${confCls}" style="width:${confPct}%"></div>
          </div>
          <div class="conf-meter-labels">
            <span>0%</span>
            <span style="color:var(--red)">Escalate (0.35)</span>
            <span style="color:var(--yellow)">Min reco (0.55)</span>
            <span>100%</span>
          </div>
        </div>
        <div class="conf-breakdown">
          ${WEIGHTS.map(w => {
            const breakdown = s.confidence_breakdown || {};
            const factor = breakdown[w.key];
            const hasFactor = typeof factor === 'number';
            return `
            <div class="conf-item">
              <div class="conf-w">${w.id} ${w.sign} ${w.val.toFixed(2)}</div>
              <div class="conf-v">${hasFactor ? factor.toFixed(2) : '—'}</div>
              <div class="conf-bar-track"><div class="conf-bar-fill ${w.sign === '-' ? 'penalty' : ''}" style="width:${hasFactor ? (factor * 100).toFixed(0) : 0}%"></div></div>
              <div class="conf-l">${w.label}</div>
            </div>
          `;
          }).join('')}
        </div>
        <div class="muted" style="margin-top:12px">confidence = W1*evidence_coverage + W2*peer_agreement + W3*kb_match - W4*staleness - W5*conflict</div>
        <div class="muted" style="margin-top:4px">KB version used: <strong>${esc((s.confidence_breakdown && s.confidence_breakdown.kb_version_label) || 'not yet diagnosed')}</strong></div>
      `;
      }

      // Render recommendation
      const recBody = document.getElementById('rec-body');
      // A G3-escalated case can carry a bookkeeping Recommendation (kb_refs
      // + evidence_refs only, no actions -- see app.py's G3-after-G4 path)
      // purely so the guardrail engine has something to evaluate. Treat it
      // as "no recommendation" for display: an empty "Recommended Action"
      // card on an escalated case reads as a contradiction otherwise.
      const hasRecommendation = s.recommendation && (s.recommendation.actions || []).length > 0;
      if (!hasRecommendation) {
        // The escalation reason always comes from the guardrail result that
        // actually fired (G1-G9) -- never a hardcoded rule or threshold,
        // since any of several guardrails (not only low confidence) can
        // be why a case has no recommendation.
        const escReasons = (s.guardrail_result && s.guardrail_result.reasons) || [];
        recBody.innerHTML = `<div class="banner banner-info"><p>No recommendation has been produced yet.</p>${
          s.current_state === 'ESCALATED'
            ? (escReasons.length
                ? `<p><strong>Case escalated.</strong></p><ul style="margin:4px 0 0 18px">${escReasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`
                : '<p><strong>Case escalated.</strong></p>')
            : ''
        }</div>`;
      } else {
        const rec = s.recommendation;
        const actions = (rec.actions || []).map(a => `
          <div style="display:flex;gap:12px;padding:12px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border);margin-bottom:8px">
            <span class="badge badge-blue">${esc(plain(a.type))}</span>
            <div><div><strong>Target:</strong> ${esc(plain(a.target))}</div><div><strong>Detail:</strong> ${esc(a.detail)}</div></div>
          </div>
        `).join('');
        recBody.innerHTML = `${actions}
          <div class="muted" style="margin-top:8px"><strong>Grounded in evidence:</strong> ${(rec.evidence_refs||[]).map(r => esc(plain(r))).join(', ') || 'none'}</div>
          <div class="muted" style="margin-top:4px"><strong>Knowledge used:</strong> ${(rec.kb_refs||[]).map(kbRef).join(', ') || 'none'}</div>
        `;
      }

      // Render guardrail grid
      const grBody = document.getElementById('gr-body');
      const gr = s.guardrail_result;
      const firedRules = gr ? (gr.rule_ids || []) : [];
      grBody.innerHTML = `
        ${gr ? `<div class="flex gap-8" style="margin-bottom:12px">
          ${gr.allowed && !gr.must_escalate ? '<span class="badge badge-green">Allowed</span>' : '<span class="badge badge-red">Blocked / Escalated</span>'}
          ${gr.requires_approval ? '<span class="badge badge-yellow">Requires Approval (G6)</span>' : ''}
        </div>` : '<p class="muted">No guardrail run yet.</p>'}
        <div class="gr-grid">
          ${GUARDRAILS.map(g => {
            const fired = firedRules.includes(g.id);
            return `<div class="gr-cell ${fired ? 'gr-fired' : 'gr-ok'}">
              <div class="gr-id">${g.id}</div>
              <div class="gr-desc">${g.desc}</div>
            </div>`;
          }).join('')}
        </div>
        ${gr && gr.reasons && gr.reasons.length ? `<ul style="margin-top:12px;list-style:none;padding:0">${gr.reasons.map(r => `<li style="padding:6px 0;border-bottom:1px solid var(--border);font-size:14px;color:var(--text-dim)">${esc(r)}</li>`).join('')}</ul>` : ''}
      `;

      // Wire advance button
      const advBtn = document.getElementById('btn-adv');
      if (advBtn) {
        advBtn.onclick = async () => {
          // A live model call can take several seconds: show it is running
          // and stop a second click starting another advance.
          advBtn.disabled = true;
          advBtn.setAttribute('aria-busy', 'true');
          const started = Date.now();
          const tick = () => { advBtn.textContent = `Gathering evidence and diagnosing… ${Math.floor((Date.now() - started) / 1000)} s`; };
          tick();
          const timer = setInterval(tick, 1000);
          try {
            await thinking(api.post(`/cases/${cid}/advance`));
            clearInterval(timer);
            showToast('Agent advanced', 'success');
            window.__app__?.refreshSystemInfo?.();
            load();
          } catch (e) {
            clearInterval(timer);
            showToast(`Error: ${e.message}`, 'error');
            advBtn.disabled = false;
            advBtn.removeAttribute('aria-busy');
            advBtn.textContent = 'Advance Agent';
          }
        };
      }
      const evAllBtn = document.getElementById('btn-ev-all');
      if (evAllBtn) evAllBtn.onclick = () => { _evidenceShowAll = !_evidenceShowAll; load(); };

      // Wire evidence toggle button
      const evToggleBtn = document.getElementById('btn-ev-toggle');
      if (evToggleBtn) {
        evToggleBtn.onclick = () => {
          _evidenceRawMode = !_evidenceRawMode;
          load();
        };
      }
    } catch (e) {
      el.innerHTML = `<div class="banner banner-error">Error: ${esc(e.message)}</div>`;
    }
  }

  load();
}

// ═══════════════════════════════════════════════════════════
// Screen 3: AOM Decision
// ═══════════════════════════════════════════════════════════
export function renderDecision(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate } = h;
  const cid = state.caseId;

  el.innerHTML = '<div class="card skeleton-card"><div class="skeleton skeleton-line" style="width:30%"></div><div class="skeleton skeleton-line" style="width:50%"></div><div class="skeleton skeleton-line" style="width:80%"></div><div class="skeleton skeleton-line" style="width:40%"></div></div>';

  async function load() {
    try {
      const [s, ek] = await Promise.all([
        api.get(`/cases/${cid}`),
        api.get(`/cases/${cid}/expert-knowledge`).catch(() => ({ matches: [] })),
        loadCauses(),
      ]);

      // Check RBAC
      const role = api.user();
      const canApprove = api.can('approve_reject_modify');
      const hazardReason = ((s.guardrail_result && s.guardrail_result.reasons) || [])
        .find(r => r.startsWith('[G2b]') || r.startsWith('[G2]'));
      if (s.ai_hypothesis && s.ai_hypothesis.status === 'ok' && s.ai_hypothesis.hypothesis && !s.ai_hypothesis.agrees_with_rules) cloudMood('alert');

      const decisionHint = (s.audit_chain_valid === false || (s.sentinel_hold || {}).active)
        ? 'this case is frozen: an auditor must review it on Governance.'
        : s.current_state === 'ESCALATED'
        ? (canApprove ? 'resolve the escalation below, or request more evidence to have the agent gather and diagnose it again.'
                      : 'escalated: an Asset Ops Manager or expert resolves it or requests more evidence.')
        : s.current_state === 'AWAITING_APPROVAL'
        ? (!canApprove ? 'an Asset Ops Manager needs to approve, reject or modify this.'
          : s.knowledge_withdrawn ? (s.ledger_valid === false
            ? 'knowledge it relied on is withheld until an auditor reviews the ledger; you can still reject.'
            : 're-score the case against the current knowledge first; you can still reject.')
          : 'approve or modify to raise a work order, or reject to close the case.')
        : s.current_state === 'EXECUTING'
        ? `approved: ${workOrderNext()} on the Outcome screen.`
        : s.current_state === 'MONITORING_OUTCOME'
        ? 'work order raised: record the outcome on the Outcome screen once the work is done.'
        : 'this case has no pending decision right now.';
      // On a projector the controls sit below the fold: one click takes the
      // AOM straight to them, after the facts at the top of the page.
      const jump = s.current_state === 'AWAITING_APPROVAL' && canApprove && s.audit_chain_valid !== false && !(s.sentinel_hold || {}).active
        ? ' <button class="btn btn-primary btn-sm" id="btn-jump-decide">Go to the decision ↓</button>' : '';
      const head = `${nextHint(decisionHint)}<h2 style="font-size:20px;margin-bottom:16px">AOM Decision - ${esc(cid)}${jump}</h2>`;
      let html = head;
      let expertTab = '';

      // Show recommendation (read-only). A G3-escalated case can carry a
      // bookkeeping Recommendation with no actions (see app.py's
      // G3-after-G4 path) -- treat that as "no recommendation" here too,
      // so it falls through to the escalation panel below instead of a
      // hollow "Recommendation Under Review" card.
      if (s.current_state !== 'ESCALATED' && s.recommendation && (s.recommendation.actions || []).length > 0) {
        // Safety/environmental hazard (G2b) belongs right next to the
        // decision itself -- not only in the Diagnosis screen's guardrail
        // grid, which an approver reviewing here may never have scrolled to.
        if (s.knowledge_withdrawn) {
          html += `<div class="banner banner-error"><p><strong>Knowledge withdrawn:</strong> ${esc(s.knowledge_withdrawn)}. ${s.ledger_valid === false ? 'Approval is blocked until an auditor reviews the knowledge ledger on Governance.' : 'The confidence below may no longer hold, so approval is blocked until the case is re-scored against the current knowledge base.'}</p>
            ${canApprove && s.ledger_valid !== false ? '<button class="btn btn-primary mt-16" id="btn-rescore">Re-score against current knowledge</button>' : ''}</div>`;
        }
        const decidedAs = s.human_decision && { approve: 'Approved', reject: 'Rejected', modify: 'Modified' }[s.human_decision.decision];
        html += `<div class="card"><div class="card-header"><h3>${decidedAs ? `Recommendation (${decidedAs})` : 'Recommendation Under Review'}</h3></div><div class="card-body">
          ${hazardReason ? `<div class="banner banner-warn" style="margin-bottom:12px"><p><strong>⚠ Safety/environmental hazard:</strong> ${esc(hazardReason.replace(/^\[G2b?\]\s*/, ''))}</p></div>` : ''}
          ${decisionFacts(s, esc, confBand)}`;
        html += `
          <span class="tier-label tier-action">Recommended action (read-only)</span>
          <span class="tier-label tier-human">Your decision ${decidedAs ? '(recorded below)' : '(below)'}</span>`;
        html += s.recommendation.actions.map(a => `
          <div style="display:flex;gap:12px;padding:12px;background:var(--bg-input);border-radius:6px;margin-bottom:8px">
            <span class="badge badge-blue">${esc(plain(a.type))}</span>
            <div><div><strong>Target:</strong> ${esc(plain(a.target))}</div><div><strong>Detail:</strong> ${esc(a.detail)}</div></div>
          </div>
        `).join('');
        expertTab = expertChecks(ek, esc);
        html += `</div></div>`;
      } else if (s.current_state === 'CLOSED' && s.history.some(e => e.from_state === 'ESCALATED' && e.to_state === 'CLOSED')) {
        const res = s.history.find(e => e.from_state === 'ESCALATED' && e.to_state === 'CLOSED');
        html += `<div class="card"><div class="card-header"><h3>Escalation Resolved</h3><span class="badge badge-green">Closed</span></div><div class="card-body">
          <p><strong>Resolved by:</strong> ${esc(res.actor)} at ${fmtTime(res.at)}</p>
          <p style="margin-top:8px"><strong>Resolution:</strong> ${esc(res.reason.replace(/^escalation resolved by [^:]+:\s*/, ''))}</p>
          <p class="muted" style="margin-top:8px">If a confirmed cause was given when closing, the resolution was also sent to a knowledge steward on Governance.</p>
        </div></div>`;
      } else if (s.current_state === 'ESCALATED') {
        // Why it escalated always comes from the guardrail result that
        // actually fired -- G1-G9, never a hardcoded rule or threshold
        // (several different guardrails can escalate a case, not only G4).
        const gr = s.guardrail_result;
        const reasons = (gr && gr.reasons) || [];
        const g3Reason = reasons.find(r => r.includes('[G3]'));
        const whoToCallMatch = g3Reason && g3Reason.match(/maps to ([^;]+);/);
        const whoToCall = whoToCallMatch ? whoToCallMatch[1].trim() : null;

        html += `<div class="banner banner-error">
          <p><strong>Case escalated.</strong> No recommendation; approve, reject or modify is not available.</p>
          ${reasons.length
            ? `<ul style="margin:8px 0 0 18px">${reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`
            : '<p>No guardrail reason was recorded for this escalation.</p>'}
        </div>`;
        if (whoToCall) {
          html += `<div class="banner banner-info"><p><strong>Who to call:</strong> ${esc(whoToCall)}</p></div>`;
        }
        if (s.diagnosis && s.diagnosis.top_cause_id !== 'unresolvable') {
          // The AOM resolving an escalation sees the same facts an approver would.
          html += `<div class="card"><div class="card-header"><h3>What the pill found</h3></div><div class="card-body">
            ${decisionFacts(s, esc, confBand)}${expertChecks(ek, esc)}</div></div>`;
        }
        if (s.audit_chain_valid !== false) {
          html += `<div class="card"><div class="card-header"><h3>Resolve Escalation</h3></div><div class="card-body" id="esc-actions"></div></div>`;
        }
      } else if (!s.human_decision) {
        html += `<div class="banner banner-info"><p>No recommendation to review yet. Case status: ${statePill(s.current_state)}</p></div>`;
      }

      // Show existing decision if any
      if (s.human_decision) {
        const hd = s.human_decision;
        const cls = hd.decision === 'approve' ? 'badge-green' : (hd.decision === 'reject' ? 'badge-red' : 'badge-blue');
        html += `<div class="card"><div class="card-header"><h3>Decision Record</h3></div><div class="card-body">
          <p><span class="badge ${cls}">${esc(hd.decision)}</span> by <strong>${esc(hd.decided_by)}</strong> at ${fmtTime(hd.timestamp)}</p>
          ${hd.rationale ? `<p style="margin-top:8px;font-style:italic">"${esc(hd.rationale)}"</p>` : ''}
          ${(hd.expert_knowledge || []).length ? `<div class="mt-16"><span class="tier-label tier-advisory">Expert knowledge in force when this was decided</span>
            ${hd.expert_knowledge.map(m => `<div class="muted" style="margin-top:6px"><strong>${esc(m.expert_name)}</strong> · ${esc(m.kb_version_label)} · <code>${esc(m.knowledge_id)}</code> — “${esc(m.evidence_quote)}”</div>`).join('')}</div>` : ''}
          ${hd.modified_actions ? `<div class="mt-16">
            <span class="tier-label tier-human">Human-Validated</span>
            <div class="diff-grid">
              <div class="diff-col original">
                <div class="diff-col-header">Original Actions (Recommended)</div>
                <div class="diff-col-body">
                  ${(hd.original_actions || []).map(a => `<div class="diff-field"><div class="diff-field-label">Type</div><div class="diff-field-value">${esc(plain(a.type))}</div><div class="diff-field-label">Target</div><div class="diff-field-value">${esc(plain(a.target))}</div><div class="diff-field-label">Detail</div><div class="diff-field-value">${esc(a.detail)}</div></div>`).join('')}
                </div>
              </div>
              <div class="diff-col modified">
                <div class="diff-col-header">Modified Actions (Human-Adjusted)</div>
                <div class="diff-col-body">
                  ${hd.modified_actions.map(a => `<div class="diff-field"><div class="diff-field-label">Type</div><div class="diff-field-value">${esc(plain(a.type))}</div><div class="diff-field-label">Target</div><div class="diff-field-value">${esc(plain(a.target))}</div><div class="diff-field-label">Detail</div><div class="diff-field-value">${esc(a.detail)}</div></div>`).join('')}
                </div>
              </div>
            </div>
          </div>` : ''}
        </div></div>`;
      } else if (s.current_state === 'AWAITING_APPROVAL' && s.audit_chain_valid !== false && !(s.sentinel_hold || {}).active) {
        // Show decision controls (never on a frozen case: the server refuses them)
        if (!canApprove) {
          html += `<div class="banner banner-error"><p><strong>Approval Blocked</strong></p><p>You are signed in as ${esc(role)} (${esc(h.roleDisplayName(role))}); that role cannot approve, reject or modify.</p><p>Switch to Asset Operations Manager (mgr1) to approve, reject, or modify.</p></div>`;
        } else {
          html += `<div class="card" id="decision-controls"><div class="card-header"><h3>Decision Controls</h3></div><div class="card-body">
            <div class="flex gap-8" style="margin-bottom:16px">
              ${s.knowledge_withdrawn ? '' : '<button class="btn btn-green" id="btn-approve">Approve</button>'}
              <button class="btn btn-red" id="btn-reject">Reject</button>
              ${s.knowledge_withdrawn ? '' : '<button class="btn btn-secondary" id="btn-modify">Modify</button>'}
            </div>
            ${s.knowledge_withdrawn ? `<p class="muted" style="margin-bottom:12px">${s.ledger_valid === false ? 'Approve and Modify return once an auditor reviews the knowledge ledger on Governance.' : 'Approve and Modify return once the case is re-scored.'} Reject is still available.</p>` : ''}
            <div id="decision-form"></div>
          </div></div>`;
        }
      }

      if (expertTab) {
        html = head + tabbed('decision', [
          { id: 'decide', label: 'Decision', html: html.slice(head.length) },
          { id: 'expert', label: 'Expert knowledge to apply', note: (ek.matches || []).length ? String(ek.matches.length) : '', html: expertTab },
        ]);
      }
      el.innerHTML = frozenWrap(s, html, esc);

      // Wire escalation resolution controls (role-gated: approve_reject_modify)
      const escBody = document.getElementById('esc-actions');
      if (escBody) {
        if (!canApprove) {
          escBody.innerHTML = `<p class="muted">Resolving an escalation requires the Asset Ops Manager role. Switch role in the top bar.</p>`;
        } else {
          const kc = s.knowledge_changed;
          escBody.innerHTML = `
            ${kc ? `<div class="banner banner-warn" style="margin-bottom:12px"><p><strong>Knowledge has changed since this was scored.</strong> It was scored on ${esc(kc.scored_on)}; ${esc(kc.pill)} is now ${esc(kc.now)}. Re-diagnosing uses the current knowledge.</p>
              <button class="btn btn-primary mt-16" id="btn-esc-rediag">Re-diagnose against current knowledge</button></div>` : ''}
            <div class="form-group"><label for="esc-reason">Reason or resolution</label><input id="esc-reason" type="text" placeholder="e.g. BMS vendor replaced controller CTL-02; tags reporting again"></div>
            ${s.asset_type === 'UNKNOWN' ? '<p class="muted" style="margin-bottom:8px">This asset is not in the registry, so there is no data source to re-query. Close it with what was found, and register the asset if the pill should cover it.</p>' : ''}
            <div class="form-group"><label for="esc-cause">Confirmed cause (optional: sends this resolution to a knowledge steward so the pill can learn it)</label>
              <select id="esc-cause"><option value="">-- not confirmed --</option>${causeOptions((_causes || []).filter(c => c.asset_type === s.asset_type))}</select></div>
            <div class="flex gap-8 flex-wrap">
              ${s.asset_type === 'UNKNOWN' ? '' : '<button class="btn btn-secondary" id="btn-esc-evidence">Request more evidence (reason required)</button>'}
              <button class="btn btn-red" id="btn-esc-close">Close escalation (resolution required)</button>
            </div>
          `;
          const btnRe = document.getElementById('btn-esc-rediag');
          if (btnRe) btnRe.onclick = async () => {
            btnRe.disabled = true; btnRe.setAttribute('aria-busy', 'true');
            btnRe.textContent = 'Re-diagnosing against current knowledge… (about 15 s)';
            try {
              const r = await thinking(api.post(`/cases/${cid}/escalation/evidence`, { reason: `re-diagnosed against current ${kc.now} knowledge (scored on ${kc.scored_on})` }));
              showToast(`Re-diagnosed: ${plain(r.current_state).toLowerCase()} at ${Math.round(r.confidence * 100)}%`, 'success');
              load();
            } catch (e) {
              showToast(`Error: ${e.message}`, 'error');
              btnRe.disabled = false; btnRe.removeAttribute('aria-busy'); btnRe.textContent = 'Re-diagnose against current knowledge';
            }
          };
          const btnEv = document.getElementById('btn-esc-evidence');
          if (btnEv) btnEv.onclick = async () => {
            const reason = document.getElementById('esc-reason').value.trim();
            if (!reason) { showToast('Give a reason to request more evidence', 'error'); return; }
            btnEv.disabled = true; btnEv.setAttribute('aria-busy', 'true');
            btnEv.textContent = 'Gathering and re-diagnosing… (the AI second opinion can take ~15 s)';
            try {
              const r = await thinking(api.post(`/cases/${cid}/escalation/evidence`, { reason }));
              showToast(`Evidence gathered again and re-diagnosed: ${plain(r.current_state).toLowerCase()} at ${Math.round(r.confidence * 100)}%`, 'success');
              load();
            } catch (e) {
              showToast(`Error: ${e.message}`, 'error');
              btnEv.disabled = false; btnEv.removeAttribute('aria-busy'); btnEv.textContent = 'Request more evidence (reason required)';
            }
          };
          document.getElementById('btn-esc-close').onclick = async () => {
            const reason = document.getElementById('esc-reason').value.trim();
            if (!reason) { showToast('Give the resolution to close this escalation', 'error'); return; }
            try {
              const r = await api.post(`/cases/${cid}/escalation/close`, { reason, confirmed_cause: document.getElementById('esc-cause').value });
              showToast(r.knowledge_proposal_id ? `Escalation closed; resolution sent to stewards as ${r.knowledge_proposal_id}` : 'Escalation closed', 'success');
              load();
            } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
          };
        }
      }

      const btnRescore = document.getElementById('btn-rescore');
      if (btnRescore) btnRescore.onclick = async () => {
        try {
          const r = await api.post(`/cases/${cid}/rescore`);
          showToast(r.current_state === 'ESCALATED'
            ? `Re-scored at ${(r.confidence * 100).toFixed(0)}%: below threshold, escalated to a human`
            : `Re-scored at ${(r.confidence * 100).toFixed(0)}%: still recommendable`, 'success');
          load();
        } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
      };

      // Wire buttons
      const btnJump = document.getElementById('btn-jump-decide');
      if (btnJump) btnJump.onclick = () => {
        const card = document.getElementById('decision-controls');
        if (!card) return;
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        (document.getElementById('btn-approve') || document.getElementById('btn-reject'))?.focus({ preventScroll: true });
      };
      const btnApprove = document.getElementById('btn-approve');
      const btnReject = document.getElementById('btn-reject');
      const btnModify = document.getElementById('btn-modify');
      if (btnApprove) btnApprove.onclick = () => showRationaleForm('approve');
      if (btnReject) btnReject.onclick = () => showRationaleForm('reject');
      if (btnModify) btnModify.onclick = () => showModifyForm();

      const hazardAck = () => hazardReason ? `<label class="hazard-ack"><input type="checkbox" id="hazard-ack"> I have read the safety/environmental hazard above and the required precautions are in place.</label>` : '';
      const ackOk = () => !hazardReason || document.getElementById('hazard-ack').checked;

      function showRationaleForm(decision) {
        const verb = { approve: 'approving', reject: 'rejecting' }[decision];
        setHTML('decision-form', `
          <div class="form-group"><label for="rat-text">Rationale (required)</label>
            <textarea id="rat-text" placeholder="Explain why you are ${verb} this recommendation..."></textarea>
          </div>
          ${decision === 'approve' ? hazardAck() : ''}
          <button class="btn ${decision === 'approve' ? 'btn-green' : 'btn-red'}" id="btn-confirm-${decision}">Confirm ${decision === 'approve' ? 'Approval' : 'Rejection'}</button>
        `);
        document.getElementById('rat-text').focus();
        document.getElementById(`btn-confirm-${decision}`).onclick = async () => {
          const rat = document.getElementById('rat-text').value.trim();
          if (!rat) { showToast('Rationale is required', 'error'); return; }
          if (decision === 'approve' && !ackOk()) { showToast('Acknowledge the hazard before approving', 'error'); return; }
          try {
            await api.post(`/cases/${cid}/approval`, { decision, rationale: rat, hazard_acknowledged: decision === 'approve' && !!hazardReason ? 'true' : '' });
            showToast(`${decision === 'approve' ? 'Approved' : 'Rejected'}`, 'success'); load();
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      }

      async function showModifyForm() {
        let templates = [];
        try { templates = (await api.get(`/cases/${cid}/action-templates`)).templates; } catch (e) { /* the server still checks */ }
        const current = ((s.recommendation || {}).actions || [])[0] || {};
        const others = templates.filter(t => !(t.type === current.type && t.detail === current.detail));
        setHTML('decision-form', `
          <div class="form-group"><label for="rat-text">Rationale (required for modify)</label><textarea id="rat-text" placeholder="Why this procedure instead of the recommended one..."></textarea></div>
          <p class="muted" style="margin-bottom:8px">Pick another of the procedures this fault's decision tree can recommend. The work order carries that reviewed procedure, never free text, and cites no knowledge. Your reasoning is recorded as the rationale. Anything outside these procedures goes through the site's engineering change process.</p>
          <div class="form-group"><label for="mod-template">Procedure</label>
            <select id="mod-template">${others.map((t, i) => `<option value="${i}">${esc(plain(t.type))} · ${esc(plain(t.target))}</option>`).join('')}</select></div>
          <p class="muted" id="mod-detail-view" style="margin-bottom:8px"></p>
          ${hazardAck()}
          <button class="btn btn-secondary" id="btn-confirm-modify" ${others.length ? '' : 'disabled'}>Confirm Modification</button>
        `);
        const sel = document.getElementById('mod-template');
        const showDetail = () => { const t = others[Number(sel.value)]; document.getElementById('mod-detail-view').textContent = t ? `Procedure: ${t.detail}` : 'No other procedure for this fault.'; };
        sel.onchange = showDetail; showDetail();
        document.getElementById('btn-confirm-modify').onclick = async () => {
          const rat = document.getElementById('rat-text').value.trim();
          const t = others[Number(sel.value)];
          if (!rat || !t) { showToast('A rationale and a procedure are required', 'error'); return; }
          if (!ackOk()) { showToast('Acknowledge the hazard before modifying', 'error'); return; }
          try { await api.post(`/cases/${cid}/approval`, { decision: 'modify', hazard_acknowledged: hazardReason ? 'true' : '', rationale: rat, modified_action_type: t.type, modified_action_target: t.target, modified_action_detail: t.detail }); showToast('Modification submitted', 'success'); load(); }
          catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      }
    } catch (e) {
      el.innerHTML = `<div class="banner banner-error">Error: ${esc(e.message)}</div>`;
    }
  }

  load();
}

// ═══════════════════════════════════════════════════════════
// Screen 4: Outcome and Feedback
// ═══════════════════════════════════════════════════════════
export function renderOutcome(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate } = h;
  const cid = state.caseId;

  el.innerHTML = '<div class="card skeleton-card"><div class="skeleton skeleton-line" style="width:30%"></div><div class="skeleton skeleton-line" style="width:50%"></div><div class="skeleton skeleton-line" style="width:80%"></div><div class="skeleton skeleton-line" style="width:40%"></div></div>';

  async function load() {
    try {
      const [s] = await Promise.all([api.get(`/cases/${cid}`), loadCauses()]);
      // Feedback submission closes the case immediately (the PROPOSAL stays
      // pending for a steward separately) -- so "submit feedback" must stop
      // showing the moment current_state is CLOSED, not stay pinned on
      // whether an outcome was ever recorded.
      const outcomeHint = (s.audit_chain_valid === false || (s.sentinel_hold || {}).active)
        ? 'this case is frozen: an auditor must review it on Governance.'
        : s.current_state === 'CLOSED'
        ? 'this case is closed. Feedback (if submitted) is with a knowledge steward on Governance.'
        : s.outcome
        ? 'submit feedback so a knowledge steward can validate it into the knowledge base.'
        : s.current_state === 'MONITORING_OUTCOME'
        ? 'record the outcome once the work is done.'
        : s.current_state === 'EXECUTING'
        ? `${workOrderNext()}.`
        : 'the outcome is recorded after the AOM approves and a work order is raised.';
      let html = `${nextHint(outcomeHint)}<h2 style="font-size:20px;margin-bottom:16px">Outcome and Feedback - ${esc(cid)}</h2>`;

      // Work and outcome first; the audit trail is a tab away.
      html += tabbed('outcome', [
        { id: 'work', label: 'Work order & outcome', html: `<div class="grid-2">
          <div class="card"><div class="card-header"><h3>Work Order</h3></div><div class="card-body" id="wo-body"></div></div>
          <div class="card"><div class="card-header"><h3>Outcome Recording</h3></div><div class="card-body" id="oc-body"></div></div>
        </div>` },
        { id: 'audit', label: 'Audit trail', note: s.audit_chain_valid === false ? 'failed' : '',
          html: `<div class="card"><div class="card-header"><h3>Audit Timeline (Hash-Chain)</h3></div><div class="card-body" id="au-body"></div></div>` },
      ]);

      el.innerHTML = frozenWrap(s, html, esc);

      // Work order
      const woBody = document.getElementById('wo-body');
      if (s.work_order_id) {
        woBody.innerHTML = `<div class="banner banner-success"><p><strong>Work Order:</strong> <code>${esc(s.work_order_id)}</code></p></div>`;
      } else if (s.current_state === 'AWAITING_APPROVAL') {
        woBody.innerHTML = '<div class="banner banner-info"><p>Approval required before a work order can be raised.</p></div>';
      } else if (s.current_state === 'EXECUTING' || s.current_state === 'MONITORING_OUTCOME') {
        const canWO = api.can('approve_reject_modify');
        woBody.innerHTML = canWO
          ? `<button class="btn btn-primary" id="btn-wo">Raise Work Order</button>`
          : `<div class="banner banner-info"><p>Only an Asset Ops Manager raises work orders. Ask your AOM to raise it; you record the outcome once the work is under way.</p></div>`;
        const btn = document.getElementById('btn-wo');
        if (btn) btn.onclick = async () => {
          try { await api.post(`/cases/${cid}/work-order`); showToast('Work order created', 'success'); load(); }
          catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      } else {
        woBody.innerHTML = `<div class="banner banner-info"><p>Work order available after approval.</p><p>Current state: <strong>${esc(s.current_state)}</strong></p></div>`;
      }

      // Outcome
      const ocBody = document.getElementById('oc-body');
      if (s.outcome) {
        const cls = s.outcome.result === 'resolved' ? 'badge-green' : 'badge-red';
        ocBody.innerHTML = `<div class="banner banner-success">
          <p><span class="badge ${cls}">${esc(s.outcome.result)}</span></p>
          ${s.outcome.root_cause_confirmed ? `<p><strong>Root Cause:</strong> ${esc(causeLabel(s.outcome.root_cause_confirmed))}</p>` : ''}
          ${s.outcome.verified_by ? `<p><strong>Verified by:</strong> ${esc(s.outcome.verified_by)}</p>` : ''}
          ${s.outcome.notes ? `<p><strong>Notes:</strong> ${esc(s.outcome.notes)}</p>` : ''}
        </div>`;
        // Feedback is accepted exactly once, while the case waits for it.
        if (s.current_state === 'CLOSED') {
          ocBody.innerHTML += s.feedback_id
            ? `<div class="banner banner-info mt-16"><p>Feedback <code>${esc(s.feedback_id)}</code> was submitted and is with a knowledge steward on Governance.</p></div>`
            : '';
        } else if (s.current_state === 'FEEDBACK_QUEUED') {
          const role = api.user();
          const canFB = api.can('submit_feedback');
          if (canFB) {
            const own = (await loadCauses()).filter(c => c.asset_type === s.asset_type);
            ocBody.innerHTML += `<div class="mt-16">
              <h4>Submit Feedback</h4>
              <div class="form-group"><label for="fb-cause">Confirmed Root Cause (${esc(s.asset_type)} causes)</label><select id="fb-cause">${causeOptions(own, s.outcome.root_cause_confirmed || (s.diagnosis && s.diagnosis.top_cause_id) || '')}</select></div>
              <div class="form-group"><label for="fb-notes">What did you find? (goes to the knowledge stewards)</label><textarea id="fb-notes" placeholder="e.g. what you found on site and what you replaced"></textarea></div>
              <button class="btn btn-primary" id="btn-fb">Submit Feedback</button>
            </div>`;
            document.getElementById('btn-fb').onclick = async () => {
              try {
                const r = await api.postJson(`/cases/${cid}/feedback`, { confirmed_cause: document.getElementById('fb-cause').value, notes: document.getElementById('fb-notes').value });
                showToast('Feedback sent to the knowledge stewards. Nothing changes in the knowledge base until a steward approves it.', 'success');
                load();
              } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
            };
          } else {
            ocBody.innerHTML += `<div class="banner banner-error mt-16"><p><strong>Feedback Blocked</strong> - ${esc(role)} (${esc(h.roleDisplayName(role))}) cannot submit feedback.</p></div>`;
          }
        }
      } else if (s.current_state === 'EXECUTING') {
        ocBody.innerHTML = `<div class="banner banner-info"><p>${api.can('approve_reject_modify') ? 'Raise the work order first.' : 'The AOM raises the work order first.'} The outcome is recorded once the work is under way.</p></div>`;
      } else if (s.current_state === 'MONITORING_OUTCOME' || s.current_state === 'RECORDING_OUTCOME') {
        const role = api.user();
        const approver = (s.human_decision || {}).decided_by;
        const canRec = api.can('record_outcome') && approver !== role;
        if (api.can('record_outcome') && approver === role) {
          ocBody.innerHTML = `<div class="banner banner-warn"><p><strong>Someone else verifies this.</strong> You approved the work, so the technician who did it (or another manager) records whether it worked. Switch to <strong>tech1</strong>.</p></div>`;
        } else if (canRec) {
          ocBody.innerHTML = `
            <div class="form-group"><label for="oc-result">Result</label><select id="oc-result"><option value="resolved">resolved</option><option value="partial">partial</option><option value="unresolved">unresolved</option></select></div>
            <div class="form-group"><label for="oc-cause">Confirmed Root Cause (${esc(s.asset_type)} causes)</label><select id="oc-cause"><option value="">-- not confirmed --</option>${causeOptions((await loadCauses()).filter(c => c.asset_type === s.asset_type), (s.diagnosis && s.diagnosis.top_cause_id) || '')}</select></div>
            <p class="muted" style="margin-bottom:12px">Verified by: <strong>${esc(role)}</strong> (your signed-in identity is recorded)</p>
            <div class="form-group"><label for="oc-notes">Notes</label><textarea id="oc-notes" placeholder="Optional notes..."></textarea></div>
            <button class="btn btn-primary" id="btn-oc">Record Outcome</button>
          `;
          document.getElementById('btn-oc').onclick = async () => {
            try {
              await api.post(`/cases/${cid}/outcome`, {
                result: document.getElementById('oc-result').value,
                root_cause_confirmed: document.getElementById('oc-cause').value,
                notes: document.getElementById('oc-notes').value,
              });
              showToast('Outcome recorded', 'success');
              load();
            } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
          };
        } else {
          ocBody.innerHTML = `<div class="banner banner-error"><p><strong>Blocked</strong> - ${esc(role)} (${esc(h.roleDisplayName(role))}) cannot record outcomes.</p></div>`;
        }
      } else {
        ocBody.innerHTML = `<div class="banner banner-info"><p>The outcome is recorded after approval and a work order.</p><p>Current state: ${statePill(s.current_state)}</p></div>`;
      }

      // Audit timeline
      const auBody = document.getElementById('au-body');
      const history = s.history || [];
      if (!history.length) {
        auBody.innerHTML = `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No audit entries</div><div class="empty-state-desc">Audit chain entries will appear here once the case progresses through state transitions.</div></div>`;
      } else {
        auBody.innerHTML = `
          ${s.audit_chain_valid ? '<span class="badge badge-green">Audit Chain Valid</span>' : '<span class="badge badge-red">Audit Chain Tampered!</span>'}
          <div class="timeline" style="margin-top:12px">
            ${history.map(h => `
              <div class="timeline-item">
                <div class="timeline-dot"></div>
                <div style="flex:1">
                  <div class="timeline-trans">${esc(h.from_state)} -> ${esc(h.to_state)}</div>
                  <div class="timeline-meta"><span><strong>Actor:</strong> ${esc(h.actor)}</span><span><strong>Reason:</strong> ${esc(h.reason)}</span><span><strong>Time:</strong> ${fmtTime(h.at)}</span></div>
                  <div class="audit-chain-entry" style="margin-top:6px">
                    <div class="audit-chain-hash"><strong>hash:</strong> ${esc(h.hash || 'N/A')}</div>
                    <button class="audit-copy-btn" onclick="window.__app__.copyToClipboard('${esc(h.hash || '')}', this)">Copy</button>
                  </div>
                  ${h.prev_hash && h.prev_hash !== '0'.repeat(64) ? `<div class="audit-chain-entry"><div class="audit-chain-hash"><strong>prev_hash:</strong> ${esc((h.prev_hash || '').substring(0, 32))}...</div><button class="audit-copy-btn" onclick="window.__app__.copyToClipboard('${esc(h.prev_hash || '')}', this)">Copy</button></div>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        `;
      }
    } catch (e) {
      el.innerHTML = `<div class="banner banner-error">Error: ${esc(e.message)}</div>`;
    }
  }

  load();
}

// ═══════════════════════════════════════════════════════════
// Screen 5: Pill Summary and Governance
// ═══════════════════════════════════════════════════════════
export function renderGovernance(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate } = h;

  el.innerHTML = `
    <h2 class="sr-only">Governance</h2>
    ${nextHint(api.role() === 'knowledge_steward'
      ? 'approve pending proposals to bump the KB version, then re-run affected cases to see the uplift.'
      : api.can('review_audit_integrity')
      ? 'check the sentinel and the ledger; anything stopped or failing waits for your review here.'
      : 'knowledge stewards approve proposals here; everything they decide is in the ledger below.')}
    ${tabbed('gov', [
      { id: 'overview', label: 'Overview', html: `
        <div class="stats-row" id="gov-stats"></div>
        <div class="card"><div class="card-header"><h3>Pill Registry</h3></div><div class="card-body" id="pill-registry-body"></div></div>
        <div class="grid-2">
          <div class="card"><div class="card-header"><h3>Cause Distribution</h3></div><div class="card-body" id="cause-dist"></div></div>
          <div class="card"><div class="card-header"><h3>Governance Pipeline</h3></div><div class="card-body" id="pipeline-body"></div></div>
        </div>` },
      { id: 'review', label: 'Approval queue', html: `
        <div class="card"><div class="card-header"><h3>Knowledge Approval Queue</h3></div><div class="card-body" id="queue-body"></div></div>
        <div class="card" id="rerun-card" hidden><div class="card-header"><h3>Re-run Diagnosis on Similar Open Cases</h3></div><div class="card-body" id="rerun-body"></div></div>` },
      { id: 'knowledge', label: 'Approved & versions', html: `
        <div class="card"><div class="card-header"><h3>Approved Knowledge</h3></div><div class="card-body" id="approved-body"></div></div>
        <div class="card"><div class="card-header"><h3>Rollback</h3></div><div class="card-body" id="rollback-body"></div></div>` },
      { id: 'audit', label: 'Audit & sentinel', html: `
        <div class="card" id="integrity-card" hidden><div class="card-header"><h3>Integrity Review</h3><span class="badge badge-red">Action needed</span></div><div class="card-body" id="integrity-body"></div></div>
        <div class="card" id="sentinel-card"><div class="card-header"><h3>Sentinel</h3><span class="muted">independent supervisor, not an AI</span></div><div class="card-body" id="sentinel-body"></div></div>
        <div class="card"><div class="card-header"><h3>Knowledge Governance Ledger</h3><span id="ledger-status"></span></div><div class="card-body" id="ledger-body"></div></div>
        <div class="card"><div class="card-header"><h3>Case Audit Trace (keyed hash chain)</h3></div><div class="card-body" id="trace-body"></div></div>
        <div class="card"><div class="card-header"><h3>Integrity Events</h3><span class="muted">tampered snapshots, archived</span></div><div class="card-body" id="tamper-body"></div></div>` },
    ], api.role() === 'knowledge_steward' ? 'review' : api.can('review_audit_integrity') ? 'audit' : 'overview')}
  `;

  // Rollback is two-person. An admin asks, for one pill at a time; nothing
  // changes until that pill's steward countersigns. Anyone can see the
  // addressable versions and the requests, so the mapping from "CRAH v1.4.0"
  // on screen to the integer /kb/rollback/{N} takes is never a guess.
  // Named so approvals and rollbacks elsewhere on this screen refresh it.
  async function loadRollback() {
    const body = document.getElementById('rollback-body');
    if (!body) return;
    const canAsk = api.can('rollback_knowledge_version');
    // Only a knowledge steward can countersign; the server checks the pill too.
    const canCountersign = api.role() === 'knowledge_steward';
    const me = api.user();
    const pill = loadRollback.pill || 'CRAH';
    try {
      const [{ versions, current_version, current_label }, { requests }] = await Promise.all([
        api.get(`/kb/versions?pill=${encodeURIComponent(pill)}`), api.get('/kb/rollback-requests')]);
      const targets = versions.filter(v => v.status === 'live' && v.version !== current_version);
      const options = targets.map(v => `<option value="${v.version}" data-label="${esc(v.label)}">v${esc(v.label)}</option>`).join('');
      const pillPicker = `<div class="flex gap-8 align-center" style="margin-bottom:10px"><label for="rb-pill" class="role-label">Pill</label>
        <select id="rb-pill">${['CRAH', 'Chiller', 'UPS', 'Pump'].map(p => `<option${p === pill ? ' selected' : ''}>${p}</option>`).join('')}</select></div>`;
      const history = versions.map(v => `<span class="badge ${v.status === 'live' ? (v.version === current_version ? 'badge-green' : 'badge-blue') : 'badge-grey'}" style="margin:2px" title="${v.status === 'live' ? 'live lineage' : 'rolled back; this label is never reused'}">v${esc(v.label)}${v.version === current_version ? ' (current)' : v.status === 'rolled_back' ? ' (rolled back)' : ''}</span>`).join(' ');
      const mine = requests.filter(r => r.pill === pill);
      const pending = mine.filter(r => r.status === 'pending');
      const askForm = !canAsk ? `<p class="muted">Only an Admin asks for a rollback. The ${esc(pill)} steward then countersigns it, and nothing changes until they do.</p>`
        : !targets.length ? `<p class="muted">Nothing to roll back to: the current version is the only live one.</p>`
        : pending.length ? `<p class="muted">A rollback of ${esc(pill)} is already waiting for ${esc(pending[0].countersigned_by)}.</p>`
        : `<div class="flex gap-8 flex-wrap align-center">
            <label for="rb-version" class="role-label">Roll back to</label>
            <select id="rb-version">${options}</select>
            <input id="rb-reason" type="text" placeholder="Reason (required, recorded in the ledger)" style="flex:1 1 260px">
            <button class="btn btn-red btn-sm" id="rb-go">Ask for rollback…</button>
          </div>
          <div id="rb-confirm" class="banner banner-warn mt-16" hidden></div>`;
      const cards = mine.slice(-4).reverse().map(r => {
        const pr = r.preview || {};
        const what = `Would remove ${pr.validated_cases || 0} validated case(s), ${pr.expert_heuristics || 0} expert heuristic(s)`
          + `${(pr.proposals || []).length ? `, and make ${esc((pr.proposals || []).join(', '))} rolled back` : ''}.`;
        const head = `<strong>${esc(r.request_id)}</strong>: roll back to ${esc(r.target_label)}, asked by ${esc(r.requested_by)}. <span class="muted">“${esc(r.reason)}”</span>`;
        if (r.status === 'countersigned') return `<div class="banner banner-success mt-16"><p>${head} <strong>Countersigned by ${esc(r.decided_by)}; rolled back.</strong></p></div>`;
        if (r.status === 'rejected') return `<div class="banner banner-warn mt-16"><p>${head} <strong>Refused by ${esc(r.decided_by)}:</strong> “${esc(r.decision_reason)}”. Nothing changed.</p></div>`;
        if (canCountersign && r.countersigned_by === me) return `<div class="card mt-16"><div class="card-body">
            <p>${head}</p><p class="muted" style="margin:6px 0"><strong>Nothing has changed yet.</strong> ${esc(what)}</p>
            <div class="flex gap-8 flex-wrap align-center">
              <input id="cs-reason-${esc(r.request_id)}" type="text" placeholder="Reason for refusing (only if you refuse)" style="flex:1 1 240px">
              <button class="btn btn-red btn-sm" data-cs="${esc(r.request_id)}">Countersign rollback</button>
              <button class="btn btn-secondary btn-sm" data-rf="${esc(r.request_id)}">Refuse</button>
            </div></div></div>`;
        return `<div class="banner banner-info mt-16"><p>${head} <strong>Waiting for ${esc(r.countersigned_by)} to countersign.</strong> Nothing has changed yet. ${esc(what)}</p></div>`;
      }).join('');
      // Rollbacks waiting for the signed-in steward, whichever pill is on screen.
      const waitingForMe = requests.filter(r => r.status === 'pending' && r.countersigned_by === me && canCountersign);
      const waitingBanner = waitingForMe.map(r => `<div class="banner banner-warn" style="margin-bottom:10px"><p><strong>${esc(r.request_id)} waits for you:</strong> roll ${esc(r.pill)} back to ${esc(r.target_label)}, asked by ${esc(r.requested_by)}. <button class="btn btn-secondary btn-sm" data-open-pill="${esc(r.pill)}">Open ${esc(r.pill)}</button></p></div>`).join('');
      body.innerHTML = `
        ${waitingBanner}
        ${pillPicker}
        <p class="muted" style="margin-bottom:8px">Current ${esc(pill)} knowledge: <strong>${esc(current_label)}</strong>. Rolling back one pill leaves the others alone. Version labels are never reused: a rolled-back version keeps its label and the next approval gets a new one.</p>
        <div style="margin-bottom:12px">${history}</div>
        ${askForm}
        ${cards}`;
      document.getElementById('rb-pill').onchange = (ev) => { loadRollback.pill = ev.target.value; loadRollback(); };
      body.querySelectorAll('[data-open-pill]').forEach(b => b.onclick = () => { loadRollback.pill = b.dataset.openPill; loadRollback(); });
      const go = document.getElementById('rb-go');
      if (go) {
        go.onclick = () => {
          const sel = document.getElementById('rb-version');
          const reason = document.getElementById('rb-reason').value.trim();
          if (!reason) { showToast('Give a reason for the rollback', 'error'); document.getElementById('rb-reason').focus(); return; }
          const label = sel.selectedOptions[0].dataset.label;
          const box = document.getElementById('rb-confirm');
          box.hidden = false;
          box.innerHTML = `<p><strong>Ask for ${esc(pill)} to go back from ${esc(current_label)} to v${esc(label)}?</strong> Nothing changes yet. The ${esc(pill)} steward must countersign it, and will see exactly what would be removed. Other pills are not touched.</p>
            <div class="flex gap-8 mt-16"><button class="btn btn-red btn-sm" id="rb-yes">Yes, ask for rollback</button><button class="btn btn-secondary btn-sm" id="rb-no">Cancel</button></div>`;
          document.getElementById('rb-no').onclick = () => { box.hidden = true; };
          document.getElementById('rb-yes').onclick = async () => {
            try {
              const r = await api.post(`/kb/rollback/${sel.value}`, { pill, reason });
              showToast(`${r.request.request_id} sent to ${r.countersigned_by} to countersign`, 'success');
              loadRollback();
            } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
          };
        };
      }
      body.querySelectorAll('[data-cs]').forEach(b => b.onclick = async () => {
        try {
          const r = await api.post(`/kb/rollback-requests/${b.dataset.cs}/countersign`, { reason: 'agreed' });
          showToast(`${r.request_id} countersigned: ${pill} rolled back`, 'success');
          refreshAll();
        } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
      });
      body.querySelectorAll('[data-rf]').forEach(b => b.onclick = async () => {
        const reason = (document.getElementById(`cs-reason-${b.dataset.rf}`) || {}).value?.trim();
        if (!reason) { showToast('Give a reason for refusing', 'error'); return; }
        try {
          await api.post(`/kb/rollback-requests/${b.dataset.rf}/reject`, { reason });
          showToast(`${b.dataset.rf} refused. Nothing changed.`, 'success');
          loadRollback();
        } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
      });
    } catch (e) {
      body.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }
  loadRollback();

  // Pill Registry — all four pills, who owns review, and how their KB is doing.
  // Named so approvals and rollbacks on this screen refresh it.
  async function loadPills() {
    const body = document.getElementById('pill-registry-body');
    if (!body) return;
    try {
      const { pills } = await api.get('/pills');
      body.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>Pill</th><th>Owner Steward</th><th>KB Version</th><th>Knowledge Items</th><th>Approval Rate</th></tr></thead>
        <tbody>${pills.map(p => `<tr>
          <td><strong>${esc(p.asset_type)}</strong></td>
          <td>${esc(p.owner_steward)}</td>
          <td>${esc(p.kb_version_label)}</td>
          <td>${p.knowledge_count}</td>
          <td>${p.approval_rate === null ? '<span class="muted">no decisions yet</span>' : `${(p.approval_rate * 100).toFixed(0)}% (${p.proposals_approved} of ${p.proposals_decided} decided)`}${p.proposals_pending ? ` <span class="muted">· ${p.proposals_pending} pending</span>` : ''}</td>
        </tr>`).join('')}</tbody>
      </table></div>
      <p class="muted" style="margin-top:10px">Each pill versions its own knowledge: approving Chiller knowledge moves only the Chiller version, and a rollback names one pill.</p>`;
    } catch (e) {
      body.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }
  loadPills();

  // Approved proposals, each revocable on its own: withdrawing one bad
  // item should not require rolling back everything approved after it.
  // A proposal filed under several pills can be withdrawn one pill at a
  // time, so each pill's steward withdraws their own part.
  const livePills = p => Object.keys(p.kb_version_labels || p.kb_versions || {})
    .filter(x => !(p.rolled_back_pills || []).includes(x) && !(p.revoked_pills || []).includes(x));
  async function loadApproved() {
    const body = document.getElementById('approved-body');
    if (!body) return;
    if (!api.can('approve_knowledge_version')) {
      body.innerHTML = rbacNote('Approved knowledge', 'knowledge stewards and admins');
      return;
    }
    try {
      const { proposals } = await api.get('/kb/proposals?status=approved');
      await loadCauses();
      if (!proposals.length) { body.innerHTML = '<p class="muted">No approved proposals in the live knowledge base.</p>'; return; }
      // Re-run candidates for the latest approval, so the list survives a reload.
      const latest = proposals.reduce((a, b) => ((b.decided_at || '') > (a.decided_at || '') ? b : a));
      const targets = latest.kind === 'expert_capture'
        ? (latest.heuristics || []).filter(x => !x.new_cause).map(x => [x.likely_cause, x.asset_type])
        : (latest.confirmed_cause ? [[latest.confirmed_cause, latest.asset_type]] : []);
      if (targets.length) loadRerunCandidates(targets);
      body.innerHTML = `<p class="muted" style="margin-bottom:8px">Revoke withdraws one proposal's knowledge and leaves everything else. Open cases scored with it are blocked from approval until re-scored.</p>` +
        proposals.slice().reverse().map(p => {
          const pid = esc(p.proposal_id);
          const what = p.kind === 'expert_capture'
            ? `Expert interview: ${esc(p.expert_name)} · ${(p.heuristics || []).length} heuristic(s)`
            : `${p.kind === 'escalation_resolution' ? 'Escalation resolution' : 'Outcome feedback'}: ${esc(causeLabel(p.confirmed_cause))} · ${esc(p.case_id)}`;
          return `<div class="rerun-row">
            <div><code>${pid}</code> ${what} <span class="muted">· approved by ${esc(p.decided_by)} · ${esc(Object.entries(p.kb_version_labels || {}).map(([k, v]) => `${k} v${v}`).join(', '))}</span></div>
            <div class="flex gap-8"><input id="rv-reason-${pid}" type="text" placeholder="Reason (required)" aria-label="Reason for revoking ${pid}" style="min-width:200px">
            ${livePills(p).length > 1 ? `<select id="rv-pill-${pid}" aria-label="Which part to revoke"><option value="">All pills</option>${livePills(p).map(x => `<option value="${esc(x)}">${esc(x)} part only</option>`).join('')}</select>` : ''}
            <button class="btn btn-red btn-sm" id="rv-go-${pid}">Revoke</button></div>
          </div>`;
        }).join('');
      proposals.forEach(p => {
        const btn = document.getElementById(`rv-go-${p.proposal_id}`);
        btn.onclick = async () => {
          const reason = document.getElementById(`rv-reason-${p.proposal_id}`).value.trim();
          if (!reason) { showToast('Give a reason for revoking', 'error'); return; }
          try {
            const pill = document.getElementById(`rv-pill-${p.proposal_id}`)?.value || '';
            const r = await api.post(`/kb/proposals/${p.proposal_id}/revoke`, pill ? { reason, pills: pill } : { reason });
            showToast(`${p.proposal_id}${pill ? ` (${pill} part)` : ''} revoked (${r.removed_items} item(s) withdrawn)`, 'success');
            refreshAll();
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      });
    } catch (e) {
      body.innerHTML = isForbidden(e)
        ? rbacNote('Revoking knowledge', 'knowledge stewards and admins')
        : `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }
  loadApproved();

  function refreshAll() {
    loadQueue(); loadStats(); loadRollback(); loadPills(); loadLedger(); loadApproved(); loadIntegrity(); loadSentinel();
    window.__app__?.refreshKbVersion?.();
  }

  // Integrity review: the way out of "frozen until an auditor reviews it".
  // An auditor records a disposition for each chain that fails verification:
  // accept it as genuine (re-signed, with the review on the chain and in the
  // ledger), for a case quarantine it (closed; redo the work as a new case),
  // or for the ledger restore the last knowledge base it verified.
  const auditNeeds = { integrity: false, sentinel: false };
  const noteAudit = () => setTabNote('gov', 'audit', auditNeeds.integrity || auditNeeds.sentinel ? 'action needed' : '');

  async function loadIntegrity() {
    const card = document.getElementById('integrity-card');
    const body = document.getElementById('integrity-body');
    if (!card || !body) return;
    try {
      const st = await api.get('/audit/status');
      // The ledger comes first: the server records every other review in it,
      // so it must be reviewed before anything else.
      const items = [
        ...(st.ledger_valid ? [] : [{ target: 'ledger', restore: true, label: `Knowledge ledger: ${st.ledger_problem || 'failed verification'}. Knowledge changes are frozen and expert knowledge is withheld from diagnoses. Review this first: every other review is recorded in the ledger.` }]),
        ...st.broken_cases.map(cid => ({ target: `case:${cid}`, label: `Case ${cid}: ${(st.case_problems || {})[cid] || 'its audit chain failed verification'}. The case is frozen.`, quarantine: true })),
        ...(st.registry_valid ? [] : [{ target: 'registry', label: `Case registry: a case was added or removed outside the app.${(st.missing_cases || []).length ? ` Missing: ${st.missing_cases.join(', ')} (opened according to the signed tool log, no longer stored).` : ''}` }]),
        ...(st.tool_log_valid ? [] : [{ target: 'tool_log', label: 'Tool log: entries were changed or removed.' }]),
      ];
      card.hidden = !items.length;
      auditNeeds.integrity = items.length > 0; noteAudit();
      if (!items.length) return;
      if (!api.can('review_audit_integrity')) {
        body.innerHTML = `<p>${items.map(i => esc(i.label)).join('<br>')}</p><p class="muted">An auditor (auditor1) reviews these and records a decision.</p>`;
        return;
      }
      body.innerHTML = `<p class="muted" style="margin-bottom:10px">Investigate first (Case Audit Trace below, the snapshot and server logs). <strong>Accept</strong> means the record is genuine as it stands: it is re-signed, and your review is written to the chain and the ledger. <strong>Quarantine</strong> closes a case whose record you do not trust; redo the work as a new case. <strong>Restore</strong> puts back the last knowledge base the ledger verified, discarding the change made outside governance.</p>` +
        items.map((i, n) => `<div class="rerun-row">
          <div>${esc(i.label)}</div>
          <div class="flex gap-8 flex-wrap"><input id="ir-reason-${n}" type="text" placeholder="What you checked (required)" style="min-width:220px">
            <button class="btn btn-secondary btn-sm" id="ir-accept-${n}">Accept</button>
            ${i.quarantine ? `<button class="btn btn-red btn-sm" id="ir-quarantine-${n}">Quarantine</button>` : ''}
            ${i.restore ? `<button class="btn btn-red btn-sm" id="ir-restore-${n}">Restore last verified</button>` : ''}</div>
        </div>`).join('');
      items.forEach((i, n) => {
        const go = async decision => {
          const reason = document.getElementById(`ir-reason-${n}`).value.trim();
          if (!reason) { showToast('Record what you checked before deciding', 'error'); document.getElementById(`ir-reason-${n}`).focus(); return; }
          try {
            await api.post('/audit/review', { target: i.target, decision, reason });
            showToast(`${i.target.replace('case:', 'Case ')} ${{ accept: 'accepted', quarantine: 'quarantined', restore: 'restored to the last verified snapshot' }[decision]}; recorded in the ledger`, 'success');
            refreshAll();
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
        document.getElementById(`ir-accept-${n}`).onclick = () => go('accept');
        const q = document.getElementById(`ir-quarantine-${n}`);
        if (q) q.onclick = () => go('quarantine');
        const rs = document.getElementById(`ir-restore-${n}`);
        if (rs) rs.onclick = () => go('restore');
      });
    } catch (e) { card.hidden = true; }
  }
  loadIntegrity();

  // Sentinel: re-checks every case after every write and stops any whose
  // record breaks a rule (sentinel.py). Auditors decide on held cases;
  // an admin can run a drill to see it work.
  async function loadSentinel() {
    const body = document.getElementById('sentinel-body');
    if (!body) return;
    try {
      const sen = await api.get('/sentinel');
      auditNeeds.sentinel = sen.held.length > 0; noteAudit();
      const canReview = api.can('review_audit_integrity');
      body.innerHTML = `
        <p style="margin-bottom:8px">Watching <strong>${sen.watching}</strong> case(s). After every write it re-checks: ${sen.checks.map(esc).join(' · ')}. On a violation it stops the case, records why on the case's audit trail, keeps what it saw, and alerts everyone.</p>
        ${sen.held.length ? sen.held.map((x, n) => `<div class="rerun-row">
            <div><span class="badge badge-red">Stopped</span> <code>${esc(x.case_id)}</code> ${esc(x.asset_id)}: ${(x.findings || []).map(esc).join('; ')}</div>
            ${canReview ? `<div class="flex gap-8 flex-wrap"><input id="sn-reason-${n}" type="text" placeholder="What you checked (required)" style="min-width:220px">
              <button class="btn btn-secondary btn-sm" id="sn-release-${n}">Release</button>
              <button class="btn btn-red btn-sm" id="sn-quarantine-${n}">Quarantine</button></div>` : '<div class="muted">An auditor decides.</div>'}
          </div>`).join('') : '<p><span class="badge badge-green">Nothing stopped</span> <span class="muted">In normal operation it finds nothing; it exists for the day a component misbehaves.</span></p>'}
        ${api.role() === 'admin' ? '<button class="btn btn-secondary btn-sm mt-16" id="sn-drill">Run a sentinel drill</button> <span class="muted">Creates a case and plays a defective tool that cites evidence the case never gathered.</span>' : ''}`;
      sen.held.forEach((x, n) => {
        const go = async decision => {
          const reason = document.getElementById(`sn-reason-${n}`).value.trim();
          if (!reason) { showToast('Record what you checked before deciding', 'error'); return; }
          try {
            await api.post('/sentinel/review', { case_id: x.case_id, decision, reason });
            showToast(`${x.case_id} ${decision === 'release' ? 'released' : 'quarantined'}; recorded in the ledger`, 'success');
            refreshAll();
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
        const rel = document.getElementById(`sn-release-${n}`);
        if (rel) rel.onclick = () => go('release');
        const q = document.getElementById(`sn-quarantine-${n}`);
        if (q) q.onclick = () => go('quarantine');
        const rs = document.getElementById(`ir-restore-${n}`);
        if (rs) rs.onclick = () => go('restore');
      });
      const drill = document.getElementById('sn-drill');
      if (drill) drill.onclick = async () => {
        drill.disabled = true;
        drill.setAttribute('aria-busy', 'true');
        drill.textContent = 'Drill running… the AI second opinion can take ~10 s';
        try {
          const r = await thinking(api.post('/sentinel/drill'));
          showToast(`Drill: the sentinel stopped ${r.case_id}`, r.held ? 'success' : 'error');
          refreshAll();
        } catch (e) { showToast(`Error: ${e.message}`, 'error'); drill.disabled = false; drill.textContent = 'Run a sentinel drill'; }
        drill.removeAttribute('aria-busy');
      };
    } catch (e) {
      body.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }
  loadSentinel();

  // Pipeline visual
  setHTML('pipeline-body', `
    <div class="pipeline">
      <div class="pipeline-step"><div class="pipeline-circle">1</div><div class="pipeline-label">Proposed</div><div class="pipeline-desc">Interview or outcome</div></div>
      <div class="pipeline-step"><div class="pipeline-circle">2</div><div class="pipeline-label">Reviewed</div><div class="pipeline-desc">By a different steward</div></div>
      <div class="pipeline-step"><div class="pipeline-circle">3</div><div class="pipeline-label">Live</div><div class="pipeline-desc">Added to knowledge</div></div>
      <div class="pipeline-step"><div class="pipeline-circle">4</div><div class="pipeline-label">Versioned</div><div class="pipeline-desc" id="pipe-version">Reversible</div></div>
    </div>
  `);

  // Knowledge queue — load real pending proposals
  let queueShown = false;
  async function loadQueue() {
    const qb = document.getElementById('queue-body');
    if (!qb) return;
    if (!api.can('approve_knowledge_version')) {
      qb.innerHTML = rbacNote('Reviewing knowledge proposals', 'knowledge stewards (steward1, steward2)');
      return;
    }
    try {
      const data = await api.get('/kb/queue');
      const queue = data.queue || [];
      setTabNote('gov', 'review', queue.length ? String(queue.length) : '');
      // A steward with something to decide lands on the queue, whichever
      // tab they last had open (once per visit, so it never yanks them back).
      if (!queueShown && api.role() === 'knowledge_steward' && queue.some(p => p.submitted_by !== api.user())) {
        queueShown = true;
        window.__tabs__.open('gov', 'review');
      }
      if (!queue.length) {
        qb.innerHTML = `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No pending proposals</div><div class="empty-state-desc">Expert interviews from the Capture screen and feedback on closed cases appear here for review by a second steward.</div></div>`;
        return;
      }
      await loadCauses();
      const me = api.user();
      // Everything that will be shown to an AOM, so the steward approves
      // exactly what reaches the decision screen.
      const lines = (title, items) => items && items.length
        ? `<div class="q-field"><span class="q-field-lbl">${title}</span><ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : '';
      const heuristicLine = x => `<li class="q-heuristic"><strong>${esc(x.cause_label || causeLabel(x.likely_cause))}</strong>
          ${x.asset_type ? `<span class="badge badge-grey">${esc(x.asset_type)}</span>` : ''}
          ${x.source === 'manual' ? '<span class="badge badge-yellow">entered by hand</span>' : ''}
          ${x.check_cause ? '<div class="kh-new">The expert\'s own words may rule this cause out.</div>' : ''}
          ${x.off_topic ? '<div class="kh-new">The expert\'s answer never names this cause or its usual signs.</div>' : ''}
          ${(x.safety_review || []).length ? `<div class="banner banner-warn q-safety"><p><strong>Protective device or work on equipment:</strong> approve only if none of these lines tells anyone to defeat, bypass or weaken a protection. Once live, this heuristic is guidance only and never raises confidence.</p><ul>${x.safety_review.map(l => `<li>${esc(l)}</li>`).join('')}</ul></div>` : ''}
          <div class="q-field"><span class="q-field-lbl">When</span> ${esc(whenText(x.symptom_pattern))}</div>
          ${lines('Check', x.checks)}${lines('Never', x.do_not)}${lines('Escalate when', x.escalate_when)}
          <div class="q-quote">"${esc(x.evidence_quote)}"</div></li>`;
      const describe = p => p.kind === 'expert_capture'
        ? `<div class="q-title"><strong>${esc(p.proposal_id)}</strong> <span class="badge badge-purple">Expert interview</span>${p.duplicate_of ? ` <span class="badge badge-yellow">Copy: same words as ${esc(p.duplicate_of)}</span>` : ''}</div>
            <div class="q-meta">${esc(p.expert_name)}, ${esc(p.expert_role)} · ${(p.heuristics || []).length} heuristic(s) · ${esc({ adp: 'drafted by Tencent Cloud ADP', mock: 'drafted by the offline models', manual: 'entered by hand' }[p.provider] || p.provider)}, reviewed by ${esc(p.submitted_by)}${p.expert_consent ? ' · expert consent recorded' : ''}</div>
            <ul class="q-list">${(p.heuristics || []).map(heuristicLine).join('')}</ul>`
        : p.kind === 'escalation_resolution'
        ? `<div class="q-title"><strong>${esc(p.proposal_id)}</strong> <span class="badge badge-red">Escalation resolution</span></div>
            <div class="q-meta">Confirmed cause: <strong>${esc(causeLabel(p.confirmed_cause))}</strong> · Case ${esc(p.case_id)} · ${esc(p.asset_id)} · resolved by ${esc(p.submitted_by)}</div>
            <div class="q-quote">"${esc(p.resolution)}"</div>`
        : `<div class="q-title"><strong>${esc(p.proposal_id)}</strong> <span class="badge badge-blue">Outcome feedback</span></div>
            <div class="q-meta">Confirmed cause: <strong>${esc(causeLabel(p.confirmed_cause))}</strong> · Case ${esc(p.case_id)} · ${esc(p.asset_id)} · submitted by ${esc(p.submitted_by)}</div>`;
      qb.innerHTML = queue.map(p => {
        const own = p.submitted_by === me;
        // Mirrors the server rule: only a knowledge steward decides, pill by
        // pill; each pill's owner decides it, and another steward stands in
        // only when the owner proposed it. Admin can view, revoke and roll
        // back, not decide.
        const waiting = p.awaiting_signoff || [];
        const decides = w => (w.owner && w.owner !== p.submitted_by) ? w.owner === me : me !== p.submitted_by;
        const mine = waiting.filter(decides).map(w => w.pill);
        const notSteward = api.role() !== 'knowledge_steward';
        const notOwner = !own && !mine.length;
        const blocked = own || notSteward || notOwner;
        const why = notSteward ? 'Only a knowledge steward decides on knowledge.'
          : own ? 'You sent this. A different steward must decide.'
          : `Waiting for ${waiting.map(w => `${esc(w.pill)} (${esc(w.owner || 'any other steward')})`).join(', ')}; you don't decide those pills.`;
        const signed = Object.entries(p.signoffs || {});
        const signLine = (signed.length || waiting.length > 1)
          ? `<div class="q-signoff">Each pill's steward signs off: ${[
              ...signed.map(([pill, s]) => `<span class="badge badge-green">${esc(pill)} ✓ ${esc(s.by)}</span>`),
              ...waiting.map(w => `<span class="badge badge-grey">${esc(w.pill)} · waiting for ${w.owner ? esc(w.owner) : `a steward other than ${esc(p.submitted_by)}${w.stand_in ? ' (the owner proposed it)' : ''}`}</span>`),
            ].join(' ')}</div>` : '';
        // Every check, and every line about a protective device, needs the
        // approver's explicit safety review (learning.needs_safety_review).
        const held = [...new Set((p.heuristics || []).flatMap(h => [...(h.checks || []), ...(h.safety_review || [])]))];
        const pid = esc(p.proposal_id);
        return `<div class="card q-card" style="margin-bottom:8px">
          <div class="q-body">${describe(p)}${signLine}</div>
          <div class="q-actions">
            <button class="btn btn-green btn-sm" id="approve-${pid}" ${blocked ? 'disabled aria-describedby="own-' + pid + '"' : ''}>${!blocked && mine.length < waiting.length ? `Sign off ${esc(mine.join(', '))}…` : 'Approve…'}</button>
            <button class="btn btn-red btn-sm" id="reject-${pid}" ${blocked ? 'disabled' : ''}>Reject…</button>
            ${blocked ? `<div class="q-own" id="own-${pid}">${why}</div>` : ''}
            <div class="q-reject" id="ap-${pid}" hidden>
              <label for="ap-reason-${pid}">Why is this sound? (recorded in the ledger)</label>
              <input id="ap-reason-${pid}" type="text" placeholder="e.g. Checked each line against the interview">
              ${held.length ? `<label class="hazard-ack"><input type="checkbox" id="ap-safety-${pid}"> Safety review: I read all ${held.length} check(s) and line(s) about protective devices above. None tells anyone to defeat, bypass or weaken a protection.</label>` : ''}
              <div class="flex gap-8"><button class="btn btn-green btn-sm" id="ap-go-${pid}">Confirm approval</button><button class="btn btn-secondary btn-sm" id="ap-cancel-${pid}">Cancel</button></div>
            </div>
            <div class="q-reject" id="rj-${pid}" hidden>
              <label for="rj-reason-${pid}">Reason (shown to the expert's capturer)</label>
              <input id="rj-reason-${pid}" type="text" placeholder="e.g. Cause is wrong for this asset">
              <div class="flex gap-8"><button class="btn btn-red btn-sm" id="rj-go-${pid}">Confirm reject</button><button class="btn btn-secondary btn-sm" id="rj-cancel-${pid}">Cancel</button></div>
            </div>
          </div>
        </div>`;
      }).join('');
      // Wire approve/reject buttons
      queue.forEach(p => {
        const id = p.proposal_id;
        const aBtn = document.getElementById(`approve-${id}`);
        const rBtn = document.getElementById(`reject-${id}`);
        const box = document.getElementById(`rj-${id}`);
        const apBox = document.getElementById(`ap-${id}`);
        if (aBtn) aBtn.onclick = () => { apBox.hidden = false; document.getElementById(`ap-reason-${id}`).focus(); };
        document.getElementById(`ap-cancel-${id}`).onclick = () => { apBox.hidden = true; };
        document.getElementById(`ap-go-${id}`).onclick = async () => {
          const rationale = document.getElementById(`ap-reason-${id}`).value.trim();
          if (!rationale) { showToast('Say why this knowledge is sound before approving', 'error'); document.getElementById(`ap-reason-${id}`).focus(); return; }
          const safety = document.getElementById(`ap-safety-${id}`);
          if (safety && !safety.checked) { showToast('Confirm the safety review of the lines about protective devices', 'error'); safety.focus(); return; }
          try {
            const r = await api.post(`/kb/proposals/${id}/approve`, { rationale, safety_reviewed: safety ? 'true' : '' });
            if (r.status === 'awaiting_signoff') {
              showToast(`${id}: you signed off ${r.signed_for.join(', ')}. Not live yet; waiting for ${r.awaiting_signoff.map(w => `${w.pill} (${w.owner || 'another steward'})`).join(', ')}.`, 'success');
            } else {
              showToast(`${id} approved: now live as ${(r.kb_version_labels || []).join(', ') || 'new knowledge'}`, 'success');
            }
            refreshAll();
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
        if (rBtn) rBtn.onclick = () => { box.hidden = false; document.getElementById(`rj-reason-${id}`).focus(); };
        const cancel = document.getElementById(`rj-cancel-${id}`);
        if (cancel) cancel.onclick = () => { box.hidden = true; };
        const go = document.getElementById(`rj-go-${id}`);
        if (go) go.onclick = async () => {
          const reason = document.getElementById(`rj-reason-${id}`).value.trim();
          if (!reason) { showToast('Give a reason so the capturer knows what to fix', 'error'); document.getElementById(`rj-reason-${id}`).focus(); return; }
          try { await api.post(`/kb/proposals/${id}/reject`, { reason }); showToast(`${id} rejected`, 'success'); refreshAll(); }
          catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      });
    } catch (e) {
      qb.innerHTML = isForbidden(e)
        ? rbacNote('Reviewing knowledge proposals', 'knowledge stewards (steward1, steward2)')
        : `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }

  // Re-run diagnosis on similar still-open cases after a proposal approves
  // (Phase 3: "confidence the KB can move" — show the before/after, live).
  // targets: [[cause, assetType], ...] — every cause the approval touched.
  async function loadRerunCandidates(targets) {
    const card = document.getElementById('rerun-card');
    const body = document.getElementById('rerun-body');
    if (!card || !body) return;
    try {
      const seen = new Set();
      const matches = [];
      for (const [cause, assetType] of targets) {
        const params = new URLSearchParams({ cause });
        if (assetType) params.set('asset_type', assetType);
        for (const m of (await api.get(`/cases/similar?${params}`)).matches) {
          if (!seen.has(m.case_id)) { seen.add(m.case_id); matches.push({ ...m, cause }); }
        }
      }
      card.hidden = false;
      const names = [...new Set(targets.map(([c]) => causeLabel(c)))].join(', ');
      if (!matches.length) {
        body.innerHTML = `<p class="muted">No open case is currently diagnosed as <strong>${esc(names)}</strong> to re-score.</p>`;
        return;
      }
      body.innerHTML = `
        <p class="muted" style="margin-bottom:10px">Open cases diagnosed with what was just approved. Re-run shows what the new knowledge alone changes, without touching the case.</p>
        ${matches.map(m => `
          <div class="rerun-row" id="rerun-row-${esc(m.case_id)}">
            <div><code>${esc(m.case_id)}</code> <span class="muted">${esc(m.asset_id)} · ${esc(causeLabel(m.cause))} · ${esc(plain(m.current_state).toLowerCase())}</span></div>
            <button class="btn btn-secondary btn-sm" id="rerun-btn-${esc(m.case_id)}">Re-run diagnosis</button>
            <span id="rerun-result-${esc(m.case_id)}"></span>
          </div>
        `).join('')}
      `;
      matches.forEach(m => {
        const btn = document.getElementById(`rerun-btn-${m.case_id}`);
        if (!btn) return;
        btn.onclick = async () => {
          btn.disabled = true;
          try {
            const preview = await api.get(`/cases/${m.case_id}/confidence-preview`);
            const before = (preview.before * 100).toFixed(1);
            const after = (preview.after * 100).toFixed(1);
            const up = preview.after >= preview.before;
            const crosses = preview.before < 0.55 && preview.after >= 0.55;
            document.getElementById(`rerun-result-${m.case_id}`).innerHTML =
              ` <span class="badge ${up ? 'badge-green' : 'badge-grey'}">${before}% &rarr; ${after}%</span>` +
              (crosses ? ` <span class="muted">now clears the 55% recommendation threshold${m.current_state === 'ESCALATED' ? '; on AOM Decision, "Request more evidence" re-diagnoses it with this knowledge' : ''}</span>` : '') +
              (Math.abs(preview.evidence_age_effect || 0) >= 0.005 ? ` <span class="muted">(effect of the knowledge only; the readings have also aged ${(Math.abs(preview.evidence_age_effect) * 100).toFixed(1)} points since the case was scored)</span>` : '');
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
          btn.disabled = false;
        };
      });
    } catch (e) {
      card.hidden = false;
      body.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }


  // Load KB stats
  async function loadStats() {
    try {
      const stats = await api.get('/kb/stats');
      const _c = await loadCauses();
      const _causeCount = _c.length;
      const _treeCount = new Set(_c.map(c => c.asset_type)).size;
      const pillLabels = Object.values(stats.kb_version_labels || {});
      // One line, not four: "v1.3.0" when every pill matches, else the range.
      const nums = pillLabels.map(l => l.replace(/^.* v/, 'v'));
      const same = nums.length && nums.every(n => n === nums[0]);
      const sorted = [...nums].sort((x, y) => x.localeCompare(y, undefined, { numeric: true }));
      const kbHeadline = !nums.length ? 'n/a' : same ? esc(nums[0]) : `${esc(sorted[0])}–${esc(sorted.at(-1))}`;
      const kbSub = same ? 'Knowledge, all pills' : 'Knowledge versions (hover for each pill)';
      setHTML('gov-stats', `
        <div class="stat"><div class="stat-val">${stats.total_validated_cases ?? 0}</div><div class="stat-lbl">Validated Cases</div></div>
        <div class="stat stat-purple"><div class="stat-val">${stats.feedback_added ?? 0}</div><div class="stat-lbl">Feedback Added</div></div>
        <div class="stat stat-yellow"><div class="stat-val">${stats.pending_proposals ?? 0}</div><div class="stat-lbl">Pending Proposals</div></div>
        <div class="stat stat-green" title="${esc(pillLabels.join(' · '))}"><div class="stat-val">${kbHeadline}</div><div class="stat-lbl">${kbSub}</div></div>
        <div class="stat stat-blue"><div class="stat-val">${_treeCount} / ${_causeCount}</div><div class="stat-lbl">Asset trees / Causes</div></div>
      `);
      const dist = stats.cause_distribution || stats.causes || {};
      const priors = stats.cause_priors || {};
      // fall back to cause_priors ({cause: {confirmed, total, rate}})
      // when the API doesn't return a flat cause_distribution dict
      const entries = Object.keys(dist).length
        ? Object.entries(dist)
        : Object.entries(priors).map(([cause, info]) => [cause, info.total || info.confirmed || 0]);
      const cdEl = document.getElementById('cause-dist');
      if (!entries.length) {
        cdEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No validated cases yet</div><div class="empty-state-desc">Once cases are closed with confirmed root causes, their validated knowledge will appear here as cause distribution bars.</div></div>`;
      } else {
        const max = Math.max(...entries.map(([, v]) => v));
        cdEl.innerHTML = entries.map(([cause, count]) => {
          const pct = (count / max * 100).toFixed(0);
          return `<div class="cause-bar"><div class="cause-bar-label" title="${esc(causeLabel(cause))}">${esc(causeLabel(cause))}</div><div class="cause-bar-track"><div class="cause-bar-fill" style="width:${pct}%"></div></div><div class="cause-bar-count">${count}</div></div>`;
        }).join('');
      }
    } catch (e) {
      setHTML('cause-dist', `<p class="muted">Error: ${esc(e.message)}</p>`);
    }
  }

  // Load audit trace
  async function loadTrace() {
    if (!api.can('read_audit_trail')) {
      setHTML('trace-body', rbacNote('The audit trail', 'auditors, knowledge stewards and admins'));
      return;
    }
    try {
      const data = await api.get('/audit/trace');
      const entries = data.entries || [];
      const tb = document.getElementById('trace-body');
      if (!tb) return;
      if (!entries.length) {
        tb.innerHTML = `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No audit entries</div><div class="empty-state-desc">SHA-256 hash-chain audit entries will appear here once cases progress through state transitions.</div></div>`;
        return;
      }
      tb.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>Case</th><th>Transition</th><th>Actor</th><th>Reason</th><th>Time</th><th>Hash</th><th>Chain</th></tr></thead>
        <tbody>${entries.slice().reverse().map(e => `<tr>
          <td><code>${esc(e.case_id)}</code></td>
          <td>${esc(e.from_state)} -> ${esc(e.to_state)}</td>
          <td>${esc(e.actor)}</td>
          <td>${esc(e.reason)}</td>
          <td>${fmtTime(e.at)}</td>
          <td><code>${esc((e.hash || '').substring(0, 12))}...</code> <button class="audit-copy-btn" onclick="window.__app__.copyToClipboard('${esc(e.hash || '')}', this)">Copy</button></td>
          <td>${e.chain_valid ? '<span class="badge badge-green">OK</span>' : '<span class="badge badge-red">FAIL</span>'}</td>
        </tr>`).join('')}</tbody>
      </table></div>`;
    } catch (e) {
      setHTML('trace-body', isForbidden(e)
        ? rbacNote('The audit trail', 'auditors, knowledge stewards and admins')
        : `<p class="muted">Error: ${esc(e.message)}</p>`);
    }
  }

  async function loadLedger() {
    if (!api.can('read_audit_trail')) {
      setHTML('ledger-body', rbacNote('The governance ledger', 'auditors, knowledge stewards and admins'));
      return;
    }
    try {
      const { entries, chain_valid } = await api.get('/kb/ledger');
      setHTML('ledger-status', chain_valid ? '<span class="badge badge-green">Ledger verified</span>' : '<span class="badge badge-red">Ledger FAILED verification</span>');
      const actionLabel = { proposal_submitted: 'Proposal submitted', proposal_approved: 'Approved', proposal_signed_off: 'Signed off (one pill)', proposal_rejected: 'Rejected', proposal_revoked: 'Revoked', rollback_requested: 'Rollback asked for', rollback_rejected: 'Rollback refused', rollback: 'Rollback countersigned', seeded: 'Seeded', integrity_review: 'Integrity review' };
      setHTML('ledger-body', !entries.length
        ? '<p class="muted">No governance actions yet.</p>'
        : `<p class="muted" style="margin-bottom:8px">Every proposal, approval, rejection, rollback and integrity review, with who did it and why. Keyed hash chain: editing any entry breaks verification.</p>
          <div class="table-wrap"><table>
          <thead><tr><th>#</th><th>Action</th><th>Actor</th><th>Proposal</th><th>Change</th><th>Reason</th><th>Time</th></tr></thead>
          <tbody>${entries.slice().reverse().map(e => `<tr>
            <td>${e.seq}</td><td>${esc(actionLabel[e.action] || e.action)}</td><td>${esc(e.actor)}</td>
            <td>${e.proposal_id ? `<code>${esc(e.proposal_id)}</code>` : '-'}</td>
            <td>${e.changes ? esc(e.changes) : '<span class="muted">no version change</span>'}</td>
            <td>${esc(e.reason)}</td><td>${fmtTime(e.at)}</td>
          </tr>`).join('')}</tbody></table></div>`);
    } catch (e) {
      setHTML('ledger-body', isForbidden(e)
        ? rbacNote('The governance ledger', 'auditors, knowledge stewards and admins')
        : `<p class="muted">Error: ${esc(e.message)}</p>`);
    }
  }

  const TAMPER_EVENTS = {
    snapshot_modified_between_saves: 'Snapshot changed on disk between saves',
    audit_chain_failure_on_load: 'Audit chain failed on restart',
    anchor_missing: 'No integrity anchor for this database',
    anchor_invalid: 'Integrity anchor was edited',
    database_replaced: 'A different database was put in place',
  };
  async function loadTamperEvents() {
    const body = document.getElementById('tamper-body');
    if (!body) return;
    if (!api.can('read_audit_trail')) {
      body.innerHTML = rbacNote('Integrity events', 'auditors, knowledge stewards and admins');
      return;
    }
    try {
      const data = await api.get('/system/integrity');
      const events = data.events || [];
      if (!events.length) {
        body.innerHTML = `<div class="empty-state"><div class="empty-state-icon">[!]</div><div class="empty-state-title">Clean</div><div class="empty-state-desc">No tamper events detected. Every snapshot written matches what this process last saw, and every audit chain verified on load.</div></div>`;
        return;
      }
      const archived = events.some(e => e.archived_path);
      const open = events.filter(e => !e.acknowledged).length;
      const canAck = api.can('review_audit_integrity');
      body.innerHTML = `<div class="banner ${open ? 'banner-error' : 'banner-warn'}" style="margin-bottom:8px"><p><strong>${events.length} integrity event(s) recorded, ${open} not yet acknowledged.</strong> ${archived ? 'Where a snapshot was tampered with, it was archived (paths below) before the clean state overwrote the file, so no restart can erase the evidence.' : 'Each says what was found.'} ${open && !canAck ? 'An auditor acknowledges each one here.' : ''}</p></div>
        <ul style="margin:0 0 0 18px">${events.slice().reverse().map(e => `<li style="margin-bottom:6px"><strong>${esc(TAMPER_EVENTS[e.event] || e.event)}</strong> — ${esc(e.detail)}${e.archived_path ? ' · <code>' + esc(e.archived_path) + '</code>' : ''}<div class="muted" style="font-size:12px">${esc(e.at)} · ${e.acknowledged ? 'acknowledged by an auditor' : '<strong>not acknowledged</strong>'}</div>
          ${!e.acknowledged && canAck ? `<div class="flex gap-8 flex-wrap align-center mt-16"><input type="text" class="tamper-reason" data-at="${esc(e.at)}" placeholder="Reason (required)" aria-label="Reason for acknowledging this event" style="flex:1 1 240px"><button class="btn btn-secondary btn-sm" data-ack="${esc(e.at)}">Acknowledge</button></div>` : ''}</li>`).join('')}</ul>`;
      body.querySelectorAll('[data-ack]').forEach(b => b.onclick = async () => {
        const reason = body.querySelector(`.tamper-reason[data-at="${CSS.escape(b.dataset.ack)}"]`).value.trim();
        if (!reason) { showToast('Give a reason for acknowledging this event', 'error'); return; }
        try {
          await api.post(`/audit/tamper/acknowledge?event_at=${encodeURIComponent(b.dataset.ack)}&reason=${encodeURIComponent(reason)}`);
          showToast('Tamper event acknowledged in the ledger', 'success');
          loadTamperEvents();
          loadIntegrity();
        } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
      });
    } catch (e) {
      setHTML('tamper-body', isForbidden(e)
        ? rbacNote('Integrity events', 'auditors, knowledge stewards and admins')
        : `<p class="muted">Error: ${esc(e.message)}</p>`);
    }
  }

  loadStats();
  loadQueue();
  loadLedger();
  loadTrace();
  loadIntegrity();
  loadTamperEvents();
}

// ════════════════════════════════════════════════════════════
// Screen 0: Expert Knowledge Capture (the harvest)
// Interview -> AI draft -> capturer reviews -> second steward approves.
// The model drafts; people decide. Nothing here touches the live KB.
// ════════════════════════════════════════════════════════════
const MAX_TRANSCRIPT = 20000;

export function renderCapture(el, state, h) {
  const { api, showToast, esc, navigate } = h;
  const role = api.user();
  const canCapture = api.can('capture_expert_knowledge');
  let draft = null;      // last AI draft from /capture/draft
  let submitted = null;  // proposal after submit
  let draftRun = 0;      // bumped when a draft is abandoned, so a late AI reply is ignored

  el.innerHTML = `
    <h2 class="sr-only">Capture expert knowledge</h2>
    ${nextHint('a different knowledge steward must approve this draft before it is reused in diagnoses.')}
    <ol class="cap-steps" id="cap-steps" aria-label="Capture progress">
      <li data-step="1">Interview</li>
      <li data-step="2">AI draft</li>
      <li data-step="3">You review</li>
      <li data-step="4">Second steward approves</li>
    </ol>
    <div class="grid-2 cap-grid">
      <div class="card">
        <div class="card-header"><h3>1. Expert interview</h3></div>
        <div class="card-body">
          <p class="muted cap-hint">Paste or transcribe what an experienced technician told you. Keep their own words: anything the AI cannot quote word for word is discarded.</p>
          <div class="cap-row">
            <div class="form-group"><label for="cap-name">Expert</label><input id="cap-name" type="text" placeholder="e.g. R. Tan" autocomplete="off"></div>
            <div class="form-group"><label for="cap-role">Role and experience</label><input id="cap-role" type="text" placeholder="e.g. Senior M&amp;E Technician, 22 years" autocomplete="off"></div>
          </div>
          <div class="form-group"><label for="cap-asset">Main asset type discussed</label>
            <select id="cap-asset"><option>CRAH</option><option>Chiller</option><option>UPS</option><option>Pump</option></select>
            <div class="field-help">Knowledge about other equipment is filed under its own pill automatically.</div></div>
          <div class="form-group"><label for="cap-text">Interview transcript</label>
            <textarea id="cap-text" rows="14" maxlength="${MAX_TRANSCRIPT}" aria-describedby="cap-count" placeholder="Interviewer: When ... what do you check first?&#10;&#10;Technician: ..."></textarea>
            <div class="field-help" id="cap-count">0 / ${MAX_TRANSCRIPT.toLocaleString()} characters</div></div>
          <div class="flex gap-8 flex-wrap">
            <button class="btn btn-secondary" id="cap-sample">Load sample interview</button>
            <button class="btn btn-primary" id="cap-run" ${canCapture ? '' : 'disabled'}>Draft knowledge with AI</button>
            <button class="btn btn-secondary" id="cap-manual" ${canCapture ? '' : 'disabled'}>Write heuristics by hand</button>
          </div>
          ${canCapture ? '' : `<div class="banner banner-info mt-16"><p><strong>View only.</strong> Capturing expert knowledge is limited to Asset Ops Managers and Knowledge Stewards. Switch role in the top bar to try it.</p></div>`}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><div class="flex align-center gap-8"><span class="card-cloud" id="cap-avatar">${cloudSvg('ready', 34)}</span><h3 id="cap-right-title">2. AI draft</h3></div><span class="badge badge-grey" id="cap-status">Not started</span></div>
        <div class="card-body" id="cap-result" aria-live="polite">
          <div class="empty-state"><div class="empty-state-icon">[ ]</div>
            <div class="empty-state-title">No draft yet</div>
            <div class="empty-state-desc">Load the sample interview, then draft knowledge. You will review every heuristic before anything is sent for approval.</div></div>
        </div>
      </div>
    </div>`;

  const $ = id => document.getElementById(id);
  const text = $('cap-text');
  const setStep = n => document.querySelectorAll('#cap-steps li').forEach(li => {
    const k = +li.dataset.step;
    li.classList.toggle('done', k < n); li.classList.toggle('current', k === n);
    if (k === n) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  });
  const setStatus = (label, cls) => {
    const b = $('cap-status'); b.textContent = label; b.className = `badge ${cls}`;
    // The avatar mirrors the drafting state: working, done, or failed.
    $('cap-avatar').innerHTML = cloudSvg({ 'badge-blue': 'thinking', 'badge-red': 'offline', 'badge-green': 'online' }[cls] || 'ready', 34);
  };
  const updateCount = () => { $('cap-count').textContent = `${text.value.length.toLocaleString()} / ${MAX_TRANSCRIPT.toLocaleString()} characters`; };
  setStep(1);

  // Editing the interview after drafting makes the draft stale.
  ['cap-text', 'cap-asset'].forEach(id => $(id).addEventListener('input', () => {
    updateCount();
    if (draft && !submitted) { draft = null; renderEmpty('The interview changed. Draft again to see updated knowledge.'); }
  }));

  function renderEmpty(msg) {
    setStep(1); setStatus('Not started', 'badge-grey'); $('cap-right-title').textContent = '2. AI draft';
    $('cap-result').innerHTML = `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No draft yet</div><div class="empty-state-desc">${esc(msg)}</div></div>`;
  }

  $('cap-sample').onclick = async () => {
    try {
      const s = await api.get('/capture/sample');
      $('cap-name').value = s.expert_name; $('cap-role').value = s.expert_role;
      $('cap-asset').value = s.asset_type; text.value = s.transcript;
      text.dispatchEvent(new Event('input'));
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
  };

  const fieldList = (title, items) => items && items.length
    ? `<div class="kh-row"><span class="kh-label">${title}</span><ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : '';

  function heuristicCard(x, i, causes, editable) {
    const filed = x.asset_type || $('cap-asset').value;
    return `
      <div class="kh-item ${editable ? 'kh-editable' : ''}" data-i="${i}">
        <div class="kh-head">
          ${editable ? `<label class="kh-include"><input type="checkbox" class="kh-keep" data-i="${i}" checked> Include</label>` : ''}
          <span class="badge ${x.new_cause ? 'badge-yellow' : 'badge-blue'}">${esc(x.cause_label || causeLabel(x.likely_cause))}</span>
          <span class="badge badge-grey" title="The pill this knowledge will be filed under">Files under: ${esc(filed)}</span>
        </div>
        ${x.new_cause ? '<div class="kh-new">New cause: the engine cannot diagnose it until an engineer adds a decision-tree branch. Kept as reference knowledge.</div>' : ''}
        ${x.check_cause ? '<div class="kh-new">Check the cause: the expert\'s own words may rule it out. Correct it below or untick this item.</div>' : ''}
        ${x.off_topic ? '<div class="kh-new">Nothing in the expert\'s answer names this cause or its usual signs. Check it is filed under the right cause.</div>' : ''}
        ${editable && !x.new_cause ? `<div class="form-group kh-cause"><label for="kh-cause-${i}">Cause (correct it if the AI got it wrong)</label><select id="kh-cause-${i}" class="kh-cause-sel" data-i="${i}">${causeOptions(causes, x.likely_cause)}</select></div>` : ''}
        ${(x.safety_review || []).length ? '<div class="kh-new">Names a protective device or work on equipment: once live it is guidance only (it never raises confidence).</div>' : ''}
        ${(x.notes || []).filter(n => !/names a protective device|pill, so it will be filed/.test(n)).map(n => `<div class="kh-note">${esc(n.replace(/^Item \d+:?\s*/, ''))}</div>`).join('')}
        <div class="kh-row"><span class="kh-label">When</span>${esc(whenText(x.symptom_pattern))}</div>
        ${fieldList('Checks', (x.checks || []).filter(c => c !== x.symptom_pattern))}${fieldList('Never', x.do_not)}${fieldList('Escalate when', x.escalate_when)}
        <span class="kh-label" style="margin-top:10px">Expert's own words</span>
        <blockquote class="kh-quote">"${esc(x.evidence_quote)}"</blockquote>
      </div>`;
  }

  // The grounding check, made visible: what the AI drafted that survived
  // (it is in the expert's own answer) and what it said that did not.
  function groundingCard(d) {
    // Each kept line keeps its field, so a "Never" line never reads as an instruction.
    const kept = d.heuristics.flatMap(x => [
      ...(x.checks || []).map(t => ['Check', t]), ...(x.do_not || []).map(t => ['Never', t]),
      ...(x.escalate_when || []).map(t => ['Escalate when', t])]);
    const rejected = d.rejected || [];
    const unused = d.unused_answers || [];
    const fieldName = { check: 'Check', never: 'Never', 'escalate-when': 'Escalate when', heuristic: 'Heuristic' };
    // A line the expert said in another answer can become its own item, by hand.
    const movable = r => r.field !== 'heuristic' && /different answer/.test(r.reason);
    return `<div class="card grounding-card"><div class="card-header"><h3>Grounding check</h3>
        <span class="badge ${rejected.length || unused.length ? 'badge-red' : 'badge-green'}">${kept.length} kept · ${rejected.length} rejected · ${unused.length} answer${unused.length === 1 ? '' : 's'} with no knowledge</span></div>
      <div class="card-body">
        <p class="muted" style="margin-bottom:8px">Every line the AI drafted must be the expert's own words from the same answer, and must not defeat a safety device. Anything else is rejected here and again on the server when you send.</p>
        <ul class="ground-list">
          ${kept.map(([f, l]) => `<li class="ground-ok"><span aria-hidden="true">✓</span> <span class="sr-only">Kept:</span> <strong>${f}:</strong> “${esc(l)}”</li>`).join('')}
          ${rejected.map((r, i) => `<li class="ground-bad"><span aria-hidden="true">✗</span> <span class="sr-only">Rejected:</span> <strong>${esc(fieldName[r.field] || r.field)}:</strong> “${esc(r.text)}” <span class="ground-why">${esc(r.reason)}</span>${movable(r) ? ` <button class="btn btn-secondary btn-sm ground-move" data-i="${i}">Add it as its own item</button>` : ''}</li>`).join('')}
          ${unused.map(u => `<li class="ground-bad"><span aria-hidden="true">!</span> <span class="sr-only">No knowledge drafted:</span> <strong>Expert answer:</strong> “${esc(u.excerpt)}” <span class="ground-why">${esc(u.reason)}</span></li>`).join('')}
        </ul>
        ${d.heuristics.length ? `<div class="ground-try">
          <label for="gt-line">Try to slip in a line the expert never said</label>
          <div class="flex gap-8 flex-wrap"><input id="gt-line" type="text" value="Tighten the terminal to 12 Nm." style="flex:1 1 260px">
          <button class="btn btn-secondary btn-sm" id="gt-go">Check it</button></div>
          <div id="gt-result" aria-live="polite"></div>
        </div>` : ''}
      </div></div>`;
  }
  function wireGroundingTry() {
    const go = $('gt-go');
    if (!go) return;
    go.onclick = async () => {
      const line = $('gt-line').value.trim();
      if (!line) return;
      const [first, ...rest] = draft.heuristics;
      const heuristics = [{ ...first, checks: [...(first.checks || []), line] }, ...rest];
      go.disabled = true;
      try {
        const r = await api.postJson('/capture/check', {
          asset_type: $('cap-asset').value, transcript: text.value, heuristics });
        const hit = (r.rejected || []).find(x => x.text === line);
        setHTML('gt-result', hit
          ? `<p class="ground-bad"><span aria-hidden="true">✗</span> <strong>Rejected:</strong> “${esc(line)}”: ${esc(hit.reason)}. It cannot become knowledge.</p>`
          : `<p class="ground-ok"><span aria-hidden="true">✓</span> Kept: the expert said this in the same answer.</p>`);
      } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
      go.disabled = false;
    };
  }

  function modelBadge(d) {
    const by = { adp: 'Tencent Cloud ADP', manual: 'Entered by hand', mock: 'Offline mock model' }[d.provider] || d.provider;
    return `<span class="badge badge-purple">Drafted by: ${esc(by)}</span>`;
  }

  async function renderDraft() {
    const causes = await loadCauses();
    setStep(3); setStatus('Draft, not submitted', 'badge-yellow'); $('cap-right-title').textContent = '3. Review the draft';
    $('cap-result').innerHTML = `
      <div class="flex gap-8 flex-wrap" style="margin-bottom:12px">
        ${modelBadge(draft)}
        <span class="badge badge-green">${draft.heuristics.length} ${draft.provider === 'manual' ? 'entered (quotes re-checked on send)' : 'grounded in the transcript'}</span>
        ${draft.dropped ? `<span class="badge badge-red">${draft.dropped} discarded: not said by the expert</span>` : ''}
      </div>
      ${(() => {
        const ws = draft.warnings || [];
        const filing = ws.filter(w => w.includes(' pill, so it will be filed'));
        // A kept heuristic's own notes are shown on its card, not as banners.
        const onCards = new Set(draft.heuristics.flatMap(x => x.notes || []));
        const other = ws.filter(w => !filing.includes(w) && !onCards.has(w));
        const moved = draft.heuristics.filter(x => x.asset_type && x.asset_type !== $('cap-asset').value);
        return other.map(w => `<div class="banner banner-warn"><p>${esc(w)}</p></div>`).join('')
          + (moved.length ? `<div class="banner banner-info"><p><strong>Filed under other pills:</strong> ${moved.map(x => `${esc(x.cause_label)} goes to ${esc(x.asset_type)}`).join('; ')}. Each pill only uses knowledge about its own equipment.</p></div>` : '');
      })()}
      ${(draft.recheck || []).length ? `<div class="banner banner-warn" role="alert"><p><strong>Re-checked before sending:</strong> the server's grounding check changed the wording of item(s) ${draft.recheck.join(', ')} (a line the expert did not say in that answer was dropped, or the WHEN was replaced by the expert's own sentence). Nothing was sent. Below is exactly what will be stored.</p></div>` : ''}
      ${groundingCard(draft)}
      <p class="muted cap-hint">Untick anything that is wrong or unclear and correct causes where needed. You cannot add words the expert did not say: the server checks every quote again.</p>
      ${draft.heuristics.map((x, i) => heuristicCard(x, i, causes, true)).join('')}
      ${manualForm(causes, draft.prefill)}
      <label class="hazard-ack"><input type="checkbox" id="cap-consent"> ${esc($('cap-name').value.trim() || 'The expert')} agreed to their words being recorded and reused as knowledge.</label>
      <div class="cap-submit">
        <button class="btn btn-primary" id="cap-submit">Send ${draft.heuristics.length} for steward approval</button>
        <span class="muted" id="cap-submit-note">A different knowledge steward must approve, and safety-review every check, before it goes live.</span>
      </div>`;
    wireManualForm(causes);
    wireGroundingMove();
    wireGroundingTry();
    const btn = $('cap-submit');
    const kept = () => [...document.querySelectorAll('.kh-keep')].filter(c => c.checked).map(c => +c.dataset.i);
    const refresh = () => {
      const n = kept().length;
      btn.disabled = n === 0;
      btn.textContent = n ? `Send ${n} for steward approval` : 'Select at least one heuristic';
      document.querySelectorAll('.kh-item').forEach(card => card.classList.toggle('kh-excluded', !kept().includes(+card.dataset.i)));
    };
    document.querySelectorAll('.kh-keep').forEach(c => c.addEventListener('change', refresh));
    // Correcting the cause changes which pill owns it -- update the "Files
    // under" chip (and the cause badge) live, not only once the review is
    // sent and the server's response comes back.
    document.querySelectorAll('.kh-cause-sel').forEach(sel => sel.addEventListener('change', () => {
      const info = causes.find(c => c.id === sel.value);
      if (!info) return;
      const card = sel.closest('.kh-item');
      const filedBadge = card.querySelector('.kh-head .badge-grey');
      if (filedBadge) filedBadge.textContent = `Files under: ${info.asset_type}`;
      const causeBadge = card.querySelector('.kh-head .badge-blue, .kh-head .badge-yellow');
      if (causeBadge) { causeBadge.textContent = info.label; causeBadge.className = 'badge badge-blue'; }
    }));
    btn.onclick = submit;
    refresh();
  }

  // Manual entry: the fallback when the AI is offline, or when the expert's
  // know-how doesn't fit what the model drafted. The same rule applies:
  // every heuristic must quote the expert's own words from the transcript.
  const norm = t => t.replace(/\s+/g, ' ').trim().toLowerCase();
  function manualForm(causes, prefill) {
    const p = prefill || {};
    const val = f => (p.field === f ? esc(p.text) : '');
    return `<div class="card mt-16" id="mh-card"><div class="card-header"><h3>Add a heuristic</h3></div><div class="card-body">
      <p class="muted" style="margin-bottom:8px">Add something the expert said that the draft missed, or a line the check put in another answer. Its quote is checked against the transcript again when you send.</p>
      <div class="form-group"><label for="mh-cause">Cause</label><select id="mh-cause">${causeOptions(causes)}</select></div>
      <div class="form-group"><label for="mh-when">When (the symptom the expert described)</label><input id="mh-when" type="text" value="${p.text ? esc(p.text) : ''}"></div>
      <div class="form-group"><label for="mh-checks">Checks (one per line)</label><textarea id="mh-checks" rows="3">${val('check')}</textarea></div>
      <div class="form-group"><label for="mh-never">Never (one per line)</label><textarea id="mh-never" rows="2">${val('never')}</textarea></div>
      <div class="form-group"><label for="mh-esc">Escalate when (one per line)</label><textarea id="mh-esc" rows="2">${val('escalate-when')}</textarea></div>
      <div class="form-group"><label for="mh-quote">Expert's own words (copy exactly from the transcript)</label><textarea id="mh-quote" rows="2">${p.text ? esc(p.text) : ''}</textarea></div>
      <button class="btn btn-secondary" id="mh-add">Add heuristic</button>
    </div></div>`;
  }
  // Rejected lines that the expert did say, in another answer, can be moved
  // into the form as their own item. Nothing is added here: the form still
  // goes through the server's grounding check when the review is sent.
  function wireGroundingMove() {
    document.querySelectorAll('.ground-move').forEach(btn => btn.onclick = () => {
      const r = (draft.rejected || [])[+btn.dataset.i];
      if (!r) return;
      draft.prefill = { text: r.text, field: r.field };
      renderDraft().then(() => $('mh-card') && $('mh-card').scrollIntoView({ block: 'start' }));
    });
  }
  function wireManualForm(causes) {
    const lines = id => $(id).value.split('\n').map(x => x.trim()).filter(Boolean);
    $('mh-add').onclick = () => {
      const quote = $('mh-quote').value.trim();
      const when = $('mh-when').value.trim();
      if (!when || !quote) { showToast('Add the symptom and the expert\'s own words', 'error'); return; }
      if (!norm(text.value).includes(norm(quote))) { showToast('That quote is not in the transcript word for word', 'error'); $('mh-quote').focus(); return; }
      const c = causes.find(x => x.id === $('mh-cause').value);
      draft.heuristics.push({ symptom_pattern: when, likely_cause: c.id, cause_label: c.label, asset_type: c.asset_type,
        checks: lines('mh-checks'), do_not: lines('mh-never'), escalate_when: lines('mh-esc'), evidence_quote: quote });
      draft.prefill = null;
      renderDraft();
    };
  }

  $('cap-manual').onclick = () => {
    if (!text.value.trim()) { showToast('Paste the interview transcript first', 'error'); text.focus(); return; }
    draftRun++;  // a draft still running is abandoned
    draft = { provider: 'manual', heuristics: [], warnings: [], dropped: 0 }; submitted = null;
    renderDraft();
  };

  async function submit() {
    const btn = $('cap-submit');
    if (!$('cap-consent').checked) { showToast("Record the expert's consent before sending", 'error'); $('cap-consent').focus(); return; }
    btn.disabled = true; btn.textContent = 'Sending…';
    const heuristics = [...document.querySelectorAll('.kh-keep')].filter(c => c.checked).map(c => {
      const i = +c.dataset.i; const sel = $(`kh-cause-${i}`);
      return { ...draft.heuristics[i], likely_cause: sel ? sel.value : draft.heuristics[i].likely_cause };
    });
    try {
      const d = await api.postJson('/capture/interview', {
        expert_name: $('cap-name').value.trim(), expert_role: $('cap-role').value.trim(),
        asset_type: $('cap-asset').value, transcript: text.value, heuristics,
        draft_id: draft.draft_id, expert_consent: true,
      });
      submitted = d;
      draft.recheck = null;
      setStep(4); setStatus('Waiting for second steward', 'badge-yellow'); $('cap-right-title').textContent = '4. Sent for approval';
      const causes = await loadCauses();
      $('cap-result').innerHTML = `
        <div class="banner banner-success"><p><strong>Sent as ${esc(d.proposal_id)}.</strong> Nothing is live yet. A knowledge steward other than you (${esc(role)}) must approve it on the Governance screen. What you see below is exactly what the steward will see.</p></div>
        ${d.duplicate_of ? `<div class="banner banner-warn"><p>The same expert words are already with the stewards as <strong>${esc(d.duplicate_of)}</strong>. The steward is told, so they can reject the copy.</p></div>` : ''}
        <div class="flex gap-8 flex-wrap" style="margin:12px 0">${modelBadge(d)}<span class="badge badge-green">${d.heuristics.length} heuristic(s) sent</span></div>
        ${d.heuristics.map((x, i) => heuristicCard(x, i, causes, false)).join('')}
        <div class="flex gap-8 flex-wrap mt-16">
          <button class="btn btn-primary" id="cap-gov">Open Governance queue</button>
          <button class="btn btn-secondary" id="cap-new">Capture another interview</button>
        </div>`;
      $('cap-gov').onclick = () => navigate('governance');
      $('cap-new').onclick = () => navigate('capture');
      showToast(`${d.proposal_id} sent for steward approval`, 'success');
    } catch (e) {
      if (e.status === 409 && e.detail && e.detail.heuristics) {
        // The server's re-check would store different wording than shown.
        // Nothing was queued: show the re-checked text, then send again.
        draft.heuristics = e.detail.heuristics;
        draft.recheck = e.detail.changed_items;
        await renderDraft();
        showToast('The re-check changed some wording. Review it, then send again.', 'error');
        return;
      }
      btn.disabled = false; btn.textContent = 'Try sending again';
      showToast(`Could not send: ${e.message}`, 'error');
    }
  }

  $('cap-run').onclick = async () => {
    const name = $('cap-name').value.trim(), who = $('cap-role').value.trim();
    const missing = [!name && 'expert', !who && 'role and experience', !text.value.trim() && 'transcript'].filter(Boolean);
    if (missing.length) {
      showToast(`Add the ${missing.join(', ')} first`, 'error');
      ({ expert: $('cap-name'), 'role and experience': $('cap-role'), transcript: text })[missing[0]].focus();
      return;
    }
    const run = $('cap-run');
    run.disabled = true; run.textContent = 'Drafting…';
    setStep(2); setStatus('Drafting…', 'badge-blue'); submitted = null;
    // The model can take a minute or two. Say what is happening, how long it
    // has taken, and offer the manual route once it runs long.
    $('cap-result').innerHTML = `<div class="skeleton-card"><div class="skeleton-line"></div><div class="skeleton-line"></div><div class="skeleton-line"></div></div>
      <p id="cap-progress-step" class="cap-progress-step"></p>
      <p class="muted" id="cap-progress-time"></p>
      <div id="cap-progress-slow" hidden><div class="banner banner-info mt-16"><p>Taking longer than usual. Drafts often take a minute or two. You can keep waiting, or write the heuristics by hand now; nothing is sent until you choose.</p>
        <button class="btn btn-secondary mt-16" id="cap-progress-manual">Write heuristics by hand</button></div></div>`;
    const started = Date.now();
    const myRun = ++draftRun;
    const stepFor = secs => secs < 4 ? 'Sending the transcript. Anything that looks like an instruction is removed first.'
      : secs < 20 ? 'The model is reading the expert\'s answers and drafting candidate knowledge.'
      : secs < 45 ? 'Still working. Each heuristic is checked against the transcript as it comes back.'
      : 'Still working on the draft.';
    const ticker = setInterval(() => {
      const secs = Math.floor((Date.now() - started) / 1000);
      const step = $('cap-progress-step'), time = $('cap-progress-time'), slow = $('cap-progress-slow');
      if (!step) { clearInterval(ticker); return; }
      step.textContent = stepFor(secs);
      time.textContent = `Elapsed ${secs} s`;
      if (slow) slow.hidden = secs < 45;
      const manualNow = $('cap-progress-manual');
      if (manualNow) manualNow.onclick = () => { clearInterval(ticker); $('cap-manual').click(); };
    }, 1000);
    try {
      const got = await thinking(api.postJson('/capture/draft', { asset_type: $('cap-asset').value, transcript: text.value }));
      clearInterval(ticker);
      window.__app__?.refreshSystemInfo?.();  // the AI chip reflects this call's outcome
      if (myRun !== draftRun) return;  // the person has moved on to writing it by hand
      draft = got;
      await renderDraft();
    } catch (e) {
      clearInterval(ticker);
      if (myRun !== draftRun) return;
      draft = null; setStep(1); setStatus('Draft failed', 'badge-red');
      window.__app__?.refreshSystemInfo?.();
      const aiDown = /extraction failed|ADP|reach|key/i.test(e.message);
      $('cap-result').innerHTML = `<div class="banner banner-error"><p><strong>No usable draft.</strong> ${esc(e.message)}</p>
        <p>${aiDown
          ? 'The AI model is unavailable, so nothing was drafted. You can still capture this interview by hand.'
          : 'The model found nothing it could quote from the expert. Write the heuristics by hand, or check the transcript holds the expert\'s own answers.'}</p>
        <button class="btn btn-secondary mt-16" id="cap-manual-fallback">Write heuristics by hand</button></div>`;
      $('cap-manual-fallback').onclick = () => $('cap-manual').click();
    } finally {
      run.disabled = !canCapture; run.textContent = 'Draft again with AI';
    }
  };
}
