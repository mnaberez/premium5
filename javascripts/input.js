class FaceplateButton {
    constructor(faceplate, buttonCode, x, y, width, height) {
        this._faceplate = faceplate;
        this.buttonCode = buttonCode;
        this.x = x;
        this.y = y;
        this.width = width;
        this.height = height;
        this._alpha = 0;
        this._fadeTimer = null;
    }

    containsPoint(x, y) {
        return x >= this.x && x < this.x + this.width &&
               y >= this.y && y < this.y + this.height;
    }

    // Show highlight at full opacity
    press() {
        this._alpha = 1.0;
        if (this._fadeTimer) { clearInterval(this._fadeTimer); this._fadeTimer = null; }
        this._faceplate.requestRedraw();
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
            this._faceplate.requestRedraw();
        }, 50);
    }

    // Draw green border at current alpha; called each frame
    highlight() {
        if (this._alpha <= 0) return;
        const ctx = this._faceplate.ctx;
        ctx.strokeStyle = 'rgba(0, 200, 0, ' + this._alpha + ')';
        ctx.lineWidth = 3;
        ctx.strokeRect(this.x, this.y, this.width, this.height);
    }
}

// uPD16432B pictograph RAM: {name, byte, bit}
const PICTOGRAPHS = [
    {name: 'mix',         byte: 5, bit: 1},
    {name: 'period',      byte: 4, bit: 5},
    {name: 'tape_metal',  byte: 2, bit: 7},
    {name: 'tape_dolby',  byte: 1, bit: 2},
];

class Input {
    constructor(canvas, faceplate, conn) {
        this._canvas = canvas;
        this._conn = conn;
        this._activeButton = null;

        const fp = faceplate;
        const B = ButtonCode;

        this._buttons = [
            // uPD16432B key scan buttons
            new FaceplateButton(fp, B.MID,       17,  18,  60,  64),
            new FaceplateButton(fp, B.BASS,      17,  89,  60,  66),
            new FaceplateButton(fp, B.TREB,      165, 18,  64,  64),
            new FaceplateButton(fp, B.FB,        165, 89,  64,  66),
            new FaceplateButton(fp, B.TAPE_SIDE, 312, 45,  68,  69),
            new FaceplateButton(fp, B.SEEK_DOWN, 64,  165, 75,  62),
            new FaceplateButton(fp, B.SEEK_UP,   147, 165, 81,  62),
            new FaceplateButton(fp, B.TUNE_DOWN, 759, 165, 79,  63),
            new FaceplateButton(fp, B.TUNE_UP,   843, 165, 79,  63),
            new FaceplateButton(fp, B.SCAN,      818, 40,  92,  92),
            new FaceplateButton(fp, B.FM,        759, 21,  58,  64),
            new FaceplateButton(fp, B.CD,        759, 91,  58,  66),
            new FaceplateButton(fp, B.AM,        913, 21,  62,  63),
            new FaceplateButton(fp, B.TAPE,      913, 90,  62,  66),
            new FaceplateButton(fp, B.PRESET_1,  143, 245, 112, 51),
            new FaceplateButton(fp, B.PRESET_2,  264, 245, 111, 51),
            new FaceplateButton(fp, B.PRESET_3,  381, 245, 111, 51),
            new FaceplateButton(fp, B.PRESET_4,  497, 245, 111, 51),
            new FaceplateButton(fp, B.PRESET_5,  612, 245, 111, 51),
            new FaceplateButton(fp, B.PRESET_6,  728, 245, 112, 51),
            new FaceplateButton(fp, B.MIX,       898, 245, 75,  51),
            // Non-uPD16432B controls
            new FaceplateButton(fp, B.POWER,     14,  245, 77,  51),
        ];

        canvas.addEventListener('mousedown', (e) => {
            const btn = this._hitTest(e);
            if (btn) {
                this._activeButton = btn;
                btn.press();
                this._conn.buttonDown(btn.buttonCode);
            }
        });

        window.addEventListener('mouseup', (e) => {
            if (this._activeButton) {
                this._activeButton.release();
                this._conn.buttonUp(this._activeButton.buttonCode);
                this._activeButton = null;
            }
        });
    }

    drawButtons() {
        for (const btn of this._buttons) {
            btn.highlight();
        }
    }

    _hitTest(e) {
        const scaleX = Faceplate.IMG_W / this._canvas.clientWidth;
        const scaleY = Faceplate.IMG_H / this._canvas.clientHeight;
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
