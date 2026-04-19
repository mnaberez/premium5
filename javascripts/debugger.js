function hex16(n) { return n.toString(16).toUpperCase().padStart(4, '0'); }
function hex8(n) { return n.toString(16).toUpperCase().padStart(2, '0'); }

class Debugger {
    static BYTES_PER_ROW = 16;

    constructor() {
        this._ramState = {};
        this._lstData = null;
        this._expanded = false;

        fetch('listing.json').then(r => r.json()).then(data => {
            this._lstData = data;
        }).catch(e => console.error('Failed to load listing:', e));
    }

    init() {
        this._initRam('ram-exp', 2048, 0xF000);
        this._initRam('ram-hs', 992, 0xFB00);
    }

    update(state) {
        this._updateRegisters(state);
        this._updateDisassembly(state);
        this._updateListing(state);
        this._updateCycles(state);
        this._updateRam('ram-exp', state.exp_ram);
        this._updateRam('ram-hs', state.hs_ram);
    }

    toggleExpand() {
        this._expanded = !this._expanded;
        const left = document.getElementById('panel-left');
        const row = document.querySelector('.info-row');
        const btn = document.getElementById('expand-btn');
        const disasmEl = document.getElementById('disasm-listing');
        const listingEl = document.getElementById('listing-view');
        const heading = document.querySelector('#panel-instructions h2');
        if (this._expanded) {
            left.style.display = 'none';
            row.style.gridTemplateColumns = '1fr';
            btn.textContent = '[-]';
            disasmEl.style.display = 'none';
            listingEl.style.display = 'block';
            heading.textContent = 'Listing';
        } else {
            left.style.display = '';
            row.style.gridTemplateColumns = '3fr 2fr';
            btn.textContent = '[+]';
            disasmEl.style.display = '';
            listingEl.style.display = 'none';
            heading.textContent = 'Instructions';
        }
    }

    _initRam(id, size, baseAddr) {
        const el = document.getElementById(id);
        this._ramState[id] = { prev: null };
        const lines = [];
        for (let row = 0; row < size; row += Debugger.BYTES_PER_ROW) {
            let line = '<span class="ram-addr">' + hex16(baseAddr + row) + '</span>  ';
            for (let col = 0; col < Debugger.BYTES_PER_ROW && row + col < size; col++) {
                line += '<span class="ram-byte" id="' + id + '-h-' + (row+col) + '">00</span> ';
            }
            line += ' ';
            for (let col = 0; col < Debugger.BYTES_PER_ROW && row + col < size; col++) {
                line += '<span class="ram-ascii-byte" id="' + id + '-a-' + (row+col) + '">.</span>';
            }
            lines.push(line);
        }
        el.innerHTML = lines.join('\n');
    }

    _updateRam(id, hexStr) {
        const st = this._ramState[id];
        const prev = st.prev;
        for (let i = 0; i < hexStr.length; i += 2) {
            const byteIdx = i / 2;
            const cur = hexStr.slice(i, i + 2);
            if (prev !== null && cur !== prev.slice(i, i + 2)) {
                const hSpan = document.getElementById(id + '-h-' + byteIdx);
                const aSpan = document.getElementById(id + '-a-' + byteIdx);
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
                const hSpan = document.getElementById(id + '-h-' + byteIdx);
                const aSpan = document.getElementById(id + '-a-' + byteIdx);
                hSpan.textContent = cur;
                const b = parseInt(cur, 16);
                aSpan.textContent = (b >= 0x20 && b <= 0x7E) ? String.fromCharCode(b) : '.';
            }
        }
        st.prev = hexStr;
    }

    _updateRegisters(state) {
        document.getElementById('reg-pc2').textContent = hex16(state.pc);
        document.getElementById('reg-sp2').textContent = hex16(state.sp);
        document.getElementById('reg-ax2').textContent = hex16(state.ax);
        document.getElementById('reg-bc2').textContent = hex16(state.bc);
        document.getElementById('reg-de2').textContent = hex16(state.de);
        document.getElementById('reg-hl2').textContent = hex16(state.hl);
        document.getElementById('reg-psw2').textContent = hex8(state.psw);
        for (let i = 0; i < 4; i++) {
            document.getElementById('rb-' + i).className = (state.rb === i) ? 'flag-set' : 'flag-clear';
        }
        for (const flag of ['ie', 'isp', 'z', 'ac', 'cy']) {
            document.getElementById('flag-' + flag + '2').className = state[flag] ? 'flag-set' : 'flag-clear';
        }
    }

    _updateDisassembly(state) {
        const el = document.getElementById('disasm-listing');
        const totalLines = 21;
        const blanks = totalLines - state.disasm_history.length - 1;
        const lines = [];
        for (let i = 0; i < blanks; i++) {
            lines.push('<div class="disasm-line">&nbsp;</div>');
        }
        state.disasm_history.forEach(line => {
            lines.push('<div class="disasm-line">' +
                '<span class="disasm-addr">' + hex16(line.addr) + '</span> ' +
                '<span class="disasm-hex">' + line.hex + '</span> ' +
                '<span class="disasm-inst">' + line.inst + '</span></div>');
        });
        const cur = state.disasm_current;
        lines.push('<div class="disasm-line-current">' +
            '<span class="disasm-addr">' + hex16(cur.addr) + '</span> ' +
            '<span class="disasm-hex">' + cur.hex + '</span> ' +
            '<span class="disasm-inst">' + cur.inst + '</span></div>');
        el.innerHTML = lines.join('');
    }

    _updateListing(state) {
        if (!this._expanded) return;
        const el = document.getElementById('listing-view');
        try {
            if (!this._lstData) {
                el.textContent = 'Loading listing...';
            } else {
                const targetLine = this._lstData.addr_to_line[String(state.pc)];
                if (targetLine) {
                    const startLine = Math.max(1, targetLine - 20);
                    const endLine = Math.min(this._lstData.lines.length, targetLine + 40);
                    const html = [];
                    for (let i = startLine; i <= endLine; i++) {
                        const text = this._lstData.lines[i - 1];
                        const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
                        const cls = (i === targetLine) ? 'listing-line-current' : 'listing-line';
                        html.push('<span class="' + cls + '">' + escaped + '</span>');
                    }
                    el.innerHTML = html.join('');
                    const currentEl = el.querySelector('.listing-line-current');
                    if (currentEl) {
                        currentEl.scrollIntoView({block: 'center', behavior: 'auto'});
                    }
                } else {
                    el.textContent = 'No listing for PC=0x' + hex16(state.pc);
                }
            }
        } catch(e) {
            el.textContent = 'ERROR: ' + e.message;
        }
    }

    _updateCycles(state) {
        document.getElementById('cycles').textContent = state.total_cycles.toLocaleString();
        document.getElementById('sim-time').textContent = (state.total_cycles / 4190000).toFixed(3);
        document.getElementById('speed-pct').textContent = (state.real_mhz / 4.19 * 100).toFixed(1);
        document.getElementById('real-mhz').textContent = state.real_mhz.toFixed(2);
        document.getElementById('potential-mhz').textContent = state.potential_mhz.toFixed(2);
    }
}
