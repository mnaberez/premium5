class MFSW {
    static VOL_DOWN = 0x00;
    static VOL_UP   = 0x01;
    static DOWN     = 0x0A;
    static UP       = 0x0B;

    constructor(container) {
        this.onButtonDown = null;
        this.onButtonUp = null;

        this._activeButton = null;

        this._bind(container, '.mfsw-vol-down', MFSW.VOL_DOWN);
        this._bind(container, '.mfsw-vol-up',   MFSW.VOL_UP);
        this._bind(container, '.mfsw-up',       MFSW.UP);
        this._bind(container, '.mfsw-down',     MFSW.DOWN);

        window.addEventListener('mouseup', (e) => {
            if (this._activeButton !== null) {
                if (this.onButtonUp) this.onButtonUp(this._activeButton);
                this._activeButton = null;
            }
        });
    }

    _bind(container, selector, code) {
        var btn = container.querySelector(selector);
        if (btn) {
            btn.addEventListener('mousedown', (e) => {
                this._activeButton = code;
                if (this.onButtonDown) this.onButtonDown(code);
            });
        }
    }
}
