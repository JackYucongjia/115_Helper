/**
 * WebSocket client for real-time events.
 */
const WS = {
  _socket: null,
  _handlers: {},
  _reconnectTimer: null,
  _heartbeatTimer: null,
  connected: false,

  connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws`;

    try {
      this._socket = new WebSocket(url);
    } catch (e) {
      console.warn('WebSocket connection failed:', e);
      this._scheduleReconnect();
      return;
    }

    this._socket.onopen = () => {
      console.log('WS connected');
      this.connected = true;
      this._updateStatusDot(true);
      this._startHeartbeat();
    };

    this._socket.onclose = () => {
      console.log('WS disconnected');
      this.connected = false;
      this._updateStatusDot(false);
      this._stopHeartbeat();
      this._scheduleReconnect();
    };

    this._socket.onerror = (err) => {
      console.error('WS error:', err);
    };

    this._socket.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        const { event, data } = msg;
        if (this._handlers[event]) {
          this._handlers[event].forEach(fn => fn(data));
        }
      } catch (e) {
        // ignore non-JSON messages
      }
    };
  },

  on(event, handler) {
    if (!this._handlers[event]) this._handlers[event] = [];
    this._handlers[event].push(handler);
  },

  off(event, handler) {
    if (!this._handlers[event]) return;
    this._handlers[event] = this._handlers[event].filter(h => h !== handler);
  },

  _startHeartbeat() {
    this._heartbeatTimer = setInterval(() => {
      if (this._socket && this._socket.readyState === WebSocket.OPEN) {
        this._socket.send('ping');
      }
    }, 30000);
  },

  _stopHeartbeat() {
    clearInterval(this._heartbeatTimer);
  },

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => this.connect(), 3000);
  },

  _updateStatusDot(online) {
    const dot = document.getElementById('ws-status-dot');
    const text = document.getElementById('ws-status-text');
    if (dot) dot.classList.toggle('online', online);
    if (text) text.textContent = online ? '已连接' : '未连接';
  },
};
