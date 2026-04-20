class FaceplateRegion {
    constructor(x, y, width, height) {
        this.x = x;
        this.y = y;
        this.width = width;
        this.height = height;
    }

    containsPoint(x, y) {
        return x >= this.x && x < this.x + this.width &&
               y >= this.y && y < this.y + this.height;
    }
}

class FaceplateAlarmLED {
    static RADIUS = 5;

    constructor(faceplate, region) {
        this._ctx = faceplate.ctx;
        this.region = region;
    }

    draw(on) {
        const ctx = this._ctx;
        const region = this.region;
        ctx.clearRect(region.x, region.y, region.width, region.height);
        if (on) {
            const cx = region.x + region.width / 2;
            const cy = region.y + region.height / 2;
            ctx.beginPath();
            ctx.arc(cx, cy, FaceplateAlarmLED.RADIUS, 0, 2 * Math.PI);
            ctx.fillStyle = '#ff3300';
            ctx.fill();
            ctx.shadowColor = '#ff3300';
            ctx.shadowBlur = 10;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
    }
}

class FaceplateLCD {
    // x offsets relative to region, pixel size per character
    static CHARS = [
        { x: 42, px: 3 }, { x: 67, px: 3 }, { x: 92, px: 3 }, { x: 117, px: 3 },
        { x: 150, px: 6 }, { x: 188, px: 6 }, { x: 226, px: 6 },
        { x: 272, px: 6 }, { x: 310, px: 6 }, { x: 348, px: 6 }, { x: 386, px: 6 },
    ];

    static CHAR_COLS = 5;
    static CHAR_ROWS = 7;
    static CHAR_Y_OFFSET = 2;
    static FG_COLOR = '#2d2d2d';

    constructor(faceplate, region) {
        this._ctx = faceplate.ctx;
        this.region = region;
    }

    // pixels is a Uint8Array containing the raw display RAM from the uPD16432B.
    // It holds 11 characters × 7 rows = 77 bytes.  Each byte's low 5 bits are
    // the 5 pixel columns for one row of one character.  Bytes are ordered: all
    // 7 rows of character 0, then all 7 rows of character 1, etc.
    draw(pixels) {
        const region = this.region;
        this._ctx.clearRect(region.x, region.y, region.width, region.height);
        this._ctx.fillStyle = FaceplateLCD.FG_COLOR;

        for (let ch = 0; ch < FaceplateLCD.CHARS.length; ch++) {
            this._drawChar(pixels, ch);
        }
    }

    _drawChar(pixels, index) {
        const region = this.region;
        const c = FaceplateLCD.CHARS[index];
        const pxGap = 1;
        const bigPx = 6;
        const bigH = FaceplateLCD.CHAR_ROWS * (bigPx + pxGap) - pxGap;
        const charH = FaceplateLCD.CHAR_ROWS * (c.px + pxGap) - pxGap;
        const yOff = region.y + FaceplateLCD.CHAR_Y_OFFSET + (bigH - charH);
        const byteBase = index * FaceplateLCD.CHAR_ROWS;

        for (let row = 0; row < FaceplateLCD.CHAR_ROWS; row++) {
            const bits = pixels[byteBase + row] & 0x1F;
            for (let col = 0; col < FaceplateLCD.CHAR_COLS; col++) {
                if ((bits >> (4 - col)) & 1) {
                    this._ctx.fillRect(
                        region.x + c.x + col * (c.px + pxGap),
                        yOff + row * (c.px + pxGap),
                        c.px, c.px);
                }
            }
        }
    }
}

class FaceplateButton {
    constructor(faceplate, region, buttonCode) {
        this._ctx = faceplate.ctx;
        this.buttonCode = buttonCode;
        this.region = region;
        this.enabled = false;
        this._alpha = 0;
        this._fadeTimer = null;
    }

    containsPoint(x, y) {
        return this.region.containsPoint(x, y);
    }

    // Show highlight at full opacity
    press() {
        this._alpha = 1.0;
        if (this._fadeTimer) { clearInterval(this._fadeTimer); this._fadeTimer = null; }
        this._redraw();
    }

    // Fade out highlight over ~500ms
    release() {
        if (this._fadeTimer) clearInterval(this._fadeTimer);
        this._fadeTimer = setInterval(() => {
            this._alpha -= 0.1;
            if (this._alpha <= 0) {
                this._alpha = 0;
                clearInterval(this._fadeTimer);
                this._fadeTimer = null;
            }
            this._redraw();
        }, 50);
    }

    // Clear this button's region and draw highlight at current alpha
    _redraw() {
        const ctx = this._ctx;
        const region = this.region;
        const pad = 2;
        ctx.clearRect(region.x - pad, region.y - pad, region.width + pad * 2, region.height + pad * 2);
        if (this._alpha > 0) {
            const color = this.enabled ? '0, 200, 0' : '200, 0, 0';
            ctx.strokeStyle = 'rgba(' + color + ', ' + this._alpha + ')';
            ctx.lineWidth = 3;
            ctx.strokeRect(region.x, region.y, region.width, region.height);
        }
    }
}

class Faceplate {
    constructor(img, canvas) {
        this.onButtonDown = null;
        this.onButtonUp = null;

        this._buttons = [];
        this._activeButton = null;

        this._img = img;
        this._canvas = canvas;
        this._ctx = canvas.getContext('2d');
        canvas.width = this._img.naturalWidth;
        canvas.height = this._img.naturalHeight;

        // lcd display
        this.lcd = this._addLCD(265, 169, 460, 55);

        // alarm led near power button
        this.alarmLED = this._addAlarmLED(105, 255, 30, 30);

        // uPD16432B key scan buttons
        this._addButton(17,  18,  60,  64,  ButtonCode.MID);
        this._addButton(17,  89,  60,  66,  ButtonCode.BASS);
        this._addButton(165, 18,  64,  64,  ButtonCode.TREB);
        this._addButton(165, 89,  64,  66,  ButtonCode.FB);
        this._addButton(312, 45,  68,  69,  ButtonCode.TAPE_SIDE);
        this._addButton(64,  165, 75,  62,  ButtonCode.SEEK_DOWN);
        this._addButton(147, 165, 81,  62,  ButtonCode.SEEK_UP);
        this._addButton(759, 165, 79,  63,  ButtonCode.TUNE_DOWN);
        this._addButton(843, 165, 79,  63,  ButtonCode.TUNE_UP);
        this._addButton(818, 40,  92,  92,  ButtonCode.SCAN);
        this._addButton(759, 21,  58,  64,  ButtonCode.FM);
        this._addButton(759, 91,  58,  66,  ButtonCode.CD);
        this._addButton(913, 21,  62,  63,  ButtonCode.AM);
        this._addButton(913, 90,  62,  66,  ButtonCode.TAPE);
        this._addButton(143, 245, 112, 51,  ButtonCode.PRESET_1);
        this._addButton(264, 245, 111, 51,  ButtonCode.PRESET_2);
        this._addButton(381, 245, 111, 51,  ButtonCode.PRESET_3);
        this._addButton(497, 245, 111, 51,  ButtonCode.PRESET_4);
        this._addButton(612, 245, 111, 51,  ButtonCode.PRESET_5);
        this._addButton(728, 245, 112, 51,  ButtonCode.PRESET_6);
        this._addButton(898, 245, 75,  51,  ButtonCode.MIX);
        // Non-uPD16432B buttons
        this._addButton(14,  245, 77,  51,  ButtonCode.POWER);
        this._addButton(241, 45,  68,  69,  ButtonCode.STOP_EJECT);

        // Non-interactive regions
        this._addButton(79,  39,  83,  94,  null);  // volume knob
        this._addButton(406, 45,  343, 71,  null);  // cassette slot

        this.disable();

        canvas.addEventListener('mousedown', (e) => {
            const btn = this._scanButtons(e);
            if (btn) {
                this._activeButton = btn;
                btn.press();
                if (this.onButtonDown) this.onButtonDown(btn.buttonCode);
            }
        });

        window.addEventListener('mouseup', (e) => {
            if (this._activeButton) {
                this._activeButton.release();
                if (this.onButtonUp) this.onButtonUp(this._activeButton.buttonCode);
                this._activeButton = null;
            }
        });
    }

    get ctx() { return this._ctx; }

    _addLCD(x, y, width, height) {
        return new FaceplateLCD(this, new FaceplateRegion(x, y, width, height));
    }

    _addAlarmLED(x, y, width, height) {
        return new FaceplateAlarmLED(this, new FaceplateRegion(x, y, width, height));
    }

    _addButton(x, y, width, height, buttonCode) {
        const btn = new FaceplateButton(this, new FaceplateRegion(x, y, width, height), buttonCode);
        this._buttons.push(btn);
        return btn;
    }

    enable() {
        for (const btn of this._buttons) {
            btn.enabled = btn.buttonCode !== null;
        }
    }

    disable() {
        for (const btn of this._buttons) { btn.enabled = false; }
    }

    _scanButtons(e) {
        const scaleX = this._img.naturalWidth / this._canvas.clientWidth;
        const scaleY = this._img.naturalHeight / this._canvas.clientHeight;
        const x = e.offsetX * scaleX;
        const y = e.offsetY * scaleY;
        for (const btn of this._buttons) {
            if (btn.containsPoint(x, y)) {
                return btn;
            }
        }
        return null;
    }
}

// TODO: wire pictograph rendering to server state
const PICTOGRAPHS = [
    {name: 'mix',         byte: 5, bit: 1},
    {name: 'period',      byte: 4, bit: 5},
    {name: 'tape_metal',  byte: 2, bit: 7},
    {name: 'tape_dolby',  byte: 1, bit: 2},
];

const PICTO_POSITIONS = {
    dolby:  new FaceplateRegion(268, 172, 17, 12),
    metal:  new FaceplateRegion(268, 207, 31, 12),
    mix:    new FaceplateRegion(691, 207, 31, 12),
    period: new FaceplateRegion(528, 214, 6,  6),
};
