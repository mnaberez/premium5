class Radio {
    static IMG_W = 990;
    static IMG_H = 311;

    static CHARS = [
        { x: 307, px: 3 }, { x: 332, px: 3 }, { x: 357, px: 3 }, { x: 382, px: 3 },
        { x: 415, px: 6 }, { x: 453, px: 6 }, { x: 491, px: 6 },
        { x: 537, px: 6 }, { x: 575, px: 6 }, { x: 613, px: 6 }, { x: 651, px: 6 },
    ];

    static CHAR_COLS = 5;
    static CHAR_ROWS = 7;
    static LCD_FG = '#2d2d2d';
    static LCD_Y = 172;
    static LED_X = 120;
    static LED_Y = 270;
    static LED_R = 5;

    static PICTO_POSITIONS = {
        dolby:  {x: 268, y: 172, w: 17, h: 12},
        metal:  {x: 268, y: 207, w: 31, h: 12},
        mix:    {x: 691, y: 207, w: 31, h: 12},
        period: {x: 528, y: 214, w: 6,  h: 6},
    };

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
        this._pictoImages = {};
        const pictoNames = ['dolby', 'metal', 'mix', 'period'];
        let loadCount = 0;
        const totalLoads = 1 + pictoNames.length;
        const checkReady = () => {
            loadCount++;
            if (loadCount >= totalLoads) {
                this._bgReady = true;
                if (this._onReady) this._onReady();
            }
        };
        const bgImg = new Image();
        bgImg.onload = () => {
            this._bgCtx.drawImage(bgImg, 0, 0);
            checkReady();
        };
        bgImg.src = 'images/faceplate-upscaled-990px.png';
        for (const name of pictoNames) {
            const img = new Image();
            img.onload = checkReady;
            img.src = 'images/pictograph-' + name + '.png';
            this._pictoImages[name] = img;
        }
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

        // Pictographs (TODO: driven by pictograph RAM)
        // for (const [name, pos] of Object.entries(Radio.PICTO_POSITIONS)) {
        //     const img = this._pictoImages[name];
        //     if (img && img.complete) {
        //         ctx.drawImage(img, pos.x, pos.y, pos.w, pos.h);
        //     }
        // }

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
