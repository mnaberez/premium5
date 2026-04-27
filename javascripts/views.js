function hex16(n) { return n.toString(16).toUpperCase().padStart(4, '0'); }
function hex8(n) { return n.toString(16).toUpperCase().padStart(2, '0'); }
const _escapeDiv = document.createElement('div');
function escapeHtml(s) { _escapeDiv.textContent = s; return _escapeDiv.innerHTML; }

class RegistersView {
    constructor(el) {
        this._el = el;
    }

    update(state) {
        const el = this._el;
        for (const reg of ['pc', 'sp', 'ax', 'bc', 'de', 'hl']) {
            el.querySelector('[data-reg="' + reg + '"]').textContent = hex16(state[reg]);
        }
        el.querySelector('[data-reg="psw"]').textContent = hex8(state.psw);
        for (let i = 0; i < 4; i++) {
            el.querySelector('[data-rb="' + i + '"]').className = (state.rb === i) ? 'flag-set' : 'flag-clear';
        }
        for (const flag of ['ie', 'isp', 'z', 'ac', 'cy']) {
            el.querySelector('[data-flag="' + flag + '"]').className = state[flag] ? 'flag-set' : 'flag-clear';
        }
    }
}

class DisassemblyView {
    constructor(el) {
        this._el = el;
    }

    update(state) {
        const totalLines = 21;
        const cur = state.disasmCurrent;
        const history = state.disasmHistory;
        const hideLast = history.length > 0 &&
            history[history.length - 1].addr === cur.addr;
        const visibleCount = hideLast ? history.length - 1 : history.length;
        const blanks = totalLines - visibleCount - 1;
        const lines = [];
        for (let i = 0; i < blanks; i++) {
            lines.push('<div class="disasm-line">&nbsp;</div>');
        }
        const end = hideLast ? history.length - 1 : history.length;
        for (let i = 0; i < end; i++) {
            const line = history[i];
            lines.push('<div class="disasm-line">' +
                '<span class="disasm-addr">' + hex16(line.addr) + '</span> ' +
                '<span class="disasm-hex">' + line.hex + '</span> ' +
                '<span class="disasm-inst">' + line.inst + '</span></div>');
        }
        lines.push('<div class="disasm-line-current">' +
            '<span class="disasm-addr">' + hex16(cur.addr) + '</span> ' +
            '<span class="disasm-hex">' + cur.hex + '</span> ' +
            '<span class="disasm-inst">' + cur.inst + '</span></div>');
        this._el.innerHTML = lines.join('');
    }
}

class ListingView {
    constructor(el) {
        this._el = el;
    }

    update(state) {
        if (!state.listingSlice) {
            this._el.textContent = 'No listing for PC=0x' + hex16(state.pc);
            return;
        }
        const html = [];
        for (const line of state.listingSlice) {
            const cls = line.current ? 'listing-line-current' : 'listing-line';
            html.push('<span class="' + cls + '">' + escapeHtml(line.text) + '</span>');
        }
        this._el.innerHTML = html.join('');
        const currentEl = this._el.querySelector('.listing-line-current');
        if (currentEl) {
            currentEl.scrollIntoView({block: 'center', behavior: 'auto'});
        }
    }
}

class MemoryView {
    static BYTES_PER_ROW = 16;

    constructor(el, size, baseAddr, stateField) {
        this._el = el;
        this._stateField = stateField;
        this._prev = null;
        this._hSpans = [];
        this._aSpans = [];

        const lines = [];
        for (let row = 0; row < size; row += MemoryView.BYTES_PER_ROW) {
            let line = '<span class="mem-addr">' + hex16(baseAddr + row) + '</span>  ';
            for (let col = 0; col < MemoryView.BYTES_PER_ROW && row + col < size; col++) {
                line += '<span class="mem-byte">00</span> ';
            }
            line += ' ';
            for (let col = 0; col < MemoryView.BYTES_PER_ROW && row + col < size; col++) {
                line += '<span class="mem-ascii">.</span>';
            }
            lines.push(line);
        }
        el.innerHTML = lines.join('\n');

        this._hSpans = el.querySelectorAll('.mem-byte');
        this._aSpans = el.querySelectorAll('.mem-ascii');
    }

    update(state) {
        const hexStr = state[this._stateField];
        const prev = this._prev;
        for (let i = 0; i < hexStr.length; i += 2) {
            const byteIdx = i / 2;
            const cur = hexStr.slice(i, i + 2);
            if (prev !== null && cur !== prev.slice(i, i + 2)) {
                const hSpan = this._hSpans[byteIdx];
                const aSpan = this._aSpans[byteIdx];
                hSpan.textContent = cur;
                const b = parseInt(cur, 16);
                aSpan.textContent = (b >= 0x20 && b <= 0x7E) ? String.fromCharCode(b) : '.';
                hSpan.style.transition = 'none';
                aSpan.style.transition = 'none';
                hSpan.style.backgroundColor = '#fc0';
                aSpan.style.backgroundColor = '#fc0';
                hSpan.offsetHeight;
                hSpan.style.transition = 'background-color 1s';
                aSpan.style.transition = 'background-color 1s';
                hSpan.style.backgroundColor = '';
                aSpan.style.backgroundColor = '';
            } else if (prev === null) {
                const hSpan = this._hSpans[byteIdx];
                const aSpan = this._aSpans[byteIdx];
                hSpan.textContent = cur;
                const b = parseInt(cur, 16);
                aSpan.textContent = (b >= 0x20 && b <= 0x7E) ? String.fromCharCode(b) : '.';
            }
        }
        this._prev = hexStr;
    }
}

class StatisticsView {
    constructor(el) {
        this._el = el;
    }

    update(state) {
        const el = this._el;
        el.querySelector('[data-stat="cycles"]').textContent = state.totalCycles.toLocaleString();
        el.querySelector('[data-stat="sim-time"]').textContent = (state.totalCycles / 4190000).toFixed(3);
        el.querySelector('[data-stat="speed-pct"]').textContent = (state.realMhz / 4.19 * 100).toFixed(1);
        el.querySelector('[data-stat="real-mhz"]').textContent = state.realMhz.toFixed(2);
        el.querySelector('[data-stat="potential-mhz"]').textContent = state.potentialMhz.toFixed(2);
    }
}
