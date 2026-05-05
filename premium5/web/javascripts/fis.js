class FISDisplay {
    static WIDTH = 64;
    static HEIGHT = 16;
    static CHARS_PER_LINE = 8;
    static CHAR_SIZE = 8;
    static FG_COLOR = '#E02517';

    constructor(canvas) {
        this._ctx = canvas.getContext('2d');
    }

    draw(pixels) {
        this._ctx.clearRect(0, 0, FISDisplay.WIDTH, FISDisplay.HEIGHT);
        this._ctx.fillStyle = FISDisplay.FG_COLOR;

        for (let ch = 0; ch < 16; ch++) {
            const row_y = (ch < FISDisplay.CHARS_PER_LINE) ? 0 : FISDisplay.CHAR_SIZE;
            const col_x = (ch % FISDisplay.CHARS_PER_LINE) * FISDisplay.CHAR_SIZE;

            for (let row = 0; row < FISDisplay.CHAR_SIZE; row++) {
                const byte = pixels[ch * FISDisplay.CHAR_SIZE + row];
                for (let bit = 7; bit >= 0; bit--) {
                    if ((byte >> bit) & 1) {
                        this._ctx.fillRect(col_x + (7 - bit), row_y + row, 1, 1);
                    }
                }
            }
        }
    }
}
