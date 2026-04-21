// WebSocket connection to the emulator server.
//
// Communication is one-directional: the client sends commands via
// the methods below, and the server pushes EmulatorState objects
// back.  Every command triggers a state response.  While the
// emulator is running, the server also pushes state continuously
// after each execution batch.
//
// All server responses are the same EmulatorState object — there
// are no other message types.

class Connection {
    constructor(url) {
        this.onStateReceived = null;  // called with EmulatorState on each server push
        this.onOpen = null;           // called when connected
        this.onClose = null;          // called when disconnected

        this._initWebSocket(url);
    }

    _initWebSocket(url) {
        this._ws = new WebSocket(url);

        this._ws.onmessage = (event) => {
            if (this.onStateReceived) {
                const state = EmulatorState.fromJSON(event.data);
                this.onStateReceived(state);
            }
        };

        this._ws.onopen = () => {
            if (this.onOpen) this.onOpen();
        };

        this._ws.onclose = () => {
            if (this.onClose) this.onClose();
        };
    }

    _send(action, extra) {
        const msg = Object.assign({action: action}, extra || {});
        this._ws.send(JSON.stringify(msg));
    }

    // Emulator control
    start()     { this._send('start'); }
    stop()      { this._send('stop'); }
    step()      { this._send('step'); }
    reset()     { this._send('reset'); }
    state()     { this._send('state'); }
    speed(val)  { this._send('speed', {value: val}); }

    // Faceplate button input
    buttonDown(buttonCode) {
        if (buttonCode.type === 'key') {
            this._send('key_down', {byte: buttonCode.upd_byte, mask: buttonCode.upd_mask});
        } else if (buttonCode.name === 'power') {
            this._send('power_key');
        }
    }

    buttonUp(buttonCode) {
        if (buttonCode.type === 'key') {
            this._send('key_up', {byte: buttonCode.upd_byte, mask: buttonCode.upd_mask});
        }
    }
}

// Hydrated from the JSON state object pushed by the server.
// All server responses use this same structure.
class EmulatorState {
    static fromJSON(json) {
        return new EmulatorState(JSON.parse(json));
    }

    constructor(data) {
        // Emulator status
        this.running = data.running;
        this.totalCycles = data.total_cycles;
        this.realMhz = data.real_mhz;
        this.potentialMhz = data.potential_mhz;

        // CPU registers
        this.pc = data.pc;
        this.sp = data.sp;
        this.ax = data.ax;
        this.bc = data.bc;
        this.de = data.de;
        this.hl = data.hl;
        this.psw = data.psw;
        this.rb = data.rb;

        // CPU flags
        this.ie = data.ie;
        this.isp = data.isp;
        this.z = data.z;
        this.ac = data.ac;
        this.cy = data.cy;

        // Disassembly and listing
        this.disasmHistory = data.disasm_history;
        this.disasmCurrent = data.disasm_current;
        this.listingSlice = data.listing_slice;

        // Faceplate hardware
        this.displayPixels = EmulatorState._decodeHex(data.display_pixels);
        this.activePictographs = EmulatorState._decodePictographs(data.pictogram_ram);
        this.led = data.led;
        this.t30 = data.t30;

        // Memory dumps
        this.expRam = data.exp_ram;
        this.hsRam = data.hs_ram;
        this.eeprom = data.eeprom;
    }

    static _decodeHex(hexStr) {
        const bytes = new Uint8Array(hexStr.length / 2);
        for (let i = 0; i < bytes.length; i++) {
            bytes[i] = parseInt(hexStr.slice(i * 2, i * 2 + 2), 16);
        }
        return bytes;
    }

    static _decodePictographs(hexStr) {
        if (!hexStr) return [];
        const ram = EmulatorState._decodeHex(hexStr);
        const active = [];
        for (const p of Pictograph.ALL) {
            if (p.isOn(ram)) active.push(p);
        }
        return active;
    }
}

// Identifies a faceplate button.  The Connection translates these
// into the appropriate server commands (uPD16432B key scan codes
// for most buttons, GPIO for power and stop/eject).
class ButtonCode {
    // uPD16432B key scan buttons
    static MID       = new ButtonCode('mid',       'key', {upd_byte: 1, upd_mask: 0x40});
    static BASS      = new ButtonCode('bass',      'key', {upd_byte: 1, upd_mask: 0x20});
    static TREB      = new ButtonCode('treb',      'key', {upd_byte: 1, upd_mask: 0x80});
    static FB        = new ButtonCode('fb',        'key', {upd_byte: 1, upd_mask: 0x10});
    static TAPE_SIDE = new ButtonCode('tape_side', 'key', {upd_byte: 1, upd_mask: 0x01});
    static SEEK_DOWN = new ButtonCode('seek_down', 'key', {upd_byte: 2, upd_mask: 0x20});
    static SEEK_UP   = new ButtonCode('seek_up',   'key', {upd_byte: 2, upd_mask: 0x40});
    static TUNE_DOWN = new ButtonCode('tune_down', 'key', {upd_byte: 3, upd_mask: 0x04});
    static TUNE_UP   = new ButtonCode('tune_up',   'key', {upd_byte: 3, upd_mask: 0x02});
    static SCAN      = new ButtonCode('scan',      'key', {upd_byte: 3, upd_mask: 0x08});
    static FM        = new ButtonCode('fm',        'key', {upd_byte: 2, upd_mask: 0x80});
    static CD        = new ButtonCode('cd',        'key', {upd_byte: 2, upd_mask: 0x08});
    static AM        = new ButtonCode('am',        'key', {upd_byte: 3, upd_mask: 0x80});
    static TAPE      = new ButtonCode('tape',      'key', {upd_byte: 1, upd_mask: 0x08});
    static PRESET_1  = new ButtonCode('preset_1',  'key', {upd_byte: 2, upd_mask: 0x04});
    static PRESET_2  = new ButtonCode('preset_2',  'key', {upd_byte: 2, upd_mask: 0x02});
    static PRESET_3  = new ButtonCode('preset_3',  'key', {upd_byte: 2, upd_mask: 0x01});
    static PRESET_4  = new ButtonCode('preset_4',  'key', {upd_byte: 3, upd_mask: 0x10});
    static PRESET_5  = new ButtonCode('preset_5',  'key', {upd_byte: 3, upd_mask: 0x20});
    static PRESET_6  = new ButtonCode('preset_6',  'key', {upd_byte: 3, upd_mask: 0x40});
    static MIX       = new ButtonCode('mix',       'key', {upd_byte: 3, upd_mask: 0x01});

    // GPIO buttons (directly wired, not scanned by uPD16432B)
    static POWER      = new ButtonCode('power',      'gpio');
    static STOP_EJECT = new ButtonCode('stop_eject', 'gpio');

    constructor(name, type, options = {}) {
        this.name = name;
        this.type = type;
        this.upd_byte = options.upd_byte;
        this.upd_mask = options.upd_mask;
    }
}

// Identifies a pictograph on the uPD16432B LCD.
// Each pictograph is a single bit in the pictograph RAM.
class Pictograph {
    static DOLBY  = new Pictograph('dolby',  1, 2);
    static METAL  = new Pictograph('metal',  2, 7);
    static MIX    = new Pictograph('mix',    5, 1);
    static PERIOD = new Pictograph('period', 4, 5);
    static ALL    = [Pictograph.DOLBY, Pictograph.METAL, Pictograph.MIX, Pictograph.PERIOD];

    constructor(name, upd_byte, upd_bit) {
        this.name = name;
        this.upd_byte = upd_byte;
        this.upd_bit = upd_bit;
    }

    isOn(pictogramRam) {
        return (pictogramRam[this.upd_byte] & (1 << this.upd_bit)) !== 0;
    }
}
