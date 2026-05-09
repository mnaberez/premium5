import unittest
from premium5.digital import Level, LogicOutput
from premium5.fis import FIS, FISReceiver, FISInterpreter


class FISReceiverTestCase(unittest.TestCase):
    """Base class for FIS receiver tests"""

    def setUp(self):
        self.packets = []
        self.fis = FISReceiver(self.packets.append)
        self.clk = LogicOutput(Level.HIGH)   # CPOL=1: idles HIGH
        self.dat = LogicOutput(Level.HIGH)
        self.ena = LogicOutput(Level.LOW)    # ENA idles LOW
        self.clk.drives(self.fis.clk_in)
        self.dat.drives(self.fis.dat_in)
        self.ena.drives(self.fis.ena_in)

    def _radio_text_packet(self):
        """A well-formed 0x81 radio text packet: "FM1 1   " / " 93.5MHZ" """
        return self._build_packet(0x81, b'\xF0FM1 1    93.5MHZ')

    def _ena_pulse(self):
        """Pulse ENA high then low with enough ticks to pass the minimum."""
        self.ena.set_high()
        self.fis.tick_1mhz(self.fis.WAITING_FOR_ENA_MIN.ticks)
        self.ena.set_low()

    def _clock_byte(self, byte_val):
        """Clock out 8 bits MSB first on DAT/CLK."""
        for bit in range(8):
            if byte_val & (0x80 >> bit):
                self.dat.set_high()
            else:
                self.dat.set_low()
            self.clk.set_low()
            self.clk.set_high()

    def _ack_wait(self):
        """Tick until the ENA ack delay expires."""
        self.fis.tick_1mhz(self.fis.DELAYING_ENA_ACK.ticks)

    def _send_packet(self, packet):
        """Send a complete packet through the ENA/CLK/DAT handshake."""
        self._ena_pulse()
        for i, byte_val in enumerate(packet):
            self._clock_byte(byte_val)
            if i < len(packet) - 1:
                self._ack_wait()

    def _build_packet(self, cmd, data):
        """Build a FIS packet with checksum.
        Length byte counts data + checksum."""
        length = len(data) + 1
        body = bytes([cmd, length]) + data
        csum = 0
        for b in body:
            csum ^= b
        return body + bytes([(csum - 1) & 0xFF])


class InitialStateTests(FISReceiverTestCase):

    def test_starts_in_waiting_for_ena_rise(self):
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    def test_ena_out_starts_low(self):
        self.assertTrue(self.fis.ena_out.low)

    def test_no_packets_received_initially(self):
        self.assertEqual(self.packets, [])


class ENAPulseTests(FISReceiverTestCase):

    # ENA rising edge

    def test_ena_rise_transitions_to_waiting_for_ena_min(self):
        self.ena.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_MIN)

    def test_ena_rise_ignored_when_not_idle(self):
        self._ena_pulse()
        # now in WAITING_FOR_CLK_FALL; spurious ENA rise should abort
        self.ena.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    # ENA pulse too short

    def test_ena_fall_before_minimum_aborts(self):
        self.ena.set_high()
        self.fis.tick_1mhz(self.fis.WAITING_FOR_ENA_MIN.ticks - 1)
        self.ena.set_low()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    # ENA pulse minimum met

    def test_minimum_met_transitions_to_waiting_for_ena_max(self):
        self.ena.set_high()
        self.fis.tick_1mhz(self.fis.WAITING_FOR_ENA_MIN.ticks)
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_MAX)

    # ENA pulse within valid range

    def test_ena_fall_after_minimum_transitions_to_waiting_for_clk(self):
        self.ena.set_high()
        self.fis.tick_1mhz(self.fis.WAITING_FOR_ENA_MIN.ticks)
        self.ena.set_low()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_CLK_FALL)

    # ENA pulse too long

    def test_ena_stuck_high_aborts(self):
        self.ena.set_high()
        self.fis.tick_1mhz(self.fis.WAITING_FOR_ENA_MIN.ticks)
        self.fis.tick_1mhz(self.fis.WAITING_FOR_ENA_MAX.ticks)
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)


class CLKFallingEdgeTests(FISReceiverTestCase):

    # First CLK edge after ENA pulse

    def test_first_clk_transitions_to_receiving_bit(self):
        self._ena_pulse()
        self.clk.set_low()
        self.assertIs(self.fis._state, self.fis.RECEIVING_BIT)

    def test_first_clk_pulls_ena_out_low(self):
        self._ena_pulse()
        # simulate post-ack: manually set ena_out high
        self.fis.ena_out.set_high()
        self.clk.set_low()
        self.assertTrue(self.fis.ena_out.low)

    # CLK ignored in wrong states

    def test_clk_ignored_during_ena_pulse(self):
        self.ena.set_high()
        self.clk.set_low()
        self.clk.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_MIN)

    def test_clk_ignored_when_idle(self):
        self.clk.set_low()
        self.clk.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    # Timeout waiting for CLK

    def test_waiting_for_clk_timeout_aborts(self):
        self._ena_pulse()
        self.fis.tick_1mhz(self.fis.WAITING_FOR_CLK_FALL.ticks)
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)


class ReceivingBitTests(FISReceiverTestCase):

    def test_shifts_in_8_bits(self):
        self._ena_pulse()
        self._clock_byte(0xA5)
        self.assertIs(self.fis._state, self.fis.DELAYING_ENA_ACK)
        self.assertEqual(self.fis._packet, bytearray([0xA5]))

    def test_bit_timeout_aborts(self):
        self._ena_pulse()
        # clock in 4 bits then let it time out
        for bit in range(4):
            self.dat.set_high()
            self.clk.set_low()
            self.clk.set_high()
        self.fis.tick_1mhz(self.fis.RECEIVING_BIT.ticks)
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    def test_bit_timeout_resets_on_each_clk(self):
        self._ena_pulse()
        # tick almost to timeout, then clock a bit to reset
        self.dat.set_high()
        self.clk.set_low()
        self.clk.set_high()
        self.fis.tick_1mhz(self.fis.RECEIVING_BIT.ticks - 1)
        self.assertIs(self.fis._state, self.fis.RECEIVING_BIT)
        # another bit resets the countdown
        self.clk.set_low()
        self.clk.set_high()
        self.fis.tick_1mhz(self.fis.RECEIVING_BIT.ticks - 1)
        self.assertIs(self.fis._state, self.fis.RECEIVING_BIT)


class ENAAckTests(FISReceiverTestCase):

    def test_ack_delay_drives_ena_high(self):
        self._ena_pulse()
        self._clock_byte(0x81)  # cmd byte, more bytes expected
        self.assertTrue(self.fis.ena_out.low)
        self._ack_wait()
        self.assertTrue(self.fis.ena_out.high)

    def test_ack_delay_transitions_to_waiting_for_clk(self):
        self._ena_pulse()
        self._clock_byte(0x81)
        self._ack_wait()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_CLK_FALL)

    def test_first_clk_after_ack_pulls_ena_low(self):
        self._ena_pulse()
        self._clock_byte(0x81)
        self._ack_wait()
        self.assertTrue(self.fis.ena_out.high)
        # first CLK of next byte
        self.dat.set_high()
        self.clk.set_low()
        self.assertTrue(self.fis.ena_out.low)


class PacketAssemblyTests(FISReceiverTestCase):

    def test_second_byte_sets_expected_length(self):
        self._ena_pulse()
        self._clock_byte(0x81)  # cmd
        self._ack_wait()
        self._clock_byte(0x12)  # length=18
        self.assertEqual(self.fis._bytes_expected, 20)  # 18 + 2

    def test_bad_checksum_does_not_deliver_packet(self):
        packet = bytearray(self._radio_text_packet())
        packet[-1] ^= 0xFF  # corrupt checksum
        self._send_packet(packet)
        self.assertEqual(self.packets, [])

    def test_minimal_valid_packet_is_delivered(self):
        # cmd + length + checksum = 3 bytes, valid checksum
        packet = self._build_packet(0x81, b'')
        self._send_packet(packet)
        self.assertEqual(len(self.packets), 1)


class SpuriousEdgeTests(FISReceiverTestCase):

    def test_spurious_ena_rise_during_receiving_aborts(self):
        self._ena_pulse()
        self.dat.set_high()
        self.clk.set_low()
        self.clk.set_high()
        self.ena.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    def test_spurious_ena_rise_during_waiting_for_clk_aborts(self):
        self._ena_pulse()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_CLK_FALL)
        self.ena.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    def test_spurious_ena_rise_during_ack_delay_aborts(self):
        self._ena_pulse()
        self._clock_byte(0x81)
        self.assertIs(self.fis._state, self.fis.DELAYING_ENA_ACK)
        self.ena.set_high()
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    def test_ena_fall_while_idle_is_ignored(self):
        self.ena.set_low()  # already low, no edge
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)


class EndToEndTests(FISReceiverTestCase):

    def test_receive_radio_text_packet(self):
        self._send_packet(self._radio_text_packet())
        self.assertEqual(len(self.packets), 1)
        self.assertEqual(self.packets[0][0], 0x81)
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)

    def test_receive_two_packets_consecutively(self):
        self._send_packet(self._radio_text_packet())
        packet2 = self._build_packet(0x81, b'\xF0AM1 1    530 KHZ')
        self._send_packet(packet2)
        self.assertEqual(len(self.packets), 2)

    def test_state_returns_to_idle_after_packet(self):
        self._send_packet(self._radio_text_packet())
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)
        self.assertTrue(self.fis.ena_out.low)
        self.assertEqual(self.fis._countdown, 0)

    def test_abort_does_not_corrupt_next_packet(self):
        # start a packet, abort mid-byte
        self._ena_pulse()
        self.dat.set_high()
        self.clk.set_low()
        self.clk.set_high()
        self.fis.tick_1mhz(self.fis.RECEIVING_BIT.ticks)  # timeout
        self.assertIs(self.fis._state, self.fis.WAITING_FOR_ENA_RISE)
        # now send a full valid packet
        self._send_packet(self._radio_text_packet())
        self.assertEqual(len(self.packets), 1)


class FISInterpreterTests(unittest.TestCase):
    """Tests for FISInterpreter command dispatch and display formatting."""

    def _checksum(self, packet):
        """Append a valid checksum to a packet bytearray."""
        csum = 0
        for b in packet:
            csum ^= b
        packet.append((csum - 1) & 0xFF)
        return packet

    def setUp(self):
        self.intp = FISInterpreter()

    # initial state

    def test_radio_data_starts_as_16_spaces(self):
        self.assertEqual(self.intp.radio_data, bytearray(b' ' * 16))

    # 0x81 radio text: short data padded

    def test_short_data_padded_to_16_bytes(self):
        packet = self._checksum(bytearray(b'\x81\x04\xF0AB'))
        self.intp.interpret(packet)
        self.assertEqual(len(self.intp.radio_data), 16)

    def test_long_data_truncated_to_16_bytes(self):
        packet = self._checksum(bytearray(b'\x81\x1a\xF0' + b'X' * 24))
        self.intp.interpret(packet)
        self.assertEqual(len(self.intp.radio_data), 16)

    # 0x81 radio text: non-printable characters replaced with space

    def test_non_printable_bytes_replaced_with_space(self):
        packet = self._checksum(bytearray(
            b'\x81\x12\xF0\x00AB\x7fCD\x80E\xf0FGHIJ\x1f'))
        self.intp.interpret(packet)
        self.assertEqual(len(self.intp.radio_data), 16)
        self.assertEqual(self.intp.radio_data, bytearray(b'AB CD E  FGHIJ  '))

    # 0x81 radio text: center justification

    def test_lines_are_center_justified(self):
        cases = (
            # trailing whitespace
            (b'A       ', b'   A    '),
            (b'AB      ', b'   AB   '),
            (b'ABC     ', b'  ABC   '),
            (b'ABCD    ', b'  ABCD  '),
            (b'ABCDE   ', b' ABCDE  '),
            (b'ABCDEF  ', b' ABCDEF '),
            (b'ABCDEFG ', b'ABCDEFG '),
            (b'ABCDEFGH', b'ABCDEFGH'),

            # leading whitespace
            (b'       1', b'   1    '),
            (b'      12', b'   12   '),
            (b'     123', b'  123   '),
            (b'    1234', b'  1234  '),
            (b'   12345', b' 12345  '),
            (b'  123456', b' 123456 '),
            (b' 1234567', b'1234567 '),
            (b'12345678', b'12345678'),
        )
        for input_line, expected in cases:
            # test as line 1
            packet = self._checksum(bytearray(b'\x81\x12\xF0' + input_line + b'12345678'))
            self.intp.interpret(packet)
            self.assertEqual(len(self.intp.radio_data), 16)
            self.assertEqual(self.intp.radio_data[:8], bytearray(expected))

            # test as line 2
            packet = self._checksum(bytearray(b'\x81\x12\xF0' + b'12345678' + input_line))
            self.intp.interpret(packet)
            self.assertEqual(len(self.intp.radio_data), 16)
            self.assertEqual(self.intp.radio_data[8:], bytearray(expected))

    # 0x81 radio text: typical decoding

    def test_radio_text_decodes_two_lines(self):
        packet = self._checksum(bytearray(b'\x81\x12\xF0FM1 1    93.5MHZ'))
        self.intp.interpret(packet)
        self.assertEqual(len(self.intp.radio_data), 16)
        self.assertEqual(self.intp.radio_data[:8], bytearray(b' FM1 1  '))
        self.assertEqual(self.intp.radio_data[8:], bytearray(b'93.5MHZ '))

    # unknown command ignored

    def test_unknown_command_does_not_change_radio_data(self):
        packet = self._checksum(bytearray(b'\x99\x12\xF0XXXXXXXXYYYYYYYY'))
        self.intp.interpret(packet)
        self.assertEqual(len(self.intp.radio_data), 16)
        self.assertEqual(self.intp.radio_data, bytearray(b' ' * 16))
