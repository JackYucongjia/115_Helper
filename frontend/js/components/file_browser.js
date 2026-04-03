/**
 * File browser component.
 */
const FileBrowser = {
  _currentCid: '0',
  _pathStack: [{ cid: '0', name: '根目录' }],
  _files: [],
  _selectMode: false,
  _onSelect: null,  // callback when selecting a directory

  async render(container) {
    container.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h3>📂 文件浏览器</h3>
          <div id="fb-actions"></div>
        </div>
        <div class="card-body" style="padding:0">
          <div class="breadcrumb" id="fb-breadcrumb" style="padding:10px 22px"></div>
          <div id="fb-file-list" style="padding:0 10px 10px"></div>
        </div>
      </div>
    `;
    await this.loadDir('0');
  },

  /**
   * Open file browser in directory-select mode (modal).
   * Returns promise that resolves with {cid, name}.
   */
  openSelectModal() {
    return new Promise((resolve, reject) => {
      const overlay = Helpers.el('div', { className: 'modal-overlay' });
      const modal = Helpers.el('div', { className: 'modal', style: 'max-width:600px' });

      modal.innerHTML = `
        <div class="modal-header">
          <h3>📁 选择目标目录</h3>
          <div class="modal-close" id="fb-modal-close">✕</div>
        </div>
        <div class="modal-body" style="padding:0;max-height:400px;overflow-y:auto">
          <div class="breadcrumb" id="fbm-breadcrumb" style="padding:10px 22px"></div>
          <div id="fbm-file-list" style="padding:0 10px 10px"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" id="fbm-cancel">取消</button>
          <button class="btn btn-primary" id="fbm-confirm">选择此目录</button>
        </div>
      `;

      overlay.appendChild(modal);
      document.body.appendChild(overlay);

      let mCid = '0';
      let mName = '根目录';
      let mStack = [{ cid: '0', name: '根目录' }];

      const loadModalDir = async (cid) => {
        mCid = cid;
        const bcEl = document.getElementById('fbm-breadcrumb');
        const listEl = document.getElementById('fbm-file-list');
        if (!bcEl || !listEl) return;

        listEl.innerHTML = '<div class="text-center" style="padding:20px"><div class="spinner" style="margin:auto"></div></div>';

        try {
          const data = await API.listFiles(cid);
          const dirs = (data.files || []).filter(f => f.is_dir);

          // Breadcrumb
          bcEl.innerHTML = mStack.map((p, i) =>
            `<span class="breadcrumb-item" data-cid="${p.cid}">${Helpers.escapeHtml(p.name)}</span>` +
            (i < mStack.length - 1 ? '<span class="breadcrumb-sep">›</span>' : '')
          ).join('');

          bcEl.querySelectorAll('.breadcrumb-item').forEach(el => {
            el.addEventListener('click', () => {
              const idx = mStack.findIndex(p => p.cid === el.dataset.cid);
              if (idx >= 0) {
                mStack = mStack.slice(0, idx + 1);
                mName = mStack[mStack.length - 1].name;
                loadModalDir(el.dataset.cid);
              }
            });
          });

          // File list (dirs only)
          if (dirs.length === 0) {
            listEl.innerHTML = '<div class="empty-state" style="padding:30px"><div class="empty-state-text">此目录下没有子目录</div></div>';
            return;
          }

          listEl.innerHTML = '';
          dirs.forEach(f => {
            const item = Helpers.el('div', { className: 'file-item' });
            item.innerHTML = `
              <span class="file-icon">📁</span>
              <span class="file-name">${Helpers.escapeHtml(f.name)}</span>
            `;
            item.addEventListener('click', () => {
              mStack.push({ cid: f.file_id, name: f.name });
              mName = f.name;
              loadModalDir(f.file_id);
            });
            listEl.appendChild(item);
          });

        } catch (e) {
          listEl.innerHTML = `<div class="empty-state" style="padding:30px"><div class="empty-state-text" style="color:var(--error)">加载失败: ${Helpers.escapeHtml(e.message)}</div></div>`;
        }
      };

      loadModalDir('0');

      document.getElementById('fbm-cancel').onclick = () => { overlay.remove(); reject(new Error('cancelled')); };
      document.getElementById('fb-modal-close').onclick = () => { overlay.remove(); reject(new Error('cancelled')); };
      overlay.addEventListener('click', (e) => { if (e.target === overlay) { overlay.remove(); reject(new Error('cancelled')); } });
      document.getElementById('fbm-confirm').onclick = () => { overlay.remove(); resolve({ cid: mCid, name: mName }); };
    });
  },

  async loadDir(cid) {
    this._currentCid = cid;
    const bcEl = document.getElementById('fb-breadcrumb');
    const listEl = document.getElementById('fb-file-list');
    if (!bcEl || !listEl) return;

    listEl.innerHTML = '<div class="text-center" style="padding:40px"><div class="spinner spinner-lg" style="margin:auto"></div></div>';

    try {
      const data = await API.listFiles(cid);
      this._files = data.files || [];

      // Update path stack
      if (cid === '0') {
        this._pathStack = [{ cid: '0', name: '根目录' }];
      }

      // Breadcrumb
      bcEl.innerHTML = this._pathStack.map((p, i) =>
        `<span class="breadcrumb-item" data-cid="${p.cid}">${Helpers.escapeHtml(p.name)}</span>` +
        (i < this._pathStack.length - 1 ? '<span class="breadcrumb-sep">›</span>' : '')
      ).join('');

      bcEl.querySelectorAll('.breadcrumb-item').forEach(el => {
        el.addEventListener('click', () => {
          const idx = this._pathStack.findIndex(p => p.cid === el.dataset.cid);
          if (idx >= 0) {
            this._pathStack = this._pathStack.slice(0, idx + 1);
            this.loadDir(el.dataset.cid);
          }
        });
      });

      // File list
      if (this._files.length === 0) {
        listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">此目录为空</div></div>';
        return;
      }

      listEl.innerHTML = '';
      this._files.forEach(f => {
        const item = Helpers.el('div', { className: 'file-item' });
        item.innerHTML = `
          <span class="file-icon">${Helpers.getFileIcon(f.name, f.is_dir)}</span>
          <span class="file-name" title="${Helpers.escapeHtml(f.name)}">${Helpers.escapeHtml(f.name)}</span>
          <span class="file-size">${f.is_dir ? '' : Helpers.formatSize(f.size)}</span>
        `;
        if (f.is_dir) {
          item.addEventListener('click', () => {
            this._pathStack.push({ cid: f.file_id, name: f.name });
            this.loadDir(f.file_id);
          });
        }
        listEl.appendChild(item);
      });

    } catch (e) {
      listEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">❌</div><div class="empty-state-text" style="color:var(--error)">加载失败: ${Helpers.escapeHtml(e.message)}</div></div>`;
    }
  },
};
