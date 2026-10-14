// app.js - App controller: navigation, role switching, toasts, helpers

import { api } from './api.js?v=9';
import { initGuide } from './guide.js?v=14';
import { initCloud, setCloudStatus, setCloudMood, setCloudScreen, cloudThinking } from './cloud.js?v=7';
import { renderDashboard, renderDiagnosis, renderDecision, renderOutcome, renderGovernance, renderCapture } from './screens.js?v=43';

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
  tech1:    { name: 'Technician',            cap: 'technician',
              does: 'Opens cases, runs the diagnosis, records the outcome and sends feedback. Cannot approve.' },
  mgr1:     { name: 'Asset Ops Manager',      cap: 'asset_ops_manager',
              does: 'Approves, rejects or modifies the recommendation, raises the work order, closes escalations.' },
  steward1: { name: 'Knowledge Steward',     cap: 'knowledge_steward',
              does: 'Decides expert knowledge and feedback for CRAH and UPS. Countersigns their rollbacks.' },
  steward2: { name: 'Knowledge Steward 2',   cap: 'knowledge_steward',
              does: 'Decides expert knowledge and feedback for Chiller and Pump. Countersigns their rollbacks.' },
  auditor1: { name: 'Auditor',                cap: 'auditor',
              does: 'Checks the audit trail and ledger; restores a verified copy or quarantines a case.' },
  admin1:   { name: 'Admin',                  cap: 'admin',
              does: 'Runs the system and asks for rollbacks, which a steward countersigns. Cannot approve cases or knowledge.' },
};

function roleDisplayName(id) {
  return ROLE_NAMES[id]?.name || id;
}

function statePill(stateVal) {
  // Status pill mapping
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

function confBand(conf, state) {
  // Confidence bands. An escalated case is with a human whatever
  // its score, so it never reads as "Medium" or "Recommendable".
  if (conf === null || conf === undefined) return { cls: 'badge-grey', label: 'N/A' };
  if (state === 'ESCALATED') return { cls: 'badge-red', label: (conf * 100).toFixed(0) + '% · escalated' };
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
// Keep the nav footer in step with each pill's live KB version (same source as Governance).
async function refreshKbVersion() {
  const el = document.getElementById('nav-kb-version');
  if (!el) return;
  try {
    const stats = await api.get('/kb/stats');
    const labels = Object.values(stats.kb_version_labels || {});
    el.textContent = labels.length ? `KB ${labels.join(' · ')}` : 'KB version unavailable';
    el.title = 'Each pill versions its own knowledge';
    el.parentElement.title = el.textContent;
  } catch (_) { if (el.textContent.includes('loading')) el.textContent = 'KB version unavailable'; }
}

function navigate(screen, caseId = null) {
  state.screen = screen;
  setCloudMood(null); // screens set a mood again if their case calls for one
  setCloudScreen(screen);
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

// ── Hideable menu (remembered per browser) ──────────────────
// The ‹ beside the brand hides it; the › at the start of the top bar
// (only there while it is hidden) brings it back.
function setNavHidden(hidden) {
  document.documentElement.classList.toggle('nav-hidden', hidden);
  try { localStorage.setItem('tbc_nav_hidden', hidden ? '1' : '0'); } catch (_) {}
  document.getElementById(hidden ? 'nav-show' : 'nav-hide')?.focus();
}
document.getElementById('nav-hide').addEventListener('click', () => setNavHidden(true));
document.getElementById('nav-show').addEventListener('click', () => setNavHidden(false));

// ── Role switcher ──────────────────────────────────────────
// Switching role means logging in as that demo user (sets the signed
// session cookie) — awaitable so callers (the guide tour included) can
// rely on the new identity being live before they act on it.
roleSelect.value = state.role;
// The badge stays "Not signed in" (set in the page) until a PIN is accepted.

// ── PIN sign-in ────────────────────────────────────────────
// Naming a user is not enough to act as them: the server checks their PIN
// (five wrong tries lock that user out for five minutes). Once a PIN has
// been proven in this browser, switching back to that user needs no PIN.
function askPin(userId, note = '') {
  // Resolves with the user who signed in, or false if the dialog was cancelled.
  const backdrop = document.getElementById('pin-backdrop');
  const form = document.getElementById('pin-dialog');
  const input = document.getElementById('pin-input');
  const err = document.getElementById('pin-error');
  const list = document.getElementById('pin-accounts');
  const prompt = document.getElementById('pin-prompt');
  let current = userId;
  const demo = (window.__DEMO_USERS__ || []).map(u => u.id);
  const accounts = demo.length ? demo : [userId];
  const showPrompt = () => {
    prompt.textContent = `Enter the PIN for ${current} (${roleDisplayName(current)}).`;
    list.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.user === current)));
  };
  list.innerHTML = accounts.map(id => `<li><button type="button" class="pin-account" data-user="${esc(id)}">
      <strong>${esc(roleDisplayName(id))}</strong> <span class="muted">${esc(id)}</span>
      <span class="pin-account-does">${esc((ROLE_NAMES[id] || {}).does || '')}</span></button></li>`).join('');
  list.querySelectorAll('button').forEach(b => b.onclick = () => {
    current = b.dataset.user; input.value = ''; err.textContent = ''; showPrompt(); input.focus();
  });
  showPrompt();
  input.value = ''; err.textContent = note;
  backdrop.hidden = false;
  input.focus();
  return new Promise(resolve => {
    const done = value => { backdrop.hidden = true; form.onsubmit = null; resolve(value); };
    form.onsubmit = async ev => {
      ev.preventDefault();
      try { await api.login(current, input.value); done(current); }
      catch (e) { err.textContent = e.message; input.select(); }
    };
    document.getElementById('pin-cancel').onclick = () => done(false);
    backdrop.onkeydown = ev => { if (ev.key === 'Escape') { ev.preventDefault(); done(false); } };
  });
}

// Resolves with the user who is now signed in (may differ from the one asked
// for, if the person picks another account in the dialog), or false.
async function signIn(userId) {
  // Every sign-in asks for the PIN, including a switch back to someone who
  // signed in earlier on this screen: the server requires it too.
  return askPin(userId);
}

// ``render: false`` when the caller navigates straight after: two renders
// racing into the same container would leave the slower (old) screen on top.
async function setRole(role, { render = true } = {}) {
  if (roleSelect.value === role && state.role === role) return true;
  const who = await signIn(role);
  if (!who) {
    roleSelect.value = state.role; // revert the dropdown
    return false;
  }
  roleSelect.value = who;
  state.role = who;
  roleBadge.textContent = roleDisplayName(state.role);
  updateKbFooter();
  if (render) renderScreen();
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
// The AI's presence on every screen: the avatar's state says whether the
// model is answering, offline, or the offline (non-LLM) models are in use.
async function refreshSystemInfo() {
  const chip = document.getElementById('model-chip');
  const banner = document.getElementById('insecure-banner');
  try {
    const info = await api.get('/system/info');
    const view = {
      online: ['online', 'badge-purple', `AI: ${info.llm_label}`],
      ready: ['ready', 'badge-purple', `AI: ${info.llm_label}`],
      offline: ['offline', 'badge-red', `AI offline (${info.llm_label})`],
      'offline-model': ['ready', 'badge-purple', 'AI: offline models (no LLM)'],
    }[info.ai_status] || ['ready', 'badge-purple', `AI: ${info.llm_label}`];
    setCloudStatus(view[0], info.ai_status === 'offline' ? info.ai_status_message : '');
    chip.className = `badge ${view[1]}`;
    chip.textContent = view[2];
    chip.title = info.ai_status_message;
    if (banner) banner.hidden = !info.demo_insecure;
  } catch (_) { chip.hidden = true; }
}

// ── Init ───────────────────────────────────────────────────
// Identity lives in a signed session cookie (auth.py): log in as the
// last-used role before any other request, so the cookie — not a client
// -controlled ?user= — is what the server sees from here on.
initCloud();
(async () => {
  let who;
  while (!(who = await signIn(state.role))) {
    showToast('Sign in to continue', 'error');
  }
  state.role = who;
  roleSelect.value = who;
  roleBadge.textContent = roleDisplayName(who);
  initGuide({ api, navigate, setRole, showToast });
  navigate('dashboard');
  updateKbFooter();
  refreshSystemInfo();
})();

// Expose for debugging
window.__app__ = { state, navigate, showToast, copyToClipboard, refreshKbVersion, refreshSystemInfo };
window.__cloud__ = { setCloudMood, cloudThinking };
