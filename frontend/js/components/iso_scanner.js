/**
 * ISO Scanner page component.
 */
const ISOScanner = {
  _results: [],
  _selectedIds: new Set(),
  _scanning: false,

  async render(container) {
    container.innerHTML = `
      <div class="card mb-16">
        <div class="card-header">
          <h3>💿 ISO 文件探测器</h3>
        </div>
        <div class="card-body">
          <p style="color:var(--text-secondary);margin-bottom:16px;font-size:13px">
            递归扫描指定目录下的所有 ISO 文件，自动识别电影/剧集拓扑结构，检测多版本碰撞状态。
          </p>
          <div class="flex gap-8 items-center">
            <div style="flex:1;position:relative">
              <input class="form-input" id="iso-dir-input" placeholder="点击选择要扫描的目录…" readonly style="cursor:pointer" />
              <input type="hidden" id="iso-dir-id" />
            </div>
            <button class="btn btn-primary" id="iso-scan-btn">
              <span>🔍</span> 开始扫描
            </button>
          </div>
          <div id="iso-progress" style="margin-top:12px;display:none">
            <div class="progress-bar"><div class="progress-bar-fill" id="iso-progress-fill" style="width:0%"></div></div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:4px" id="iso-progress-text">正在扫描…</div>
          </div>
        </div>
      </div>

      <!-- Results -->
      <div class="card" id="iso-results-card" style="display:none">
        <div class="card-header">
          <h3>📋 扫描结果 <span class="badge badge-info" id="iso-count-badge">0</span></h3>
          <div class="flex gap-8">
            <button class="btn btn-secondary btn-sm" id="iso-select-all">全选</button>
            <button class="btn btn-primary btn-sm" id="iso-copy-btn" disabled>📋 复制</button>
            <button class="btn btn-secondary btn-sm" id="iso-move-btn" disabled>📦 移动</button>
            <button class="btn btn-danger btn-sm" id="iso-delete-btn" disabled>🗑️ 删除</button>
          </div>
        </div>
        <div style="overflow-x:auto">
          <table class="data-table" id="iso-results-table">
            <thead>
              <tr>
                <th style="width:40px"><input type="checkbox" id="iso-check-all" /></th>
                <th>文件名</th>
                <th>大小</th>
                <th>类型</th>
                <th>碰撞状态</th>
                <th>同级视频</th>
                <th>归属根节点</th>
              </tr>
            </thead>
            <tbody id="iso-results-body"></tbody>
          </table>
        </div>
        <div class="card-body" id="iso-summary" style="border-top:1px solid var(--border-subtle);padding:14px 22px">
        </div>
      </div>
    `;

    this._bindEvents();
  },

  _bindEvents() {
    // Dir picker
    document.getElementById('iso-dir-input')?.addEventListener('click', async () => {
      try {
        const { cid, name } = await FileBrowser.openSelectModal();
        document.getElementById('iso-dir-input').value = name;
        document.getElementById('iso-dir-id').value = cid;
      } catch (e) { /* cancelled */ }
    });

    // Scan button
    document.getElementById('iso-scan-btn')?.addEventListener('click', () => this._startScan());

    // Select all
    document.getElementById('iso-check-all')?.addEventListener('change', (e) => {
      const checked = e.target.checked;
      this._results.forEach(r => {
        if (checked) this._selectedIds.add(r.file_id);
        else this._selectedIds.delete(r.file_id);
      });
      this._updateCheckboxes();
      this._updateActionButtons();
    });

    document.getElementById('iso-select-all')?.addEventListener('click', () => {
      const allSelected = this._selectedIds.size === this._results.length;
      this._results.forEach(r => {
        if (allSelected) this._selectedIds.delete(r.file_id);
        else this._selectedIds.add(r.file_id);
      });
      this._updateCheckboxes();
      this._updateActionButtons();
    });

    // Action buttons
    document.getElementById('iso-copy-btn')?.addEventListener('click', () => this._processAction('copy'));
    document.getElementById('iso-move-btn')?.addEventListener('click', () => this._processAction('move'));
    document.getElementById('iso-delete-btn')?.addEventListener('click', () => this._processAction('delete'));

    // WS progress listener
    WS.on('task_progress', (data) => {
      const fill = document.getElementById('iso-progress-fill');
      const text = document.getElementById('iso-progress-text');
      if (fill && data.total > 0) {
        fill.style.width = `${(data.current / data.total) * 100}%`;
      }
      if (text) text.textContent = data.message || '';
    });
  },

  async _startScan() {
    const dirId = document.getElementById('iso-dir-id')?.value;
    if (!dirId) {
      Toast.warning('请先选择要扫描的目录');
      return;
    }

    this._scanning = true;
    this._results = [];
    this._selectedIds.clear();

    const btn = document.getElementById('iso-scan-btn');
    const progress = document.getElementById('iso-progress');
    if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div> 扫描中…'; }
    if (progress) progress.style.display = 'block';

    try {
      const data = await API.scanISO(dirId);
      this._results = data.iso_files || [];
      this._renderResults(data);
      Toast.success(`扫描完成，发现 ${this._results.length} 个 ISO 文件`);
    } catch (e) {
      Toast.error(`扫描失败: ${e.message}`);
    } finally {
      this._scanning = false;
      if (btn) { btn.disabled = false; btn.innerHTML = '<span>🔍</span> 开始扫描'; }
      if (progress) progress.style.display = 'none';
    }
  },

  _renderResults(data) {
    const card = document.getElementById('iso-results-card');
    const tbody = document.getElementById('iso-results-body');
    const badge = document.getElementById('iso-count-badge');
    const summary = document.getElementById('iso-summary');

    if (card) card.style.display = 'block';
    if (badge) badge.textContent = `${data.total_count} 个`;
    if (summary) {
      summary.innerHTML = `
        <span style="color:var(--text-muted);font-size:12px">
          总计: ${data.total_count} 个 ISO 文件 · 总大小: ${Helpers.formatSize(data.total_size)}
        </span>
      `;
    }

    if (!tbody) return;
    tbody.innerHTML = '';

    this._results.forEach(r => {
      const tr = document.createElement('tr');
      const collisionBadge = r.collision === 'collision'
        ? '<span class="badge badge-warning">⚠ 碰撞</span>'
        : '<span class="badge badge-success">✓ 无碰撞</span>';
      const typeBadge = r.topology === 'movie'
        ? '<span class="badge badge-info">🎬 电影</span>'
        : '<span class="badge badge-info">📺 剧集</span>';

      tr.innerHTML = `
        <td><input type="checkbox" data-fid="${r.file_id}" class="iso-checkbox" /></td>
        <td title="${Helpers.escapeHtml(r.full_path)}">
          <div style="font-weight:500;color:var(--text-primary)">${Helpers.escapeHtml(r.name)}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px">${Helpers.escapeHtml(Helpers.truncate(r.full_path, 80))}</div>
        </td>
        <td>${Helpers.formatSize(r.size)}</td>
        <td>${typeBadge}</td>
        <td>${collisionBadge}</td>
        <td style="font-size:12px">${r.sibling_videos.length > 0 ? r.sibling_videos.map(v => Helpers.escapeHtml(Helpers.truncate(v, 30))).join('<br>') : '—'}</td>
        <td style="font-size:12px">${Helpers.escapeHtml(Helpers.truncate(r.root_node_name, 40))}</td>
      `;

      const cb = tr.querySelector('.iso-checkbox');
      cb.addEventListener('change', () => {
        if (cb.checked) this._selectedIds.add(r.file_id);
        else this._selectedIds.delete(r.file_id);
        this._updateActionButtons();
      });

      tbody.appendChild(tr);
    });
  },

  _updateCheckboxes() {
    document.querySelectorAll('.iso-checkbox').forEach(cb => {
      cb.checked = this._selectedIds.has(cb.dataset.fid);
    });
    const checkAll = document.getElementById('iso-check-all');
    if (checkAll) checkAll.checked = this._selectedIds.size === this._results.length && this._results.length > 0;
  },

  _updateActionButtons() {
    const hasSelection = this._selectedIds.size > 0;
    ['iso-copy-btn', 'iso-move-btn', 'iso-delete-btn'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = !hasSelection;
    });
  },

  async _processAction(action) {
    if (this._selectedIds.size === 0) return;

    let targetDirId = null;

    if (action !== 'delete') {
      try {
        const { cid } = await FileBrowser.openSelectModal();
        targetDirId = cid;
      } catch (e) { return; /* cancelled */ }
    } else {
      if (!confirm(`确定要删除选中的 ${this._selectedIds.size} 个 ISO 文件及其专属资产吗？此操作不可逆！`)) return;
    }

    const actionLabels = { copy: '复制', move: '移动', delete: '删除' };

    try {
      Toast.info(`正在${actionLabels[action]}…`);
      const result = await API.processISO(action, Array.from(this._selectedIds), targetDirId);
      if (result.errors && result.errors.length > 0) {
        Toast.warning(`${actionLabels[action]}部分完成: ${result.success}/${result.total} 成功`);
      } else {
        Toast.success(`${actionLabels[action]}完成: ${result.success} 个文件`);
      }
    } catch (e) {
      Toast.error(`${actionLabels[action]}失败: ${e.message}`);
    }
  },
};
