function createRadio(canvas) {
    const IMG_W = 990;
    const IMG_H = 311;
    const ctx = canvas.getContext('2d');

    const bgCanvas = document.createElement('canvas');
    bgCanvas.width = IMG_W;
    bgCanvas.height = IMG_H;
    const bgCtx = bgCanvas.getContext('2d');
    const bgImg = new Image();
    let bgReady = false;

    bgImg.onload = function() {
        bgCtx.drawImage(bgImg, 0, 0);
        bgReady = true;
    };
    bgImg.src = 'images/faceplate-upscaled-990px.png';

    const CHAR_COLS = 5;
    const CHAR_ROWS = 7;
    const LCD_FG = '#2d2d2d';
    const LCD_Y = 173;

    const CHARS = [
        { x: 309, px: 3 }, { x: 334, px: 3 }, { x: 359, px: 3 }, { x: 384, px: 3 },
        { x: 417, px: 6 }, { x: 455, px: 6 }, { x: 493, px: 6 },
        { x: 539, px: 6 }, { x: 577, px: 6 }, { x: 615, px: 6 }, { x: 653, px: 6 },
    ];

    const LED_X = 120;
    const LED_Y = 270;
    const LED_R = 5;

    let highlight = null;

    function setHighlight(h) {
        highlight = h;
    }

    function draw(hexStr, ledOn) {
        if (!bgReady) return;
        ctx.drawImage(bgCanvas, 0, 0);

        // LCD characters
        const bigPx = 6;
        const pxGap = 1;
        const bigH = CHAR_ROWS * (bigPx + pxGap) - pxGap;
        ctx.fillStyle = LCD_FG;
        for (let ch = 0; ch < CHARS.length; ch++) {
            const c = CHARS[ch];
            const charH = CHAR_ROWS * (c.px + pxGap) - pxGap;
            const yOff = LCD_Y + (bigH - charH);
            const byteBase = ch * CHAR_ROWS * 2;
            for (let row = 0; row < CHAR_ROWS; row++) {
                const byteIdx = byteBase + row * 2;
                const byte = parseInt(hexStr.slice(byteIdx, byteIdx + 2), 16);
                const pixels = byte & 0x1F;
                for (let col = 0; col < CHAR_COLS; col++) {
                    if ((pixels >> (4 - col)) & 1) {
                        ctx.fillRect(
                            c.x + col * (c.px + pxGap),
                            yOff + row * (c.px + pxGap),
                            c.px, c.px);
                    }
                }
            }
        }

        // Button click highlight
        if (highlight) {
            ctx.strokeStyle = 'rgba(0, 200, 0, ' + highlight.alpha + ')';
            ctx.lineWidth = 3;
            ctx.strokeRect(highlight.x, highlight.y, highlight.w, highlight.h);
        }

        // LED
        if (ledOn) {
            ctx.beginPath();
            ctx.arc(LED_X, LED_Y, LED_R, 0, 2 * Math.PI);
            ctx.fillStyle = '#ff3300';
            ctx.fill();
            ctx.shadowColor = '#ff3300';
            ctx.shadowBlur = 10;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
    }

    return {
        IMG_W: IMG_W,
        IMG_H: IMG_H,
        draw: draw,
        setHighlight: setHighlight,
        isReady: function() { return bgReady; },
    };
}
