"""
k0emu web frontend server.

Runs the 78K/0 emulator and serves a web UI over WebSocket.
The frontend shows registers, disassembly, display buffer, and
provides start/stop control.

Usage: pypy3 server.py <rom.bin>
"""

import sys
import os
import json
import asyncio
import time
import http.server
import threading
from collections import deque

import websockets

# Add k0emu to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'k0emu-main'))

from k0dasm.disassemble import disassemble
from k0emu.system import make_processor, populate_eeprom, patch_rom, configure_interrupts
from k0emu.processor import RegisterPairs, Flags


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
        patch_rom(self.proc)
        self.proc.bus.reset()
        configure_interrupts(self.proc)
        # S-Contact (P9.0) left low = ignition off, alarm LED will blink
        self.upd = self.proc.bus.device("csi30").target
        self.running = False
        self._trace = False
        self.steps_per_frame = 50000
        self.potential_mhz = 0.0  # raw execution speed (no throttle)
        self.real_mhz = 0.0      # actual throughput (with throttle)
        self._epoch_time = 0.0   # wall-clock time when run started
        self._epoch_cycles = 0   # cycle count when run started
        self._disasm_history = deque(maxlen=20)
        self.speed_pct = 100     # 0-100, throttle target as % of real clock
        self._listing = listing

    def get_state(self):
        proc = self.proc
        psw = proc.read_psw()

        # Current instruction (not yet executed)
        try:
            dasm = disassemble(proc.bus, proc.pc)
            hex_str = ' '.join(["%02x" % x for x in dasm.all_bytes])
            current = {'addr': proc.pc, 'hex': hex_str, 'inst': str(dasm)}
        except Exception:
            hex_str = "%02x" % proc.bus.read(proc.pc)
            current = {'addr': proc.pc, 'hex': hex_str, 'inst': '???'}

        # Display pixels from UPD16432B
        display_pixels = bytes(self.upd.get_display_pixels()).hex()

        # LED
        led = not bool(proc.bus.read(0xFF03) & 0x08)

        # Voltage
        t30 = proc.bus.read(0xF18D) * 0.1

        # Real speed (measured after throttle sleep)
        wall_since_epoch = time.monotonic() - self._epoch_time
        if wall_since_epoch > 0 and self.running:
            self.real_mhz = ((proc.total_cycles - self._epoch_cycles) / wall_since_epoch) / 1_000_000

        # RAM dumps
        exp_ram = proc.bus.device("expansion_ram")._data
        hs_ram = proc.bus.device("high_speed_ram")._data

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
            'led': led,
            't30': round(t30, 1),
            'real_mhz': round(self.real_mhz, 2),
            'potential_mhz': round(self.potential_mhz, 2),
            'exp_ram': bytes(exp_ram).hex(),
            'exp_ram_base': 0xF000,
            'hs_ram': bytes(hs_ram).hex(),
            'hs_ram_base': 0xFB00,
            'listing_slice': self.get_listing_slice(),
        }

    CLOCK_HZ = 4_190_000

    def start_run(self):
        self._epoch_time = time.monotonic()
        self._epoch_cycles = self.proc.total_cycles
        self.running = True

    def _record_instruction(self):
        proc = self.proc
        try:
            dasm = disassemble(proc.bus, proc.pc)
            hex_str = ' '.join(["%02x" % x for x in dasm.all_bytes])
            self._disasm_history.append({'addr': proc.pc, 'hex': hex_str, 'inst': str(dasm)})
        except Exception:
            hex_str = "%02x" % proc.bus.read(proc.pc)
            self._disasm_history.append({'addr': proc.pc, 'hex': hex_str, 'inst': '???'})

    def step_batch(self):
        t0 = time.monotonic()
        c0 = self.proc.total_cycles
        tail = self._disasm_history.maxlen
        head_count = self.steps_per_frame - tail
        # Run most steps without recording
        last_pc = None
        for _ in range(head_count):
            pc = self.proc.pc
            if pc != last_pc and last_pc is not None:
                # non-halt instruction
                if self._trace:
                    sys.stderr.write("  PC=%04X\n" % pc)
            last_pc = pc
            self.proc.step()
        # Record the last N steps
        for _ in range(tail):
            self._record_instruction()
            self.proc.step()
        elapsed = time.monotonic() - t0
        if elapsed > 0:
            self.potential_mhz = ((self.proc.total_cycles - c0) / elapsed) / 1_000_000

    def throttle_delay(self):
        """Return seconds to sleep to maintain target speed."""
        if self.speed_pct <= 0:
            return 0.05  # paused, just idle
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
        self._record_instruction()
        self.proc.step()


async def handle_client(websocket, emulator):
    # Send initial state
    await websocket.send(json.dumps(emulator.get_state()))

    async def run_loop():
        while emulator.running:
            if emulator.speed_pct > 0:
                emulator.step_batch()
                await websocket.send(json.dumps(emulator.get_state()))
                delay = emulator.throttle_delay()
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0.05)

    run_task = None

    async for message in websocket:
        cmd = json.loads(message)
        action = cmd.get('action')

        if action == 'start':
            emulator.start_run()
            if run_task is None or run_task.done():
                run_task = asyncio.create_task(run_loop())

        elif action == 'stop':
            emulator.running = False
            if run_task:
                await run_task
                run_task = None
            await websocket.send(json.dumps(emulator.get_state()))

        elif action == 'step':
            if not emulator.running:
                emulator.step_one()
                await websocket.send(json.dumps(emulator.get_state()))

        elif action == 'reset':
            emulator.running = False
            if run_task:
                await run_task
                run_task = None
            emulator.reset()
            await websocket.send(json.dumps(emulator.get_state()))

        elif action == 'speed':
            emulator.speed_pct = cmd.get('value', 100)
            # Reset epoch so throttle recalibrates from this point
            emulator._epoch_time = time.monotonic()
            emulator._epoch_cycles = emulator.proc.total_cycles

        elif action == 'power_key':
            sys.stderr.write("POWER KEY pressed\n")
            p0 = emulator.proc.bus.device("p0")
            p0.press_power_key()

        elif action == 'key_down':
            upd = emulator.upd
            upd.key_data[cmd['byte']] |= cmd['mask']

        elif action == 'key_up':
            upd = emulator.upd
            upd.key_data[cmd['byte']] &= ~cmd['mask']

        elif action == 'state':
            await websocket.send(json.dumps(emulator.get_state()))


def serve_http(port):
    """Serve static files from the current directory."""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(('', port), handler)
    httpd.serve_forever()


async def main(rom_path):
    listing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'listing.json')
    listing = Listing(listing_path) if os.path.exists(listing_path) else None
    emulator = Emulator(rom_path, listing)

    # Start HTTP server in background thread
    http_port = 8080
    ws_port = 8765
    http_thread = threading.Thread(target=serve_http, args=(http_port,), daemon=True)
    http_thread.start()

    print("k0emu web frontend")
    print("  HTTP: http://localhost:%d" % http_port)
    print("  WebSocket: ws://localhost:%d" % ws_port)
    print()
    print("Open http://localhost:%d in a browser." % http_port)

    async with websockets.serve(
        lambda ws: handle_client(ws, emulator),
        "localhost", ws_port
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
