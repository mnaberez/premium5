import unittest
from premium5.nec import (NECTransmitter, NECReceiver, Symbol,
                          START_SYMBOL, ZERO_SYMBOL, ONE_SYMBOL,
                          REPEAT_SYMBOL, STOP_SYMBOL, TIMEOUT_TICKS)
from premium5.digital import LogicOutput


class NECTransmitterTests(unittest.TestCase):

    def setUp(self):
        self.completions = []
        self.tx = NECTransmitter(0xAA, 0x55,
                                 lambda: self.completions.append(True))

    def test_data_out_idles_low(self):
        self.assertTrue(self.tx.data_out.low)

    def test_not_busy_initially(self):
        self.assertFalse(self.tx.busy)

    def test_busy_during_transmission(self):
        self.tx.send(0x08)
        self.assertTrue(self.tx.busy)

    def test_data_out_goes_high_on_send(self):
        self.tx.send(0x08)
        self.assertTrue(self.tx.data_out.high)

    def test_data_out_returns_to_idle_after_packet(self):
        self.tx.send(0x08)
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
        self.assertTrue(self.tx.data_out.low)
        self.assertFalse(self.tx.busy)

    def test_on_complete_fires(self):
        self.tx.send(0x08)
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
        self.assertEqual(len(self.completions), 1)

    def test_start_mark_timing(self):
        self.tx.send(0x08)
        # data_out starts HIGH (mark)
        self.assertTrue(self.tx.data_out.high)
        # Tick through the start mark (9009 ticks)
        for _ in range(9008):
            self.tx.tick_1mhz()
            self.assertTrue(self.tx.data_out.high)
        self.tx.tick_1mhz()  # transition to LOW (space)
        self.assertTrue(self.tx.data_out.low)

    def test_tick_with_bulk_ticks(self):
        self.tx.send(0x08)
        self.tx.tick_1mhz(9009)
        self.assertTrue(self.tx.data_out.low)  # past start mark, now in start space

    def test_tick_while_idle_is_harmless(self):
        for _ in range(1000):
            self.tx.tick_1mhz()
        self.assertTrue(self.tx.data_out.low)
        self.assertFalse(self.tx.busy)

    def test_can_send_after_complete(self):
        self.tx.send(0x08)
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
        self.assertFalse(self.tx.busy)
        self.tx.send(0x27)
        self.assertTrue(self.tx.busy)

    def test_packet_has_correct_headers(self):
        rx = self._receive_packet(0x08)
        self.assertEqual(rx[0], 0xAA)
        self.assertEqual(rx[1], 0x55)

    def test_packet_has_correct_command(self):
        rx = self._receive_packet(0x08)
        self.assertEqual(rx[2], 0x08)

    def test_packet_has_correct_checksum(self):
        rx = self._receive_packet(0x08)
        self.assertEqual(rx[3], 0x08 ^ 0xFF)

    def test_packet_command_0x00(self):
        rx = self._receive_packet(0x00)
        self.assertEqual(rx, [0xAA, 0x55, 0x00, 0xFF])

    def test_packet_command_0xff(self):
        rx = self._receive_packet(0xFF)
        self.assertEqual(rx, [0xAA, 0x55, 0xFF, 0x00])

    # repeat()

    def test_repeat_busy(self):
        self.tx.repeat()
        self.assertTrue(self.tx.busy)

    def test_repeat_completes(self):
        self.tx.repeat()
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
        self.assertFalse(self.tx.busy)
        self.assertEqual(len(self.completions), 1)

    def test_repeat_returns_to_idle(self):
        self.tx.repeat()
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
        self.assertTrue(self.tx.data_out.low)

    def _receive_packet(self, command):
        """Send a command, capture edges, decode 4 bytes."""
        self.tx.send(command)
        edges = []
        prev = self.tx.data_out.high
        total = 0
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
            total += 1
            if self.tx.data_out.high != prev:
                edges.append((total, prev))
                total = 0
                prev = self.tx.data_out.high
            if not self.tx.busy:
                if total > 0:
                    edges.append((total, prev))
                break
        # skip start symbol (2 edges)
        bit_edges = edges[2:]
        bits = []
        for i in range(0, 64, 2):
            period = bit_edges[i][0] + bit_edges[i + 1][0]
            bits.append(1 if period > 1800 else 0)
        rx_bytes = []
        for byte_idx in range(4):
            val = 0
            for bit_idx in range(8):
                val |= bits[byte_idx * 8 + bit_idx] << bit_idx
            rx_bytes.append(val)
        return rx_bytes


class NECReceiverTests(unittest.TestCase):

    def setUp(self):
        self.commands = []
        self.repeats = []
        self.rx = NECReceiver(0xCA, 0x34, self.commands.append,
                              lambda: self.repeats.append(True))
        self.signal = LogicOutput()
        self.signal.drives(self.rx.data_in)

    def _start_bit(self):
        self.signal.set_high()
        self.rx.tick_1mhz(START_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(START_SYMBOL.space_ticks)

    def _send_repeat(self):
        """Send a repeat frame: repeat symbol + stop mark + falling edge."""
        # repeat symbol (mark + space)
        self.signal.set_high()
        self.rx.tick_1mhz(REPEAT_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(REPEAT_SYMBOL.space_ticks)
        # stop mark + falling edge
        self.signal.set_high()
        self.rx.tick_1mhz(STOP_SYMBOL.mark_ticks)
        self.signal.set_low()

    def _send_packet(self, *data_bytes):
        """Send a complete packet:
           start symbol + data bytes + stop mark + falling edge."""

        self._start_bit()

        # data bytes, LSB first
        for byte in data_bytes:
            for i in range(8):
                bit = (byte >> i) & 1

                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)

                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        # stop mark + falling edge
        self.signal.set_high()
        self.rx.tick_1mhz(STOP_SYMBOL.mark_ticks)
        self.signal.set_low()

    # valid commands

    def test_receives_command_0x08(self):
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self.assertEqual(self.commands, [0x08])

    def test_receives_command_0x27(self):
        self._send_packet(0xCA, 0x34, 0x27, 0xD8)
        self.assertEqual(self.commands, [0x27])

    def test_receives_two_commands(self):
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self._send_packet(0xCA, 0x34, 0x27, 0xD8)
        self.assertEqual(self.commands, [0x08, 0x27])

    # validation

    def test_rejects_packet_too_short(self):
        self._send_packet(0xCA, 0x34)
        self.assertEqual(self.commands, [])

    def test_truncates_at_32_bits(self):
        # The receiver accepts the first 32 bits and treats the next
        # mark as the stop pulse.  Extra bits after that are ignored.
        self._send_packet(0xCA, 0x34, 0x08, 0xF7, 0x00)
        self.assertEqual(self.commands, [0x08])

    def test_rejects_bad_first_header_byte(self):
        self._send_packet(0xCA + 1, 0x34, 0x08, 0xF7)
        self.assertEqual(self.commands, [])

    def test_rejects_bad_second_header_byte(self):
        self._send_packet(0xCA, 0x34 + 1, 0x08, 0xF7)
        self.assertEqual(self.commands, [])

    def test_rejects_bad_checksum(self):
        self._send_packet(0xCA, 0x34, 0x08, 0x00)
        self.assertEqual(self.commands, [])

    # noise rejection

    def test_noise_before_command_is_ignored(self):
        # short glitches
        self.signal.set_high()
        self.rx.tick_1mhz(100)
        self.signal.set_low()
        self.rx.tick_1mhz(100)

        # then a real command
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self.assertEqual(self.commands, [0x08])

    # partial reception

    def test_partial_reception_discarded_by_timeout(self):
        # start bit + 2 bytes of garbage
        self._start_bit()

        for _ in range(16):
            self.signal.set_high()
            self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
            self.signal.set_low()
            self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        # timeout discards the partial bits
        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [])

        # next command after timeout works
        self._send_packet(0xCA, 0x34, 0x27, 0xD8)
        self.assertEqual(self.commands, [0x27])

    # mark timeout

    def test_mark_timeout_discards_bits(self):
        self._start_bit()

        for _ in range(8):
            self.signal.set_high()
            self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
            self.signal.set_low()
            self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        # stuck in mark — timeout
        self.signal.set_high()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)
        self.signal.set_low()
        self.rx.tick_1mhz(100)

        # now a real command should still work
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self.assertEqual(self.commands, [0x08])

    # timing tolerance (±20%)

    def test_accepts_start_mark_at_minus_20_percent(self):
        self.signal.set_high()
        self.rx.tick_1mhz(START_SYMBOL.mark_range.start)
        self.signal.set_low()
        self.rx.tick_1mhz(START_SYMBOL.space_ticks)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_start_mark_at_plus_20_percent(self):
        self.signal.set_high()
        self.rx.tick_1mhz(START_SYMBOL.mark_range.stop - 1)
        self.signal.set_low()
        self.rx.tick_1mhz(START_SYMBOL.space_ticks)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_rejects_start_mark_too_short(self):
        self.signal.set_high()
        self.rx.tick_1mhz(START_SYMBOL.mark_range.start - 1)
        self.signal.set_low()
        self.rx.tick_1mhz(START_SYMBOL.space_ticks)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [])

    def test_accepts_start_space_at_minus_20_percent(self):
        self.signal.set_high()
        self.rx.tick_1mhz(START_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(START_SYMBOL.space_range.start)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_data_mark_at_minus_20_percent(self):
        self._start_bit()

        mark_ticks = ZERO_SYMBOL.mark_range.start
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        self.signal.set_high()
        self.rx.tick_1mhz(mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_data_mark_at_plus_20_percent(self):
        self._start_bit()

        mark_ticks = ZERO_SYMBOL.mark_range.stop - 1
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)

        self.signal.set_high()
        self.rx.tick_1mhz(mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_zero_space_at_minus_20_percent(self):
        self._start_bit()

        zero_space = ZERO_SYMBOL.space_range.start
        one_space = ONE_SYMBOL.space_ticks
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                self.rx.tick_1mhz(one_space if bit else zero_space)

        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_one_space_at_plus_20_percent(self):
        self._start_bit()

        one_space = ONE_SYMBOL.space_range.stop - 1
        zero_space = ZERO_SYMBOL.space_ticks
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                self.rx.tick_1mhz(one_space if bit else zero_space)

        self.signal.set_high()
        self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    # repeat

    def test_receives_repeat(self):
        self._send_repeat()
        self.assertEqual(len(self.repeats), 1)

    def test_repeat_does_not_fire_on_command(self):
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self.assertEqual(len(self.repeats), 0)

    def test_command_after_repeat(self):
        self._send_repeat()
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self.assertEqual(len(self.repeats), 1)
        self.assertEqual(self.commands, [0x08])

    # stop mark validation

    def test_rejects_repeat_with_bad_stop_mark(self):
        # repeat symbol
        self.signal.set_high()
        self.rx.tick_1mhz(REPEAT_SYMBOL.mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(REPEAT_SYMBOL.space_ticks)
        # stop mark too long
        self.signal.set_high()
        self.rx.tick_1mhz(STOP_SYMBOL.mark_range.stop)
        self.signal.set_low()
        self.assertEqual(len(self.repeats), 0)

    def test_rejects_command_with_bad_stop_mark(self):
        self._start_bit()
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(ZERO_SYMBOL.mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(ONE_SYMBOL.space_ticks)
                else:
                    self.rx.tick_1mhz(ZERO_SYMBOL.space_ticks)
        # stop mark too long
        self.signal.set_high()
        self.rx.tick_1mhz(STOP_SYMBOL.mark_range.stop)
        self.signal.set_low()
        self.assertEqual(self.commands, [])



class NECEndToEndTests(unittest.TestCase):

    def setUp(self):
        self.commands = []
        self.repeats = []
        self.tx = NECTransmitter(0xAA, 0x55, lambda: None)
        self.rx = NECReceiver(0xAA, 0x55, self.commands.append,
                              lambda: self.repeats.append(True))
        self.tx.data_out.drives(self.rx.data_in)

    def _tick(self, ticks):
        for _ in range(ticks):
            self.tx.tick_1mhz()
            self.rx.tick_1mhz(1)

    def test_receives_command_0x00(self):
        self.tx.send(0x00)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x00])

    def test_receives_command_0x08(self):
        self.tx.send(0x08)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x08])

    def test_receives_command_0x27(self):
        self.tx.send(0x27)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x27])

    def test_receives_command_0xff(self):
        self.tx.send(0xFF)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0xFF])

    def test_receives_two_commands(self):
        self.tx.send(0x08)
        self._tick(1_000_000)
        self.tx.send(0x27)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x08, 0x27])

    def test_receives_repeat(self):
        self.tx.repeat()
        self._tick(1_000_000)
        self.assertEqual(len(self.commands), 0)
        self.assertEqual(len(self.repeats), 1)


class SymbolTests(unittest.TestCase):

    def test_detects_exact_nominal(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertTrue(s.detect(mark_ticks=1000, space_ticks=500))

    def test_detects_at_minus_20_percent(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertTrue(s.detect(mark_ticks=800, space_ticks=400))

    def test_detects_at_plus_20_percent(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertTrue(s.detect(mark_ticks=1200, space_ticks=600))

    def test_rejects_mark_too_short(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertFalse(s.detect(mark_ticks=799, space_ticks=500))

    def test_rejects_mark_too_long(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertFalse(s.detect(mark_ticks=1201, space_ticks=500))

    def test_rejects_space_too_short(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertFalse(s.detect(mark_ticks=1000, space_ticks=399))

    def test_rejects_space_too_long(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertFalse(s.detect(mark_ticks=1000, space_ticks=601))

    def test_rejects_both_out_of_range(self):
        s = Symbol(mark_ticks=1000, space_ticks=500)
        self.assertFalse(s.detect(mark_ticks=799, space_ticks=399))

    def test_min_ticks_never_below_one(self):
        s = Symbol(mark_ticks=1, space_ticks=1)
        self.assertTrue(s.detect(mark_ticks=1, space_ticks=1))
        self.assertFalse(s.detect(mark_ticks=0, space_ticks=1))
        self.assertFalse(s.detect(mark_ticks=1, space_ticks=0))
