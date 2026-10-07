// screens.js - Renderers for all 5 screens + demo case seeder

import { api } from './api.js?v=7';
import { cloudSvg } from './cloud.js?v=4';

// Async loaders can resolve after the user has navigated away; never crash.
function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
  return el;
}

// A case whose audit chain fails verification is frozen server-side (423).
// Show that up front and hide every control that would only be refused.
function frozenWrap(s, html, esc) {
  if (s.audit_chain_valid !== false) return html;
  return `<div class="banner banner-error"><p><strong>Case frozen:</strong> the audit chain for ${esc(s.case_id)} failed verification, so it can be read but not advanced, decided or closed until an auditor reviews it.</p></div>
    <div class="case-frozen">${html}</div>`;
}

const isForbidden = e => e?.status === 403 || /403|lacks capability|forbidden/i.test(e?.message || '');
const rbacNote = (what, roles) => `<div class="banner banner-info"><p><strong>Role-based access:</strong> ${what} is limited to ${roles}. Switch role in the top bar to see it.</p></div>`;

// A one-line orientation cue at the top of every screen, so someone who
// just landed on it (or is watching over a shoulder) knows what to do or
// expect next without reading the whole card stack first.
const nextHint = text => `<p class="next-hint">${_esc(text)}</p>`;

// F5: local HTML-escape for module-level helper (render functions receive `esc` via helpers)
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
// "kb:technical_services:pump_tree:v1:Q2" -> "Pump tree v1, Q2"; the full
// reference stays in the tooltip.
const kbRef = r => {
  const parts = String(r).split(':');
  const label = parts.length >= 4
    ? `${plain(parts[2]).replace(/^\w/, c => c.toUpperCase()).replace(/^(Ups|Crah)\b/, m => m.toUpperCase())} ${parts.slice(3).join(', ')}`
    : String(r);
  return `<span class="kb-ref" title="${_esc(r)}">${_esc(label)}</span>`;
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
  const abnormal = [`Trigger: ${plain(obs.type)} (reading ${obs.reading_status || 'unknown'})`];
  (s.evidence || []).forEach(ev => {
    (ev.abnormal || []).forEach(k => {
      abnormal.push(`${_humaniseKey(k)}: ${_formatValue(k, ev.payload[k], true)}`);
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
  return m.matched_terms && m.matched_terms.length
    ? `<div class="muted" style="margin:4px 0"><span class="badge badge-green">Seen in this case's evidence</span> ${m.matched_terms.map(t => `<code>${esc(t)}</code>`).join(' ')}</div>`
    : `<div class="muted" style="margin:4px 0"><span class="badge badge-grey">Not seen in this case's evidence</span> Shown as guidance; it does not raise confidence.</div>`;
}

// Approved expert know-how for this cause, shown where the decision is made.
function expertChecks(ek, esc) {
  if (!ek.matches || !ek.matches.length) {
    return `<p class="muted" style="margin-top:8px">No approved expert knowledge matches this cause yet.</p>`;
  }
  const list = (title, items) => items && items.length ? `<div><strong>${title}:</strong><ul class="expert-list">${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : '';
  return `<div class="mt-16"><span class="tier-label tier-advisory">Expert knowledge to apply (steward-approved)</span>
    ${ek.matches.map(m => `<article class="expert-match">
      <div><strong>${esc(m.expert_name)}</strong> <span class="muted">— ${esc(m.expert_role)} · KB v${esc(m.kb_version_label)}</span></div>
      ${corroboration(m, esc)}
      ${list('Check before acting', m.checks)}${list('Never', m.do_not)}${list('Escalate when', m.escalate_when)}
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

// F5: Evidence display toggle state (plain English vs raw JSON)
let _evidenceRawMode = false;
// The timeline opens on abnormal readings only; "show all" lists every item.
let _evidenceShowAll = false;

const FIELD_LABELS = {
  soh_pct: 'State of health (%)', age_months: 'Age (months)', battery_temp_c: 'Battery temp (°C)',
  temp_c: 'Temp (°C)', charge_pct: 'Refrigerant charge (%)', approach_temp: 'Approach temp (°C)',
  axial_mm_s: 'Axial vibration (mm/s)', npsh_margin: 'NPSH margin', load_pct: 'Load (%)',
  flow_pct: 'Flow (%)', float_voltage: 'Float voltage (V)', battery_voltage: 'Battery voltage (V)',
};

function _humaniseKey(key) {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
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

function renderEvidencePlain(payload, abnormalKeys = []) {
  if (!payload || typeof payload !== 'object') {
    return '<span class="muted">—</span>';
  }
  const entries = Object.entries(payload);
  return `<div class="evidence-plain">` + entries.map(([key, val]) => {
    const label = _humaniseKey(key);
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
export function renderDashboard(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate } = h;
  const isAdmin = api.role() === 'admin';

  el.innerHTML = `
    ${nextHint('click a case to see its diagnosis, or create a new one to get started.')}
    <div id="integrity-banner"></div>
    <details class="card why-panel">
      <summary><h3 style="display:inline">Why this exists</h3></summary>
      <div class="card-body">
        <p><strong>Problem:</strong> fault diagnosis know-how lives in individual technicians' heads. When an experienced tech is unavailable or retires, that judgement isn't captured anywhere a new case can reuse it.</p>
        <p><strong>Users:</strong> technicians trigger and work cases; Asset Ops Managers approve every recommendation before anything happens; Knowledge Stewards review and govern what the pill learns from interviews and closed cases.</p>
        <p><strong>Value:</strong> <em>assumption: manual triage without captured expert knowledge takes roughly 90 minutes per fault; replace with a measured Keppel baseline.</em> This pill's claim is narrower and checkable: a rule-based diagnosis plus any matching approved expert knowledge appears in seconds (see the Diagnosis screen), and a validated fix measurably raises confidence on the next identical fault (see Governance, and <code>make demo</code>). Nothing above the <em>assumption</em> line is Keppel data — it isn't.</p>
      </div>
    </details>
    <details class="card why-panel">
      <summary><h3 style="display:inline">Deployment path</h3></summary>
      <div class="card-body">
        <p><strong>Stage 1 -- Pilot:</strong> the decision tree, guardrails, governance loop, audit trail and RBAC in this repo are real and tested today; telemetry is a static mock registry pending a real BMS/SCADA feed.</p>
        <p><strong>Stage 2 -- Production on Tencent Cloud:</strong> containerised deploy (the repo's own Dockerfile), SQLite swapped for a managed database, secrets moved to Tencent Cloud's secret manager, real CMMS work-order integration.</p>
        <p><strong>Stage 3 -- Scale:</strong> additional asset types and sites, per-site knowledge-base governance, a real steward roster in place of the fixed two-steward registry demo.</p>
        <p class="muted">Full detail, including exactly what's real versus stubbed at each stage: <code>docs/IMPLEMENTATION_PATH.md</code>.</p>
      </div>
    </details>
    <div class="flex justify-between align-center" style="margin-bottom:20px">
      <div></div>
      <div class="flex gap-8">
        <button class="btn btn-secondary" id="btn-seed" ${isAdmin ? '' : 'disabled title="Seeding demo cases is limited to the Admin role"'}>Seed Demo Cases</button>
        <button class="btn btn-primary" id="btn-new">New Case</button>
      </div>
    </div>
    <div class="stats-row" id="stats-row"></div>
    <div class="card">
      <div class="table-wrap">
        <table id="cases-table">
          <thead><tr>
            <th>Case ID</th><th>Asset</th><th>Fault</th><th>Sensor</th>
            <th>Reading</th><th>Status</th><th>Confidence</th><th>Action</th>
          </tr></thead>
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
          <div class="form-group"><label>Sensor ID</label><input id="nc-sensor" type="text" value="SA-TEMP-01" placeholder="e.g. SA-TEMP-01"></div>
          <div class="form-group"><label>Fault Type</label><select id="nc-fault">
            <option value="temperature_measurement_missing">temperature measurement missing</option>
            <option value="chiller_compressor_trip">chiller compressor trip</option>
            <option value="ups_battery_fault">ups battery fault</option>
            <option value="pump_vibration_high">pump vibration high</option>
          </select></div>
          <div class="form-group"><label>Reading Status</label><select id="nc-reading">
            <option value="absent">absent</option>
            <option value="invalid">invalid</option>
          </select></div>
        </div>
        <button class="btn btn-primary" id="btn-create">Create Case</button>
      </div>
    </div>
  `;

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
      const st = await api.get('/audit/status');
      if (st.ok) return;
      const parts = [];
      if (st.broken_cases.length) parts.push(`case audit chain failed for ${st.broken_cases.map(esc).join(', ')} (frozen: no further actions allowed)`);
      if (!st.ledger_valid) parts.push('the knowledge governance ledger failed verification');
      if (!st.registry_valid) parts.push('the set of cases does not match its seal (a case was added or removed outside the app)');
      if (!st.tool_log_valid) parts.push('the tool audit log failed verification');
      setHTML('integrity-banner', `<div class="banner banner-error" role="alert"><p><strong>Audit integrity alert:</strong> ${parts.join('; ')}. An auditor should review this before anyone relies on it.</p></div>`);
    } catch (_) { /* banner is best-effort */ }
  })();
  document.getElementById('btn-new').onclick = () => {
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
    document.getElementById('nc-sensor').value = a ? a.default_sensor : 'UNKNOWN-SENSOR';
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
        sensor_id: document.getElementById('nc-sensor').value,
        observation_type: document.getElementById('nc-fault').value,
        reading_status: document.getElementById('nc-reading').value,
      });
      showToast(`Case created: ${r.case_id} (${r.evidence_count} evidence items)`, 'success');
      loadCases();
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
  };

  async function loadCases() {
    try {
      const data = await api.get('/cases');
      const ids = data.cases || [];
      const snapshots = await Promise.all(ids.map(id => api.get(`/cases/${id}`).catch(() => null)));
      const cases = snapshots.filter(s => s);

      renderStats(cases);
      renderTable(cases);
    } catch (e) {
      setHTML('cases-tbody', `<tr><td colspan="8" class="muted">Error: ${esc(e.message)}</td></tr>`);
    }
  }

  function renderStats(cases) {
    const total = cases.length;
    const action = cases.filter(c => c.current_state === 'AWAITING_APPROVAL').length;
    const escalated = cases.filter(c => c.current_state === 'ESCALATED').length;
    const closed = cases.filter(c => c.current_state === 'CLOSED').length;
    setHTML('stats-row', `
      <div class="stat"><div class="stat-val">${total}</div><div class="stat-lbl">Total Cases</div></div>
      <div class="stat stat-yellow"><div class="stat-val">${action}</div><div class="stat-lbl">Awaiting Approval</div></div>
      <div class="stat stat-red"><div class="stat-val">${escalated}</div><div class="stat-lbl">Escalated</div></div>
      <div class="stat stat-green"><div class="stat-val">${closed}</div><div class="stat-lbl">Resolved</div></div>
    `);
  }

  function renderTable(cases) {
    const tbody = document.getElementById('cases-tbody');
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
      const confCell = c.knowledge_withdrawn
        ? `<span class="badge badge-red" title="${esc(c.knowledge_withdrawn)}">${(c.confidence * 100).toFixed(0)}% · knowledge withdrawn</span>`
        : c.diagnosis
        ? (() => {
            const wasEscalated = (c.history || []).some(x => x.to_state === 'ESCALATED' && x.from_state !== 'ESCALATED');
            const cb = confBand(c.confidence, wasEscalated ? 'ESCALATED' : c.current_state);
            return `<span class="badge ${cb.cls}">${cb.label}</span>`;
          })()
        : '<span class="muted">Not yet diagnosed</span>';
      const canAdv = c.current_state === 'GATHERING_EVIDENCE';
      return `<tr class="clickable" tabindex="0" role="link" aria-label="Open case ${c.case_id} on ${c.asset_id}" onclick="window.__app__.navigate('diagnosis', '${c.case_id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();window.__app__.navigate('diagnosis', '${c.case_id}')}">
        <td><code>${esc(c.case_id)}</code></td>
        <td><strong>${esc(c.asset_id)}</strong></td>
        <td>${esc((obs.type || '-').replace(/_/g, ' '))}</td>
        <td>${esc(obs.sensor_id || '-')}</td>
        <td>${esc(obs.reading_status || '-')}</td>
        <td>${statePill(c.current_state)}</td>
        <td>${confCell}</td>
        <td onclick="event.stopPropagation()">
          ${canAdv ? `<button class="btn btn-sm btn-primary" onclick="advCase('${c.case_id}', this)">Advance</button>` : '<span class="muted">-</span>'}
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

  el.innerHTML = '<div class="card skeleton-card"><div class="skeleton skeleton-line" style="width:30%"></div><div class="skeleton skeleton-line" style="width:50%"></div><div class="skeleton skeleton-line" style="width:80%"></div><div class="skeleton skeleton-line" style="width:40%"></div></div>';

  async function load() {
    try {
      const [s, expertKnowledge, sysInfo] = await Promise.all([
        api.get(`/cases/${cid}`),
        api.get(`/cases/${cid}/expert-knowledge`),
        api.get('/system/info'),
        loadCauses(),
      ]);
      const obs = s.observation || {};
      const cb = s.diagnosis ? confBand(s.confidence, s.current_state) : { cls: 'badge-grey', label: 'Not yet diagnosed' };

      const nextHintText = {
        GATHERING_EVIDENCE: 'click Advance Agent to run the decision tree.',
        DIAGNOSING: 'the agent is diagnosing; refresh in a moment.',
        RECOMMENDING: 'a recommendation is being prepared.',
        AWAITING_APPROVAL: s.knowledge_withdrawn
          ? 'knowledge this diagnosis used was withdrawn: re-score it on AOM Decision before anyone approves it.'
          : 'move to AOM Decision to approve, reject or modify it.',
        EXECUTING: 'a work order is being raised; check the Outcome screen.',
        MONITORING_OUTCOME: 'record the outcome once work is complete, on the Outcome screen.',
        RECORDING_OUTCOME: 'outcome recording is in progress.',
        FEEDBACK_QUEUED: 'feedback is queued for a knowledge steward to review.',
        ESCALATED: 'move to AOM Decision to see why, and to resolve it.',
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
        <div>${s.current_state === 'GATHERING_EVIDENCE' ? `<button class="btn btn-primary" id="btn-adv">Advance Agent</button>` : ''}</div>
      </div>`;

      if (s.knowledge_withdrawn) {
        html += `<div class="banner banner-error"><p><strong>Knowledge withdrawn:</strong> ${esc(s.knowledge_withdrawn)}. The confidence below may no longer hold; re-score on AOM Decision before approval.</p></div>`;
      }

      // Summary first: what the agent concluded and what happens next, so the
      // detail below is there to check, not to read through.
      const evsAll = s.evidence || [];
      const abnormalReadings = evsAll.flatMap(ev => (ev.abnormal || [])
        .filter(k => ev.payload && k in ev.payload)
        .map(k => `${_humaniseKey(k)}: ${_formatValue(k, ev.payload[k], true)}`));
      if (s.diagnosis) {
        const hypS = s.ai_hypothesis;
        const aiLine = !hypS ? 'not run'
          : hypS.status === 'unavailable' ? 'AI offline'
          : !hypS.hypothesis ? 'no independent opinion'
          : hypS.agrees_with_rules ? `agrees (${causeLabel(hypS.hypothesis)})`
          : `disagrees: suggests ${causeLabel(hypS.hypothesis)} (G9, advisory)`;
        const firstAction = s.recommendation && (s.recommendation.actions || [])[0];
        html += `<div class="card summary-card"><div class="card-body">
          <div class="summary-grid">
            <div><div class="summary-lbl">Likely cause</div><div class="summary-val">${esc(causeLabel(s.diagnosis.top_cause_id))}</div></div>
            <div><div class="summary-lbl">Confidence</div><div class="summary-val"><span class="badge ${cb.cls}">${cb.label}</span></div></div>
            <div><div class="summary-lbl">AI second opinion</div><div class="summary-val">${esc(aiLine)}</div></div>
            <div><div class="summary-lbl">Recommendation</div><div class="summary-val">${firstAction ? esc(firstAction.detail) : '<span class="muted">none: a person decides</span>'}</div></div>
          </div>
          <div class="summary-row"><span class="summary-lbl">Abnormal readings</span> ${abnormalReadings.length ? abnormalReadings.map(r => `<span class="badge badge-red">${esc(r)}</span>`).join(' ') : '<span class="muted">none flagged</span>'}</div>
          <div class="summary-row"><span class="summary-lbl">Next step</span> ${esc(nextHintText)}</div>
        </div></div>`;
      }

      // Two-column: evidence + diagnosis
      const abnormalCount = evsAll.filter(ev => (ev.abnormal || []).length).length;
      html += `<div class="grid-2">
        <div class="card"><div class="card-header"><h3>Evidence Timeline</h3><div class="flex align-center gap-8"><span class="muted">${abnormalCount && !_evidenceShowAll ? `${abnormalCount} of ${evsAll.length} abnormal` : `${evsAll.length} items`}</span>${abnormalCount && abnormalCount < evsAll.length ? `<button class="evidence-toggle" id="btn-ev-all">${_evidenceShowAll ? 'Abnormal only' : 'Show all'}</button>` : ''}<button class="evidence-toggle" id="btn-ev-toggle">${_evidenceRawMode ? 'Plain English' : 'Raw JSON'}</button></div></div><div class="card-body">
          <span class="tier-label tier-fact">Tier 1 - Sensor Observations (Facts)</span>
          <div id="ev-body"></div>
        </div></div>
        <div class="card"><div class="card-header"><h3>Decision-Tree Diagnosis</h3></div><div class="card-body">
          <span class="tier-label tier-fact">Rule-based diagnosis (expert decision tree)</span>
          <div id="diag-body"></div>
        </div></div>
      </div>`;

      html += `<div class="card"><div class="card-header">
          <div class="flex align-center gap-8">
            <span class="card-cloud" id="ai-avatar"></span>
            <h3>AI Second Opinion</h3>
          </div>
          <span class="badge badge-purple">AI HARVEST</span>
        </div><div class="card-body" id="ai-opinion-body"></div></div>`;

      // Recommendation
      html += `<div class="card"><div class="card-header"><h3>Recommended Action</h3></div><div class="card-body">
        <span class="tier-label tier-action">Tier 3 - Recommended Action (from approved Intelligence Pill knowledge)</span>
        <div id="rec-body"></div>
      </div></div>`;

      html += `<div class="card"><div class="card-header"><h3>Expert Knowledge Reused</h3><span class="badge badge-purple">AI HARVEST</span></div><div class="card-body" id="expert-knowledge-body"></div></div>`;

      // The working behind the summary: collapsed, one click away.
      const firedCount = ((s.guardrail_result || {}).rule_ids || []).length;
      html += `<details class="card why-panel"><summary><strong>Confidence breakdown (W1-W5)</strong> <span class="muted">· how ${s.diagnosis ? (s.confidence * 100).toFixed(0) + '%' : 'the score'} was worked out</span></summary><div class="card-body" id="conf-body"></div></details>`;
      html += `<details class="card why-panel"><summary><strong>Guardrail engine (G1-G9)</strong> <span class="muted">· ${s.guardrail_result ? (firedCount ? `${firedCount} rule(s) fired` : 'no rule fired') : 'not run yet'}</span></summary><div class="card-body" id="gr-body"></div></details>`;

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
            : renderEvidencePlain(ev.payload, ev.abnormal || []);
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
          <span class="tier-label tier-advisory">Advisory only — does not affect routing</span>
          <div class="flex gap-8 align-center flex-wrap" style="margin:8px 0">
            <span class="badge ${hyp.status === 'unavailable' ? 'badge-red' : 'badge-purple'}">${esc(modelLabel)}</span>
            ${hyp.status === 'ok' ? (hyp.hypothesis
              ? `<span class="badge ${agrees ? 'badge-green' : 'badge-yellow'}">${agrees ? 'Agrees with rule-based diagnosis' : 'Disagrees with rule-based diagnosis (G9)'}</span>`
              : '<span class="badge badge-grey">No independent opinion</span>') : ''}
          </div>
          ${hyp.hypothesis ? `<div style="margin-bottom:8px"><span class="muted">AI hypothesis:</span> <strong>${esc(causeLabel(hyp.hypothesis))}</strong></div>` : ''}
          <p class="muted" style="margin-bottom:8px">${esc(hyp.summary || '')}</p>
          ${hyp.supporting_evidence && hyp.supporting_evidence.length ? `<div><strong>Supporting:</strong><ul class="expert-list">${hyp.supporting_evidence.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>` : ''}
          ${hyp.conflicting_evidence && hyp.conflicting_evidence.length ? `<div><strong>Conflicting:</strong><ul class="expert-list">${hyp.conflicting_evidence.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>` : ''}
          ${hyp.missing_evidence && hyp.missing_evidence.length ? `<div><strong>Would help:</strong><ul class="expert-list">${hyp.missing_evidence.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>` : ''}
          ${hyp.recommended_next_check ? `<div class="muted" style="margin-top:8px"><strong>Suggested next check:</strong> ${esc(hyp.recommended_next_check)}</div>` : ''}
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
                <span><strong>KB version:</strong> ${esc(item.kb_version_label)}</span>
                <span><strong>Cause:</strong> ${esc(causeLabel(item.likely_cause))}</span>
              </div>
              <p><strong>Matched pattern:</strong> ${esc(item.symptom_pattern)}</p>
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
          advBtn.textContent = 'Gathering evidence and diagnosing…';
          try {
            await thinking(api.post(`/cases/${cid}/advance`));
            showToast('Agent advanced', 'success');
            window.__app__?.refreshSystemInfo?.();
            load();
          } catch (e) {
            showToast(`Error: ${e.message}`, 'error');
            advBtn.disabled = false;
            advBtn.removeAttribute('aria-busy');
            advBtn.textContent = 'Advance Agent';
          }
        };
      }
      const evAllBtn = document.getElementById('btn-ev-all');
      if (evAllBtn) evAllBtn.onclick = () => { _evidenceShowAll = !_evidenceShowAll; load(); };

      // F5: Wire evidence toggle button
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

      const decisionHint = s.current_state === 'ESCALATED'
        ? 'resolve the escalation below, or request more evidence to send it back to the agent.'
        : s.current_state === 'AWAITING_APPROVAL'
        ? (canApprove ? 'approve, reject or modify sends the case to execution.' : 'an Asset Ops Manager needs to approve, reject or modify this.')
        : 'this case has no pending decision right now.';
      let html = `${nextHint(decisionHint)}<h2 style="font-size:20px;margin-bottom:16px">AOM Decision - ${esc(cid)}</h2>`;

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
          html += `<div class="banner banner-error"><p><strong>Knowledge withdrawn:</strong> ${esc(s.knowledge_withdrawn)}. The confidence below may no longer hold, so approval is blocked until the case is re-scored against the current knowledge base.</p>
            ${canApprove ? '<button class="btn btn-primary mt-16" id="btn-rescore">Re-score against current knowledge</button>' : ''}</div>`;
        }
        const decidedAs = s.human_decision && { approve: 'Approved', reject: 'Rejected', modify: 'Modified' }[s.human_decision.decision];
        html += `<div class="card"><div class="card-header"><h3>${decidedAs ? `Recommendation (${decidedAs})` : 'Recommendation Under Review'}</h3></div><div class="card-body">
          ${hazardReason ? `<div class="banner banner-warn" style="margin-bottom:12px"><p><strong>⚠ Safety/environmental hazard:</strong> ${esc(hazardReason.replace(/^\[G2b?\]\s*/, ''))}</p></div>` : ''}
          ${decisionFacts(s, esc, confBand)}`;
        html += `
          <span class="tier-label tier-action">Tier 3 - Recommended Action (Read-Only)</span>
          <span class="tier-label tier-human">Tier 4 - Human Decision ${decidedAs ? '(recorded below)' : '(Below)'}</span>`;
        html += s.recommendation.actions.map(a => `
          <div style="display:flex;gap:12px;padding:12px;background:var(--bg-input);border-radius:6px;margin-bottom:8px">
            <span class="badge badge-blue">${esc(plain(a.type))}</span>
            <div><div><strong>Target:</strong> ${esc(plain(a.target))}</div><div><strong>Detail:</strong> ${esc(a.detail)}</div></div>
          </div>
        `).join('');
        html += expertChecks(ek, esc);
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
        html += `<div class="card"><div class="card-header"><h3>Resolve Escalation</h3></div><div class="card-body" id="esc-actions"></div></div>`;
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
            ${hd.expert_knowledge.map(m => `<div class="muted" style="margin-top:6px"><strong>${esc(m.expert_name)}</strong> · KB v${esc(m.kb_version_label)} · <code>${esc(m.knowledge_id)}</code> — “${esc(m.evidence_quote)}”</div>`).join('')}</div>` : ''}
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
      } else if (s.current_state === 'AWAITING_APPROVAL') {
        // Show decision controls
        if (!canApprove) {
          html += `<div class="banner banner-error"><p><strong>Approval Blocked</strong></p><p>You are signed in as ${esc(role)} (${esc(h.roleDisplayName(role))}); that role cannot approve, reject or modify.</p><p>Switch to Asset Operations Manager (mgr1) to approve, reject, or modify.</p></div>`;
        } else {
          html += `<div class="card"><div class="card-header"><h3>Decision Controls</h3></div><div class="card-body">
            <div class="flex gap-8" style="margin-bottom:16px">
              ${s.knowledge_withdrawn ? '' : '<button class="btn btn-green" id="btn-approve">Approve</button>'}
              <button class="btn btn-red" id="btn-reject">Reject</button>
              ${s.knowledge_withdrawn ? '' : '<button class="btn btn-secondary" id="btn-modify">Modify</button>'}
            </div>
            ${s.knowledge_withdrawn ? '<p class="muted" style="margin-bottom:12px">Approve and Modify return once the case is re-scored. Reject is still available.</p>' : ''}
            <div id="decision-form"></div>
          </div></div>`;
        }
      }

      el.innerHTML = frozenWrap(s, html, esc);

      // Wire escalation resolution controls (role-gated: approve_reject_modify)
      const escBody = document.getElementById('esc-actions');
      if (escBody) {
        if (!canApprove) {
          escBody.innerHTML = `<p class="muted">Resolving an escalation requires the Asset Ops Manager role. Switch role in the top bar.</p>`;
        } else {
          escBody.innerHTML = `
            <div class="form-group"><label for="esc-reason">Reason or resolution</label><input id="esc-reason" type="text" placeholder="e.g. BMS vendor replaced controller CTL-02; tags reporting again"></div>
            ${s.asset_type === 'UNKNOWN' ? '<p class="muted" style="margin-bottom:8px">This asset is not in the registry, so there is no data source to re-query. Close it with what was found, and register the asset if the pill should cover it.</p>' : ''}
            <div class="form-group"><label for="esc-cause">Confirmed cause (optional: sends this resolution to a knowledge steward so the pill can learn it)</label>
              <select id="esc-cause"><option value="">-- not confirmed --</option>${causeOptions((_causes || []).filter(c => c.asset_type === s.asset_type))}</select></div>
            <div class="flex gap-8 flex-wrap">
              ${s.asset_type === 'UNKNOWN' ? '' : '<button class="btn btn-secondary" id="btn-esc-evidence">Request more evidence (reason required)</button>'}
              <button class="btn btn-red" id="btn-esc-close">Close escalation (resolution required)</button>
            </div>
          `;
          const btnEv = document.getElementById('btn-esc-evidence');
          if (btnEv) btnEv.onclick = async () => {
            const reason = document.getElementById('esc-reason').value.trim();
            if (!reason) { showToast('Give a reason to request more evidence', 'error'); return; }
            try {
              await api.post(`/cases/${cid}/escalation/evidence`, { reason });
              showToast('More evidence requested; case returned to gathering', 'success');
              load();
            } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
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

      function showModifyForm() {
        setHTML('decision-form', `
          <div class="form-group"><label>Rationale (required for modify)</label><textarea id="rat-text" placeholder="Explain the modification..."></textarea></div>
          <div class="grid-2">
            <div class="form-group"><label>Modified Action Type</label><input id="mod-type" type="text" placeholder="e.g. sensor_replacement"></div>
            <div class="form-group"><label>Modified Action Target</label><input id="mod-target" type="text" placeholder="e.g. CRAH-DC1-01 / SA-TEMP-01"></div>
          </div>
          <div class="form-group"><label>Modified Action Detail</label><input id="mod-detail" type="text" placeholder="e.g. Replace supply-air RTD sensor"></div>
          ${hazardAck()}
          <button class="btn btn-secondary" id="btn-confirm-modify">Confirm Modification</button>
        `);
        document.getElementById('btn-confirm-modify').onclick = async () => {
          const rat = document.getElementById('rat-text').value.trim();
          const mt = document.getElementById('mod-type').value.trim();
          const mtg = document.getElementById('mod-target').value.trim();
          if (!rat || !mt || !mtg) { showToast('Rationale, type, and target are required', 'error'); return; }
          if (!ackOk()) { showToast('Acknowledge the hazard before modifying', 'error'); return; }
          try { await api.post(`/cases/${cid}/approval`, { decision: 'modify', hazard_acknowledged: hazardReason ? 'true' : '', rationale: rat, modified_action_type: mt, modified_action_target: mtg, modified_action_detail: document.getElementById('mod-detail').value }); showToast('Modification submitted', 'success'); load(); }
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
      const s = await api.get(`/cases/${cid}`);
      // Feedback submission closes the case immediately (the PROPOSAL stays
      // pending for a steward separately) -- so "submit feedback" must stop
      // showing the moment current_state is CLOSED, not stay pinned on
      // whether an outcome was ever recorded.
      const outcomeHint = s.current_state === 'CLOSED'
        ? 'this case is closed. Feedback (if submitted) is with a knowledge steward on Governance.'
        : s.outcome
        ? 'submit feedback so a knowledge steward can validate it into the knowledge base.'
        : 'raise the work order, then record the outcome once the work is done.';
      let html = `${nextHint(outcomeHint)}<h2 style="font-size:20px;margin-bottom:16px">Outcome and Feedback - ${esc(cid)}</h2>`;

      // Work order
      html += `<div class="grid-2">
        <div class="card"><div class="card-header"><h3>Work Order</h3></div><div class="card-body" id="wo-body"></div></div>
        <div class="card"><div class="card-header"><h3>Outcome Recording</h3></div><div class="card-body" id="oc-body"></div></div>
      </div>`;

      // Audit timeline
      html += `<div class="card"><div class="card-header"><h3>Audit Timeline (Hash-Chain)</h3></div><div class="card-body" id="au-body"></div></div>`;

      el.innerHTML = frozenWrap(s, html, esc);

      // Work order
      const woBody = document.getElementById('wo-body');
      if (s.work_order_id) {
        woBody.innerHTML = `<div class="banner banner-success"><p><strong>Work Order:</strong> <code>${esc(s.work_order_id)}</code></p></div>`;
      } else if (s.current_state === 'AWAITING_APPROVAL') {
        woBody.innerHTML = '<div class="banner banner-info"><p>Approval required before a work order can be raised.</p></div>';
      } else if (s.current_state === 'EXECUTING' || s.current_state === 'MONITORING_OUTCOME') {
        const role = api.user();
        const canWO = api.can('approve_reject_modify');
        woBody.innerHTML = canWO
          ? `<button class="btn btn-primary" id="btn-wo">Raise Work Order</button>`
          : `<div class="banner banner-error"><p><strong>Blocked</strong> - ${esc(role)} (${esc(h.roleDisplayName(role))}) cannot create work orders.</p></div>`;
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
              <div class="form-group"><label>Notes</label><textarea id="fb-notes" placeholder="Optional notes..."></textarea></div>
              <button class="btn btn-primary" id="btn-fb">Submit Feedback</button>
            </div>`;
            document.getElementById('btn-fb').onclick = async () => {
              try {
                const r = await api.postJson(`/cases/${cid}/feedback`, { confirmed_cause: document.getElementById('fb-cause').value, notes: document.getElementById('fb-notes').value });
                showToast(`Feedback submitted (KB: ${r.kb_cases_total} cases)`, 'success');
                load();
              } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
            };
          } else {
            ocBody.innerHTML += `<div class="banner banner-error mt-16"><p><strong>Feedback Blocked</strong> - ${esc(role)} (${esc(h.roleDisplayName(role))}) cannot submit feedback.</p></div>`;
          }
        }
      } else if (s.current_state === 'EXECUTING') {
        ocBody.innerHTML = '<div class="banner banner-info"><p>Raise the work order first. The outcome is recorded once the work is under way.</p></div>';
      } else if (s.current_state === 'MONITORING_OUTCOME' || s.current_state === 'RECORDING_OUTCOME') {
        const role = api.user();
        const canRec = api.can('record_outcome');
        if (canRec) {
          ocBody.innerHTML = `
            <div class="form-group"><label>Result</label><select id="oc-result"><option value="resolved">resolved</option><option value="partial">partial</option><option value="unresolved">unresolved</option></select></div>
            <div class="form-group"><label for="oc-cause">Confirmed Root Cause (${esc(s.asset_type)} causes)</label><select id="oc-cause"><option value="">-- not confirmed --</option>${causeOptions((await loadCauses()).filter(c => c.asset_type === s.asset_type), (s.diagnosis && s.diagnosis.top_cause_id) || '')}</select></div>
            <p class="muted" style="margin-bottom:12px">Verified by: <strong>${esc(role)}</strong> (your signed-in identity is recorded)</p>
            <div class="form-group"><label>Notes</label><textarea id="oc-notes" placeholder="Optional notes..."></textarea></div>
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
    ${nextHint('approve pending proposals to bump the KB version, then re-run affected cases to see the uplift.')}
    <div class="stats-row" id="gov-stats"></div>
    <div class="card"><div class="card-header"><h3>Pill Registry</h3></div><div class="card-body" id="pill-registry-body"></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><h3>Cause Distribution</h3></div><div class="card-body" id="cause-dist"></div></div>
      <div class="card"><div class="card-header"><h3>Governance Pipeline</h3></div><div class="card-body" id="pipeline-body"></div></div>
    </div>
    <div class="card"><div class="card-header"><h3>Knowledge Approval Queue</h3></div><div class="card-body" id="queue-body"></div></div>
    <div class="card" id="rerun-card" hidden><div class="card-header"><h3>Re-run Diagnosis on Similar Open Cases</h3></div><div class="card-body" id="rerun-body"></div></div>
    <div class="card"><div class="card-header"><h3>Approved Knowledge</h3></div><div class="card-body" id="approved-body"></div></div>
    <div class="card"><div class="card-header"><h3>Rollback</h3></div><div class="card-body" id="rollback-body"></div></div>
    <div class="card"><div class="card-header"><h3>Knowledge Governance Ledger</h3><span id="ledger-status"></span></div><div class="card-body" id="ledger-body"></div></div>
    <div class="card"><div class="card-header"><h3>Case Audit Trace (keyed hash chain)</h3></div><div class="card-body" id="trace-body"></div></div>
  `;

  // Rollback -- admin only, one pill at a time. Lets anyone see the
  // addressable versions even if they can't act on them, so the mapping from
  // "CRAH v1.4.0" on screen to the integer /kb/rollback/{N} takes is never a guess. A named function
  // (not a fire-and-forget IIFE) so an approval/rejection elsewhere on this
  // same screen can refresh it too -- otherwise it shows a stale "current".
  async function loadRollback() {
    const body = document.getElementById('rollback-body');
    if (!body) return;
    const role = api.user();
    const canRollback = api.can('rollback_knowledge_version');
    const pill = loadRollback.pill || 'CRAH';
    try {
      const { versions, current_version, current_label } = await api.get(`/kb/versions?pill=${encodeURIComponent(pill)}`);
      const targets = versions.filter(v => v.status === 'live' && v.version !== current_version);
      const options = targets.map(v => `<option value="${v.version}" data-label="${esc(v.label)}">v${esc(v.label)}</option>`).join('');
      const pillPicker = `<div class="flex gap-8 align-center" style="margin-bottom:10px"><label for="rb-pill" class="role-label">Pill</label>
        <select id="rb-pill">${['CRAH', 'Chiller', 'UPS', 'Pump'].map(p => `<option${p === pill ? ' selected' : ''}>${p}</option>`).join('')}</select></div>`;
      const history = versions.map(v => `<span class="badge ${v.status === 'live' ? (v.version === current_version ? 'badge-green' : 'badge-blue') : 'badge-grey'}" style="margin:2px" title="${v.status === 'live' ? 'live lineage' : 'rolled back; this label is never reused'}">v${esc(v.label)}${v.version === current_version ? ' (current)' : v.status === 'rolled_back' ? ' (rolled back)' : ''}</span>`).join(' ');
      body.innerHTML = `
        ${pillPicker}
        <p class="muted" style="margin-bottom:8px">Current ${esc(pill)} knowledge: <strong>${esc(current_label)}</strong>. Rolling back one pill leaves the others alone. Version labels are never reused: a rolled-back version keeps its label and the next approval gets a new one.</p>
        <div style="margin-bottom:12px">${history}</div>
        ${!canRollback ? `<p class="muted">Rolling back requires the Admin role. Switch role in the top bar to see the control.</p>`
          : !targets.length ? `<p class="muted">Nothing to roll back to: the current version is the only live one.</p>` : `
          <div class="flex gap-8 flex-wrap align-center">
            <label for="rb-version" class="role-label">Roll back to</label>
            <select id="rb-version">${options}</select>
            <input id="rb-reason" type="text" placeholder="Reason (required, recorded in the ledger)" style="flex:1 1 260px">
            <button class="btn btn-red btn-sm" id="rb-go">Roll back…</button>
          </div>
          <div id="rb-confirm" class="banner banner-warn mt-16" hidden></div>
        `}
      `;
      document.getElementById('rb-pill').onchange = (ev) => { loadRollback.pill = ev.target.value; loadRollback(); };
      const go = document.getElementById('rb-go');
      if (go) {
        go.onclick = () => {
          const sel = document.getElementById('rb-version');
          const reason = document.getElementById('rb-reason').value.trim();
          if (!reason) { showToast('Give a reason for the rollback', 'error'); document.getElementById('rb-reason').focus(); return; }
          const label = sel.selectedOptions[0].dataset.label;
          const box = document.getElementById('rb-confirm');
          box.hidden = false;
          box.innerHTML = `<p><strong>Roll ${esc(pill)} knowledge back from ${esc(current_label)} to v${esc(label)}?</strong> Every ${esc(pill)} case and expert heuristic approved after v${esc(label)} stops being used; other pills are not touched. This is recorded in the ledger with your reason.</p>
            <div class="flex gap-8 mt-16"><button class="btn btn-red btn-sm" id="rb-yes">Yes, roll back</button><button class="btn btn-secondary btn-sm" id="rb-no">Cancel</button></div>`;
          document.getElementById('rb-no').onclick = () => { box.hidden = true; };
          document.getElementById('rb-yes').onclick = async () => {
            try {
              const r = await api.post(`/kb/rollback/${sel.value}`, { pill, reason });
              showToast(`${pill} rolled back to v${label} (${r.removed_cases} item(s) removed)`, 'success');
              refreshAll();
            } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
          };
        };
      }
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
  async function loadApproved() {
    const body = document.getElementById('approved-body');
    if (!body) return;
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
            <div class="flex gap-8"><input id="rv-reason-${pid}" type="text" placeholder="Reason (required)" style="min-width:200px">
            <button class="btn btn-red btn-sm" id="rv-go-${pid}">Revoke</button></div>
          </div>`;
        }).join('');
      proposals.forEach(p => {
        const btn = document.getElementById(`rv-go-${p.proposal_id}`);
        btn.onclick = async () => {
          const reason = document.getElementById(`rv-reason-${p.proposal_id}`).value.trim();
          if (!reason) { showToast('Give a reason for revoking', 'error'); return; }
          try {
            const r = await api.post(`/kb/proposals/${p.proposal_id}/revoke`, { reason });
            showToast(`${p.proposal_id} revoked (${r.removed_items} item(s) withdrawn)`, 'success');
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
    loadQueue(); loadStats(); loadRollback(); loadPills(); loadLedger(); loadApproved();
    window.__app__?.refreshKbVersion?.();
  }

  // Pipeline visual
  setHTML('pipeline-body', `
    <div class="pipeline">
      <div class="pipeline-step"><div class="pipeline-circle">1</div><div class="pipeline-label">Expert or Outcome Proposes</div><div class="pipeline-desc">AI-drafted interviews and confirmed outcomes become pending proposals</div></div>
      <div class="pipeline-arrow">-></div>
      <div class="pipeline-step"><div class="pipeline-circle">2</div><div class="pipeline-label">Second Steward Reviews</div><div class="pipeline-desc">Proposer can never approve their own change</div></div>
      <div class="pipeline-arrow">-></div>
      <div class="pipeline-step"><div class="pipeline-circle">3</div><div class="pipeline-label">Validated</div><div class="pipeline-desc">Written to KB</div></div>
      <div class="pipeline-arrow">-></div>
      <div class="pipeline-step"><div class="pipeline-circle">4</div><div class="pipeline-label">Version Bump</div><div class="pipeline-desc" id="pipe-version">Each approval bumps the KB version</div></div>
    </div>
    <div class="banner banner-info mt-16"><p>A candidate must <strong>never</strong> appear as already-approved knowledge.</p></div>
  `);

  // Knowledge queue — load real pending proposals
  async function loadQueue() {
    const qb = document.getElementById('queue-body');
    if (!qb) return;
    try {
      const data = await api.get('/kb/queue');
      const queue = data.queue || [];
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
          <div class="q-field"><span class="q-field-lbl">When</span> ${esc(x.symptom_pattern)}</div>
          ${lines('Check', x.checks)}${lines('Never', x.do_not)}${lines('Escalate when', x.escalate_when)}
          <div class="q-quote">"${esc(x.evidence_quote)}"</div></li>`;
      const describe = p => p.kind === 'expert_capture'
        ? `<div class="q-title"><strong>${esc(p.proposal_id)}</strong> <span class="badge badge-purple">Expert interview</span></div>
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
        // Mirrors the server rule: the pill's owner decides, the other
        // steward stands in only when the owner proposed it; admin may.
        const notOwner = !own && api.role() !== 'admin' && p.owner_steward
          && p.owner_steward !== me && p.owner_steward !== p.submitted_by;
        const blocked = own || notOwner;
        const why = own ? 'You sent this. A different steward must decide.'
          : `${esc(p.asset_type)} knowledge is owned by ${esc(p.owner_steward)}; they (or an admin) decide.`;
        const pid = esc(p.proposal_id);
        return `<div class="card q-card" style="margin-bottom:8px">
          <div class="q-body">${describe(p)}</div>
          <div class="q-actions">
            <button class="btn btn-green btn-sm" id="approve-${pid}" ${blocked ? 'disabled aria-describedby="own-' + pid + '"' : ''}>Approve…</button>
            <button class="btn btn-red btn-sm" id="reject-${pid}" ${blocked ? 'disabled' : ''}>Reject…</button>
            ${blocked ? `<div class="q-own" id="own-${pid}">${why}</div>` : ''}
            <div class="q-reject" id="ap-${pid}" hidden>
              <label for="ap-reason-${pid}">Why is this sound? (recorded in the ledger)</label>
              <input id="ap-reason-${pid}" type="text" placeholder="e.g. Checked each line against the interview">
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
          try {
            const r = await api.post(`/kb/proposals/${id}/approve`, { rationale });
            showToast(`${id} approved: now live as ${(r.kb_version_labels || []).join(', ') || 'new knowledge'}`, 'success');
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
        <p class="muted" style="margin-bottom:10px">Open cases diagnosed with what was just approved. Re-run shows what the new knowledge changes, without touching the case.</p>
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
              (crosses ? ` <span class="muted">now clears the 55% recommendation threshold${m.current_state === 'ESCALATED' ? '; on AOM Decision, "Request more evidence" re-diagnoses it with this knowledge' : ''}</span>` : '');
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
      setHTML('pipe-version', 'Each approval bumps the version of the pill(s) it files knowledge under');
      setHTML('gov-stats', `
        <div class="stat"><div class="stat-val">${stats.total_validated_cases ?? 0}</div><div class="stat-lbl">Validated Cases</div></div>
        <div class="stat stat-purple"><div class="stat-val">${stats.feedback_added ?? 0}</div><div class="stat-lbl">Feedback Added</div></div>
        <div class="stat stat-yellow"><div class="stat-val">${stats.pending_proposals ?? 0}</div><div class="stat-lbl">Pending Proposals</div></div>
        <div class="stat stat-green"><div class="stat-val" style="font-size:0.95rem;line-height:1.5">${pillLabels.length ? pillLabels.map(esc).join('<br>') : 'n/a'}</div><div class="stat-lbl">KB Version per pill</div></div>
        <div class="stat stat-blue"><div class="stat-val">${_treeCount} / ${_causeCount}</div><div class="stat-lbl">Asset trees / Causes</div></div>
      `);
      const dist = stats.cause_distribution || stats.causes || {};
      const priors = stats.cause_priors || {};
      // F6: fall back to cause_priors ({cause: {confirmed, total, rate}})
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
          return `<div class="cause-bar"><div class="cause-bar-label">${esc(causeLabel(cause))}</div><div class="cause-bar-track"><div class="cause-bar-fill" style="width:${pct}%"></div></div><div class="cause-bar-count">${count}</div></div>`;
        }).join('');
      }
    } catch (e) {
      setHTML('cause-dist', `<p class="muted">Error: ${esc(e.message)}</p>`);
    }
  }

  // Load audit trace
  async function loadTrace() {
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
    try {
      const { entries, chain_valid } = await api.get('/kb/ledger');
      setHTML('ledger-status', chain_valid ? '<span class="badge badge-green">Ledger verified</span>' : '<span class="badge badge-red">Ledger FAILED verification</span>');
      const actionLabel = { proposal_submitted: 'Proposal submitted', proposal_approved: 'Approved', proposal_rejected: 'Rejected', proposal_revoked: 'Revoked', rollback: 'Rollback', seeded: 'Seeded' };
      setHTML('ledger-body', !entries.length
        ? '<p class="muted">No governance actions yet.</p>'
        : `<p class="muted" style="margin-bottom:8px">Every proposal, approval, rejection and rollback, with who did it and why. Keyed hash chain: editing any entry breaks verification.</p>
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

  loadStats();
  loadQueue();
  loadLedger();
  loadTrace();
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

  el.innerHTML = `
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
        <div class="kh-row"><span class="kh-label">When</span>${esc(x.symptom_pattern)}</div>
        ${fieldList('Checks', (x.checks || []).filter(c => c !== x.symptom_pattern))}${fieldList('Never', x.do_not)}${fieldList('Escalate when', x.escalate_when)}
        <span class="kh-label" style="margin-top:10px">Expert's own words</span>
        <blockquote class="kh-quote">"${esc(x.evidence_quote)}"</blockquote>
      </div>`;
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
        const other = ws.filter(w => !filing.includes(w));
        const moved = draft.heuristics.filter(x => x.asset_type && x.asset_type !== $('cap-asset').value);
        return other.map(w => `<div class="banner banner-warn"><p>${esc(w)}</p></div>`).join('')
          + (moved.length ? `<div class="banner banner-info"><p><strong>Filed under other pills:</strong> ${moved.map(x => `${esc(x.cause_label)} goes to ${esc(x.asset_type)}`).join('; ')}. Each pill only uses knowledge about its own equipment.</p></div>` : '');
      })()}
      <p class="muted cap-hint">Untick anything that is wrong or unclear and correct causes where needed. You cannot add words the expert did not say: the server checks every quote again.</p>
      ${draft.heuristics.map((x, i) => heuristicCard(x, i, causes, true)).join('')}
      ${draft.provider === 'manual' ? manualForm(causes) : ''}
      <label class="hazard-ack"><input type="checkbox" id="cap-consent"> ${esc($('cap-name').value.trim() || 'The expert')} agreed to their words being recorded and reused as knowledge.</label>
      <div class="cap-submit">
        <button class="btn btn-primary" id="cap-submit">Send ${draft.heuristics.length} for steward approval</button>
        <span class="muted" id="cap-submit-note">A different knowledge steward must approve before it goes live.</span>
      </div>`;
    if (draft.provider === 'manual') wireManualForm(causes);
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
  function manualForm(causes) {
    return `<div class="card mt-16"><div class="card-header"><h3>Add a heuristic</h3></div><div class="card-body">
      <div class="form-group"><label for="mh-cause">Cause</label><select id="mh-cause">${causeOptions(causes)}</select></div>
      <div class="form-group"><label for="mh-when">When (the symptom the expert described)</label><input id="mh-when" type="text"></div>
      <div class="form-group"><label for="mh-checks">Checks (one per line)</label><textarea id="mh-checks" rows="3"></textarea></div>
      <div class="form-group"><label for="mh-never">Never (one per line)</label><textarea id="mh-never" rows="2"></textarea></div>
      <div class="form-group"><label for="mh-esc">Escalate when (one per line)</label><textarea id="mh-esc" rows="2"></textarea></div>
      <div class="form-group"><label for="mh-quote">Expert's own words (copy exactly from the transcript)</label><textarea id="mh-quote" rows="2"></textarea></div>
      <button class="btn btn-secondary" id="mh-add">Add heuristic</button>
    </div></div>`;
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
      renderDraft();
    };
  }

  $('cap-manual').onclick = () => {
    if (!text.value.trim()) { showToast('Paste the interview transcript first', 'error'); text.focus(); return; }
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
      setStep(4); setStatus('Waiting for second steward', 'badge-yellow'); $('cap-right-title').textContent = '4. Sent for approval';
      const causes = await loadCauses();
      $('cap-result').innerHTML = `
        <div class="banner banner-success"><p><strong>Sent as ${esc(d.proposal_id)}.</strong> Nothing is live yet. A knowledge steward other than you (${esc(role)}) must approve it on the Governance screen.</p></div>
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
    $('cap-result').innerHTML = '<div class="skeleton-card"><div class="skeleton-line"></div><div class="skeleton-line"></div><div class="skeleton-line"></div></div><p class="muted">The model is reading the interview. Each heuristic must quote the expert word for word.</p>';
    try {
      draft = await thinking(api.postJson('/capture/draft', { asset_type: $('cap-asset').value, transcript: text.value }));
      await renderDraft();
    } catch (e) {
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
