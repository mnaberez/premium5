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

    // Radio input
    powerKey()  { this._send('power_key'); }
    keyDown(byte, mask) { this._send('key_down', {byte: byte, mask: mask}); }
    keyUp(byte, mask)   { this._send('key_up', {byte: byte, mask: mask}); }
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

        // Disassembly
        this.disasmHistory = data.disasm_history;
        this.disasmCurrent = data.disasm_current;

        // Radio hardware
        this.displayPixels = data.display_pixels;
        this.led = data.led;
        this.t30 = data.t30;

        // RAM dumps
        this.expRam = data.exp_ram;
        this.hsRam = data.hs_ram;
    }
}
