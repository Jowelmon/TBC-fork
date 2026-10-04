// app.js - App controller: navigation, role switching, toasts, helpers

import { api } from './api.js?v=3';
import { initGuide } from './guide.js?v=3';
import { renderDashboard, renderDiagnosis, renderDecision, renderOutcome, renderGovernance, renderCapture, seedDemoCases } from './screens.js?v=3';

// ── State ──────────────────────────────────────────────────
const state = {
  screen: 'dashboard',
  caseId: null,
  role: localStorage.getItem('tbc_user') || 'mgr1',
};

const SCREEN_TITLES = {
  dashboard: 'Asset and Fault Dashboard',
  capture: 'Expert Knowledge Capture',
  diagnosis: 'Diagnosis and Recommendation',
  decision: 'AOM Decision',
  outcome: 'Outcome and Feedback',
  governance: 'Pill Summary and Governance',
};

// ── DOM refs ───────────────────────────────────────────────
const content = document.getElementById('content');
const screenTitle = document.getElementById('screen-title');
const roleSelect = document.getElementById('role-select');
const roleBadge = document.getElementById('role-badge');
const breadcrumbCurrent = document.getElementById('breadcrumb-current');
const navItems = document.querySelectorAll('.nav-item');

// ── Helpers ────────────────────────────────────────────────
async function updateKbFooter() {
  const footer = document.getElementById('kb-footer');
  if (!footer) return;
  try {
    const stats = await api.get('/kb/stats');
    const version = stats && stats.kb_version !== undefined ? stats.kb_version : 0;
    footer.innerHTML = `v${version}<br><span class="nav-footer-sub">Keppel AI Harvest</span>`;
  } catch (err) {
    footer.innerHTML = `v0<br><span class="nav-footer-sub">KB unavailable</span>`;
  }
}

function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => (t.className = 'toast'), 4000);
}

// ── Copy to clipboard (for audit chain) ─────────────────────
function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.textContent = 'Copied';
    setTimeout(() => { btn.classList.remove('copied'); btn.textContent = 'Copy'; }, 2000);
  });
}

// ── Role display name ───────────────────────────────────────
const ROLE_NAMES = {
  tech1:    { name: 'Technician',            cap: 'technician' },
  mgr1:     { name: 'Asset Ops Manager',      cap: 'asset_ops_manager' },
  steward1: { name: 'Knowledge Steward',     cap: 'knowledge_steward' },
  steward2: { name: 'Knowledge Steward 2',   cap: 'knowledge_steward' },
  auditor1: { name: 'Auditor',                cap: 'auditor' },
  admin1:   { name: 'Admin',                  cap: 'admin' },
};

function roleDisplayName(id) {
  return ROLE_NAMES[id]?.name || id;
}

function statePill(stateVal) {
  // Miora spec status pill mapping
  const map = {
    TRIGGERED:          { cls: 'badge-grey',   label: 'Awaiting diagnosis' },
    GATHERING_EVIDENCE: { cls: 'badge-grey',   label: 'Awaiting diagnosis' },
    DIAGNOSING:         { cls: 'badge-grey',   label: 'Awaiting diagnosis' },
    RECOMMENDING:       { cls: 'badge-grey',   label: 'Awaiting diagnosis' },
    AWAITING_APPROVAL:  { cls: 'badge-yellow', label: 'Action required' },
    EXECUTING:          { cls: 'badge-blue',   label: 'In maintenance' },
    MONITORING_OUTCOME: { cls: 'badge-blue',   label: 'In maintenance' },
    RECORDING_OUTCOME:  { cls: 'badge-blue',   label: 'In maintenance' },
    FEEDBACK_QUEUED:    { cls: 'badge-grey',   label: 'Awaiting feedback' },
    ESCALATED:          { cls: 'badge-red',    label: 'Escalated' },
    CLOSED:             { cls: 'badge-green',  label: 'Resolved' },
  };
  const m = map[stateVal] || { cls: 'badge-grey', label: stateVal };
  return `<span class="badge ${m.cls}">${m.label}</span>`;
}

function confBand(conf) {
  // Miora spec confidence bands
  if (conf === null || conf === undefined) return { cls: 'badge-grey', label: 'N/A' };
  if (conf < 0.35) return { cls: 'badge-red', label: (conf * 100).toFixed(0) + '% Escalate' };
  if (conf < 0.55) return { cls: 'badge-yellow', label: (conf * 100).toFixed(0) + '% Medium' };
  return { cls: 'badge-green', label: (conf * 100).toFixed(0) + '% Recommendable' };
}

function fmtTime(ts) {
  if (!ts) return '-';
  try { return new Date(ts).toLocaleString('en-SG', { hour12: false }); }
  catch { return ts; }
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Navigation ─────────────────────────────────────────────
// Keep the nav footer in step with the live KB version (same source as Governance).
async function refreshKbVersion() {
  const el = document.getElementById('nav-kb-version');
  if (!el) return;
  try {
    const stats = await api.get('/kb/stats');
    if (stats.kb_version_label) el.textContent = `KB v${stats.kb_version_label}`;
  } catch (_) { /* leave last known value */ }
}

function navigate(screen, caseId = null) {
  state.screen = screen;
  refreshKbVersion();
  if (caseId) state.caseId = caseId;

  // Update nav items
  navItems.forEach(item => {
    item.classList.remove('active');
    if (item.dataset.screen === screen) item.classList.add('active');
  });

  // Enable case-specific nav items if a case is selected
  const caseScreens = ['diagnosis', 'decision', 'outcome'];
  navItems.forEach(item => {
    if (caseScreens.includes(item.dataset.screen)) {
      item.disabled = !state.caseId;
    }
  });

  screenTitle.textContent = SCREEN_TITLES[screen] || screen;

  // Update breadcrumbs
  if (breadcrumbCurrent) {
    if (state.caseId && caseScreens.includes(screen)) {
      breadcrumbCurrent.textContent = `${SCREEN_TITLES[screen]} / ${state.caseId}`;
    } else {
      breadcrumbCurrent.textContent = SCREEN_TITLES[screen] || screen;
    }
  }

  // Update role badge
  if (roleBadge) {
    roleBadge.textContent = roleDisplayName(state.role);
  }

  renderScreen();
}

function renderScreen() {
  const h = { api, showToast, statePill, confBand, fmtTime, esc, navigate, seedDemoCases, copyToClipboard, roleDisplayName };
  switch (state.screen) {
    case 'dashboard':
      renderDashboard(content, state, h);
      break;
    case 'diagnosis':
      renderDiagnosis(content, state, h);
      break;
    case 'decision':
      renderDecision(content, state, h);
      break;
    case 'outcome':
      renderOutcome(content, state, h);
      break;
    case 'governance':
      renderGovernance(content, state, h);
      break;
    case 'capture':
      renderCapture(content, state, h);
      break;
  }
}

// ── Role switcher ──────────────────────────────────────────
roleSelect.value = state.role;
roleBadge.textContent = roleDisplayName(state.role);
function setRole(role) {
  if (roleSelect.value === role) return;
  roleSelect.value = role;
  roleSelect.dispatchEvent(new Event('change'));
}

roleSelect.addEventListener('change', () => {
  state.role = roleSelect.value;
  localStorage.setItem('tbc_user', state.role);
  roleBadge.textContent = roleDisplayName(state.role);
  updateKbFooter();
  renderScreen();
});

// ── Nav click handlers ─────────────────────────────────────
navItems.forEach(item => {
  item.addEventListener('click', () => {
    if (item.disabled) return;
    navigate(item.dataset.screen);
  });
});

// ── Model chip (which model drafts expert knowledge) ───────
(async () => {
  const chip = document.getElementById('model-chip');
  try {
    const info = await api.get('/system/info');
    chip.textContent = `Capture model: ${info.llm_label}`;
    if (info.llm_provider === 'adp' && !info.adp_configured) {
      chip.textContent += ' (key missing)';
      chip.className = 'badge badge-red';
    }
  } catch (_) { chip.hidden = true; }
})();

// ── Init ───────────────────────────────────────────────────
initGuide({ api, navigate, setRole, showToast });
navigate('dashboard');
updateKbFooter();

// Expose for debugging
window.__app__ = { state, navigate, showToast, copyToClipboard, refreshKbVersion };
