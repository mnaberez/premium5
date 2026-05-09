import unittest
from premium5.digital import LogicInput, LogicOutput, Level
from premium5.spi import UPD16432B


def _make_upd():
    """Create a UPD16432B with LogicOutputs to drive its inputs."""
    upd = UPD16432B()

    stb = LogicOutput()
    stb.drives(upd.stb_in)

    clk = LogicOutput()
    clk.set_high()
    clk.drives(upd.clk_in)

    dat = LogicOutput()
    dat.drives(upd.dat_in)

    dat_read = LogicInput(pull_level=Level.LOW)
    upd.dat_out.drives(dat_read)

    return upd, stb, clk, dat, dat_read


def _clock_byte(stb, clk, dat, dat_read, tx_byte):
    """Clock one byte through the UPD16432B.
    Returns the byte shifted out by the UPD."""
    rx_byte = 0x00
    for bit_pos in range(8):
        # Falling edge: set data bit (MSB first), read response bit
        tx_bit = (tx_byte >> (7 - bit_pos)) & 1
        if tx_bit:
            dat.set_high()
        else:
            dat.set_low()
        clk.set_low()
        rx_byte |= (int(dat_read) << (7 - bit_pos))

        # Rising edge: UPD latches data bit
        clk.set_high()

    return rx_byte


def _send(stb, clk, dat, dat_read, spi_bytes):
    """Send a complete SPI command (STB high, clock bytes, STB low)."""
    stb.set_high()
    for b in spi_bytes:
        _clock_byte(stb, clk, dat, dat_read, b)
    stb.set_low()


class UPD16432B_InitTests(unittest.TestCase):

    def test_display_ram_initialized_to_zeros(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertEqual(upd.display_ram, bytearray(0x19))

    def test_pictograph_ram_initialized_to_zeros(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertEqual(upd.pictograph_ram, bytearray(0x08))

    def test_chargen_ram_initialized_to_zeros(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertEqual(upd.chargen_ram, bytearray(0x70))

    def test_led_ram_initialized_to_zeros(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertEqual(upd.led_ram, bytearray(0x01))

    def test_key_data_initialized_to_zeros(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertEqual(upd.key_data, bytearray(4))

    def test_current_ram_initially_none(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertIsNone(upd._current_ram)

    def test_address_initially_zero(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertEqual(upd._address, 0)

    def test_increment_initially_false(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertFalse(upd._increment)

    def test_empty_spi_command_does_not_raise(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        stb.set_high()
        stb.set_low()


class UPD16432B_DataSettingTests(unittest.TestCase):

    def test_sets_display_ram_area_increment_off(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000  # data setting command
        cmd |= 0b00000000  # display ram
        cmd |= 0b00001000  # increment off
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.display_ram)
        self.assertFalse(upd._increment)

    def test_sets_display_ram_area_increment_on(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000000
        cmd |= 0b00000000  # increment on
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.display_ram)
        self.assertTrue(upd._increment)

    def test_sets_pictograph_ram_area_increment_off(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000001  # pictograph ram
        cmd |= 0b00001000  # increment off
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.pictograph_ram)
        self.assertFalse(upd._increment)

    def test_sets_chargen_ram_area_increment_on(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000010  # chargen ram
        cmd |= 0b00000000  # increment on
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.chargen_ram)
        self.assertTrue(upd._increment)

    def test_sets_chargen_ram_area_ignores_increment_off(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000010  # chargen ram
        cmd |= 0b00001000  # increment off (should be ignored)
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.chargen_ram)
        self.assertTrue(upd._increment)

    def test_sets_led_ram_area_increment_on(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000011  # led output latch
        cmd |= 0b00000000  # increment on
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.led_ram)
        self.assertTrue(upd._increment)

    def test_sets_led_ram_area_ignores_increment_off(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000011  # led output latch
        cmd |= 0b00001000  # increment off (should be ignored)
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIs(upd._current_ram, upd.led_ram)
        self.assertTrue(upd._increment)

    def test_unrecognized_ram_area_sets_none(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000111  # not a valid ram area
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIsNone(upd._current_ram)
        self.assertEqual(upd._address, 0)

    def test_unrecognized_ram_area_ignores_increment_off(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        cmd  = 0b01000000
        cmd |= 0b00000111  # not a valid ram area
        cmd |= 0b00001000  # increment off (should be ignored)
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertIsNone(upd._current_ram)
        self.assertEqual(upd._address, 0)


class UPD16432B_AddressSettingTests(unittest.TestCase):

    def test_no_current_ram_sets_zero(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        self.assertIsNone(upd._current_ram)
        cmd  = 0b10000000  # address setting command
        cmd |= 0b00000011  # address 0x03
        _send(stb, clk, dat, dat_read, [cmd])
        self.assertEqual(upd._address, 0)

    def test_sets_addresses_for_each_ram_area(self):
        tuples = (
            (0b00000000, 0,       0),  # display min
            (0b00000000, 0x18, 0x18),  # display max
            (0b00000000, 0x19,    0),  # display wraps

            (0b00000001,    0,    0),  # pictograph min
            (0b00000001, 0x07, 0x07),  # pictograph max
            (0b00000001, 0x08,    0),  # pictograph wraps

            (0b00000010,    0,    0),  # chargen min
            (0b00000010, 0x0f, 0x69),  # chargen max
            (0b00000010, 0x10,    0),  # chargen wraps

            (0b00000011,    0,    0),  # led min
            (0b00000011,    0,    0),  # led max
            (0b00000011,    1,    0),  # led wraps
        )
        for ram_select_bits, address, expected_address in tuples:
            upd, stb, clk, dat, dat_read = _make_upd()
            # data setting command
            _send(stb, clk, dat, dat_read, [0b01000000 | ram_select_bits])
            # address setting command
            _send(stb, clk, dat, dat_read, [0b10000000 | address])
            self.assertEqual(upd._address, expected_address)


class UPD16432B_WritingDataTests(unittest.TestCase):

    def test_no_ram_area_ignores_data(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        old_display = bytes(upd.display_ram)
        old_picto = bytes(upd.pictograph_ram)
        old_chargen = bytes(upd.chargen_ram)
        old_led = bytes(upd.led_ram)
        cmd = 0b10000000 | 0  # address 0
        data = list(range(1, 8))
        _send(stb, clk, dat, dat_read, [cmd] + data)
        self.assertEqual(bytes(upd.display_ram), old_display)
        self.assertEqual(bytes(upd.pictograph_ram), old_picto)
        self.assertEqual(bytes(upd.chargen_ram), old_chargen)
        self.assertEqual(bytes(upd.led_ram), old_led)

    def test_display_ram_increment_on_writes_data(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        _send(stb, clk, dat, dat_read, [0b01000000])  # display ram, increment on
        cmd = 0b10000000 | 0  # address 0
        data = list(range(1, 26))
        _send(stb, clk, dat, dat_read, [cmd] + data)
        self.assertTrue(upd._increment)
        self.assertEqual(upd._address, 0)  # wrapped around
        self.assertEqual(upd.display_ram, bytearray(data))

    def test_display_ram_increment_off_rewrites_same_address(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        _send(stb, clk, dat, dat_read, [0b01001000])  # display ram, increment off
        _send(stb, clk, dat, dat_read, [0b10000000, 0xAA, 0xBB])  # address 0, data
        self.assertEqual(upd.display_ram[0], 0xBB)
        self.assertEqual(upd.display_ram[1], 0x00)

    def test_pictograph_ram_increment_on_writes_data(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        _send(stb, clk, dat, dat_read, [0b01000001])  # pictograph ram, increment on
        data = list(range(1, 9))
        _send(stb, clk, dat, dat_read, [0b10000000] + data)
        self.assertEqual(upd.pictograph_ram, bytearray(data))

    def test_pictograph_ram_increment_off_rewrites_same_address(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        _send(stb, clk, dat, dat_read, [0b01001001])  # pictograph ram, increment off
        _send(stb, clk, dat, dat_read, [0b10000000, 0xAA, 0xBB])
        self.assertEqual(upd.pictograph_ram[0], 0xBB)
        self.assertEqual(upd.pictograph_ram[1], 0x00)


class UPD16432B_KeyDataTests(unittest.TestCase):

    def test_key_data_returned(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        upd.key_data[0] = 0xAA
        upd.key_data[1] = 0xBB
        upd.key_data[2] = 0xCC
        upd.key_data[3] = 0xDD
        stb.set_high()
        _clock_byte(stb, clk, dat, dat_read, 0x44)  # key data request
        r0 = _clock_byte(stb, clk, dat, dat_read, 0x00)
        r1 = _clock_byte(stb, clk, dat, dat_read, 0x00)
        r2 = _clock_byte(stb, clk, dat, dat_read, 0x00)
        r3 = _clock_byte(stb, clk, dat, dat_read, 0x00)
        stb.set_low()
        self.assertEqual(r0, 0xAA)
        self.assertEqual(r1, 0xBB)
        self.assertEqual(r2, 0xCC)
        self.assertEqual(r3, 0xDD)

    def test_key_data_wraps(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        upd.key_data[0] = 0x11
        upd.key_data[1] = 0x22
        upd.key_data[2] = 0x33
        upd.key_data[3] = 0x44
        stb.set_high()
        _clock_byte(stb, clk, dat, dat_read, 0x44)  # key data request
        for _ in range(4):
            _clock_byte(stb, clk, dat, dat_read, 0x00)
        r0 = _clock_byte(stb, clk, dat, dat_read, 0x00)  # wraps to key_data[0]
        stb.set_low()
        self.assertEqual(r0, 0x11)

    def test_key_data_changes_between_reads(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        upd.key_data[0] = 0xAA
        stb.set_high()
        _clock_byte(stb, clk, dat, dat_read, 0x44)
        r0 = _clock_byte(stb, clk, dat, dat_read, 0x00)
        self.assertEqual(r0, 0xAA)
        stb.set_low()
        # Change key data and read again
        upd.key_data[0] = 0x55
        stb.set_high()
        _clock_byte(stb, clk, dat, dat_read, 0x44)
        r0 = _clock_byte(stb, clk, dat, dat_read, 0x00)
        stb.set_low()
        self.assertEqual(r0, 0x55)

    def test_key_read_does_not_modify_any_ram(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        old_display = bytes(upd.display_ram)
        old_picto = bytes(upd.pictograph_ram)
        old_chargen = bytes(upd.chargen_ram)
        old_led = bytes(upd.led_ram)
        stb.set_high()
        _clock_byte(stb, clk, dat, dat_read, 0x44)
        for _ in range(4):
            _clock_byte(stb, clk, dat, dat_read, 0x00)
        stb.set_low()
        self.assertEqual(bytes(upd.display_ram), old_display)
        self.assertEqual(bytes(upd.pictograph_ram), old_picto)
        self.assertEqual(bytes(upd.chargen_ram), old_chargen)
        self.assertEqual(bytes(upd.led_ram), old_led)


class UPD16432B_SelectTests(unittest.TestCase):

    def test_stb_rising_edge_resets_state(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        # Write some data
        _send(stb, clk, dat, dat_read, [0b01000000])  # display ram, increment on
        _send(stb, clk, dat, dat_read, [0b10000000, 0x42])  # address 0, write 0x42
        self.assertEqual(upd.display_ram[0], 0x42)
        # STB rising edge resets to command mode
        _send(stb, clk, dat, dat_read, [0b10000000 | 5])  # this is now a command, not data
        self.assertEqual(upd.display_ram[1], 0x00)  # no data written

    def test_no_clocking_while_deselected(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        _send(stb, clk, dat, dat_read, [0b01000000])  # display ram, increment on
        # Clock bytes while STB is low — should be ignored
        _clock_byte(stb, clk, dat, dat_read, 0b10000000)
        _clock_byte(stb, clk, dat, dat_read, 0xFF)
        self.assertEqual(upd.display_ram[0], 0x00)


class UPD16432B_DisplayPixelsTests(unittest.TestCase):

    def test_returns_correct_length(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        pixels = upd.display_pixels
        self.assertEqual(len(pixels), 7 * 0x19)

    def test_all_zeros_uses_chargen_char_0(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        pixels = upd.display_pixels
        self.assertEqual(pixels[:7], bytearray(7))

    def test_charset_character(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        _send(stb, clk, dat, dat_read, [0b01000000])
        _send(stb, clk, dat, dat_read, [0b10000000, 0x41])  # 'A' at position 0
        pixels = upd.display_pixels
        self.assertNotEqual(pixels[:7], bytearray(7))

    def test_display_ram_write_updates_pixels(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        pixels1 = bytes(upd.display_pixels)
        _send(stb, clk, dat, dat_read, [0b01000000])
        _send(stb, clk, dat, dat_read, [0b10000000, 0x41])
        pixels2 = bytes(upd.display_pixels)
        self.assertNotEqual(pixels1, pixels2)

    def test_chargen_character(self):
        upd, stb, clk, dat, dat_read = _make_upd()
        # Write custom character to chargen slot 0
        _send(stb, clk, dat, dat_read, [0b01000010])  # chargen ram, increment on
        _send(stb, clk, dat, dat_read, [0b10000000] + [0xFF] * 7)
        # Set display position 0 to chargen slot 0
        _send(stb, clk, dat, dat_read, [0b01000000])
        _send(stb, clk, dat, dat_read, [0b10000000, 0x00])
        pixels = upd.display_pixels
        # Chargen slot 0 was written with 0xFF bytes
        for i in range(7):
            self.assertNotEqual(pixels[i], 0)
