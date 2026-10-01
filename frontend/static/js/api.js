// api.js - API client wrapping all backend endpoints with ?user= param

const api = {
  user() {
    return localStorage.getItem('tbc_user') || 'mgr1';
  },

  async get(path) {
    const sep = path.includes('?') ? '&' : '?';
    const res = await fetch(`${path}${sep}user=${this.user()}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async post(path, params) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('user', this.user());
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') {
          url.searchParams.set(k, v);
        }
      }
    }
    const res = await fetch(url, { method: 'POST' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    return body;
  },

  async postJson(path, jsonBody) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('user', this.user());
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(jsonBody || {}),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    return body;
  },
};

export { api };
