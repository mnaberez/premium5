import unittest
from premium5.devices import Port0Device, Port9Device, SPIControllerDevice, UARTDevice
from premium5.digital import LogicInput, LogicOutput, Level
from premium5.serial import AsyncSerialReceiver, BaudRateGenerator, Parity


class Port0DeviceTests(unittest.TestCase):

    def test_name(self):
        p0 = Port0Device()
        self.assertEqual(p0.name, "p0")

    def test_has_edge_detection(self):
        p0 = Port0Device()
        self.assertTrue(hasattr(p0, '_egp'))
        self.assertTrue(hasattr(p0, '_egn'))

    def test_has_pullups(self):
        p0 = Port0Device()
        self.assertTrue(hasattr(p0, '_pullup'))

    def test_size_includes_egp_egn(self):
        p0 = Port0Device()
        self.assertEqual(p0.size, 5)


class Port9DeviceTests(unittest.TestCase):

    def test_name(self):
        p9 = Port9Device()
        self.assertEqual(p9.name, "p9")

    def test_undriven_pins_default_floating(self):
        p9 = Port9Device()
        for i in range(8):
            self.assertFalse(p9.pins[i].high)


class SPIControllerDeviceTests(unittest.TestCase):

    def setUp(self):
        self.spi = SPIControllerDevice("csi30")
        self.spi.bus = self
        self.interrupts = []

    def interrupt(self, device, int_num):
        self.interrupts.append((device, int_num))

    def _enable(self):
        self.spi.write(self.spi.CSIM, 0x81)  # enabled, SCL=01 (fX/8)

    def _transfer(self):
        """Tick through a full 8-bit transfer at fX/8 (4 ticks per edge, 64 total)."""
        for _ in range(64):
            self.spi.tick(1)

    # enable/disable (CSIE bit 7 of CSIM)

    def test_starts_disabled(self):
        self.assertTrue(self.spi.enabled_out.low)

    def test_enable_sets_enabled_out_high(self):
        self.spi.write(self.spi.CSIM, 0x80)
        self.assertTrue(self.spi.enabled_out.high)

    def test_disable_sets_enabled_out_low(self):
        self.spi.write(self.spi.CSIM, 0x80)
        self.spi.write(self.spi.CSIM, 0x00)
        self.assertTrue(self.spi.enabled_out.low)

    def test_disable_clears_sio(self):
        self.spi.write(self.spi.CSIM, 0x80)
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.write(self.spi.CSIM, 0x00)
        self.assertEqual(self.spi.read(self.spi.SIO), 0x00)

    def test_disable_stops_transfer(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.write(self.spi.CSIM, 0x00)
        # ticking should do nothing — transfer was stopped
        self.spi.tick(100)
        self.assertEqual(self.interrupts, [])

    # write to SIO

    def test_write_sio_when_disabled_does_not_start_transfer(self):
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.tick(100)
        self.assertEqual(self.interrupts, [])

    def test_write_sio_when_enabled_starts_transfer(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.tick(4)  # first edge at fX/8
        self.assertTrue(self.spi.clk_out.low)

    # reset

    def test_reset_clears_sio(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.reset()
        self.assertEqual(self.spi.read(self.spi.SIO), 0x00)

    def test_reset_clears_csim(self):
        self._enable()
        self.spi.reset()
        self.assertEqual(self.spi.read(self.spi.CSIM), 0x00)

    def test_reset_sets_enabled_out_low(self):
        self._enable()
        self.spi.reset()
        self.assertTrue(self.spi.enabled_out.low)

    # read

    def test_read_sio_returns_shift_register(self):
        self.assertEqual(self.spi.read(self.spi.SIO), 0x00)

    def test_read_csim_returns_mode_register(self):
        self._enable()
        self.assertEqual(self.spi.read(self.spi.CSIM), 0x81)

    # clock idle state

    def test_clk_idles_high(self):
        self.assertTrue(self.spi.clk_out.high)

    # transfer: clock output

    def test_first_edge_drives_clk_low(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0x00)
        self.spi.tick(4)  # fX/8: 4 ticks per edge
        self.assertTrue(self.spi.clk_out.low)

    def test_second_edge_drives_clk_high(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0x00)
        self.spi.tick(4)
        self.spi.tick(4)
        self.assertTrue(self.spi.clk_out.high)

    # transfer: data output (MSB first)

    def test_shifts_out_msb_first(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0xA5)  # 10100101
        bits = []
        for _ in range(8):
            self.spi.tick(4)  # falling edge: data set
            bits.append(int(self.spi.dat_out.high))
            self.spi.tick(4)  # rising edge
        self.assertEqual(bits, [1, 0, 1, 0, 0, 1, 0, 1])

    def test_dat_out_ready_before_falling_edge(self):
        # An external device that latches on the falling edge of clk_out
        # must see the correct data bit at the moment the edge fires.
        # This is how FIS and UPD16432B receive data from CSI30.
        clk_monitor = LogicInput()
        self.spi.clk_out.bind(clk_monitor)

        bits = []
        def on_clk_falling():
            bits.append(int(self.spi.dat_out.high))
        clk_monitor.on_falling = on_clk_falling

        self._enable()
        self.spi.write(self.spi.SIO, 0xA5)  # 10100101
        self._transfer()
        self.assertEqual(bits, [1, 0, 1, 0, 0, 1, 0, 1])

    # transfer: data input

    def test_shifts_in_dat_on_rising_edge(self):
        driver = LogicOutput(Level.LOW)
        driver.bind(self.spi.dat_in)

        self._enable()
        self.spi.write(self.spi.SIO, 0x00)

        # clock in 0xC3 = 11000011
        input_bits = [1, 1, 0, 0, 0, 0, 1, 1]
        for bit in input_bits:
            self.spi.tick(4)  # falling edge
            if bit:
                driver.set_high()
            else:
                driver.set_low()
            self.spi.tick(4)  # rising edge: latch

        self.assertEqual(self.spi.read(self.spi.SIO), 0xC3)

    # transfer: completion

    def test_transfer_completes_after_8_bits(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0x00)
        self._transfer()
        self.assertEqual(len(self.interrupts), 1)

    def test_transfer_fires_interrupt(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0x00)
        self._transfer()
        self.assertEqual(len(self.interrupts), 1)
        self.assertIs(self.interrupts[0][0], self.spi)
        self.assertEqual(self.interrupts[0][1], self.spi.INT_TRANSFER)

    def test_sio_holds_received_byte_after_transfer(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0x00)
        self._transfer()
        # dat_in defaults LOW, so all received bits are 0
        self.assertEqual(self.spi.read(self.spi.SIO), 0x00)

    def test_clk_returns_high_after_transfer(self):
        self._enable()
        self.spi.write(self.spi.SIO, 0x00)
        self._transfer()
        self.assertTrue(self.spi.clk_out.high)

    # tick while idle

    def test_tick_while_idle_does_nothing(self):
        self._enable()
        self.spi.tick(1)
        self.assertTrue(self.spi.clk_out.high)
        self.assertEqual(self.interrupts, [])

    # prescaler

    def test_prescaler_fx8_half_clock_is_4_ticks(self):
        self.spi.write(self.spi.CSIM, 0x81)  # enabled, SCL=01 (fX/8)
        self.spi.write(self.spi.SIO, 0x80)
        # CLK should stay high for 3 ticks, fall on tick 4
        for _ in range(3):
            self.spi.tick(1)
            self.assertTrue(self.spi.clk_out.high)
        self.spi.tick(1)
        self.assertTrue(self.spi.clk_out.low)

    def test_prescaler_fx16_half_clock_is_8_ticks(self):
        self.spi.write(self.spi.CSIM, 0x82)  # enabled, SCL=10 (fX/16)
        self.spi.write(self.spi.SIO, 0x80)
        for _ in range(7):
            self.spi.tick(1)
            self.assertTrue(self.spi.clk_out.high)
        self.spi.tick(1)
        self.assertTrue(self.spi.clk_out.low)

    def test_prescaler_fx64_half_clock_is_32_ticks(self):
        self.spi.write(self.spi.CSIM, 0x83)  # enabled, SCL=11 (fX/64)
        self.spi.write(self.spi.SIO, 0x80)
        for _ in range(31):
            self.spi.tick(1)
            self.assertTrue(self.spi.clk_out.high)
        self.spi.tick(1)
        self.assertTrue(self.spi.clk_out.low)

    def test_prescaler_full_byte_fx8(self):
        self.spi.write(self.spi.CSIM, 0x81)  # enabled, SCL=01 (fX/8)
        self.spi.write(self.spi.SIO, 0xA5)
        # 8 bits * 2 half-clocks * 4 ticks = 64 ticks
        for _ in range(63):
            self.spi.tick(1)
        self.assertEqual(self.interrupts, [])
        self.spi.tick(1)
        self.assertEqual(len(self.interrupts), 1)


    # MODE bit (receive-only mode)

    def test_write_sio_in_receive_only_mode_does_not_start_transfer(self):
        # MODE=1, SCL=01 (fX/8): 0x85
        self.spi.write(self.spi.CSIM, 0x85)
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.tick(100)
        self.assertEqual(self.interrupts, [])

    def test_read_sio_in_receive_only_mode_starts_transfer(self):
        # MODE=1, SCL=01 (fX/8): 0x85
        self.spi.write(self.spi.CSIM, 0x85)
        self.spi.read(self.spi.SIO)
        # tick through a full 8-bit transfer
        for _ in range(64):
            self.spi.tick(1)
        self.assertEqual(len(self.interrupts), 1)

    def test_read_sio_in_transmit_mode_does_not_start_transfer(self):
        # MODE=0, SCL=01 (fX/8): 0x81
        self._enable()
        self.spi.read(self.spi.SIO)
        self.spi.tick(100)
        self.assertEqual(self.interrupts, [])

    def test_receive_only_mode_shifts_in_data(self):
        driver = LogicOutput(Level.LOW)
        driver.bind(self.spi.dat_in)

        self.spi.write(self.spi.CSIM, 0x85)  # MODE=1, SCL=01 (fX/8)
        self.spi.read(self.spi.SIO)  # trigger transfer

        # clock in 0xC3 = 11000011
        input_bits = [1, 1, 0, 0, 0, 0, 1, 1]
        for bit in input_bits:
            self.spi.tick(4)  # falling edge
            if bit:
                driver.set_high()
            else:
                driver.set_low()
            self.spi.tick(4)  # rising edge: latch

        self.assertEqual(self.spi.read(self.spi.SIO), 0xC3)

    # external clock (SCL=00)

    def test_external_clock_tick_does_nothing(self):
        # SCL=00 (external clock), MODE=0: 0x80
        self.spi.write(self.spi.CSIM, 0x80)
        self.spi.write(self.spi.SIO, 0xA5)
        self.spi.tick(1000)
        self.assertEqual(self.interrupts, [])

    def test_external_clock_shifts_in_data(self):
        ext_clk = LogicOutput(Level.HIGH)
        ext_dat = LogicOutput(Level.LOW)
        ext_clk.bind(self.spi.clk_in)
        ext_dat.bind(self.spi.dat_in)

        # SCL=00, MODE=1 (receive-only): 0x84
        self.spi.write(self.spi.CSIM, 0x84)
        self.spi.read(self.spi.SIO)  # trigger transfer

        # clock in 0xA5 = 10100101
        input_bits = [1, 0, 1, 0, 0, 1, 0, 1]
        for bit in input_bits:
            ext_clk.set_low()     # falling edge
            if bit:
                ext_dat.set_high()
            else:
                ext_dat.set_low()
            ext_clk.set_high()    # rising edge: latch

        self.assertEqual(self.spi.read(self.spi.SIO), 0xA5)

    def test_external_clock_fires_interrupt_after_8_bits(self):
        ext_clk = LogicOutput(Level.HIGH)
        ext_clk.bind(self.spi.clk_in)

        # SCL=00, MODE=1 (receive-only): 0x84
        self.spi.write(self.spi.CSIM, 0x84)
        self.spi.read(self.spi.SIO)  # trigger transfer

        for _ in range(8):
            ext_clk.set_low()
            ext_clk.set_high()

        self.assertEqual(len(self.interrupts), 1)
        self.assertIs(self.interrupts[0][0], self.spi)
        self.assertEqual(self.interrupts[0][1], self.spi.INT_TRANSFER)

    def test_external_clock_receives_multiple_bytes(self):
        ext_clk = LogicOutput(Level.HIGH)
        ext_dat = LogicOutput(Level.LOW)
        ext_clk.bind(self.spi.clk_in)
        ext_dat.bind(self.spi.dat_in)

        # SCL=00, MODE=1 (receive-only): 0x84
        self.spi.write(self.spi.CSIM, 0x84)

        send_bytes = [0x34, 0xBE, 0xFC]
        received = []
        for byte_val in send_bytes:
            # trigger receive by reading SIO
            self.spi.read(self.spi.SIO)

            # clock in 8 bits MSB first
            for bit_pos in range(8):
                bit = (byte_val >> (7 - bit_pos)) & 1
                ext_clk.set_low()
                if bit:
                    ext_dat.set_high()
                else:
                    ext_dat.set_low()
                ext_clk.set_high()

            received.append(self.spi.read(self.spi.SIO))

        self.assertEqual(received, send_bytes)

    def test_external_clock_shifts_out_data(self):
        ext_clk = LogicOutput(Level.HIGH)
        ext_clk.bind(self.spi.clk_in)

        # SCL=00, MODE=0 (transmit): 0x80
        self.spi.write(self.spi.CSIM, 0x80)
        self.spi.write(self.spi.SIO, 0xA5)  # 10100101

        bits = []
        for _ in range(8):
            ext_clk.set_low()     # falling edge: data set
            bits.append(int(self.spi.dat_out.high))
            ext_clk.set_high()    # rising edge

        self.assertEqual(bits, [1, 0, 1, 0, 0, 1, 0, 1])


class UARTBaudRateGeneratorTests(unittest.TestCase):

    def setUp(self):
        self.brg = BaudRateGenerator()

    # initial state

    def test_ctor_clock_low(self):
        self.assertTrue(self.brg.baud_clk_out.low)

    def test_ctor_not_running(self):
        self.brg.tick(999)
        self.assertTrue(self.brg.baud_clk_out.low)

    # enable with 0 cycles per bit is a no-op.  This is how the
    # UART device handles invalid register configurations.

    def test_configure_zero_enable_does_not_run(self):
        self.brg.configure(0)
        self.brg.enable()
        self.assertFalse(self.brg._enabled)

    def test_configure_zero_enable_stays_low(self):
        self.brg.configure(0)
        self.brg.enable()
        self.brg.tick(999)
        self.assertTrue(self.brg.baud_clk_out.low)

    # enable's contract with the receiver and transmitter: its
    # output starts low for exactly one half bit period, then
    # then toggles every half bit period.  In particular, the
    # receiver depends on this to achieve mid-bit sampling.

    def test_enable_output_starts_low(self):
        self.brg.configure(400)  # 400 cycles per bit
        self.brg.enable()
        self.assertTrue(self.brg.baud_clk_out.low)

    def test_enable_stays_low_for_half_bit_period(self):
        self.brg.configure(400)  # 400 cycles per bit
        self.brg.enable()
        self.brg.tick(199)
        self.assertTrue(self.brg.baud_clk_out.low)

    def test_enable_first_rising_edge_at_half_bit_period(self):
        self.brg.configure(400)  # 400 cycles per bit
        self.brg.enable()
        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)

    # enable / disable

    def test_enable_starts_clock(self):
        self.brg.configure(400)
        self.brg.enable()

        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)
        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.low)

    def test_disable_stops_clock(self):
        self.brg.configure(400)
        self.brg.enable()

        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)

        self.brg.disable()
        self.assertTrue(self.brg.baud_clk_out.low)
        self.brg.tick(999)
        self.assertTrue(self.brg.baud_clk_out.low)

    def test_re_enable_resumes(self):
        self.brg.configure(400)
        self.brg.enable()

        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)

        self.brg.disable()
        self.assertTrue(self.brg.baud_clk_out.low)

        self.brg.enable()
        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)
        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.low)

    def test_reset_stops_clock(self):
        self.brg.configure(400)
        self.brg.enable()

        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)

        self.brg.reset()
        self.assertTrue(self.brg.baud_clk_out.low)
        self.brg.tick(999)
        self.assertTrue(self.brg.baud_clk_out.low)

    # Clock generation at 10400 baud (BRGC0=0x39)
    #
    # The BRG is ticked once per CPU cycle.  At 4.19 MHz, BRGC0=0x39 produces
    # 10400 baud.  The formula is:  baud = fX / (2^(TPS+1) * (16 + MDL))
    #
    #   0x39 = TPS=011 (n=3), MDL=1001 (k=9)
    #   cycles_per_bit = 2^(3+1) * (16+9) = 16 * 25 = 400
    #   baud = 4,190,000 / 400 = 10,475 (≈10400)
    #
    # The clock is a square wave at the baud rate.  One full cycle
    # (rising edge to rising edge) = one bit period = 400 cycles.
    # The clock toggles every 200 cycles.  The UART shifts one bit
    # on each rising edge.

    def test_10400_baud_toggle_timing(self):
        self.brg.configure(400)
        self.brg.enable()

        # should not toggle before 200 ticks
        self.brg.tick(199)
        self.assertTrue(self.brg.baud_clk_out.low)

        # tick 200: rising edge (start of bit)
        self.brg.tick(1)
        self.assertTrue(self.brg.baud_clk_out.high)

        # tick 400: falling edge
        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.low)

        # tick 600: rising edge (start of next bit)
        self.brg.tick(200)
        self.assertTrue(self.brg.baud_clk_out.high)

    def test_10400_baud_10_bits_in_4000_cycles(self):
        self.brg.configure(400)
        self.brg.enable()

        rising_edges = 0
        last = self.brg.baud_clk_out.high
        for _ in range(4000):
            self.brg.tick(1)
            if self.brg.baud_clk_out.high and not last:
                rising_edges += 1
            last = self.brg.baud_clk_out.high

        self.assertEqual(rising_edges, 10)

    # Verify the formula works at a second baud rate: 9600 (BRGC0=0x3B)
    #   TPS=3 (n=3), MDL=11 (k=11)
    #   cycles_per_bit = 2^4 * 27 = 432
    #   baud = 4,190,000 / 432 = 9699 (≈9600)

    def test_9600_baud_10_bits_in_4320_cycles(self):
        self.brg.configure(432)
        self.brg.enable()

        rising_edges = 0
        last = self.brg.baud_clk_out.high
        for _ in range(4320):
            self.brg.tick(1)
            if self.brg.baud_clk_out.high and not last:
                rising_edges += 1
            last = self.brg.baud_clk_out.high

        self.assertEqual(rising_edges, 10)


class UARTDeviceTests(unittest.TestCase):
    """Tests for UART0 transmit path.

    The UART owns its BRG internally.  At BRGC0=0x39 (10400 baud
    at 4.19 MHz), one bit = 400 CPU cycles.
    """

    def setUp(self):
        self.uart = UARTDevice("uart0")
        self.uart.bus = self
        self.interrupts = []
        self.uart.write(self.uart.BRGC0, 0x39)

    def interrupt(self, device, int_num):
        self.interrupts.append((device, int_num))

    def _tick_one_bit(self):
        """Tick one full bit period (400 cycles at 10400 baud)."""
        self.uart.tick(400)

    def _capture_tx_bits(self, n):
        """Capture n bits from TxD0, one per bit period."""
        bits = []
        for _ in range(n):
            self._tick_one_bit()
            bits.append(int(self.uart.txd_out.high))
        return bits

    # initial state

    def test_ctor_txd_idles_high(self):
        self.assertTrue(self.uart.txd_out.high)

    def test_ctor_rxd_idles_high(self):
        self.assertTrue(self.uart.rxd_in.high)

    # register read-back

    def test_brgc0_read_back(self):
        self.assertEqual(self.uart.read(self.uart.BRGC0), 0x39)

    def test_brgc0_tps_zero_does_not_run(self):
        # TPS=0 is external clock (not supported)
        self.uart.reset()
        self.uart.write(self.uart.BRGC0, 0x09)  # TPS=0, MDL=9
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(4000)
        self.assertTrue(self.uart.txd_out.high)
        self.assertEqual(self.interrupts, [])

    def test_brgc0_mdl_fifteen_does_not_run(self):
        # MDL=15 is prohibited
        self.uart.reset()
        self.uart.write(self.uart.BRGC0, 0x3F)  # TPS=3, MDL=15
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(4000)
        self.assertTrue(self.uart.txd_out.high)
        self.assertEqual(self.interrupts, [])

    def test_asim0_read_back(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.assertEqual(self.uart.read(self.uart.ASIM0), 0xC8)

    def test_asis0_zero_after_reset(self):
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    def test_rxb0_ff_after_reset(self):
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0xFF)

    # reset

    def test_reset_clears_asim0(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.reset()
        self.assertEqual(self.uart.read(self.uart.ASIM0), 0x00)

    def test_reset_clears_asis0(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.txd_out.bind(self.uart.rxd_in)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        self.uart.tick(5000)
        self.uart.reset()
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    def test_reset_restores_rxb0_to_ff(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.txd_out.bind(self.uart.rxd_in)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.uart.reset()
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0xFF)

    # enable / disable (verified via TX behavior)

    # transmit: 8N1 frame (0xCA = TX+RX enabled, no parity, 8 bits, 1 stop)

    def test_tx_8n1_frame(self):
        self.uart.write(self.uart.ASIM0, 0xCA)  # TX+RX, 8N1

        # transmit 0x55 (01010101)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)

        # capture 10 bits: start(1) + data(8) + stop(1)
        bits = self._capture_tx_bits(10)

        # start bit = 0
        self.assertEqual(bits[0], 0)

        # data bits LSB first: 0x55 = 10101010 LSB first
        self.assertEqual(bits[1:9], [1, 0, 1, 0, 1, 0, 1, 0])

        # stop bit = 1
        self.assertEqual(bits[9], 1)

    def test_tx_8e1_frame_even_parity(self):
        # 0xFA = TXE0=1, RXE0=1, PS=11 (even parity), CL0=1 (8 bits), SL0=0 (1 stop)
        self.uart.write(self.uart.ASIM0, 0xFA)

        # transmit 0x55 (01010101) — 4 ones, even parity bit = 0
        self.uart.write(self.uart.TXS0_RXB0, 0x55)

        # capture 11 bits: start(1) + data(8) + parity(1) + stop(1)
        bits = self._capture_tx_bits(11)

        self.assertEqual(bits[0], 0)  # start
        self.assertEqual(bits[1:9], [1, 0, 1, 0, 1, 0, 1, 0])  # data
        self.assertEqual(bits[9], 0)  # even parity (4 ones → 0)
        self.assertEqual(bits[10], 1)  # stop

    def test_tx_8e1_frame_even_parity_odd_ones(self):
        self.uart.write(self.uart.ASIM0, 0xFA)  # even parity, 8N1

        # transmit 0x57 (01010111) — 5 ones, even parity bit = 1
        self.uart.write(self.uart.TXS0_RXB0, 0x57)

        bits = self._capture_tx_bits(11)

        self.assertEqual(bits[0], 0)  # start
        self.assertEqual(bits[9], 1)  # even parity (5 ones → 1)
        self.assertEqual(bits[10], 1)  # stop

    def test_tx_fires_interrupt(self):
        self.uart.write(self.uart.ASIM0, 0xCA)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)

        for _ in range(10):
            self._tick_one_bit()

        self.assertEqual(len(self.interrupts), 1)
        self.assertIs(self.interrupts[0][0], self.uart)
        self.assertEqual(self.interrupts[0][1], self.uart.INT_TX)

    def test_tx_returns_to_idle_after_frame(self):
        self.uart.write(self.uart.ASIM0, 0xCA)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)

        for _ in range(10):
            self._tick_one_bit()

        # TxD should be high (idle/mark)
        self.assertTrue(self.uart.txd_out.high)

        # further ticking should not fire more interrupts
        for _ in range(10):
            self._tick_one_bit()
        self.assertEqual(len(self.interrupts), 1)

    def test_tx_disabled_does_not_send(self):
        # don't enable TX
        self.uart.write(self.uart.TXS0_RXB0, 0x55)

        self.uart.tick(4000)
        self.assertTrue(self.uart.txd_out.high)
        self.assertEqual(self.interrupts, [])

    # 8O1

    def test_tx_8o1_frame_odd_parity(self):
        # TXE0=1, RXE0=1, PS=10 (odd parity), CL0=1, SL0=0
        self.uart.write(self.uart.ASIM0, 0xE8)
        # 0x55 has 4 ones, odd parity bit = 1
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        bits = self._capture_tx_bits(11)
        self.assertEqual(bits[0], 0)  # start
        self.assertEqual(bits[1:9], [1, 0, 1, 0, 1, 0, 1, 0])  # data
        self.assertEqual(bits[9], 1)  # odd parity (4 ones → 1)
        self.assertEqual(bits[10], 1)  # stop

    # 8Z1

    def test_tx_8z1_frame_zero_parity(self):
        # TXE0=1, RXE0=1, PS=01 (zero parity), CL0=1, SL0=0
        self.uart.write(self.uart.ASIM0, 0xD8)
        # 0xFF has 8 ones, zero parity bit = always 0
        self.uart.write(self.uart.TXS0_RXB0, 0xFF)
        bits = self._capture_tx_bits(11)
        self.assertEqual(bits[0], 0)  # start
        self.assertEqual(bits[1:9], [1, 1, 1, 1, 1, 1, 1, 1])  # data
        self.assertEqual(bits[9], 0)  # zero parity (always 0)
        self.assertEqual(bits[10], 1)  # stop

    # 7N1

    def test_tx_7n1_frame(self):
        # TXE0=1, RXE0=1, PS=00, CL0=0 (7 bits), SL0=0
        self.uart.write(self.uart.ASIM0, 0xC0)
        # 0x55 as 7 bits = 1010101
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        bits = self._capture_tx_bits(9)
        self.assertEqual(bits[0], 0)  # start
        self.assertEqual(bits[1:8], [1, 0, 1, 0, 1, 0, 1])  # 7 data bits
        self.assertEqual(bits[8], 1)  # stop

    # 8N2

    def test_tx_8n2_frame(self):
        # TXE0=1, RXE0=1, PS=00, CL0=1, SL0=1 (2 stop bits)
        self.uart.write(self.uart.ASIM0, 0xCC)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        bits = self._capture_tx_bits(11)
        self.assertEqual(bits[0], 0)  # start
        self.assertEqual(bits[1:9], [1, 0, 1, 0, 1, 0, 1, 0])  # data
        self.assertEqual(bits[9], 1)  # stop 1
        self.assertEqual(bits[10], 1)  # stop 2

    # transmit while busy

    def test_tx_while_busy_ignored(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        # capture start + D0, then write another byte mid-frame
        bits = self._capture_tx_bits(2)
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        # rest of the frame should still be 0x55
        bits += self._capture_tx_bits(8)
        # full frame: start(0) + 10101010 LSB first + stop(1)
        self.assertEqual(bits, [0, 1, 0, 1, 0, 1, 0, 1, 0, 1])


class UARTReceiverTests(unittest.TestCase):
    """Isolated tests for the UART receiver.

    Drives rxd_in directly with bit patterns.  At TPS=3, MDL=9
    (10400 baud), one bit = 400 cycles, half bit = 200 cycles.
    """

    def setUp(self):
        self.rxd_driver = LogicOutput(Level.HIGH)
        rxd_input = LogicInput(pull_level=Level.HIGH)
        self.rxd_driver.bind(rxd_input)

        self.completions = []
        self.errors = []

        def on_complete(data, error):
            self.completions.append(data)
            if error:
                self.errors.append(error)

        self.rx = AsyncSerialReceiver(rxd_input, on_complete)
        self.rx.configure_brg(400)
        rxd_input.on_falling = self.rx._on_rxd_falling
        self.rx.enable()

    def _drive_bits(self, bits):
        """Drive a sequence of bits on rxd_in, one bit period each."""
        for bit in bits:
            if bit:
                self.rxd_driver.set_high()
            else:
                self.rxd_driver.set_low()
            self.rx.tick(400)
        self.rxd_driver.set_high()
        self.rx.tick(400)

    # 8N1

    def test_8n1_receive_0x55(self):
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
        self.assertEqual(self.completions, [0x55])

    def test_8n1_receive_0xff(self):
        self._drive_bits([0, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        self.assertEqual(self.completions, [0xFF])

    def test_8n1_receive_0x00(self):
        self._drive_bits([0, 0, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(self.completions, [0x00])

    # 7N1

    def test_7n1_receive_0x55(self):
        self.rx.configure_frame(7, 1, Parity.NONE)
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 1])
        self.assertEqual(self.completions, [0x55])

    def test_7n1_receive_0x2a(self):
        self.rx.configure_frame(7, 1, Parity.NONE)
        self._drive_bits([0, 0, 1, 0, 1, 0, 1, 0, 1])
        self.assertEqual(self.completions, [0x2A])

    # 8E1

    def test_8e1_good_parity(self):
        self.rx.configure_frame(8, 1, Parity.EVEN)
        # 0x55 has 4 ones, even parity bit = 0
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1])
        self.assertEqual(self.completions, [0x55])
        self.assertEqual(self.errors, [])

    def test_8e1_bad_parity(self):
        self.rx.configure_frame(8, 1, Parity.EVEN)
        # 0x55 with wrong parity bit (1 instead of 0)
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1])
        self.assertEqual(self.completions, [0x55])
        self.assertEqual(len(self.errors), 1)
        self.assertFalse(self.errors[0].framing_error)
        self.assertTrue(self.errors[0].parity_error)

    # 8O1

    def test_8o1_good_parity(self):
        self.rx.configure_frame(8, 1, Parity.ODD)
        # 0x55 has 4 ones, odd parity bit = 1
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1])
        self.assertEqual(self.completions, [0x55])
        self.assertEqual(self.errors, [])

    def test_8o1_bad_parity(self):
        self.rx.configure_frame(8, 1, Parity.ODD)
        # 0x55 with wrong parity bit (0 instead of 1)
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1])
        self.assertEqual(self.completions, [0x55])
        self.assertTrue(self.errors[0].parity_error)

    # 8Z1 (zero parity, no check on receive)

    def test_8z1_ignores_parity_bit(self):
        self.rx.configure_frame(8, 1, Parity.ZERO)
        # parity bit = 1 (wrong for zero parity TX, but RX doesn't check)
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1])
        self.assertEqual(self.completions, [0x55])
        self.assertEqual(self.errors, [])

    # framing error (bad stop bit)

    def test_framing_error_bad_stop_bit(self):
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 0])
        self.assertEqual(self.completions, [0x55])
        self.assertEqual(len(self.errors), 1)
        self.assertTrue(self.errors[0].framing_error)
        self.assertFalse(self.errors[0].parity_error)

    # framing + parity error simultaneously

    def test_framing_and_parity_error(self):
        self.rx.configure_frame(8, 1, Parity.EVEN)
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
        self.assertEqual(self.completions, [0x55])
        self.assertEqual(len(self.errors), 1)
        self.assertTrue(self.errors[0].framing_error)
        self.assertTrue(self.errors[0].parity_error)

    # start bit glitch rejection

    def test_glitch_rejected_at_mid_start_bit(self):
        self.rxd_driver.set_low()
        self.rx.tick(100)
        self.rxd_driver.set_high()
        self.rx.tick(5000)
        self.assertEqual(self.completions, [])
        self.assertEqual(self.errors, [])

    # disabled

    def test_disabled_ignores_falling_edge(self):
        self.rx.disable()
        self._drive_bits([0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
        self.assertEqual(self.completions, [])
        self.assertEqual(self.errors, [])


class UARTLoopbackTests(unittest.TestCase):
    """End-to-end UART tests with TxD wired to RxD.

    At BRGC0=0x39 (10400 baud at 4.19 MHz), one bit = 400 cycles.
    A full 8N1 frame is 10 bits = 4000 cycles.  The RX BRG starts
    half a bit after the TX, so we tick 5000 to be safe.
    """

    def setUp(self):
        self.uart = UARTDevice("uart0")
        self.uart.bus = self
        self.interrupts = []
        self.uart.txd_out.bind(self.uart.rxd_in)
        self.uart.write(self.uart.BRGC0, 0x39)

    def interrupt(self, device, int_num):
        self.interrupts.append((device, int_num))

    def _int_nums(self):
        return [i[1] for i in self.interrupts]

    # 8N1 loopback

    def test_loopback_8n1_0x55(self):
        self.uart.write(self.uart.ASIM0, 0xC8)  # TX+RX, 8N1
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0x55)

    def test_loopback_8n1_0xaa(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0xAA)

    def test_loopback_8n1_0x00(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x00)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0x00)

    def test_loopback_8n1_0xff(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0xFF)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0xFF)

    def test_loopback_8n1_no_errors(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    def test_loopback_8n1_interrupts(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.assertIn(self.uart.INT_TX, self._int_nums())
        self.assertIn(self.uart.INT_RX, self._int_nums())
        self.assertNotIn(self.uart.INT_ERR, self._int_nums())

    # 8E1 loopback (even parity)

    def test_loopback_8e1_0x55(self):
        self.uart.write(self.uart.ASIM0, 0xF8)  # TX+RX, even parity, 8 bits, 1 stop
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5500)
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0x55)
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    def test_loopback_8e1_0xff(self):
        self.uart.write(self.uart.ASIM0, 0xF8)
        self.uart.write(self.uart.TXS0_RXB0, 0xFF)
        self.uart.tick(5500)
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0xFF)
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    # RX checks only one stop bit regardless of SL0

    def test_loopback_8n2_rx_checks_one_stop_bit(self):
        # TX+RX, no parity, 8 bits, 2 stop bits (SL0=1)
        self.uart.write(self.uart.ASIM0, 0xCC)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(6000)  # 12 bits * 400 + margin
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0x55)
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    # bad start bit is silently discarded

    def test_glitch_on_rxd_does_not_receive(self):
        self.uart.write(self.uart.ASIM0, 0xC8)  # TX+RX, 8N1

        # drive rxd_in externally instead of loopback
        rxd_driver = LogicOutput(Level.HIGH)
        rxd_driver.bind(self.uart.rxd_in)

        # glitch: falling edge triggers start bit detection,
        # but line goes high before mid-bit sample
        rxd_driver.set_low()
        self.uart.tick(100)  # less than half a bit (200 cycles)
        rxd_driver.set_high()
        self.uart.tick(5000)

        # no data received, no interrupts
        self.assertEqual(self.uart.read(self.uart.TXS0_RXB0), 0xFF)  # reset value
        self.assertNotIn(self.uart.INT_RX, self._int_nums())
        self.assertNotIn(self.uart.INT_ERR, self._int_nums())

    # RX disabled ignores data

    def test_rx_disabled_does_not_receive(self):
        self.uart.write(self.uart.ASIM0, 0x88)  # TX only, no RX
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.assertIn(self.uart.INT_TX, self._int_nums())
        self.assertNotIn(self.uart.INT_RX, self._int_nums())

    # overrun

    def test_overrun_sets_ove0(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        # don't read RXB0, send another byte
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.ASIS0) & 0x01, 0x01)  # OVE0

    def test_no_overrun_if_rxb0_read(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        self.uart.read(self.uart.TXS0_RXB0)  # read first byte
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        self.uart.tick(5000)
        self.assertEqual(self.uart.read(self.uart.ASIS0) & 0x01, 0x00)

    # ASIS0 cleared on read

    def test_asis0_cleared_by_reading_rxb0(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        # don't read RXB0, send another to trigger overrun
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        self.uart.tick(5000)
        self.assertNotEqual(self.uart.read(self.uart.ASIS0), 0x00)  # flags set
        self.uart.read(self.uart.TXS0_RXB0)  # reading RXB0 clears ASIS0
        self.assertEqual(self.uart.read(self.uart.ASIS0), 0x00)

    def test_asis0_not_cleared_by_reading_asis0(self):
        self.uart.write(self.uart.ASIM0, 0xC8)
        self.uart.write(self.uart.TXS0_RXB0, 0x55)
        self.uart.tick(5000)
        # don't read RXB0, send another to trigger overrun
        self.uart.write(self.uart.TXS0_RXB0, 0xAA)
        self.uart.tick(5000)
        self.assertNotEqual(self.uart.read(self.uart.ASIS0), 0x00)  # flags set
        self.assertNotEqual(self.uart.read(self.uart.ASIS0), 0x00)  # still set


