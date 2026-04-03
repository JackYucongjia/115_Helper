/**
 * Directory restructure page component.
 */
const Restructure = {
  _blacklist: [],
  _previewData: null,

  async render(container) {
    // Load saved blacklist
    try {
      const cfg = await API.getBlacklist();
      this._blacklist = cfg.blacklist || [];
    } catch (e) {
      this._blacklist = [];
    }

    container.innerHTML = `
      <div class="card mb-16">
        <div class="card-header">
          <h3>🏗️ 扁平目录重构</h3>
        </div>
        <div class="card-body">
          <p style="color:var(--text-secondary);margin-bottom:16px;font-size:13px">
            将扁平堆放的大量视频文件，自动按清洗后的文件名创建独立子目录并归集。
            适用于合集打包目录（如 DMM 原档、P2P 下载等）。
          </p>

          <!-- Source dir -->
          <div class="form-group">
            <label class="form-label">源目录</label>
            <div class="flex gap-8 items-center">
              <input class="form-input" id="rst-dir-input" placeholder="点击选择要重构的目录…" readonly style="cursor:pointer;flex:1" />
              <input type="hidden" id="rst-dir-id" />
            </div>
          </div>

          <!-- Blacklist -->
          <div class="form-group">
            <label class="form-label">文件名黑名单 (正则表达式)</label>
            <div class="tag-input-wrapper" id="rst-tag-wrapper">
              <input class="tag-input" id="rst-tag-input" placeholder="输入正则后按回车添加…" />
            </div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
              清洗引擎将按顺序应用这些规则移除文件名中的噪点字符
            </div>
          </div>

          <div class="flex gap-8">
            <button class="btn btn-secondary" id="rst-preview-btn">👁️ 预览结果</button>
            <button class="btn btn-primary" id="rst-execute-btn" disabled>🚀 执行重构</button>
            <button class="btn btn-secondary btn-sm" id="rst-save-bl-btn" style="margin-left:auto">💾 保存黑名单</button>
          </div>

          <div id="rst-progress" style="margin-top:12px;display:none">
            <div class="progress-bar"><div class="progress-bar-fill" id="rst-progress-fill" style="width:0%"></div></div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:4px" id="rst-progress-text"></div>
          </div>
        </div>
      </div>

      <!-- Preview -->
      <div class="card" id="rst-preview-card" style="display:none">
        <div class="card-header">
          <h3>📋 预览 <span class="badge badge-info" id="rst-preview-badge"></span></h3>
        </div>
        <div style="overflow-x:auto">
          <table class="data-table">
            <thead>
              <tr>
                <th>原始文件名</th>
                <th>→</th>
                <th>目标目录名</th>
              </tr>
            </thead>
            <tbody id="rst-preview-body"></tbody>
          </table>
        </div>
      </div>
    `;

    this._renderTags();
    this._bindEvents();
  },

  _renderTags() {
    const wrapper = document.getElementById('rst-tag-wrapper');
    if (!wrapper) return;

    // Remove existing tags
    wrapper.querySelectorAll('.tag').forEach(t => t.remove());

    const input = document.getElementById('rst-tag-input');
    this._blacklist.forEach((pattern, idx) => {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.innerHTML = `${Helpers.escapeHtml(pattern)} <span class="tag-close" data-idx="${idx}">×</span>`;
      wrapper.insertBefore(tag, input);
    });

    // Re-bind remove handlers
    wrapper.querySelectorAll('.tag-close').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.idx);
        this._blacklist.splice(idx, 1);
        this._renderTags();
      });
    });
  },

  _bindEvents() {
    // Dir picker
    document.getElementById('rst-dir-input')?.addEventListener('click', async () => {
      try {
        const { cid, name } = await FileBrowser.openSelectModal();
        document.getElementById('rst-dir-input').value = name;
        document.getElementById('rst-dir-id').value = cid;
      } catch (e) { /* cancelled */ }
    });

    // Tag input
    document.getElementById('rst-tag-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.value.trim()) {
        e.preventDefault();
        this._blacklist.push(e.target.value.trim());
        e.target.value = '';
        this._renderTags();
      }
    });

    // Click on wrapper focuses input
    document.getElementById('rst-tag-wrapper')?.addEventListener('click', () => {
      document.getElementById('rst-tag-input')?.focus();
    });

    // Preview
    document.getElementById('rst-preview-btn')?.addEventListener('click', () => this._doPreview());

    // Execute
    document.getElementById('rst-execute-btn')?.addEventListener('click', () => this._doExecute());

    // Save blacklist
    document.getElementById('rst-save-bl-btn')?.addEventListener('click', async () => {
      try {
        await API.updateBlacklist(this._blacklist);
        Toast.success('黑名单已保存');
      } catch (e) {
        Toast.error(`保存失败: ${e.message}`);
      }
    });

    // WS progress
    WS.on('task_progress', (data) => {
      const fill = document.getElementById('rst-progress-fill');
      const text = document.getElementById('rst-progress-text');
      if (fill && data.total > 0) {
        fill.style.width = `${(data.current / data.total) * 100}%`;
      } else if (fill) {
        fill.style.width = `${data.current}%`;
      }
      if (text) text.textContent = data.message || '';
    });
  },

  async _doPreview() {
    const dirId = document.getElementById('rst-dir-id')?.value;
    if (!dirId) { Toast.warning('请先选择源目录'); return; }

    const btn = document.getElementById('rst-preview-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div> 预览中…'; }

    try {
      const data = await API.previewRestructure(dirId, this._blacklist);
      this._previewData = data;
      this._renderPreview(data);
      document.getElementById('rst-execute-btn').disabled = false;
      Toast.success(`预览完成: ${data.items?.length || 0} 个文件将被归集到 ${data.new_dirs_count || 0} 个目录`);
    } catch (e) {
      Toast.error(`预览失败: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '👁️ 预览结果'; }
    }
  },

  _renderPreview(data) {
    const card = document.getElementById('rst-preview-card');
    const badge = document.getElementById('rst-preview-badge');
    const tbody = document.getElementById('rst-preview-body');

    if (card) card.style.display = 'block';
    if (badge) badge.textContent = `${data.items?.length || 0} 个文件 → ${data.new_dirs_count || 0} 个目录`;

    if (!tbody) return;
    tbody.innerHTML = '';

    (data.items || []).forEach(item => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td title="${Helpers.escapeHtml(item.original_name)}">
          <span style="color:var(--text-secondary)">${Helpers.escapeHtml(Helpers.truncate(item.original_name, 60))}</span>
        </td>
        <td style="color:var(--accent-1);font-size:16px;text-align:center">→</td>
        <td>
          <span style="color:var(--success);font-weight:500">${Helpers.escapeHtml(item.cleaned_name)}</span>/
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  async _doExecute() {
    const dirId = document.getElementById('rst-dir-id')?.value;
    if (!dirId) { Toast.warning('请先选择源目录'); return; }

    if (!confirm('确认执行目录重构？此操作将在 115 云端创建子目录并移动文件。')) return;

    const btn = document.getElementById('rst-execute-btn');
    const progress = document.getElementById('rst-progress');
    if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div> 执行中…'; }
    if (progress) progress.style.display = 'block';

    try {
      const result = await API.executeRestructure(dirId, this._blacklist);
      if (result.errors && result.errors.length > 0) {
        Toast.warning(`重构部分完成: ${result.moved}/${result.total} 个文件已归集`);
      } else {
        Toast.success(`重构完成: ${result.moved} 个文件已归集到 ${result.dirs_created} 个目录`);
      }
    } catch (e) {
      Toast.error(`执行失败: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '🚀 执行重构'; }
      if (progress) setTimeout(() => { progress.style.display = 'none'; }, 2000);
    }
  },
};
