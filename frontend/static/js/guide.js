// Guided demo tour: each step sets the role and screen, says what to tell
// the audience, and what they should notice. Doubles as the live demo script.

const STEPS = [
  {
    title: 'The problem',
    role: 'mgr1', screen: 'dashboard',
    say: 'Data centre cooling faults are diagnosed by a handful of senior technicians. When they leave, the know-how leaves with them. This Intelligence Pill captures that know-how for Technical Services fault diagnosis.',
    notice: 'Seeded cases: one resolved, a bus fault escalated to the BMS pill, a chiller waiting for the Asset Operations Manager, a UPS where the AI disagrees with the rules, and a pump escalated at 49% because nobody has written down how to read its vibration yet.',
  },
  {
    title: 'Harvest tacit knowledge',
    role: 'steward1', screen: 'capture',
    say: 'A knowledge steward interviews an experienced technician. The AI model drafts structured heuristics from the transcript: symptom, likely cause, what to check, what never to do, when to escalate.',
    notice: 'Click "Load sample interview" then "Draft knowledge with AI". Every heuristic sits beside the expert\'s own words; anything they did not say is dropped. Untick one heuristic, then "Send for steward approval". Chiller knowledge from a CRAH interview is filed under the Chiller pill.',
  },
  {
    title: 'Nobody approves their own change',
    role: 'steward1', screen: 'governance', tab: ['gov', 'review'],
    say: 'The draft is a proposal, not knowledge. As the steward who captured it, I will try to approve it myself.',
    notice: 'On the Approval queue tab, look at your own expert-interview proposal: Approve is locked with "You sent this". The server enforces the same rule if anyone calls it directly.',
  },
  {
    title: 'Second steward approves, version bumps',
    role: 'steward2', screen: 'governance', tab: ['gov', 'review'],
    say: 'A second steward reviews the expert\'s words and approves. Only now does it become live knowledge, versioned and reversible.',
    notice: 'Approve the proposal with a reason and tick the safety review: every check must be confirmed safe before it goes live. The chiller answer mentions a trip, so that heuristic becomes guidance only and never raises confidence. The KB version in the sidebar ticks up, and "Re-run diagnosis" appears for the open cases this knowledge touches. Re-run the PUMP-DC1-01 case: 49% becomes about 60%, past the 55% recommendation threshold.',
  },
  {
    title: 'Captured know-how changes the outcome',
    role: 'tech1', screen: 'diagnosis', asset: 'PUMP-DC1-01', tab: ['diag', 'expert'],
    newCase: { sensor_id: 'PUMP-DC1-01-VIB', observation_type: 'pump_vibration_high', reading_status: 'invalid' },
    say: 'A new vibration alarm on the same pump. Yesterday this escalated at 49%. Today the pill knows what R. Tan knows.',
    notice: 'This is a fresh PUMP-DC1-01 case diagnosed with the approved knowledge: it now clears 55% and goes to the Asset Operations Manager. The Expert knowledge tab quotes R. Tan and shows which of his words match this case\'s abnormal readings.',
  },
  {
    title: 'Transparent, deterministic diagnosis',
    role: 'tech1', screen: 'diagnosis', asset: 'CHILLER-DC1-01', tab: ['diag', 'scoring'],
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
    notice: 'Approve, modify and reject all require a rationale. Every transition is written to a keyed (HMAC-SHA256) hash-chained audit trail.',
  },
  {
    title: 'From one asset to the portfolio',
    role: 'auditor1', screen: 'governance', tab: ['gov', 'audit'],
    say: 'Chillers, CRAH units, UPS and pumps share one engine. Knowledge is plain data the organisation owns, the model is swappable, and every decision is auditable.',
    notice: 'The Audit & sentinel tab holds the ledger, the case audit trace and the sentinel; Overview has the version history and cause distribution a compliance officer reviews.',
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

  // Minimised, the guide is a slim bar (step, title, Next) that stays out of
  // the way of the screen; the choice is remembered.
  let mini = false;
  try { mini = localStorage.getItem('tbc_guide_mini') === '1'; } catch (_) { /* default */ }
  function setMini(v) {
    mini = v;
    try { localStorage.setItem('tbc_guide_mini', v ? '1' : '0'); } catch (_) { /* not remembered */ }
    render();
  }

  function render() {
    const s = STEPS[idx];
    panel.classList.toggle('guide-mini', mini);
    if (mini) {
      panel.innerHTML = `
        <span class="guide-count">Step ${idx + 1}/${STEPS.length}</span>
        <span class="guide-mini-title">${s.title}</span>
        <button class="btn btn-secondary btn-sm" id="guide-next" ${idx === STEPS.length - 1 ? 'disabled' : ''}>Next</button>
        <button class="guide-close" id="guide-expand" aria-label="Expand demo guide" title="Expand">&#9652;</button>
        <button class="guide-close" id="guide-close" aria-label="Close demo guide" title="Close">&times;</button>`;
      document.getElementById('guide-expand').onclick = () => setMini(false);
      document.getElementById('guide-close').onclick = close;
      document.getElementById('guide-next').onclick = () => { idx += 1; save(); go(); };
      return;
    }
    panel.innerHTML = `
      <div class="guide-head">
        <span class="guide-count">Step ${idx + 1} of ${STEPS.length}</span>
        <span>
          <button class="guide-close" id="guide-min" aria-label="Minimise demo guide" title="Minimise">&#8211;</button>
          <button class="guide-close" id="guide-close" aria-label="Close demo guide" title="Close">&times;</button>
        </span>
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
    document.getElementById('guide-min').onclick = () => setMini(true);
    document.getElementById('guide-prev').onclick = () => { idx -= 1; save(); go(); };
    document.getElementById('guide-next').onclick = () => { idx += 1; save(); go(); };
    document.getElementById('guide-go').onclick = go;
  }

  function save() { localStorage.setItem('tbc_guide_step', String(idx)); render(); }

  async function go() {
    const s = STEPS[idx];
    await setRole(s.role);
    let caseId = null;
    if (s.newCase) {
      // Raise a fresh alarm so the diagnosis uses today's knowledge base.
      try {
        const r = await api.post('/cases', { asset_id: s.asset, ...s.newCase });
        await api.post(`/cases/${r.case_id}/advance`);
        caseId = r.case_id;
      } catch (e) { showToast(`Could not raise the case: ${e.message}`, 'error'); }
    } else if (s.asset) {
      try { caseId = await findCaseId(api, s.asset); } catch (_) { /* fall through */ }
      if (!caseId) { showToast(`No ${s.asset} case yet. Switch to admin1 and click Seed Demo Cases on the Dashboard.`, 'error'); navigate('dashboard'); return; }
    }
    navigate(s.screen, caseId);
    // Land on the tab this step talks about, once the screen has drawn it.
    const tab = s.tab || { diagnosis: ['diag', 'summary'], decision: ['decision', 'decide'], outcome: ['outcome', 'work'] }[s.screen];
    if (tab) {
      for (let i = 0; i < 20 && !document.getElementById(`tab-${tab[0]}-${tab[1]}`); i++) {
        await new Promise(r => setTimeout(r, 150));
      }
      window.__tabs__?.open(...tab);
    }
  }

  function open() { panel.hidden = false; toggle.setAttribute('aria-expanded', 'true'); render(); }
  function close() { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); }

  toggle.onclick = () => (panel.hidden ? open() : close());
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) close(); });
}
