window.onload = function() {

const faceplateImg = document.querySelector('.faceplate-img');
const faceplateCanvas = document.getElementById('faceplate-canvas');
const faceplate = new Faceplate(faceplateImg, faceplateCanvas);

const registersView = new RegistersView(document.getElementById('registers-view'));
const disasmView = new DisassemblyView(document.getElementById('disasm-listing'));
const listingView = new ListingView(document.getElementById('listing-view'));
const ramHs = new MemoryView(document.getElementById('mem-hs-ram'), 992, 0xFB00, 'hsRam');
const ramExp = new MemoryView(document.getElementById('mem-exp-ram'), 2048, 0xF000, 'expRam');
const eeprom = new MemoryView(document.getElementById('mem-eeprom'), 512, 0x0000, 'eeprom');
const statisticsView = new StatisticsView(document.getElementById('statistics-view'));

const conn = new Connection('ws://localhost:8765');
conn.onStateReceived = function(state) {
    faceplate.characterMatrix.draw(state.displayPixels);
    faceplate.drawPictographs(state.activePictographs);
    faceplate.alarmLED.draw(state.led);
    if (state.running) { faceplate.enable(); } else { faceplate.disable(); }
    registersView.update(state);
    disasmView.update(state);
    listingView.update(state);
    ramHs.update(state);
    ramExp.update(state);
    eeprom.update(state);
    statisticsView.update(state);
    controls.updateStatus(state);
};
conn.onOpen = function() {
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
window.sendMFSW = function(code) { conn.mfsw(code); };
window.toggleAnimate = function() { controls.toggleAnimate(); };
window.setAnimateSpeed = function(val) { controls.setAnimateSpeed(val); };
window.toggleExpand = function() {
    const left = document.getElementById('panel-left');
    const row = document.querySelector('.info-row');
    const btn = document.getElementById('expand-btn');
    const disasmEl = document.getElementById('disasm-listing');
    const listingEl = document.getElementById('listing-view');
    const heading = document.querySelector('#panel-instructions h2');
    const expanded = listingEl.style.display === 'block';
    if (!expanded) {
        left.style.display = 'none';
        row.style.gridTemplateColumns = '1fr';
        btn.textContent = '[-]';
        disasmEl.style.display = 'none';
        listingEl.style.display = 'block';
        heading.textContent = 'Listing';
    } else {
        left.style.display = '';
        row.style.gridTemplateColumns = '3fr 2fr';
        btn.textContent = '[+]';
        disasmEl.style.display = '';
        listingEl.style.display = 'none';
        heading.textContent = 'Instructions';
    }
    controls.state();
};
window.switchTab = function(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-bar button').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    event.target.classList.add('active');
};

}; // window.onload
