document.addEventListener('DOMContentLoaded', function() {

const radioCanvas = document.getElementById('radio-canvas');
const radio = new Radio(radioCanvas);
radio._onReady = function() { redraw(); };
const dbg = new Debugger();

let lastState = null;
let highlightTimer = null;

function redraw() {
    if (lastState) radio.draw(lastState.displayPixels, lastState.led);
}

const conn = new Connection('ws://localhost:8765');
conn.onStateReceived = function(state) {
    lastState = state;
    radio.draw(state.displayPixels, state.led);
    dbg.update(state);
    controls.updateStatus(state);
};
conn.onOpen = function() {
    dbg.init();
    controls.stop();
};
conn.onClose = function() {
    controls.setDisconnected();
};

const controls = new Controls(conn);

new Input(radioCanvas, Radio.IMG_W, Radio.IMG_H,
    function onDown(r) {
        radio.setHighlight({x: r.x, y: r.y, w: r.w, h: r.h, alpha: 1.0});
        if (highlightTimer) { clearInterval(highlightTimer); highlightTimer = null; }
        redraw();

        if (r.name === 'power') {
            conn.powerKey();
        } else if (r.key) {
            conn.keyDown(r.key[0], r.key[1]);
        }
    },
    function onUp(r) {
        if (r.key) {
            conn.keyUp(r.key[0], r.key[1]);
        }

        let alpha = 1.0;
        if (highlightTimer) clearInterval(highlightTimer);
        highlightTimer = setInterval(function() {
            alpha -= 0.1;
            if (alpha <= 0) {
                radio.setHighlight(null);
                clearInterval(highlightTimer);
                highlightTimer = null;
            } else {
                radio.setHighlight({x: r.x, y: r.y, w: r.w, h: r.h, alpha: alpha});
            }
            redraw();
        }, 50);
    }
);

// Expose globals for inline onclick handlers in HTML
window.sendCmd = function(action) { controls[action](); };
window.toggleAnimate = function() { controls.toggleAnimate(); };
window.setAnimateSpeed = function(val) { controls.setAnimateSpeed(val); };
window.toggleExpand = function() { dbg.toggleExpand(); controls.state(); };
window.switchTab = function(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-bar button').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    event.target.classList.add('active');
};

}); // DOMContentLoaded
