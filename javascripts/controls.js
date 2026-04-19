function createControls(conn) {
    let isRunning = false;
    let animateTimer = null;
    let animateMs = 200;

    function send(action) {
        if ((action === 'start' || action === 'step') && animateTimer) {
            stopAnimate();
        }
        if (action === 'stop' && animateTimer) {
            stopAnimate();
        }
        if (action === 'step' && isRunning) {
            conn.send('stop');
        }
        conn.send(action);
    }

    function startAnimate() {
        if (animateTimer) clearInterval(animateTimer);
        animateTimer = setInterval(() => conn.send('step'), animateMs);
    }

    function stopAnimate() {
        if (animateTimer) {
            clearInterval(animateTimer);
            animateTimer = null;
        }
        document.getElementById('btn-animate').style.borderColor = '';
        document.getElementById('animate-speed').style.display = 'none';
    }

    function toggleAnimate() {
        if (animateTimer) return;
        if (isRunning) conn.send('stop');
        startAnimate();
        document.getElementById('btn-animate').style.borderColor = '#2a2';
        document.getElementById('animate-speed').style.display = '';
    }

    function setAnimateSpeed(val) {
        animateMs = parseInt(val);
        document.getElementById('speed-label').textContent = animateMs + 'ms';
        if (animateTimer) startAnimate();
    }

    function updateStatus(state) {
        isRunning = state.running;
        document.getElementById('btn-start').disabled = isRunning;
        document.getElementById('btn-stop').disabled = false;
        document.getElementById('btn-step').disabled = false;
        const statusEl = document.getElementById('status');
        const statusText = isRunning ? 'RUNNING' : (animateTimer ? 'ANIMATE' : 'STOPPED');
        const statusClass = (isRunning || animateTimer) ? 'status-running' : 'status-stopped';
        statusEl.textContent = statusText;
        statusEl.className = 'status-text ' + statusClass;
    }

    function setDisconnected() {
        document.getElementById('status').textContent = 'DISCONNECTED';
        document.getElementById('status').className = 'status-text status-stopped';
    }

    return {
        send: send,
        toggleAnimate: toggleAnimate,
        setAnimateSpeed: setAnimateSpeed,
        updateStatus: updateStatus,
        setDisconnected: setDisconnected,
    };
}
