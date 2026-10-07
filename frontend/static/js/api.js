// api.js - API client. Identity travels in a signed session cookie set by
// POST /login (see auth.py) — requests no longer carry ?user= themselves.
// `user()` is local UI bookkeeping only (which role this browser last
// logged in as); the server never trusts it on its own.

const api = {
  user() {
    return localStorage.getItem('tbc_user') || 'mgr1';
  },

  // Sets the signed session cookie for `userId` after the server checks
  // their PIN. Call this — not a raw ?user= param — to switch who
  // subsequent requests act as.
  async login(userId, pin) {
    const q = new URLSearchParams({ user_id: userId, pin: pin || '' });
    const res = await fetch(`/login?${q}`, {
      method: 'POST', credentials: 'same-origin',
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    localStorage.setItem('tbc_user', userId);
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
