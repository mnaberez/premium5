class Input {
    // uPD16432B pictograph RAM: {name, byte, bit}
    static PICTOGRAPHS = [
        {name: 'mix',         byte: 5, bit: 1},
        {name: 'period',      byte: 4, bit: 5},
        {name: 'tape_metal',  byte: 2, bit: 7},
        {name: 'tape_dolby',  byte: 1, bit: 2},
    ];

    static HIT_REGIONS = [
        // uPD16432B key scan buttons: [byte_index, bit_mask]
        {name: 'mid',        x: 17,  y: 18,  w: 60,  h: 64,  key: [1, 0x40]},
        {name: 'bass',       x: 17,  y: 89,  w: 60,  h: 66,  key: [1, 0x20]},
        {name: 'treb',       x: 165, y: 18,  w: 64,  h: 64,  key: [1, 0x80]},
        {name: 'fb',         x: 165, y: 89,  w: 64,  h: 66,  key: [1, 0x10]},
        {name: 'tape_side',  x: 312, y: 45,  w: 68,  h: 69,  key: [1, 0x01]},
        {name: 'seek_down',  x: 64,  y: 165, w: 75,  h: 62,  key: [2, 0x20]},
        {name: 'seek_up',    x: 147, y: 165, w: 81,  h: 62,  key: [2, 0x40]},
        {name: 'tune_down',  x: 759, y: 165, w: 79,  h: 63,  key: [3, 0x04]},
        {name: 'tune_up',    x: 843, y: 165, w: 79,  h: 63,  key: [3, 0x02]},
        {name: 'scan',       x: 818, y: 40,  w: 92,  h: 92,  key: [3, 0x08]},
        {name: 'fm',         x: 759, y: 21,  w: 58,  h: 64,  key: [2, 0x80]},
        {name: 'cd',         x: 759, y: 91,  w: 58,  h: 66,  key: [2, 0x08]},
        {name: 'am',         x: 913, y: 21,  w: 62,  h: 63,  key: [3, 0x80]},
        {name: 'tape',       x: 913, y: 90,  w: 62,  h: 66,  key: [1, 0x08]},
        {name: 'preset_1',   x: 143, y: 245, w: 112, h: 51,  key: [2, 0x04]},
        {name: 'preset_2',   x: 264, y: 245, w: 111, h: 51,  key: [2, 0x02]},
        {name: 'preset_3',   x: 381, y: 245, w: 111, h: 51,  key: [2, 0x01]},
        {name: 'preset_4',   x: 497, y: 245, w: 111, h: 51,  key: [3, 0x10]},
        {name: 'preset_5',   x: 612, y: 245, w: 111, h: 51,  key: [3, 0x20]},
        {name: 'preset_6',   x: 728, y: 245, w: 112, h: 51,  key: [3, 0x40]},
        {name: 'mix',        x: 898, y: 245, w: 75,  h: 51,  key: [3, 0x01]},
        // Non-uPD16432B controls (directly wired to GPIO or not buttons)
        {name: 'power',      x: 14,  y: 245, w: 77,  h: 51},
        // {name: 'stop_eject', x: 241, y: 45,  w: 68,  h: 69},
        // {name: 'volume',     x: 79,  y: 39,  w: 83,  h: 94},
        // {name: 'cassette',   x: 406, y: 45,  w: 343, h: 71},
        // {name: 'lcd',        x: 265, y: 167, w: 460, h: 58},
        // {name: 'alarm_led',  x: 111, y: 258, w: 22,  h: 24},
    ];

    constructor(canvas, imgW, imgH, onDown, onUp) {
        this._canvas = canvas;
        this._imgW = imgW;
        this._imgH = imgH;
        this._activeButton = null;

        canvas.addEventListener('mousedown', (e) => {
            const r = this._hitTest(e);
            if (r) {
                this._activeButton = r;
                onDown(r);
            }
        });

        window.addEventListener('mouseup', (e) => {
            if (this._activeButton) {
                onUp(this._activeButton);
                this._activeButton = null;
            }
        });
    }

    _hitTest(e) {
        const scaleX = this._imgW / this._canvas.clientWidth;
        const scaleY = this._imgH / this._canvas.clientHeight;
        const nx = e.offsetX * scaleX;
        const ny = e.offsetY * scaleY;
        for (const r of Input.HIT_REGIONS) {
            if (nx >= r.x && nx < r.x + r.w && ny >= r.y && ny < r.y + r.h) {
                return r;
            }
        }
        return null;
    }
}
