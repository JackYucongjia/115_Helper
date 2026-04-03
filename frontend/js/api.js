/**
 * Backend API client wrapper.
 */
const API = {
  base: '',

  async _fetch(url, options = {}) {
    try {
      const resp = await fetch(this.base + url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
      }
      return data;
    } catch (err) {
      console.error(`API ${url}:`, err);
      throw err;
    }
  },

  // ── Auth ──────────────────────────────────────────────
  getAuthStatus()   { return this._fetch('/api/auth/status'); },
  getAppTypes()     { return this._fetch('/api/auth/app-types'); },
  loginCookie(cookies) {
    return this._fetch('/api/auth/cookie', {
      method: 'POST', body: JSON.stringify({ cookies }),
    });
  },
  startQRLogin(appType = 'alipaymini') {
    return this._fetch('/api/auth/qrcode', {
      method: 'POST', body: JSON.stringify({ app_type: appType }),
    });
  },
  cancelQR()  { return this._fetch('/api/auth/qrcode/cancel', { method: 'POST' }); },
  logout()    { return this._fetch('/api/auth/logout', { method: 'POST' }); },

  // ── Files ─────────────────────────────────────────────
  listFiles(cid = '0') {
    return this._fetch(`/api/files/list?cid=${encodeURIComponent(cid)}`);
  },
  searchDirs(keyword, cid = '0') {
    return this._fetch(`/api/files/search?keyword=${encodeURIComponent(keyword)}&cid=${encodeURIComponent(cid)}`);
  },

  // ── ISO ───────────────────────────────────────────────
  scanISO(dirId) {
    return this._fetch('/api/iso/scan', {
      method: 'POST', body: JSON.stringify({ target_dir_id: dirId }),
    });
  },
  processISO(action, fileIds, targetDirId = null) {
    return this._fetch('/api/iso/process', {
      method: 'POST', body: JSON.stringify({
        action, file_ids: fileIds, target_dir_id: targetDirId,
      }),
    });
  },

  // ── Restructure ───────────────────────────────────────
  previewRestructure(dirId, blacklist = []) {
    return this._fetch('/api/restructure/preview', {
      method: 'POST', body: JSON.stringify({ target_dir_id: dirId, blacklist }),
    });
  },
  executeRestructure(dirId, blacklist = []) {
    return this._fetch('/api/restructure/execute', {
      method: 'POST', body: JSON.stringify({ target_dir_id: dirId, blacklist }),
    });
  },
  getBlacklist() { return this._fetch('/api/restructure/blacklist'); },
  updateBlacklist(blacklist) {
    return this._fetch('/api/restructure/blacklist', {
      method: 'PUT', body: JSON.stringify({ blacklist }),
    });
  },
};
