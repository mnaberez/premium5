"""
k0emu web frontend server.

Runs the 78K/0 emulator and serves a web UI over HTTP.
The frontend receives emulator state via Server-Sent Events
and sends commands via HTTP POST.

Usage: pypy3 server.py <rom.bin>
"""

import sys
import os
import json
import asyncio
import time
import mimetypes
from collections import deque

# Add k0emu to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'k0emu-main'))

from k0dasm.disassemble import disassemble
from k0emu.system import make_processor, populate_eeprom, configure_interrupts
from k0emu.processor import RegisterPairs, Flags, RunState
from k0emu.mfsw import MFSWTransmitter


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
        # S-Contact (P9.0) left low = ignition off, alarm LED will blink
        self.upd = self.proc.bus.device("csi30").target
        self.mfsw = MFSWTransmitter()
        self._p0 = self.proc.bus.device("p0")
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

        # Display pixels and pictograph RAM from UPD16432B
        display_pixels = bytes(self.upd.get_display_pixels()).hex()
        pictograph_ram = bytes(self.upd.pictograph_ram).hex()

        # LED
        led = not bool(proc.bus.read(0xFF03) & 0x08)

        # Voltage
        t30 = proc.bus.read(0xF18D) * 0.1

        # Real speed (measured after throttle sleep)
        wall_since_epoch = time.monotonic() - self._epoch_time
        if wall_since_epoch > 0 and self.running:
            self.real_mhz = ((proc.total_cycles - self._epoch_cycles) / wall_since_epoch) / 1_000_000

        # Memory dumps
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
        """Tick the MFSW transmitter and update P0.0."""
        cycles = self.proc.inst_cycles
        self.mfsw.tick(cycles)
        # Wire is active-low, HEF40106BT inverts: wire LOW -> P0.0 HIGH
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
            p0.set_external_input(4, True)   # release (ensures edge on re-press)
            p0.set_external_input(2, False)  # P0.2 low (wake)
            p0.set_external_input(4, False)  # P0.4 low (key pressed)

        elif action == 'key_down':
            self.upd.key_data[cmd['byte']] |= cmd['mask']

        elif action == 'key_up':
            self.upd.key_data[cmd['byte']] &= ~cmd['mask']

        elif action == 'mfsw':
            import k0emu.mfsw as mfsw
            code = cmd.get('code')
            codes = {
                'vol_down': mfsw.VOL_DOWN,
                'vol_up': mfsw.VOL_UP,
                'up': mfsw.UP,
                'down': mfsw.DOWN,
            }
            if code in codes and not self.mfsw.busy:
                self.mfsw.send(codes[code])


WEB_ROOT = os.path.dirname(os.path.abspath(__file__))


async def handle_connection(reader, writer, emulator, sse_clients):
    try:
        while True:
            request_line = await reader.readline()
            if not request_line:
                break

            method, path, _ = request_line.decode().split(' ', 2)
            sys.stderr.write('%s %s\n' % (method, path))

            # Read headers
            headers = {}
            while True:
                line = await reader.readline()
                if line == b'\r\n' or not line:
                    break
                name, _, value = line.decode().partition(':')
                headers[name.strip().lower()] = value.strip()

            if method == 'GET' and path == '/events':
                writer.write(b'HTTP/1.1 200 OK\r\n')
                writer.write(b'Content-Type: text/event-stream\r\n')
                writer.write(b'Cache-Control: no-cache\r\n')
                writer.write(b'Connection: keep-alive\r\n')
                writer.write(b'\r\n')
                await writer.drain()
                sse_clients.add(writer)
                data = json.dumps(emulator.get_state())
                writer.write(('data: %s\n\n' % data).encode())
                await writer.drain()
                try:
                    while not reader.at_eof():
                        await asyncio.sleep(1)
                finally:
                    sse_clients.discard(writer)
                break

            if method == 'POST' and path == '/command':
                content_length = int(headers.get('content-length', 0))
                body = await reader.readexactly(content_length)
                cmd = json.loads(body)
                emulator.handle_command(cmd)
                writer.write(b'HTTP/1.1 204 No Content\r\n')
                writer.write(b'Connection: keep-alive\r\n')
                writer.write(b'\r\n')
                await writer.drain()
                await send_sse_state(emulator, sse_clients)
                continue

            # Static file serving
            if path == '/':
                path = '/index.html'

            file_path = os.path.normpath(os.path.join(WEB_ROOT, path.lstrip('/')))
            if not file_path.startswith(WEB_ROOT):
                writer.write(b'HTTP/1.1 403 Forbidden\r\n'
                             b'Connection: close\r\n\r\n')
                await writer.drain()
                break

            if os.path.isfile(file_path):
                content_type, _ = mimetypes.guess_type(file_path)
                if content_type is None:
                    content_type = 'application/octet-stream'
                with open(file_path, 'rb') as f:
                    body = f.read()
                writer.write(('HTTP/1.1 200 OK\r\n'
                              'Content-Type: %s\r\n'
                              'Content-Length: %d\r\n'
                              'Connection: keep-alive\r\n'
                              '\r\n' % (content_type, len(body))).encode())
                writer.write(body)
                await writer.drain()
                continue
            else:
                writer.write(b'HTTP/1.1 404 Not Found\r\n'
                             b'Connection: close\r\n\r\n')
                await writer.drain()
                break
    except (ConnectionError, asyncio.IncompleteReadError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def send_sse_state(emulator, sse_clients):
    if not sse_clients:
        return
    data = json.dumps(emulator.get_state())
    message = ('data: %s\n\n' % data).encode()
    dead = set()
    for client in sse_clients:
        try:
            client.write(message)
            await client.drain()
        except (ConnectionError, asyncio.CancelledError):
            dead.add(client)
    sse_clients -= dead


async def run_loop(emulator, sse_clients):
    while True:
        if emulator.running and emulator.speed_pct > 0:
            emulator.step_batch()
            await send_sse_state(emulator, sse_clients)
            delay = emulator.throttle_delay()
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0.05)


async def main(rom_path):
    listing_path = os.path.join(WEB_ROOT, 'listing.json')
    listing = Listing(listing_path) if os.path.exists(listing_path) else None
    emulator = Emulator(rom_path, listing)

    sse_clients = set()

    port = 8080
    server = await asyncio.start_server(
        lambda r, w: handle_connection(r, w, emulator, sse_clients),
        'localhost', port
    )

    asyncio.create_task(run_loop(emulator, sse_clients))

    print("k0emu web frontend")
    print("  http://localhost:%d" % port)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
