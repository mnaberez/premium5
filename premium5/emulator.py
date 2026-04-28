import sys
import os
import json
import time
import threading
from collections import deque

from k0dasm.disassemble import disassemble
from k0emu.processor import RegisterPairs, Flags, RunState
from premium5.system import make_processor, populate_eeprom, configure_interrupts
from premium5.mfsw import MFSWTransmitter


class Listing:
    CONTEXT_BEFORE = 20
    CONTEXT_AFTER = 40

    def __init__(self, path):
        with open(path) as f:
            data = json.load(f)
        self._lines = data['lines']
        self._addr_to_line = data['addr_to_line']

    def get_slice(self, pc):
        target_line = self._addr_to_line.get(str(pc))
        if not target_line:
            return None
        start = max(1, target_line - self.CONTEXT_BEFORE)
        end = min(len(self._lines), target_line + self.CONTEXT_AFTER)
        lines = []
        for i in range(start, end + 1):
            lines.append({'text': self._lines[i - 1], 'current': i == target_line})
        return lines


class Emulator:
    def __init__(self, rom_path, listing=None):
        self.proc = make_processor()
        with open(rom_path, 'rb') as f:
            self.proc.bus.device("rom").load(0, f.read())
        populate_eeprom(self.proc)
        self.proc.bus.reset()
        configure_interrupts(self.proc)
        self.upd = self.proc.bus.device("csi30").target
        self.mfsw = MFSWTransmitter()
        self._p0 = self.proc.bus.device("p0")
        self.running = False
        self.steps_per_frame = 50000
        self.potential_mhz = 0.0
        self.real_mhz = 0.0
        self._epoch_time = 0.0
        self._epoch_cycles = 0
        self._disasm_history = deque(maxlen=20)
        self.speed_pct = 100
        self._listing = listing
        self.lock = threading.Lock()
        self.state_changed = threading.Condition(self.lock)

    def get_state(self):
        proc = self.proc
        psw = proc.read_psw()

        try:
            dasm = disassemble(proc.bus, proc.pc)
            hex_str = ' '.join(["%02x" % x for x in dasm.all_bytes])
            current = {'addr': proc.pc, 'hex': hex_str, 'inst': str(dasm)}
        except Exception:
            hex_str = "%02x" % proc.bus.read(proc.pc)
            current = {'addr': proc.pc, 'hex': hex_str, 'inst': '???'}

        display_pixels = bytes(self.upd.get_display_pixels()).hex()
        pictograph_ram = bytes(self.upd.pictograph_ram).hex()
        led = not bool(proc.bus.read(0xFF03) & 0x08)
        t30 = proc.bus.read(0xF18D) * 0.1

        wall_since_epoch = time.monotonic() - self._epoch_time
        if wall_since_epoch > 0 and self.running:
            self.real_mhz = ((proc.total_cycles - self._epoch_cycles) / wall_since_epoch) / 1_000_000

        exp_ram = proc.bus.device("expansion_ram")._data
        hs_ram = proc.bus.device("high_speed_ram")._data
        eeprom = proc.bus.device("iic0")._targets[0x50]._data

        return {
            'running': self.running,
            'pc': proc.pc,
            'sp': proc.read_sp(),
            'ax': proc.read_gp_regpair(RegisterPairs.AX),
            'bc': proc.read_gp_regpair(RegisterPairs.BC),
            'de': proc.read_gp_regpair(RegisterPairs.DE),
            'hl': proc.read_gp_regpair(RegisterPairs.HL),
            'psw': psw,
            'ie': bool(psw & Flags.IE),
            'rb': proc.read_rb(),
            'isp': bool(psw & Flags.ISP),
            'z': bool(psw & Flags.Z),
            'ac': bool(psw & Flags.AC),
            'cy': bool(psw & Flags.CY),
            'total_cycles': proc.total_cycles,
            'disasm_history': list(self._disasm_history),
            'disasm_current': current,
            'display_pixels': display_pixels,
            'pictograph_ram': pictograph_ram,
            'led': led,
            't30': round(t30, 1),
            'real_mhz': round(self.real_mhz, 2),
            'potential_mhz': round(self.potential_mhz, 2),
            'exp_ram': bytes(exp_ram).hex(),
            'exp_ram_base': 0xF000,
            'hs_ram': bytes(hs_ram).hex(),
            'hs_ram_base': 0xFB00,
            'eeprom': bytes(eeprom).hex(),
            'eeprom_base': 0x0000,
            'listing_slice': self.get_listing_slice(),
        }

    CLOCK_HZ = 4_190_000

    def start_run(self):
        self._epoch_time = time.monotonic()
        self._epoch_cycles = self.proc.total_cycles
        self.running = True

    def _disasm_at(self, pc):
        try:
            dasm = disassemble(self.proc.bus, pc)
            hex_str = ' '.join(["%02x" % x for x in dasm.all_bytes])
            self._disasm_history.append({'addr': pc, 'hex': hex_str, 'inst': str(dasm)})
        except Exception:
            hex_str = "%02x" % self.proc.bus.read(pc)
            self._disasm_history.append({'addr': pc, 'hex': hex_str, 'inst': '???'})

    def _tick_mfsw(self):
        cycles = self.proc.inst_cycles
        self.mfsw.tick(cycles)
        self._p0.set_external_input(0, not self.mfsw.wire)

    def step_batch(self):
        t0 = time.monotonic()
        c0 = self.proc.total_cycles
        recent_pcs = deque(maxlen=self._disasm_history.maxlen)
        for _ in range(self.steps_per_frame):
            if self.proc.run_state != RunState.HALTED:
                recent_pcs.append(self.proc.pc)
            self.proc.step()
            self._tick_mfsw()
        for pc in recent_pcs:
            self._disasm_at(pc)
        elapsed = time.monotonic() - t0
        if elapsed > 0:
            self.potential_mhz = ((self.proc.total_cycles - c0) / elapsed) / 1_000_000

    def throttle_delay(self):
        if self.speed_pct <= 0:
            return 0.05
        target_hz = self.CLOCK_HZ * self.speed_pct / 100
        cycles_since_epoch = self.proc.total_cycles - self._epoch_cycles
        target_wall = cycles_since_epoch / target_hz
        actual_wall = time.monotonic() - self._epoch_time
        return max(0, target_wall - actual_wall)

    def reset(self):
        self.proc.bus.reset()
        configure_interrupts(self.proc)
        self._disasm_history.clear()
        self.real_mhz = 0.0
        self.potential_mhz = 0.0

    def get_listing_slice(self):
        if not self._listing:
            return None
        return self._listing.get_slice(self.proc.pc)

    def step_one(self):
        self._disasm_at(self.proc.pc)
        self.proc.step()
        self._tick_mfsw()

    def handle_command(self, cmd):
        action = cmd.get('action')

        if action == 'start':
            self.start_run()

        elif action == 'stop':
            self.running = False

        elif action == 'step':
            if not self.running:
                self.step_one()

        elif action == 'reset':
            self.running = False
            self.reset()

        elif action == 'speed':
            self.speed_pct = cmd.get('value', 100)
            self._epoch_time = time.monotonic()
            self._epoch_cycles = self.proc.total_cycles

        elif action == 'power_key':
            p0 = self.proc.bus.device("p0")
            p0.set_external_input(4, True)
            p0.set_external_input(2, False)
            p0.set_external_input(4, False)

        elif action == 'key_down':
            self.upd.key_data[cmd['byte']] |= cmd['mask']

        elif action == 'key_up':
            self.upd.key_data[cmd['byte']] &= ~cmd['mask']

        elif action == 'mfsw':
            import premium5.mfsw as mfsw
            code = cmd.get('code')
            codes = {
                'vol_down': mfsw.VOL_DOWN,
                'vol_up': mfsw.VOL_UP,
                'up': mfsw.UP,
                'down': mfsw.DOWN,
            }
            if code in codes and not self.mfsw.busy:
                self.mfsw.send(codes[code])


def emulator_thread(emulator):
    while True:
        with emulator.lock:
            if emulator.running and emulator.speed_pct > 0:
                emulator.step_batch()
                emulator.state_changed.notify_all()
        if emulator.running and emulator.speed_pct > 0:
            delay = emulator.throttle_delay()
            time.sleep(delay)
        else:
            time.sleep(0.05)
