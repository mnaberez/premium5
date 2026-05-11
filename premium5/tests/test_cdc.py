import unittest
from premium5.cdc import CDCReceiver
from premium5.digital import LogicOutput


class CDCReceiverTests(unittest.TestCase):

    def setUp(self):
        self.commands = []
        self.rx = CDCReceiver(lambda cmd: self.commands.append(cmd))
        self.signal = LogicOutput()
        self.signal.drives(self.rx.cmd_in)

    def _start_bit(self):
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.START_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.START_SPACE_TICKS)

    def _send_packet(self, *data_bytes):
        """Send a complete packet:
           start bit + data bytes + trailing mark + timeout."""

        self._start_bit()

        # data bytes, LSB first
        for byte in data_bytes:
            for i in range(8):
                bit = (byte >> i) & 1

                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)

                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        # trailing mark + timeout
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

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

    def test_rejects_packet_too_long(self):
        self._send_packet(0xCA, 0x34, 0x08, 0xF7, 0x00)
        self.assertEqual(self.commands, [])

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
            self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
            self.signal.set_low()
            self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        # timeout discards the partial bits
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [])

        # next command after timeout works
        self._send_packet(0xCA, 0x34, 0x27, 0xD8)
        self.assertEqual(self.commands, [0x27])

    def test_start_bit_resets_mid_stream(self):
        # start bit + 2 bytes of garbage
        self._start_bit()

        for _ in range(16):
            self.signal.set_high()
            self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
            self.signal.set_low()
            self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        # new start bit resets, then real command
        self._send_packet(0xCA, 0x34, 0x27, 0xD8)
        self.assertEqual(self.commands, [0x27])

    # mark timeout

    def test_mark_timeout_discards_bits(self):
        self._start_bit()

        for _ in range(8):
            self.signal.set_high()
            self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
            self.signal.set_low()
            self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        # stuck in mark — timeout
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)
        self.signal.set_low()
        self.rx.tick_1mhz(100)

        # now a real command should still work
        self._send_packet(0xCA, 0x34, 0x08, 0xF7)
        self.assertEqual(self.commands, [0x08])

    # timing tolerance (±20%)

    def test_accepts_start_mark_at_minus_20_percent(self):
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.START_SYMBOL._mark.start)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.START_SPACE_TICKS)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_start_mark_at_plus_20_percent(self):
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.START_SYMBOL._mark.stop - 1)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.START_SPACE_TICKS)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_rejects_start_mark_too_short(self):
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.START_SYMBOL._mark.start - 1)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.START_SPACE_TICKS)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [])

    def test_accepts_start_space_at_minus_20_percent(self):
        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.START_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.START_SYMBOL._space.start)

        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_data_mark_at_minus_20_percent(self):
        self._start_bit()

        mark_ticks = self.rx.ZERO_SYMBOL._mark.start
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        self.signal.set_high()
        self.rx.tick_1mhz(mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_data_mark_at_plus_20_percent(self):
        self._start_bit()

        mark_ticks = self.rx.ZERO_SYMBOL._mark.stop - 1
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(mark_ticks)
                self.signal.set_low()
                if bit:
                    self.rx.tick_1mhz(self.rx.ONE_SPACE_TICKS)
                else:
                    self.rx.tick_1mhz(self.rx.ZERO_SPACE_TICKS)

        self.signal.set_high()
        self.rx.tick_1mhz(mark_ticks)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_zero_space_at_minus_20_percent(self):
        self._start_bit()

        zero_space = self.rx.ZERO_SYMBOL._space.start
        one_space = self.rx.ONE_SPACE_TICKS
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
                self.signal.set_low()
                self.rx.tick_1mhz(one_space if bit else zero_space)

        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])

    def test_accepts_one_space_at_plus_20_percent(self):
        self._start_bit()

        one_space = self.rx.ONE_SYMBOL._space.stop - 1
        zero_space = self.rx.ZERO_SPACE_TICKS
        for byte in [0xCA, 0x34, 0x08, 0xF7]:
            for i in range(8):
                bit = (byte >> i) & 1
                self.signal.set_high()
                self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
                self.signal.set_low()
                self.rx.tick_1mhz(one_space if bit else zero_space)

        self.signal.set_high()
        self.rx.tick_1mhz(self.rx.DATA_MARK_TICKS)
        self.signal.set_low()
        self.rx.tick_1mhz(self.rx.TIMEOUT_TICKS + 1)

        self.assertEqual(self.commands, [0x08])
