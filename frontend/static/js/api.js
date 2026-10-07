// api.js - API client. Identity travels in a signed session cookie set by
// POST /login (see auth.py) — requests no longer carry ?user= themselves.
// `user()` is local UI bookkeeping only (which role this browser last
// logged in as); the server never trusts it on its own.

// Server details are written for developers ("record_outcome only valid in
// MONITORING_OUTCOME"); say the same thing in words an operator can act on.
const STEP_NAMES = {
  complete_diagnosis: 'Diagnosing', propose_recommendation: 'Recommending',
  record_human_decision: 'Approving, rejecting or modifying', acknowledge_work_order: 'Raising a work order',
  record_outcome: 'Recording the outcome', queue_feedback: 'Submitting feedback',
  close_escalation: 'Resolving the escalation', request_more_evidence: 'Requesting more evidence',
};
const STATE_NAMES = {
  DIAGNOSING: 'diagnosing', RECOMMENDING: 'recommending', AWAITING_APPROVAL: 'awaiting approval',
  EXECUTING: 'executing (work order raised)', MONITORING_OUTCOME: 'monitoring the outcome',
  FEEDBACK_QUEUED: 'waiting for feedback', ESCALATED: 'escalated',
};

function humanDetail(detail, status) {
  if (Array.isArray(detail)) return detail.map(d => d.msg || String(d)).join('; ');
  if (typeof detail !== 'string') return `Request failed (HTTP ${status})`;
  const m = detail.match(/^(\w+) only valid in (\w+)$/);
  if (m) {
    return `${STEP_NAMES[m[1]] || m[1].replace(/_/g, ' ')} is only possible once the case is ${STATE_NAMES[m[2]] || m[2]}. Refresh to see where the case is now.`;
  }
  return detail;
}

function apiError(res, body) {
  const e = new Error(humanDetail(body.detail, res.status));
  e.status = res.status;
  return e;
}

const api = {
  user() {
    return localStorage.getItem('tbc_user') || 'mgr1';
  },

  // Who the session is and what it may do (set by login). Screens gate on
  // capabilities, never on user names; the server enforces them anyway.
  me: null,
  can(cap) { return !!(this.me && this.me.capabilities.includes(cap)); },
  role() { return this.me ? this.me.role : null; },

  // Logs in as `userId`. The PIN goes in the request body, never the URL.
  // Without a PIN this only succeeds for a user this browser has already
  // proven the PIN for (an httpOnly cookie the server signs); the browser
  // itself never stores PINs.
  async login(userId, pin) {
    const res = await fetch('/login', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pin === undefined ? { user_id: userId } : { user_id: userId, pin }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw apiError(res, body);
    localStorage.setItem('tbc_user', userId);
    this.me = body;
    return body;
  },

  async get(path) {
    const res = await fetch(path, { credentials: 'same-origin' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw apiError(res, body);
    }
    return res.json();
  },

  async post(path, params) {
    const url = new URL(path, window.location.origin);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') {
          url.searchParams.set(k, v);
        }
      }
    }
    const res = await fetch(url, { method: 'POST', credentials: 'same-origin' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw apiError(res, body);
    return body;
  },

  async postJson(path, jsonBody) {
    const url = new URL(path, window.location.origin);
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(jsonBody || {}),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw apiError(res, body);
    return body;
  },
};

export { api };
