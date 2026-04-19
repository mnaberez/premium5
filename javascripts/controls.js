class Controls {
    constructor(conn) {
        this._conn = conn;
        this._isRunning = false;
        this._animateTimer = null;
        this._animateMs = 200;
    }

    send(action) {
        if ((action === 'start' || action === 'step') && this._animateTimer) {
            this._stopAnimate();
        }
        if (action === 'stop' && this._animateTimer) {
            this._stopAnimate();
        }
        if (action === 'step' && this._isRunning) {
            this._conn.send('stop');
        }
        this._conn.send(action);
    }

    toggleAnimate() {
        if (this._animateTimer) return;
        if (this._isRunning) this._conn.send('stop');
        this._startAnimate();
        document.getElementById('btn-animate').style.borderColor = '#2a2';
        document.getElementById('animate-speed').style.display = '';
    }

    setAnimateSpeed(val) {
        this._animateMs = parseInt(val);
        document.getElementById('speed-label').textContent = this._animateMs + 'ms';
        if (this._animateTimer) this._startAnimate();
    }

    updateStatus(state) {
        this._isRunning = state.running;
        document.getElementById('btn-start').disabled = this._isRunning;
        document.getElementById('btn-stop').disabled = false;
        document.getElementById('btn-step').disabled = false;
        const statusEl = document.getElementById('status');
        const statusText = this._isRunning ? 'RUNNING' : (this._animateTimer ? 'ANIMATE' : 'STOPPED');
        const statusClass = (this._isRunning || this._animateTimer) ? 'status-running' : 'status-stopped';
        statusEl.textContent = statusText;
        statusEl.className = 'status-text ' + statusClass;
    }

    setDisconnected() {
        document.getElementById('status').textContent = 'DISCONNECTED';
        document.getElementById('status').className = 'status-text status-stopped';
    }

    _startAnimate() {
        if (this._animateTimer) clearInterval(this._animateTimer);
        this._animateTimer = setInterval(() => this._conn.send('step'), this._animateMs);
    }

    _stopAnimate() {
        if (this._animateTimer) {
            clearInterval(this._animateTimer);
            this._animateTimer = null;
        }
        document.getElementById('btn-animate').style.borderColor = '';
        document.getElementById('animate-speed').style.display = 'none';
    }
}
