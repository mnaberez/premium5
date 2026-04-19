class Radio {
    static IMG_W = 990;
    static IMG_H = 311;

    static CHARS = [
        { x: 309, px: 3 }, { x: 334, px: 3 }, { x: 359, px: 3 }, { x: 384, px: 3 },
        { x: 417, px: 6 }, { x: 455, px: 6 }, { x: 493, px: 6 },
        { x: 539, px: 6 }, { x: 577, px: 6 }, { x: 615, px: 6 }, { x: 653, px: 6 },
    ];

    static CHAR_COLS = 5;
    static CHAR_ROWS = 7;
    static LCD_FG = '#2d2d2d';
    static LCD_Y = 172;
    static LED_X = 120;
    static LED_Y = 270;
    static LED_R = 5;

    constructor(canvas) {
        this._canvas = canvas;
        this._ctx = canvas.getContext('2d');
        this._bgCanvas = document.createElement('canvas');
        this._bgCanvas.width = Radio.IMG_W;
        this._bgCanvas.height = Radio.IMG_H;
        this._bgCtx = this._bgCanvas.getContext('2d');
        this._bgReady = false;
        this._highlight = null;

        this._onReady = null;
        const bgImg = new Image();
        bgImg.onload = () => {
            this._bgCtx.drawImage(bgImg, 0, 0);
            this._bgReady = true;
            if (this._onReady) this._onReady();
        };
        bgImg.src = 'images/faceplate-upscaled-990px.png';
    }

    setHighlight(h) {
        this._highlight = h;
    }

    draw(hexStr, ledOn) {
        if (!this._bgReady) return;
        const ctx = this._ctx;
        ctx.drawImage(this._bgCanvas, 0, 0);

        const bigPx = 6;
        const pxGap = 1;
        const bigH = Radio.CHAR_ROWS * (bigPx + pxGap) - pxGap;
        ctx.fillStyle = Radio.LCD_FG;

        for (let ch = 0; ch < Radio.CHARS.length; ch++) {
            const c = Radio.CHARS[ch];
            const charH = Radio.CHAR_ROWS * (c.px + pxGap) - pxGap;
            const yOff = Radio.LCD_Y + (bigH - charH);
            const byteBase = ch * Radio.CHAR_ROWS * 2;
            for (let row = 0; row < Radio.CHAR_ROWS; row++) {
                const byteIdx = byteBase + row * 2;
                const byte = parseInt(hexStr.slice(byteIdx, byteIdx + 2), 16);
                const pixels = byte & 0x1F;
                for (let col = 0; col < Radio.CHAR_COLS; col++) {
                    if ((pixels >> (4 - col)) & 1) {
                        ctx.fillRect(
                            c.x + col * (c.px + pxGap),
                            yOff + row * (c.px + pxGap),
                            c.px, c.px);
                    }
                }
            }
        }

        if (this._highlight) {
            ctx.strokeStyle = 'rgba(0, 200, 0, ' + this._highlight.alpha + ')';
            ctx.lineWidth = 3;
            ctx.strokeRect(this._highlight.x, this._highlight.y,
                           this._highlight.w, this._highlight.h);
        }

        if (ledOn) {
            ctx.beginPath();
            ctx.arc(Radio.LED_X, Radio.LED_Y, Radio.LED_R, 0, 2 * Math.PI);
            ctx.fillStyle = '#ff3300';
            ctx.fill();
            ctx.shadowColor = '#ff3300';
            ctx.shadowBlur = 10;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
    }
}
