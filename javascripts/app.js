window.onload = function() {

const faceplateImg = document.querySelector('.faceplate-img');
const faceplateCanvas = document.getElementById('faceplate-canvas');
const faceplate = new Faceplate(faceplateImg, faceplateCanvas);

const dbg = new Debugger();

const conn = new Connection('ws://localhost:8765');
conn.onStateReceived = function(state) {
    faceplate.characterMatrix.draw(state.displayPixels);
    faceplate.drawPictographs(state.activePictographs);
    faceplate.alarmLED.draw(state.led);
    if (state.running) { faceplate.enable(); } else { faceplate.disable(); }
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
faceplate.onButtonDown = function(buttonCode) { conn.buttonDown(buttonCode); };
faceplate.onButtonUp = function(buttonCode) { conn.buttonUp(buttonCode); };

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

}; // window.onload
