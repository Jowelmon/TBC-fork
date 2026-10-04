// screens.js - Renderers for all 5 screens + demo case seeder

import { api } from './api.js?v=3';

// Async loaders can resolve after the user has navigated away; never crash.
function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
  return el;
}

const isForbidden = e => /403|lacks capability|forbidden/i.test(e?.message || '');
const rbacNote = (what, roles) => `<div class="banner banner-info"><p><strong>Role-based access:</strong> ${what} is limited to ${roles}. Switch role in the top bar to see it.</p></div>`;

// F5: local HTML-escape for module-level helper (render functions receive `esc` via helpers)
function _esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Known cause IDs for validated root-cause dropdown ──────
const KNOWN_CAUSES = [
  'comm_bus_failure', 'config_drift', 'loose_wiring', 'sensor_hardware_failure',
  'data_path_drop', 'intermittent_fault', 'sensor_drift', 'sensor_fault_noise',
  'refrigerant_leak', 'low_refrigerant_charge', 'condenser_fouling', 'compressor_motor_fault', 'chiller_electrical_fault',
  'thermal_runaway_risk', 'battery_eol', 'charger_failure', 'ground_fault', 'inverter_fault',
  'cavitation', 'shaft_misalignment', 'foundation_looseness', 'bearing_wear', 'impeller_imbalance',
];

// ── Guardrail definitions for G1-G8 grid ───────────────────
const GUARDRAILS = [
  { id: 'G1', desc: 'BMS setpoint/interlock block' },
  { id: 'G2', desc: 'Safety-critical escalate' },
  { id: 'G3', desc: 'Cross-domain coordinate' },
  { id: 'G4', desc: 'Low confidence escalate' },
  { id: 'G5', desc: 'Unknown asset escalate' },
  { id: 'G6', desc: 'Force approval' },
  { id: 'G7', desc: 'Sanitize injection' },
  { id: 'G8', desc: 'Ungrounded reject' },
];

// ── Confidence weights for W1-W5 breakdown ────────────────
const WEIGHTS = [
  { id: 'W1', val: 0.30, label: 'Evidence Coverage', sign: '+' },
  { id: 'W2', val: 0.20, label: 'Peer Agreement', sign: '+' },
  { id: 'W3', val: 0.25, label: 'KB Match', sign: '+' },
  { id: 'W4', val: 0.10, label: 'Data Staleness', sign: '-' },
  { id: 'W5', val: 0.15, label: 'Conflict Penalty', sign: '-' },
];

// F5: Evidence display toggle state (plain English vs raw JSON)
let _evidenceRawMode = false;

// F5: Keys whose value `true` indicates an abnormal/fault condition
const _ABNORMAL_BOOL_KEYS = new Set([
  'low_pressure_switch', 'high_pressure_switch', 'leak_detected',
  'motor_overcurrent', 'temp_rising', 'greasing_overdue',
  'soft_foot_detected', 'directional_dominant', 'on_battery',
  'balance_ok',
]);

// F5: Numeric thresholds for abnormal values { key: { max?, min?, equals?, suffix? } }
const _ABNORMAL_THRESHOLDS = {
  charge_pct:       { max: 70, suffix: '%' },
  soh_pct:          { max: 60, suffix: '%' },
  battery_temp_c:   { max: 35, suffix: '°C' },
  temp_c:           { max: 60, suffix: '°C' },
  approach_temp:    { min: 3.0, suffix: '°C' },
  axial_mm_s:       { max: 4.5, suffix: ' mm/s' },
  dominant_order:   { equals: '2x' },
};

function _humaniseKey(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function renderEvidencePlain(payload) {
  if (!payload || typeof payload !== 'object') {
    return '<span class="muted">—</span>';
  }
  const entries = Object.entries(payload);
  return `<div class="evidence-plain">` + entries.map(([key, val]) => {
    const label = _humaniseKey(key);
    let displayVal = val;
    let abnormal = false;

    if (_ABNORMAL_BOOL_KEYS.has(key) && val === true) {
      abnormal = true;
      displayVal = key === 'balance_ok' ? 'Imbalanced' : 'TRIPPED';
    } else if (key === 'alarms' && Array.isArray(val) && val.length > 0) {
      abnormal = true;
      displayVal = val.join(', ');
    } else if (key === 'alarms' && Array.isArray(val) && val.length === 0) {
      displayVal = 'None';
    } else if (typeof val === 'boolean') {
      displayVal = val ? 'Yes' : 'No';
    } else if (typeof val === 'number') {
      const t = _ABNORMAL_THRESHOLDS[key];
      if (t) {
        if (t.max !== undefined && val > t.max) abnormal = true;
        if (t.min !== undefined && val < t.min) abnormal = true;
        displayVal = val + (t.suffix || '');
      } else {
        displayVal = String(val);
      }
    } else if (typeof val === 'string') {
      const t = _ABNORMAL_THRESHOLDS[key];
      if (t && t.equals !== undefined && val === t.equals) {
        abnormal = true;
      }
      displayVal = val;
    } else {
      displayVal = JSON.stringify(val);
    }

    const cls = abnormal ? 'evidence-abnormal' : 'evidence-normal';
    return `<div class="evidence-field ${cls}">
      <span class="evidence-field-label">${_esc(label)}</span>
      <span class="evidence-field-value">${_esc(String(displayVal))}</span>
    </div>`;
  }).join('') + `</div>`;
}

// F7: Track whether auto-seed has already run this session
let _autoSeeded = false;

// ═══════════════════════════════════════════════════════════
// Screen 1: Dashboard
// ═══════════════════════════════════════════════════════════
export function renderDashboard(el, state, h) {
  const { api, showToast, statePill, confBand, fmtTime, esc, navigate, seedDemoCases } = h;

  el.innerHTML = `
    <div class="flex justify-between align-center" style="margin-bottom:20px">
      <div></div>
      <div class="flex gap-8">
        <button class="btn btn-secondary" id="btn-seed">Seed Demo Cases</button>
        <button class="btn btn-primary" id="btn-new">New Case</button>
      </div>
    </div>
    <div class="stats-row" id="stats-row"></div>
    <div class="card">
      <div class="table-wrap">
        <table>
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
          <div class="form-group"><label>Asset ID</label><select id="nc-asset">
            <option value="CRAH-DC1-01">CRAH-DC1-01 (CRAH)</option>
            <option value="CRAH-DC1-02">CRAH-DC1-02 (CRAH)</option>
            <option value="CHILLER-DC1-01">CHILLER-DC1-01 (Chiller)</option>
            <option value="UPS-DC1-01">UPS-DC1-01 (UPS)</option>
            <option value="PUMP-DC1-01">PUMP-DC1-01 (Pump)</option>
          </select></div>
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

  document.getElementById('btn-seed').onclick = () => seedDemoCases(h);
  document.getElementById('btn-new').onclick = () => {
    const f = document.getElementById('new-case-form');
    f.style.display = f.style.display === 'none' ? 'block' : 'none';
  };
  document.getElementById('btn-create').onclick = async () => {
    try {
      const r = await api.post('/cases', {
        asset_id: document.getElementById('nc-asset').value,
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

      // F7: Auto-seed 3 demo cases on first dashboard load if empty
      if (!cases.length && !_autoSeeded) {
        _autoSeeded = true;
        showToast('Auto-seeding demo cases…', 'info');
        await seedDemoCases(h);
        return; // seedDemoCases navigates back to dashboard which re-loads
      }

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
          <div class="empty-state-desc">Click "Seed Demo Cases" to populate the dashboard with sample CRAH and chiller fault scenarios, or "New Case" to create one manually.</div>
        </div>
      </td></tr>`;
      return;
    }
    tbody.innerHTML = cases.map(c => {
      const obs = c.observation || {};
      const cb = confBand(c.confidence);
      const canAdv = c.current_state === 'GATHERING_EVIDENCE';
      return `<tr class="clickable" tabindex="0" role="link" aria-label="Open case ${c.case_id} on ${c.asset_id}" onclick="window.__app__.navigate('diagnosis', '${c.case_id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();window.__app__.navigate('diagnosis', '${c.case_id}')}">
        <td><code>${esc(c.case_id)}</code></td>
        <td><strong>${esc(c.asset_id)}</strong></td>
        <td>${esc((obs.type || '-').replace(/_/g, ' '))}</td>
        <td>${esc(obs.sensor_id || '-')}</td>
        <td>${esc(obs.reading_status || '-')}</td>
        <td>${statePill(c.current_state)}</td>
        <td><span class="badge ${cb.cls}">${cb.label}</span></td>
        <td onclick="event.stopPropagation()">
          ${canAdv ? `<button class="btn btn-sm btn-primary" onclick="advCase('${c.case_id}')">Advance</button>` : '<span class="muted">-</span>'}
        </td>
      </tr>`;
    }).join('');
  }

  window.advCase = async (id) => {
    try {
      await api.post(`/cases/${id}/advance`);
      showToast('Agent advanced', 'success');
      loadCases();
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
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
      const s = await api.get(`/cases/${cid}`);
      const obs = s.observation || {};
      const cb = confBand(s.confidence);

      // Header
      let html = `<div class="flex justify-between align-center" style="margin-bottom:16px">
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

      // Two-column: evidence + diagnosis
      html += `<div class="grid-2">
        <div class="card"><div class="card-header"><h3>Evidence Timeline</h3><div class="flex align-center gap-8"><span class="muted">${(s.evidence||[]).length} items</span><button class="evidence-toggle" id="btn-ev-toggle">${_evidenceRawMode ? 'Plain English' : 'Raw JSON'}</button></div></div><div class="card-body">
          <span class="tier-label tier-fact">Tier 1 - Sensor Observations (Facts)</span>
          <div id="ev-body"></div>
        </div></div>
        <div class="card"><div class="card-header"><h3>Decision-Tree Diagnosis</h3></div><div class="card-body">
          <span class="tier-label tier-ai">Tier 2 - Decision-Tree Diagnosis + Confidence</span>
          <div id="diag-body"></div>
        </div></div>
      </div>`;

      // Confidence breakdown
      html += `<div class="card"><div class="card-header"><h3>Confidence Breakdown (W1-W5)</h3></div><div class="card-body" id="conf-body"></div></div>`;

      // Recommendation
      html += `<div class="card"><div class="card-header"><h3>Recommended Action</h3></div><div class="card-body">
        <span class="tier-label tier-action">Tier 3 - Recommended Action (from approved Intelligence Pill knowledge)</span>
        <div id="rec-body"></div>
      </div></div>`;

      // Guardrail grid
      html += `<div class="card"><div class="card-header"><h3>Guardrail Engine (G1-G8)</h3></div><div class="card-body" id="gr-body"></div></div>`;

      el.innerHTML = html;

      // Render evidence
      const evBody = document.getElementById('ev-body');
      const evs = s.evidence || [];
      if (!evs.length) {
        evBody.innerHTML = `<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No evidence gathered yet</div><div class="empty-state-desc">The agent is gathering sensor readings, BMS data, and historical patterns. Click "Advance Agent" to trigger evidence collection.</div></div>`;
      } else {
        evBody.innerHTML = evs.map(ev => {
          const src = ev.source || 'unknown';
          const payload = JSON.stringify(ev.payload, null, 2);
          const payloadHtml = _evidenceRawMode
            ? `<pre class="evidence-payload">${esc(payload)}</pre>`
            : renderEvidencePlain(ev.payload);
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
          const evRefs = (c.evidence_refs || []).map(r => `<code>${esc(r)}</code>`).join(' ') || '—';
          return `<div style="padding:10px;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;${top ? 'border-color:var(--green);background:var(--green-bg);' : ''}">
            ${top ? '<span class="badge badge-green">Top</span> ' : ''}<code>${esc(c.id)}</code>
            <strong>${esc(c.label)}</strong>
            <span class="muted" style="margin-left:auto;font-size:12px">Evidence: ${evRefs}</span>
          </div>`;
        }).join('');
        diagBody.innerHTML = `
          <div style="font-size:16px;margin-bottom:8px"><span class="muted">Root Cause:</span> <strong style="color:var(--blue)">${esc(diag.top_cause_id || '-')}</strong></div>
          <div class="muted" style="margin-bottom:8px">${esc(diag.reasoning_trace || '')}</div>
          ${diag.kb_refs && diag.kb_refs.length ? `<div class="muted" style="margin-bottom:8px">KB: ${diag.kb_refs.map(r => `<code>${esc(r)}</code>`).join(' ')}</div>` : ''}
          <h4 style="margin:14px 0 8px">Candidate Causes</h4>
          ${causes}
        `;
      }

      // Render confidence breakdown
      const confBody = document.getElementById('conf-body');
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
          ${WEIGHTS.map(w => `
            <div class="conf-item">
              <div class="conf-w">${w.id} = ${w.val.toFixed(2)}</div>
              <div class="conf-v">${w.sign}</div>
              <div class="conf-l">${w.label}</div>
            </div>
          `).join('')}
        </div>
        <div class="muted" style="margin-top:12px">confidence = W1*evidence_coverage + W2*peer_agreement + W3*kb_match - W4*staleness - W5*conflict</div>
      `;

      // Render recommendation
      const recBody = document.getElementById('rec-body');
      if (!s.recommendation) {
        recBody.innerHTML = `<div class="banner banner-info"><p>No recommendation has been produced yet.</p>${s.current_state === 'ESCALATED' ? '<p><strong>Case escalated.</strong> Confidence is below the escalation threshold (0.35).</p>' : ''}</div>`;
      } else {
        const rec = s.recommendation;
        const actions = (rec.actions || []).map(a => `
          <div style="display:flex;gap:12px;padding:12px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border);margin-bottom:8px">
            <span class="badge badge-blue">${esc(a.type)}</span>
            <div><div><strong>Target:</strong> ${esc(a.target)}</div><div><strong>Detail:</strong> ${esc(a.detail)}</div></div>
          </div>
        `).join('');
        recBody.innerHTML = `${actions}
          <div class="muted" style="margin-top:8px"><strong>Evidence Refs:</strong> ${(rec.evidence_refs||[]).map(r => `<code>${esc(r)}</code>`).join(' ') || 'none'}</div>
          <div class="muted" style="margin-top:4px"><strong>KB Refs:</strong> ${(rec.kb_refs||[]).map(r => `<code>${esc(r)}</code>`).join(' ') || 'none'}</div>
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
          try {
            await api.post(`/cases/${cid}/advance`);
            showToast('Agent advanced', 'success');
            load();
          } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      }

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
      const s = await api.get(`/cases/${cid}`);

      // Check RBAC
      const role = api.user();
      const canApprove = ['mgr1', 'admin1'].includes(role);

      let html = `<h2 style="font-size:20px;margin-bottom:16px">AOM Decision - ${esc(cid)}</h2>`;

      // Show recommendation (read-only)
      if (s.recommendation && s.recommendation.actions) {
        html += `<div class="card"><div class="card-header"><h3>Recommendation Under Review</h3></div><div class="card-body">
          <span class="tier-label tier-action">Tier 3 - Recommended Action (Read-Only)</span>
          <span class="tier-label tier-human">Tier 4 - Human Decision (Below)</span>`;
        html += s.recommendation.actions.map(a => `
          <div style="display:flex;gap:12px;padding:12px;background:var(--bg-input);border-radius:6px;margin-bottom:8px">
            <span class="badge badge-blue">${esc(a.type)}</span>
            <div><div><strong>Target:</strong> ${esc(a.target)}</div><div><strong>Detail:</strong> ${esc(a.detail)}</div></div>
          </div>
        `).join('');
        html += `</div></div>`;
      } else {
        // No recommendation — check if escalated due to low confidence
        if (s.current_state === 'ESCALATED' || (s.confidence !== null && s.confidence < 0.35)) {
          html += `<div class="banner banner-error">
            <p><strong>Escalated - No Recommendation (G4)</strong></p>
            <p>Confidence ${s.confidence !== null ? '(' + (s.confidence * 100).toFixed(0) + '%)' : ''} is below the escalation threshold (0.35).</p>
            <p>This case has been automatically escalated. No approve/reject/modify controls are available.</p>
          </div>`;
        } else {
          html += `<div class="banner banner-info"><p>No recommendation to review yet.</p><p>Current state: <strong>${esc(s.current_state)}</strong></p></div>`;
        }
      }

      // Show existing decision if any
      if (s.human_decision) {
        const hd = s.human_decision;
        const cls = hd.decision === 'approve' ? 'badge-green' : (hd.decision === 'reject' ? 'badge-red' : 'badge-blue');
        html += `<div class="card"><div class="card-header"><h3>Decision Record</h3></div><div class="card-body">
          <p><span class="badge ${cls}">${esc(hd.decision)}</span> by <strong>${esc(hd.decided_by)}</strong> at ${fmtTime(hd.timestamp)}</p>
          ${hd.rationale ? `<p style="margin-top:8px;font-style:italic">"${esc(hd.rationale)}"</p>` : ''}
          ${hd.modified_actions ? `<div class="mt-16">
            <span class="tier-label tier-human">Human-Validated</span>
            <div class="diff-grid">
              <div class="diff-col original">
                <div class="diff-col-header">Original Actions (Recommended)</div>
                <div class="diff-col-body">
                  ${(hd.original_actions || []).map(a => `<div class="diff-field"><div class="diff-field-label">Type</div><div class="diff-field-value">${esc(a.type)}</div><div class="diff-field-label">Target</div><div class="diff-field-value">${esc(a.target)}</div><div class="diff-field-label">Detail</div><div class="diff-field-value">${esc(a.detail)}</div></div>`).join('')}
                </div>
              </div>
              <div class="diff-col modified">
                <div class="diff-col-header">Modified Actions (Human-Adjusted)</div>
                <div class="diff-col-body">
                  ${hd.modified_actions.map(a => `<div class="diff-field"><div class="diff-field-label">Type</div><div class="diff-field-value">${esc(a.type)}</div><div class="diff-field-label">Target</div><div class="diff-field-value">${esc(a.target)}</div><div class="diff-field-label">Detail</div><div class="diff-field-value">${esc(a.detail)}</div></div>`).join('')}
                </div>
              </div>
            </div>
          </div>` : ''}
        </div></div>`;
      } else if (s.current_state === 'AWAITING_APPROVAL') {
        // Show decision controls
        if (!canApprove) {
          html += `<div class="banner banner-error"><p><strong>Approval Blocked</strong></p><p>Role "${esc(role)}" does not have the approve_reject_modify capability.</p><p>Switch to Asset Operations Manager (mgr1) to approve, reject, or modify.</p></div>`;
        } else {
          html += `<div class="card"><div class="card-header"><h3>Decision Controls</h3></div><div class="card-body">
            <div class="flex gap-8" style="margin-bottom:16px">
              <button class="btn btn-green" id="btn-approve">Approve</button>
              <button class="btn btn-red" id="btn-reject">Reject</button>
              <button class="btn btn-secondary" id="btn-modify">Modify</button>
            </div>
            <div id="decision-form"></div>
          </div></div>`;
        }
      } else {
        html += `<div class="banner banner-info"><p>Decision controls are available when the case is in <strong>AWAITING_APPROVAL</strong> state.</p><p>Current state: <strong>${esc(s.current_state)}</strong></p></div>`;
      }

      el.innerHTML = html;

      // Wire buttons
      const btnApprove = document.getElementById('btn-approve');
      const btnReject = document.getElementById('btn-reject');
      const btnModify = document.getElementById('btn-modify');
      if (btnApprove) btnApprove.onclick = async () => {
        try { await api.post(`/cases/${cid}/approval`, { decision: 'approve' }); showToast('Approved', 'success'); load(); }
        catch (e) { showToast(`Error: ${e.message}`, 'error'); }
      };
      if (btnReject) btnReject.onclick = () => showRationaleForm('reject');
      if (btnModify) btnModify.onclick = () => showModifyForm();

      function showRationaleForm(decision) {
        setHTML('decision-form', `
          <div class="form-group"><label>Rationale (required for ${decision})</label>
            <textarea id="rat-text" placeholder="Explain why you are ${decision}ing this recommendation..."></textarea>
          </div>
          <button class="btn btn-red" id="btn-confirm-${decision}">Confirm ${decision === 'reject' ? 'Rejection' : 'Modification'}</button>
        `);
        document.getElementById(`btn-confirm-${decision}`).onclick = async () => {
          const rat = document.getElementById('rat-text').value.trim();
          if (!rat) { showToast('Rationale is required', 'error'); return; }
          try { await api.post(`/cases/${cid}/approval`, { decision, rationale: rat }); showToast(`${decision} submitted`, 'success'); load(); }
          catch (e) { showToast(`Error: ${e.message}`, 'error'); }
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
          <button class="btn btn-secondary" id="btn-confirm-modify">Confirm Modification</button>
        `);
        document.getElementById('btn-confirm-modify').onclick = async () => {
          const rat = document.getElementById('rat-text').value.trim();
          const mt = document.getElementById('mod-type').value.trim();
          const mtg = document.getElementById('mod-target').value.trim();
          if (!rat || !mt || !mtg) { showToast('Rationale, type, and target are required', 'error'); return; }
          try { await api.post(`/cases/${cid}/approval`, { decision: 'modify', rationale: rat, modified_action_type: mt, modified_action_target: mtg, modified_action_detail: document.getElementById('mod-detail').value }); showToast('Modification submitted', 'success'); load(); }
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
      let html = `<h2 style="font-size:20px;margin-bottom:16px">Outcome and Feedback - ${esc(cid)}</h2>`;

      // Work order
      html += `<div class="grid-2">
        <div class="card"><div class="card-header"><h3>Work Order</h3></div><div class="card-body" id="wo-body"></div></div>
        <div class="card"><div class="card-header"><h3>Outcome Recording</h3></div><div class="card-body" id="oc-body"></div></div>
      </div>`;

      // Audit timeline
      html += `<div class="card"><div class="card-header"><h3>Audit Timeline (Hash-Chain)</h3></div><div class="card-body" id="au-body"></div></div>`;

      el.innerHTML = html;

      // Work order
      const woBody = document.getElementById('wo-body');
      if (s.work_order_id) {
        woBody.innerHTML = `<div class="banner banner-success"><p><strong>Work Order:</strong> <code>${esc(s.work_order_id)}</code></p></div>`;
      } else if (s.current_state === 'AWAITING_APPROVAL') {
        woBody.innerHTML = '<div class="banner banner-info"><p>Approval required before a work order can be raised.</p></div>';
      } else if (s.current_state === 'EXECUTING' || s.current_state === 'MONITORING_OUTCOME') {
        const role = api.user();
        const canWO = ['mgr1', 'admin1'].includes(role);
        woBody.innerHTML = canWO
          ? `<button class="btn btn-primary" id="btn-wo">Raise Work Order</button>`
          : `<div class="banner banner-error"><p><strong>Blocked</strong> - Role "${esc(role)}" cannot create work orders.</p></div>`;
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
          ${s.outcome.root_cause_confirmed ? `<p><strong>Root Cause:</strong> <code>${esc(s.outcome.root_cause_confirmed)}</code></p>` : ''}
          ${s.outcome.verified_by ? `<p><strong>Verified by:</strong> ${esc(s.outcome.verified_by)}</p>` : ''}
          ${s.outcome.notes ? `<p><strong>Notes:</strong> ${esc(s.outcome.notes)}</p>` : ''}
        </div>`;
        // Feedback
        if (s.current_state === 'FEEDBACK_QUEUED' || s.current_state === 'CLOSED') {
          const role = api.user();
          const canFB = ['mgr1', 'steward1', 'steward2', 'admin1'].includes(role);
          if (canFB) {
            ocBody.innerHTML += `<div class="mt-16">
              <h4>Submit Feedback</h4>
              <div class="form-group"><label>Confirmed Root Cause</label><select id="fb-cause"><option value="">-- select --</option>${KNOWN_CAUSES.map(c => `<option value="${c}">${c.replace(/_/g,' ')}</option>`).join('')}</select></div>
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
            ocBody.innerHTML += `<div class="banner banner-error mt-16"><p><strong>Feedback Blocked</strong> - Role "${esc(role)}" cannot submit feedback.</p></div>`;
          }
        }
      } else if (s.current_state === 'EXECUTING' || s.current_state === 'MONITORING_OUTCOME' || s.current_state === 'RECORDING_OUTCOME') {
        const role = api.user();
        const canRec = ['tech1', 'mgr1', 'admin1'].includes(role);
        if (canRec) {
          ocBody.innerHTML = `
            <div class="form-group"><label>Result</label><select id="oc-result"><option value="resolved">resolved</option><option value="partial">partial</option><option value="unresolved">unresolved</option></select></div>
            <div class="form-group"><label>Confirmed Root Cause</label><select id="oc-cause"><option value="">-- select --</option>${KNOWN_CAUSES.map(c => `<option value="${c}">${c.replace(/_/g,' ')}</option>`).join('')}</select></div>
            <div class="form-group"><label>Verified By</label><input id="oc-verified" type="text" value="tech1"></div>
            <div class="form-group"><label>Notes</label><textarea id="oc-notes" placeholder="Optional notes..."></textarea></div>
            <button class="btn btn-primary" id="btn-oc">Record Outcome</button>
          `;
          document.getElementById('btn-oc').onclick = async () => {
            try {
              await api.post(`/cases/${cid}/outcome`, {
                result: document.getElementById('oc-result').value,
                root_cause_confirmed: document.getElementById('oc-cause').value,
                verified_by: document.getElementById('oc-verified').value,
                notes: document.getElementById('oc-notes').value,
              });
              showToast('Outcome recorded', 'success');
              load();
            } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
          };
        } else {
          ocBody.innerHTML = `<div class="banner banner-error"><p><strong>Blocked</strong> - Role "${esc(role)}" cannot record outcomes.</p></div>`;
        }
      } else {
        ocBody.innerHTML = `<div class="banner banner-info"><p>Outcome recording available after work order execution.</p><p>Current state: <strong>${esc(s.current_state)}</strong></p></div>`;
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
    <div class="stats-row" id="gov-stats"></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><h3>Cause Distribution</h3></div><div class="card-body" id="cause-dist"></div></div>
      <div class="card"><div class="card-header"><h3>Governance Pipeline</h3></div><div class="card-body" id="pipeline-body"></div></div>
    </div>
    <div class="card"><div class="card-header"><h3>Knowledge Approval Queue</h3></div><div class="card-body" id="queue-body"></div></div>
    <div class="card"><div class="card-header"><h3>SHA-256 Audit Trace</h3></div><div class="card-body" id="trace-body"></div></div>
  `;

  // Pipeline visual
  setHTML('pipeline-body', `
    <div class="pipeline">
      <div class="pipeline-step"><div class="pipeline-circle">1</div><div class="pipeline-label">Expert or Outcome Proposes</div><div class="pipeline-desc">AI-drafted interviews and confirmed outcomes become pending proposals</div></div>
      <div class="pipeline-arrow">-></div>
      <div class="pipeline-step"><div class="pipeline-circle">2</div><div class="pipeline-label">Second Steward Reviews</div><div class="pipeline-desc">Proposer can never approve their own change</div></div>
      <div class="pipeline-arrow">-></div>
      <div class="pipeline-step"><div class="pipeline-circle">3</div><div class="pipeline-label">Validated</div><div class="pipeline-desc">Written to KB</div></div>
      <div class="pipeline-arrow">-></div>
      <div class="pipeline-step"><div class="pipeline-circle">4</div><div class="pipeline-label">Version Bump</div><div class="pipeline-desc">1.3.0 -> 1.4.0</div></div>
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
      const describe = p => p.kind === 'expert_capture'
        ? `<strong>${esc(p.proposal_id)}</strong> <span class="badge badge-purple">Expert interview</span>
            <div style="font-size:13px;margin-top:4px">${esc(p.expert_name)} (${esc(p.expert_role)}), ${esc(p.asset_type)}: ${(p.heuristics || []).length} heuristic(s), drafted by ${p.provider === 'adp' ? 'Tencent Cloud ADP' : 'offline mock model'}</div>
            <ul style="margin:6px 0 0 18px;font-size:13px">${(p.heuristics || []).map(x => `<li><code>${esc(x.likely_cause)}</code>: <em>"${esc(x.evidence_quote)}"</em></li>`).join('')}</ul>
            <div style="font-size:12px;color:var(--muted)">Submitted by: ${esc(p.submitted_by)}</div>`
        : `<strong>${esc(p.proposal_id)}</strong> <span class="badge badge-blue">Outcome feedback</span> Cause: <code>${esc(p.confirmed_cause)}</code>
            <div style="font-size:12px;color:var(--muted)">Case: ${esc(p.case_id)} | Asset: ${esc(p.asset_id)} | Submitted by: ${esc(p.submitted_by)}</div>`;
      qb.innerHTML = queue.map(p => `<div class="card" style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
          <div>${describe(p)}</div>
          <div class="flex gap-8">
            <button class="btn btn-green btn-sm" id="approve-${esc(p.proposal_id)}">Approve</button>
            <button class="btn btn-red btn-sm" id="reject-${esc(p.proposal_id)}">Reject</button>
          </div>
        </div>
      </div>`).join('');
      // Wire approve/reject buttons
      queue.forEach(p => {
        const aBtn = document.getElementById(`approve-${p.proposal_id}`);
        const rBtn = document.getElementById(`reject-${p.proposal_id}`);
        if (aBtn) aBtn.onclick = async () => {
          try { await api.post(`/kb/proposals/${p.proposal_id}/approve`); showToast('Proposal approved', 'success'); loadQueue(); loadStats(); window.__app__?.refreshKbVersion?.(); }
          catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
        if (rBtn) rBtn.onclick = async () => {
          try { await api.post(`/kb/proposals/${p.proposal_id}/reject`, { reason: 'Rejected by reviewer' }); showToast('Proposal rejected', 'success'); loadQueue(); }
          catch (e) { showToast(`Error: ${e.message}`, 'error'); }
        };
      });
    } catch (e) {
      qb.innerHTML = isForbidden(e)
        ? rbacNote('Reviewing knowledge proposals', 'knowledge stewards (steward1, steward2)')
        : `<p class="muted">Error: ${esc(e.message)}</p>`;
    }
  }

  // Load KB stats
  async function loadStats() {
    try {
      const stats = await api.get('/kb/stats');
      setHTML('gov-stats', `
        <div class="stat"><div class="stat-val">${stats.total_validated_cases ?? 0}</div><div class="stat-lbl">Validated Cases</div></div>
        <div class="stat stat-purple"><div class="stat-val">${stats.feedback_added ?? 0}</div><div class="stat-lbl">Feedback Added</div></div>
        <div class="stat stat-yellow"><div class="stat-val">${stats.pending_proposals ?? 0}</div><div class="stat-lbl">Pending Proposals</div></div>
        <div class="stat stat-green"><div class="stat-val">v${stats.kb_version_label ?? "1.3.0"}</div><div class="stat-lbl">KB Version</div></div>
        <div class="stat stat-blue"><div class="stat-val">4 / 24</div><div class="stat-lbl">Trees / Causes</div></div>
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
          return `<div class="cause-bar"><div class="cause-bar-label">${esc(cause.replace(/_/g,' '))}</div><div class="cause-bar-track"><div class="cause-bar-fill" style="width:${pct}%"></div></div><div class="cause-bar-count">${count}</div></div>`;
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

  loadStats();
  loadQueue();
  loadTrace();
}

// ═══════════════════════════════════════════════════════════
// Demo case seeder
// ═══════════════════════════════════════════════════════════
export async function seedDemoCases(h) {
  const { showToast, navigate } = h;

  async function apiAs(user, method, path, params) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('user', user);
    if (method === 'POST' && params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
      }
    }
    const res = await fetch(url, { method });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    return body;
  }

  async function apiJsonAs(user, path, jsonBody) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('user', user);
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(jsonBody || {}) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    return body;
  }

  try {
    showToast('Seeding demo cases...', 'info');

    // Case 1: CRAH-DC1-01 - happy path to CLOSED
    let r = await apiAs('tech1', 'POST', '/cases', { asset_id: 'CRAH-DC1-01', sensor_id: 'SA-TEMP-01', observation_type: 'temperature_measurement_missing', reading_status: 'absent' });
    const c1 = r.case_id;
    await apiAs('tech1', 'POST', `/cases/${c1}/advance`);
    await apiAs('mgr1', 'POST', `/cases/${c1}/approval`, { decision: 'approve' });
    await apiAs('mgr1', 'POST', `/cases/${c1}/work-order`);
    await apiAs('tech1', 'POST', `/cases/${c1}/outcome`, { result: 'resolved', root_cause_confirmed: 'sensor_hardware_failure', verified_by: 'tech1', notes: 'Sensor replaced, temperature restored' });
    await apiJsonAs('mgr1', `/cases/${c1}/feedback`, { confirmed_cause: 'sensor_hardware_failure', notes: 'Confirmed root cause' });

    // Case 2: CRAH-DC1-02 - bus failure, escalates
    r = await apiAs('tech1', 'POST', '/cases', { asset_id: 'CRAH-DC1-02', sensor_id: 'SA-TEMP-02', observation_type: 'temperature_measurement_missing', reading_status: 'absent' });
    const c2 = r.case_id;
    await apiAs('tech1', 'POST', `/cases/${c2}/advance`);

    // Case 3: CHILLER-DC1-01 - chiller compressor trip, awaiting approval
    r = await apiAs('tech1', 'POST', '/cases', { asset_id: 'CHILLER-DC1-01', sensor_id: 'CH-COMP-PRESSURE', observation_type: 'chiller_compressor_trip', reading_status: 'absent' });
    const c3 = r.case_id;
    await apiAs('tech1', 'POST', `/cases/${c3}/advance`);

    showToast('Seeded 3 cases: 1 CLOSED, 1 ESCALATED, 1 AWAITING_APPROVAL', 'success');
    navigate('dashboard');
  } catch (e) {
    showToast(`Seed error: ${e.message}`, 'error');
  }
}

// ════════════════════════════════════════════════════════════
// Screen 0: Expert Knowledge Capture (the harvest)
// The model drafts; a different knowledge steward decides.
// ════════════════════════════════════════════════════════════
export function renderCapture(el, state, h) {
  const { api, showToast, esc, navigate } = h;
  const role = api.user();
  const canCapture = ['mgr1', 'steward1', 'steward2', 'admin1'].includes(role);

  el.innerHTML = `
    <div class="banner banner-info mb-0" style="margin-bottom:16px">
      <p><strong>How expert know-how enters the Intelligence Pill.</strong>
      Paste or transcribe an interview with an experienced technician. An AI model drafts structured
      heuristics from it. Anything the expert did not say word for word is discarded, and nothing goes
      live until a <strong>different</strong> knowledge steward approves it on the Governance screen.</p>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-header"><h3>Expert Interview</h3></div>
        <div class="card-body">
          <div class="form-group"><label for="cap-name">Expert</label><input id="cap-name" type="text" placeholder="e.g. R. Tan"></div>
          <div class="form-group"><label for="cap-role">Role and experience</label><input id="cap-role" type="text" placeholder="e.g. Senior M&amp;E Technician, 22 years"></div>
          <div class="form-group"><label for="cap-asset">Asset type</label>
            <select id="cap-asset"><option>CRAH</option><option>Chiller</option><option>UPS</option><option>Pump</option></select></div>
          <div class="form-group"><label for="cap-text">Interview transcript</label>
            <textarea id="cap-text" rows="14" placeholder="Interviewer: When ... what do you check first?"></textarea></div>
          <div class="flex gap-8 flex-wrap">
            <button class="btn btn-secondary" id="cap-sample">Load sample interview</button>
            <button class="btn btn-primary" id="cap-run" ${canCapture ? '' : 'disabled'}>Draft knowledge with AI</button>
          </div>
          ${canCapture ? '' : `<div class="banner banner-error mt-16"><p>Role "${esc(role)}" cannot capture expert knowledge. Switch to an Asset Ops Manager or Knowledge Steward.</p></div>`}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h3>AI Draft</h3><span class="badge badge-yellow">Pending steward approval</span></div>
        <div class="card-body" id="cap-result">
          <div class="empty-state"><div class="empty-state-icon">[ ]</div>
            <div class="empty-state-title">No draft yet</div>
            <div class="empty-state-desc">Load the sample interview, then draft knowledge to see what the model extracts and why.</div></div>
        </div>
      </div>
    </div>`;

  document.getElementById('cap-sample').onclick = async () => {
    try {
      const s = await api.get('/capture/sample');
      document.getElementById('cap-name').value = s.expert_name;
      document.getElementById('cap-role').value = s.expert_role;
      document.getElementById('cap-asset').value = s.asset_type;
      document.getElementById('cap-text').value = s.transcript;
    } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
  };

  const list = (title, items) => items && items.length
    ? `<div class="kh-row"><span class="kh-label">${title}</span><ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : '';

  document.getElementById('cap-run').onclick = async () => {
    const body = {
      expert_name: document.getElementById('cap-name').value.trim(),
      expert_role: document.getElementById('cap-role').value.trim(),
      asset_type: document.getElementById('cap-asset').value,
      transcript: document.getElementById('cap-text').value,
    };
    if (!body.expert_name || !body.expert_role || !body.transcript.trim()) {
      showToast('Fill in expert, role and transcript first', 'error'); return;
    }
    const out = document.getElementById('cap-result');
    out.innerHTML = '<div class="skeleton-card"><div class="skeleton-line"></div><div class="skeleton-line"></div><div class="skeleton-line"></div></div>';
    try {
      const res = await fetch(`/capture/interview?user=${encodeURIComponent(role)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || `HTTP ${res.status}`);
      const model = d.provider === 'adp' ? 'Tencent Cloud ADP' : 'Offline mock model';
      out.innerHTML = `
        <div class="flex gap-8 flex-wrap" style="margin-bottom:12px">
          <span class="badge badge-purple">Model: ${esc(model)}</span>
          <span class="badge badge-green">${d.heuristics.length} grounded</span>
          ${d.dropped ? `<span class="badge badge-red">${d.dropped} dropped as ungrounded</span>` : ''}
        </div>
        ${(d.warnings || []).map(w => `<div class="banner banner-warn"><p>${esc(w)}</p></div>`).join('')}
        ${d.heuristics.map(x => `
          <div class="kh-item">
            <div class="kh-head">
              <span class="badge ${x.new_cause ? 'badge-yellow' : 'badge-blue'}">${esc(x.likely_cause)}</span>
              ${x.new_cause ? '<span class="kh-new">New cause: needs an engineered decision-tree branch</span>' : ''}
            </div>
            <div class="kh-row"><span class="kh-label">When</span>${esc(x.symptom_pattern)}</div>
            ${list('Checks', x.checks)}${list('Never', x.do_not)}${list('Escalate when', x.escalate_when)}
            <div class="kh-label" style="margin-top:10px">Expert's own words</div>
            <blockquote class="kh-quote">"${esc(x.evidence_quote)}"</blockquote>
          </div>`).join('')}
        <div class="banner banner-success mt-16"><p>Queued as <strong>${esc(d.proposal_id)}</strong>. A different knowledge steward must approve it before it goes live.</p></div>
        <button class="btn btn-secondary mt-16" id="cap-gov">Open Governance queue</button>`;
      document.getElementById('cap-gov').onclick = () => navigate('governance');
      showToast('Draft queued for steward review', 'success');
    } catch (e) {
      out.innerHTML = `<div class="banner banner-error"><p>${esc(e.message)}</p></div>`;
    }
  };
}
