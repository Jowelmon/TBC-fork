// app.js - App controller: navigation, role switching, toasts, helpers

import { api } from './api.js?v=5';
import { initGuide } from './guide.js?v=8';
import { renderDashboard, renderDiagnosis, renderDecision, renderOutcome, renderGovernance, renderCapture } from './screens.js?v=15';

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
  // Single footer, single source: the live KB version label from /kb/stats.
  return refreshKbVersion();
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
    el.textContent = stats.kb_version_label ? `KB v${stats.kb_version_label}` : 'KB version unavailable';
  } catch (_) { if (el.textContent.includes('loading')) el.textContent = 'KB version unavailable'; }
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
  const h = { api, showToast, statePill, confBand, fmtTime, esc, navigate, copyToClipboard, roleDisplayName };
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

// ── Theme toggle (light by default; dark is explicit opt-in) ──────────
const themeToggle = document.getElementById('theme-toggle');
function applyThemeButtonLabel() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  themeToggle.textContent = isDark ? 'Light theme' : 'Dark theme';
  themeToggle.setAttribute('aria-pressed', String(isDark));
}
applyThemeButtonLabel();
themeToggle.addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  if (next === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  localStorage.setItem('tbc_theme', next);
  applyThemeButtonLabel();
});

// ── Role switcher ──────────────────────────────────────────
// Switching role means logging in as that demo user (sets the signed
// session cookie) — awaitable so callers (the guide tour included) can
// rely on the new identity being live before they act on it.
roleSelect.value = state.role;
roleBadge.textContent = roleDisplayName(state.role);

// ── PIN sign-in ────────────────────────────────────────────
// Naming a user is not enough to act as them: the server checks their
// PIN. PINs typed here are kept for this browser tab only, so the demo
// can move between roles without retyping each time.
const pinCache = JSON.parse(sessionStorage.getItem('tbc_pins') || '{}');

function askPin(userId) {
  const backdrop = document.getElementById('pin-backdrop');
  const form = document.getElementById('pin-dialog');
  const input = document.getElementById('pin-input');
  const err = document.getElementById('pin-error');
  document.getElementById('pin-prompt').textContent =
    `Enter the PIN for ${userId} (${roleDisplayName(userId)}). Demo PINs are listed in DEMO.md.`;
  input.value = ''; err.textContent = '';
  backdrop.hidden = false;
  input.focus();
  return new Promise(resolve => {
    const done = value => { backdrop.hidden = true; form.onsubmit = null; resolve(value); };
    form.onsubmit = async ev => {
      ev.preventDefault();
      try {
        await api.login(userId, input.value);
        pinCache[userId] = input.value;
        sessionStorage.setItem('tbc_pins', JSON.stringify(pinCache));
        done(true);
      } catch (e) { err.textContent = e.message; input.select(); }
    };
    document.getElementById('pin-cancel').onclick = () => done(false);
  });
}

async function signIn(userId) {
  if (pinCache[userId]) {
    try { await api.login(userId, pinCache[userId]); return true; }
    catch (_) { delete pinCache[userId]; }
  }
  return askPin(userId);
}

async function setRole(role) {
  if (roleSelect.value === role && state.role === role) return true;
  if (!(await signIn(role))) {
    roleSelect.value = state.role; // revert the dropdown
    return false;
  }
  roleSelect.value = role;
  state.role = role;
  roleBadge.textContent = roleDisplayName(state.role);
  updateKbFooter();
  renderScreen();
  return true;
}

roleSelect.addEventListener('change', () => setRole(roleSelect.value));

// ── Nav click handlers ─────────────────────────────────────
navItems.forEach(item => {
  item.addEventListener('click', () => {
    if (item.disabled) return;
    navigate(item.dataset.screen);
  });
});

// ── Model chip (which model drafts expert knowledge) + insecure banner ──
async function refreshSystemInfo() {
  const chip = document.getElementById('model-chip');
  const banner = document.getElementById('insecure-banner');
  try {
    const info = await api.get('/system/info');
    chip.textContent = `Capture model: ${info.llm_label}`;
    if (info.llm_provider === 'adp' && !info.adp_configured) {
      chip.textContent += ' (key missing)';
      chip.className = 'badge badge-red';
    }
    if (banner) banner.hidden = !info.demo_insecure;
  } catch (_) { chip.hidden = true; }
}

// ── Init ───────────────────────────────────────────────────
// Identity lives in a signed session cookie (auth.py): log in as the
// last-used role before any other request, so the cookie — not a client
// -controlled ?user= — is what the server sees from here on.
(async () => {
  while (!(await signIn(state.role))) {
    showToast('Sign in to continue', 'error');
  }
  initGuide({ api, navigate, setRole, showToast });
  navigate('dashboard');
  updateKbFooter();
  refreshSystemInfo();
})();

// Expose for debugging
window.__app__ = { state, navigate, showToast, copyToClipboard, refreshKbVersion };
