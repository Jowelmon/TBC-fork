// Guided demo tour: each step sets the role and screen, says what to tell
// the audience, and what they should notice. Doubles as the live demo script.

const STEPS = [
  {
    title: 'The problem',
    role: 'mgr1', screen: 'dashboard',
    say: 'Data centre cooling faults are diagnosed by a handful of senior technicians. When they leave, the know-how leaves with them. This Intelligence Pill captures that know-how for Technical Services fault diagnosis.',
    notice: 'Three live cases: one resolved, one escalated, one waiting for the Asset Operations Manager.',
  },
  {
    title: 'Harvest tacit knowledge',
    role: 'steward1', screen: 'capture',
    say: 'A knowledge steward interviews an experienced technician. The AI model drafts structured heuristics from the transcript: symptom, likely cause, what to check, what never to do, when to escalate.',
    notice: 'Click "Load sample interview" then "Draft knowledge with AI". Every heuristic sits beside the expert\'s own words; anything they did not say is dropped. Untick one heuristic, then "Send for steward approval". Chiller knowledge from a CRAH interview is filed under the Chiller pill.',
  },
  {
    title: 'Nobody approves their own change',
    role: 'steward1', screen: 'governance',
    say: 'The draft is a proposal, not knowledge. As the steward who captured it, I will try to approve it myself.',
    notice: 'Look at your own expert-interview proposal: Approve is locked with "You sent this". The server enforces the same rule if anyone calls it directly.',
  },
  {
    title: 'Second steward approves, version bumps',
    role: 'steward2', screen: 'governance',
    say: 'A second steward reviews the expert\'s words and approves. Only now does it become live knowledge, versioned and reversible.',
    notice: 'Approve the proposal. The KB version in the sidebar ticks up. Rollback restores any earlier version.',
  },
  {
    title: 'Transparent, deterministic diagnosis',
    role: 'tech1', screen: 'diagnosis', asset: 'CHILLER-DC1-01',
    say: 'Diagnosis is a deterministic decision tree built from approved knowledge. Same evidence, same answer, every time. Confidence is a visible formula, not a black box.',
    notice: 'Evidence in plain English, the W1 to W5 confidence breakdown against the 0.55 and 0.35 thresholds, and a refrigerant leak forced to human approval with a safety escalation.',
  },
  {
    title: 'Knowing its own boundary',
    role: 'tech1', screen: 'diagnosis', asset: 'CRAH-DC1-02',
    say: 'Here every sensor on a controller went silent at once. That is a building management system fault, outside this pill\'s scope.',
    notice: 'Guardrail G3 escalates to the BMS pill owner instead of recommending anything. The system refuses rather than guesses.',
  },
  {
    title: 'The Asset Operations Manager decides',
    role: 'mgr1', screen: 'decision', asset: 'CHILLER-DC1-01',
    say: 'No work order exists until the AOM approves, modifies or rejects, with a rationale. A technician cannot do this step.',
    notice: 'Approve, modify and reject all require a rationale. Every transition is written to a SHA-256 hash-chained audit trail.',
  },
  {
    title: 'From one asset to the portfolio',
    role: 'auditor1', screen: 'governance',
    say: 'Chillers, CRAH units, UPS and pumps share one engine. Knowledge is plain data the organisation owns, the model is swappable, and every decision is auditable.',
    notice: 'The audit trace, version history and cause distribution are what a compliance officer reviews.',
  },
];

async function findCaseId(api, assetId) {
  const { cases = [] } = await api.get('/cases');
  for (const id of cases) {
    const snap = await api.get(`/cases/${id}`);
    if (snap.asset_id === assetId) return id;
  }
  return null;
}

export function initGuide({ api, navigate, setRole, showToast }) {
  let idx = Number(localStorage.getItem('tbc_guide_step') || 0);
  const panel = document.getElementById('guide-panel');
  const toggle = document.getElementById('guide-toggle');

  function render() {
    const s = STEPS[idx];
    panel.innerHTML = `
      <div class="guide-head">
        <span class="guide-count">Step ${idx + 1} of ${STEPS.length}</span>
        <button class="guide-close" id="guide-close" aria-label="Close demo guide">&times;</button>
      </div>
      <h2 class="guide-title">${s.title}</h2>
      <div class="guide-label">Say</div>
      <p class="guide-say">${s.say}</p>
      <div class="guide-label">Notice</div>
      <p class="guide-notice">${s.notice}</p>
      <div class="guide-actions">
        <button class="btn btn-secondary btn-sm" id="guide-prev" ${idx === 0 ? 'disabled' : ''}>Back</button>
        <button class="btn btn-primary btn-sm" id="guide-go">Go to this step</button>
        <button class="btn btn-secondary btn-sm" id="guide-next" ${idx === STEPS.length - 1 ? 'disabled' : ''}>Next</button>
      </div>`;
    document.getElementById('guide-close').onclick = close;
    document.getElementById('guide-prev').onclick = () => { idx -= 1; save(); go(); };
    document.getElementById('guide-next').onclick = () => { idx += 1; save(); go(); };
    document.getElementById('guide-go').onclick = go;
  }

  function save() { localStorage.setItem('tbc_guide_step', String(idx)); render(); }

  async function go() {
    const s = STEPS[idx];
    await setRole(s.role);
    let caseId = null;
    if (s.asset) {
      try { caseId = await findCaseId(api, s.asset); } catch (_) { /* fall through */ }
      if (!caseId) { showToast(`No ${s.asset} case yet. Seed demo cases on the Dashboard.`, 'error'); navigate('dashboard'); return; }
    }
    navigate(s.screen, caseId);
  }

  function open() { panel.hidden = false; toggle.setAttribute('aria-expanded', 'true'); render(); }
  function close() { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); }

  toggle.onclick = () => (panel.hidden ? open() : close());
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) close(); });
}
