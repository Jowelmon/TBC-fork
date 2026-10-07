// api.js - API client. Identity travels in a signed session cookie set by
// POST /login (see auth.py) — requests no longer carry ?user= themselves.
// `user()` is local UI bookkeeping only (which role this browser last
// logged in as); the server never trusts it on its own.

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
    if (!res.ok) { const e = new Error(body.detail || `HTTP ${res.status}`); e.status = res.status; throw e; }
    localStorage.setItem('tbc_user', userId);
    this.me = body;
    return body;
  },

  async get(path) {
    const res = await fetch(path, { credentials: 'same-origin' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
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
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
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
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    return body;
  },
};

export { api };
