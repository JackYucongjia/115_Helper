/**
 * Sidebar navigation component.
 */
const Sidebar = {
  _activeView: 'auth',

  render() {
    const el = document.getElementById('sidebar');
    if (!el) return;

    el.innerHTML = `
      <!-- Logo -->
      <div class="sidebar-header">
        <div class="sidebar-logo">
          <div class="logo-icon">H</div>
          <div>
            <div class="logo-text">115_Helper</div>
          </div>
          <span class="logo-version">v1.0</span>
        </div>
      </div>

      <!-- Nav Items -->
      <nav class="sidebar-nav">
        <div class="nav-section-title">认证</div>
        <div class="nav-item ${this._activeView === 'auth' ? 'active' : ''}" data-view="auth">
          <span class="nav-icon">🔐</span>
          <span>登录管理</span>
        </div>

        <div class="nav-section-title">功能</div>
        <div class="nav-item ${this._activeView === 'browser' ? 'active' : ''}" data-view="browser">
          <span class="nav-icon">📂</span>
          <span>文件浏览</span>
        </div>
        <div class="nav-item ${this._activeView === 'iso' ? 'active' : ''}" data-view="iso">
          <span class="nav-icon">💿</span>
          <span>ISO 探测器</span>
        </div>
        <div class="nav-item ${this._activeView === 'restructure' ? 'active' : ''}" data-view="restructure">
          <span class="nav-icon">🏗️</span>
          <span>目录重构</span>
        </div>
      </nav>

      <!-- Footer -->
      <div class="sidebar-footer">
        <div class="connection-status">
          <div class="status-dot" id="ws-status-dot"></div>
          <span id="ws-status-text">未连接</span>
        </div>
      </div>
    `;

    // Bind click handlers
    el.querySelectorAll('.nav-item[data-view]').forEach(item => {
      item.addEventListener('click', () => {
        const view = item.dataset.view;
        this.setActive(view);
        App.navigate(view);
      });
    });
  },

  setActive(view) {
    this._activeView = view;
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
      item.classList.toggle('active', item.dataset.view === view);
    });
  },
};
