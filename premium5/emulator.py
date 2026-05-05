import sys
import os
import json
import time
import threading
from collections import deque

from k0dasm.disassemble import disassemble
from k0emu.processor import RegisterPairs, Flags, RunState
from premium5.system import make_processor
from premium5.eeprom import populate_eeprom
from premium5.digital import Level, LogicOutput, Inverter
from premium5.mfsw import MFSWTransmitter
from premium5.timing import Governor, ReferenceTick


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
    SYSTEM_CLOCK_HZ = 4_190_000  # cpu clock frequency (4.19 MHz)

    def __init__(self, rom_path, listing=None):
        self.proc = make_processor()
        with open(rom_path, 'rb') as f:
            self.proc.bus.device("rom").load(0, f.read())
        populate_eeprom(self.proc)
        self.proc.bus.reset()
        csi30 = self.proc.bus.device("csi30")
        self.upd = csi30.upd
        self.fis = csi30.fis

        p0 = self.proc.bus.device("p0")
        self._p3 = self.proc.bus.device("p3")

        self.mfsw = MFSWTransmitter()
        inverter = Inverter()
        self.mfsw.swc_out.bind(inverter.input)
        inverter.output.bind(p0.pins[0].input)

        self._power_key = LogicOutput(Level.HIGH)
        self._power_key.bind(p0.pins[4].input)

        self._p02_driver = LogicOutput(Level.HIGH)
        self._p02_driver.bind(p0.pins[2].input)

        self.governor = Governor(self.SYSTEM_CLOCK_HZ)
        self.reference_tick = ReferenceTick(self.SYSTEM_CLOCK_HZ)
        self.reference_tick.add_listener(self.mfsw)
        self.reference_tick.add_listener(self.fis)

        self.running = False
        self.steps_per_frame = 50000
        self._disasm_history = deque(maxlen=20)
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

        display_pixels = bytes(self.upd.display_pixels).hex()
        pictograph_ram = bytes(self.upd.pictograph_ram).hex()
        led = self._p3.pins[3].low  # led is active low

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
            'fis_display_pixels': bytes(self.fis.display_pixels).hex(),
            'real_mhz': self.governor.real_mhz,
            'potential_mhz': self.governor.potential_mhz,
            'exp_ram': bytes(exp_ram).hex(),
            'exp_ram_base': 0xF000,
            'hs_ram': bytes(hs_ram).hex(),
            'hs_ram_base': 0xFB00,
            'eeprom': bytes(eeprom).hex(),
            'eeprom_base': 0x0000,
            'listing_slice': self.get_listing_slice(),
        }

    def start_run(self):
        self.governor.reset()
        self.running = True

    def _disasm_at(self, pc):
        try:
            dasm = disassemble(self.proc.bus, pc)
            hex_str = ' '.join(["%02x" % x for x in dasm.all_bytes])
            self._disasm_history.append({'addr': pc, 'hex': hex_str, 'inst': str(dasm)})
        except Exception:
            hex_str = "%02x" % self.proc.bus.read(pc)
            self._disasm_history.append({'addr': pc, 'hex': hex_str, 'inst': '???'})

    def step_batch(self):
        self.governor.batch()
        recent_pcs = deque(maxlen=self._disasm_history.maxlen)
        for _ in range(self.steps_per_frame):
            if self.proc.run_state != RunState.HALTED:
                recent_pcs.append(self.proc.pc)
            self.proc.step()
            cycles = self.proc.inst_cycles
            self.governor.advance(cycles)
            self.reference_tick.advance(cycles)
        for pc in recent_pcs:
            self._disasm_at(pc)


    def reset(self):
        self.proc.bus.reset()
        self._disasm_history.clear()
        self.governor.reset()

    def get_listing_slice(self):
        if not self._listing:
            return None
        return self._listing.get_slice(self.proc.pc)

    def step_one(self):
        self._disasm_at(self.proc.pc)
        self.proc.step()
        cycles = self.proc.inst_cycles
        self.governor.advance(cycles)
        self.reference_tick.advance(cycles)

    def handle_command(self, cmd):
        action = cmd.get('action')

        if action == 'start':
            self.start_run()

        elif action == 'stop':
            self.running = False
            self.governor.reset()

        elif action == 'step':
            if not self.running:
                self.step_one()

        elif action == 'reset':
            self.running = False
            self.reset()


        elif action == 'power_key':
            self._power_key.set_high()   # release (ensures edge on re-press)
            self._p02_driver.set_low()   # P0.2 low (wake)
            self._power_key.set_low()    # P0.4 low (key pressed)

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
            if emulator.running:
                emulator.step_batch()
                emulator.state_changed.notify_all()
        if emulator.running:
            emulator.governor.throttle()
        else:
            time.sleep(0.05)
