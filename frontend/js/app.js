/**
 * 115_Helper — Main Application
 * SPA router, auth page rendering, lifecycle management.
 */
const App = {
  _currentView: null,
  _isLoggedIn: false,

  async init() {
    // Render sidebar
    Sidebar.render();

    // Connect WebSocket
    WS.connect();

    // Listen for login events from WS
    WS.on('login_success', (data) => {
      this._isLoggedIn = true;
      Toast.success(`登录成功 (${data.app_label || data.app_type})`);
      this.navigate('browser');
      this._updateTopBar();
    });

    WS.on('alert', (data) => {
      Toast[data.level === 'error' ? 'error' : 'warning'](data.message);
    });

    // Check auth status and navigate
    try {
      const status = await API.getAuthStatus();
      this._isLoggedIn = status.logged_in;
      if (this._isLoggedIn) {
        this.navigate('browser');
      } else {
        this.navigate('auth');
      }
    } catch (e) {
      this.navigate('auth');
    }

    this._updateTopBar();
  },

  navigate(view) {
    this._currentView = view;
    Sidebar.setActive(view);

    const container = document.getElementById('content-area');
    if (!container) return;

    const titles = {
      auth: '登录管理',
      browser: '文件浏览',
      iso: 'ISO 探测器',
      restructure: '目录重构',
    };

    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = titles[view] || '115_Helper';

    switch (view) {
      case 'auth':
        this._renderAuthPage(container);
        break;
      case 'browser':
        this._requireAuth(() => FileBrowser.render(container));
        break;
      case 'iso':
        this._requireAuth(() => ISOScanner.render(container));
        break;
      case 'restructure':
        this._requireAuth(() => Restructure.render(container));
        break;
      default:
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🤔</div><div class="empty-state-text">未知页面</div></div>';
    }
  },

  _requireAuth(fn) {
    if (!this._isLoggedIn) {
      Toast.warning('请先登录 115 网盘');
      this.navigate('auth');
      return;
    }
    fn();
  },

  _updateTopBar() {
    const actions = document.getElementById('top-bar-actions');
    if (!actions) return;

    if (this._isLoggedIn) {
      actions.innerHTML = `
        <span class="badge badge-success">✓ 已登录</span>
        <button class="btn btn-secondary btn-sm" id="logout-btn">退出登录</button>
      `;
      document.getElementById('logout-btn')?.addEventListener('click', async () => {
        try {
          await API.logout();
          this._isLoggedIn = false;
          this._updateTopBar();
          Toast.info('已退出登录');
          this.navigate('auth');
        } catch (e) {
          Toast.error(`退出失败: ${e.message}`);
        }
      });
    } else {
      actions.innerHTML = '<span class="badge badge-warning">⚠ 未登录</span>';
    }
  },

  // ── Auth Page ─────────────────────────────────────────

  async _renderAuthPage(container) {
    // Fetch app types
    let appTypes = [];
    try {
      const data = await API.getAppTypes();
      appTypes = data.app_types || [];
    } catch (e) {
      appTypes = [{ key: 'alipaymini', label: '支付宝小程序' }];
    }

    const optionsHtml = appTypes.map(t =>
      `<option value="${t.key}" ${t.key === 'alipaymini' ? 'selected' : ''}>${Helpers.escapeHtml(t.label)}</option>`
    ).join('');

    container.innerHTML = `
      <div class="auth-container">
        <div style="text-align:center;margin-bottom:8px">
          <div style="font-size:48px;margin-bottom:8px">🔐</div>
          <h2 style="font-size:20px;font-weight:600;margin-bottom:4px">连接 115 网盘</h2>
          <p style="color:var(--text-muted);font-size:13px">选择登录方式开始使用</p>
        </div>

        <!-- Tab Switch -->
        <div class="tab-group" style="margin-bottom:20px">
          <button class="tab-btn active" data-tab="cookie">手动输入 Cookie</button>
          <button class="tab-btn" data-tab="qrcode">扫码登录</button>
        </div>

        <!-- Cookie Tab -->
        <div class="auth-card card" id="tab-cookie">
          <div class="card-body">
            <div class="form-group">
              <label class="form-label">115 Cookie 字符串</label>
              <textarea class="form-textarea" id="cookie-input" rows="4"
                placeholder="UID=...; CID=...; SEID=...; KID=..."></textarea>
              <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
                从浏览器开发者工具中获取 115 网盘的 Cookie 并粘贴到此处
              </div>
            </div>
            <button class="btn btn-primary w-full" id="cookie-login-btn">🔑 登录</button>
          </div>
        </div>

        <!-- QR Code Tab -->
        <div class="auth-card card" id="tab-qrcode" style="display:none">
          <div class="card-body">
            <div class="form-group">
              <label class="form-label">终端类型</label>
              <select class="form-select" id="qr-app-type">${optionsHtml}</select>
              <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
                选择不常使用的终端类型（如支付宝小程序）可获得更长久的 Cookie 有效期
              </div>
            </div>
            <button class="btn btn-primary w-full" id="qr-start-btn">📱 生成二维码</button>
            <div id="qr-code-area" style="display:none">
              <div class="qr-code-box">
                <img id="qr-code-img" src="" alt="QR Code" />
                <div class="qr-status-text" id="qr-status-text">请使用 115 手机客户端扫描二维码</div>
              </div>
              <button class="btn btn-secondary w-full mt-16" id="qr-cancel-btn">取消扫码</button>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindAuthEvents();
  },

  _bindAuthEvents() {
    // Tab switching
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn[data-tab]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.getElementById('tab-cookie').style.display = tab === 'cookie' ? 'block' : 'none';
        document.getElementById('tab-qrcode').style.display = tab === 'qrcode' ? 'block' : 'none';
      });
    });

    // Cookie login
    document.getElementById('cookie-login-btn')?.addEventListener('click', async () => {
      const cookies = document.getElementById('cookie-input')?.value?.trim();
      if (!cookies) { Toast.warning('请输入 Cookie'); return; }

      const btn = document.getElementById('cookie-login-btn');
      if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div> 登录中…'; }

      try {
        await API.loginCookie(cookies);
        this._isLoggedIn = true;
        Toast.success('Cookie 登录成功！');
        this._updateTopBar();
        this.navigate('browser');
      } catch (e) {
        Toast.error(`登录失败: ${e.message}`);
      } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '🔑 登录'; }
      }
    });

    // QR code start
    document.getElementById('qr-start-btn')?.addEventListener('click', async () => {
      const appType = document.getElementById('qr-app-type')?.value || 'alipaymini';
      const btn = document.getElementById('qr-start-btn');
      if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div> 生成中…'; }

      try {
        const data = await API.startQRLogin(appType);
        if (data.qr_image_base64) {
          document.getElementById('qr-code-img').src = `data:image/png;base64,${data.qr_image_base64}`;
          document.getElementById('qr-code-area').style.display = 'block';
          document.getElementById('qr-status-text').textContent =
            `请使用 115 手机客户端扫描 (${data.app_label || appType})`;
          if (btn) btn.style.display = 'none';
        }
      } catch (e) {
        Toast.error(`生成二维码失败: ${e.message}`);
        if (btn) { btn.disabled = false; btn.innerHTML = '📱 生成二维码'; }
      }
    });

    // QR cancel
    document.getElementById('qr-cancel-btn')?.addEventListener('click', async () => {
      await API.cancelQR();
      document.getElementById('qr-code-area').style.display = 'none';
      const btn = document.getElementById('qr-start-btn');
      if (btn) { btn.style.display = 'block'; btn.disabled = false; btn.innerHTML = '📱 生成二维码'; }
    });

    // WS QR status
    WS.on('qr_status', (data) => {
      const text = document.getElementById('qr-status-text');
      if (!text) return;
      switch (data.status) {
        case 'scanned':  text.textContent = '✅ 已扫描，请在手机上确认…'; break;
        case 'confirmed': text.textContent = '🎉 已确认，正在登录…'; break;
        case 'expired':  text.textContent = '⏰ 二维码已过期，请重新生成'; break;
        case 'cancelled': text.textContent = '❌ 扫码已取消'; break;
      }
    });
  },
};

// ── Bootstrap ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => App.init());
