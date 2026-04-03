/**
 * Utility helpers
 */
const Helpers = {
  /**
   * Format bytes to human-readable string.
   */
  formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
  },

  /**
   * Escape HTML to prevent XSS.
   */
  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  /**
   * Truncate string with ellipsis.
   */
  truncate(str, maxLen = 60) {
    if (!str || str.length <= maxLen) return str;
    return str.slice(0, maxLen - 3) + '…';
  },

  /**
   * Debounce function calls.
   */
  debounce(fn, ms = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(null, args), ms);
    };
  },

  /**
   * Get icon for file type.
   */
  getFileIcon(name, isDir) {
    if (isDir) return '📁';
    const ext = (name.split('.').pop() || '').toLowerCase();
    const icons = {
      iso: '💿', mkv: '🎬', mp4: '🎬', ts: '🎬', avi: '🎬',
      rmvb: '🎬', wmv: '🎬', flv: '🎬', mov: '🎬', m4v: '🎬',
      nfo: '📋', jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️',
      srt: '📝', ass: '📝', ssa: '📝', sub: '📝',
      txt: '📄', pdf: '📄', doc: '📄',
      zip: '📦', rar: '📦', '7z': '📦',
      torrent: '🧲',
    };
    return icons[ext] || '📄';
  },

  /**
   * Create element with attributes and children.
   */
  el(tag, attrs = {}, ...children) {
    const element = document.createElement(tag);
    for (const [key, val] of Object.entries(attrs)) {
      if (key === 'className') element.className = val;
      else if (key === 'innerHTML') element.innerHTML = val;
      else if (key.startsWith('on')) element.addEventListener(key.slice(2).toLowerCase(), val);
      else element.setAttribute(key, val);
    }
    for (const child of children) {
      if (typeof child === 'string') element.appendChild(document.createTextNode(child));
      else if (child) element.appendChild(child);
    }
    return element;
  },
};
