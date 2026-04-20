document.addEventListener('DOMContentLoaded', function() {

const faceplateCanvas = document.getElementById('faceplate-canvas');
const faceplate = new Faceplate(faceplateCanvas);
const dbg = new Debugger();

let lastState = null;

function redraw() {
    if (lastState) {
        faceplate.draw(lastState.displayPixels, lastState.led);
        input.drawButtons();
    }
}

faceplate._onReady = redraw;
faceplate._onRedraw = redraw;

const conn = new Connection('ws://localhost:8765');
conn.onStateReceived = function(state) {
    lastState = state;
    redraw();
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
const input = new Input(faceplateCanvas, faceplate, conn);

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
