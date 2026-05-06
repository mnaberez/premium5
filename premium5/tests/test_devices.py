import unittest
from premium5.devices import Port0Device, Port9Device, SPIControllerDevice, BaudRateGeneratorDevice, UARTDevice


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

    def _make_spi(self):
        spi = SPIControllerDevice("csi30")
        spi.bus = self
        self.interrupts = []
        return spi

    def interrupt(self, device, int_num):
        self.interrupts.append((device, int_num))

    def _enable(self, spi):
        spi.write(spi.CSIM, 0x81)  # enabled, SCL=01 (fX/8)

    def _transfer(self, spi):
        """Tick through a full 8-bit transfer at fX/8 (4 ticks per edge, 64 total)."""
        for _ in range(64):
            spi.tick(1)

    # enable/disable (CSIE bit 7 of CSIM)

    def test_starts_disabled(self):
        spi = self._make_spi()
        self.assertTrue(spi.enabled_out.low)

    def test_enable_sets_enabled_out_high(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x80)
        self.assertTrue(spi.enabled_out.high)

    def test_disable_sets_enabled_out_low(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x80)
        spi.write(spi.CSIM, 0x00)
        self.assertTrue(spi.enabled_out.low)

    def test_disable_clears_sio(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x80)
        spi.write(spi.SIO, 0xA5)
        spi.write(spi.CSIM, 0x00)
        self.assertEqual(spi.read(spi.SIO), 0x00)

    def test_disable_stops_transfer(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0xA5)
        spi.write(spi.CSIM, 0x00)
        # ticking should do nothing — transfer was stopped
        spi.tick(100)
        self.assertEqual(self.interrupts, [])

    # write to SIO

    def test_write_sio_when_disabled_does_not_start_transfer(self):
        spi = self._make_spi()
        spi.write(spi.SIO, 0xA5)
        spi.tick(100)
        self.assertEqual(self.interrupts, [])

    def test_write_sio_when_enabled_starts_transfer(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0xA5)
        spi.tick(4)  # first edge at fX/8
        self.assertTrue(spi.clk_out.low)

    # reset

    def test_reset_clears_sio(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0xA5)
        spi.reset()
        self.assertEqual(spi.read(spi.SIO), 0x00)

    def test_reset_clears_csim(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.reset()
        self.assertEqual(spi.read(spi.CSIM), 0x00)

    def test_reset_sets_enabled_out_low(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.reset()
        self.assertTrue(spi.enabled_out.low)

    # read

    def test_read_sio_returns_shift_register(self):
        spi = self._make_spi()
        self.assertEqual(spi.read(spi.SIO), 0x00)

    def test_read_csim_returns_mode_register(self):
        spi = self._make_spi()
        self._enable(spi)
        self.assertEqual(spi.read(spi.CSIM), 0x81)

    # clock idle state

    def test_clk_idles_high(self):
        spi = self._make_spi()
        self.assertTrue(spi.clk_out.high)

    # transfer: clock output

    def test_first_edge_drives_clk_low(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0x00)
        spi.tick(4)  # fX/8: 4 ticks per edge
        self.assertTrue(spi.clk_out.low)

    def test_second_edge_drives_clk_high(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0x00)
        spi.tick(4)
        spi.tick(4)
        self.assertTrue(spi.clk_out.high)

    # transfer: data output (MSB first)

    def test_shifts_out_msb_first(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0xA5)  # 10100101
        bits = []
        for _ in range(8):
            spi.tick(4)  # falling edge: data set
            bits.append(int(spi.dat_out.high))
            spi.tick(4)  # rising edge
        self.assertEqual(bits, [1, 0, 1, 0, 0, 1, 0, 1])

    # transfer: data input

    def test_shifts_in_dat_on_rising_edge(self):
        spi = self._make_spi()
        from premium5.digital import LogicOutput, Level
        driver = LogicOutput(Level.LOW)
        driver.bind(spi.dat_in)

        self._enable(spi)
        spi.write(spi.SIO, 0x00)

        # clock in 0xC3 = 11000011
        input_bits = [1, 1, 0, 0, 0, 0, 1, 1]
        for bit in input_bits:
            spi.tick(4)  # falling edge
            if bit:
                driver.set_high()
            else:
                driver.set_low()
            spi.tick(4)  # rising edge: latch

        self.assertEqual(spi.read(spi.SIO), 0xC3)

    # transfer: completion

    def test_transfer_completes_after_8_bits(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0x00)
        self._transfer(spi)
        self.assertEqual(len(self.interrupts), 1)

    def test_transfer_fires_interrupt(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0x00)
        self._transfer(spi)
        self.assertEqual(len(self.interrupts), 1)
        self.assertIs(self.interrupts[0][0], spi)
        self.assertEqual(self.interrupts[0][1], spi.INT_TRANSFER)

    def test_sio_holds_received_byte_after_transfer(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0x00)
        self._transfer(spi)
        # dat_in defaults LOW, so all received bits are 0
        self.assertEqual(spi.read(spi.SIO), 0x00)

    def test_clk_returns_high_after_transfer(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.write(spi.SIO, 0x00)
        self._transfer(spi)
        self.assertTrue(spi.clk_out.high)

    # tick while idle

    def test_tick_while_idle_does_nothing(self):
        spi = self._make_spi()
        self._enable(spi)
        spi.tick(1)
        self.assertTrue(spi.clk_out.high)
        self.assertEqual(self.interrupts, [])

    # prescaler

    def test_prescaler_fx8_half_clock_is_4_ticks(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x81)  # enabled, SCL=01 (fX/8)
        spi.write(spi.SIO, 0x80)
        # CLK should stay high for 3 ticks, fall on tick 4
        for _ in range(3):
            spi.tick(1)
            self.assertTrue(spi.clk_out.high)
        spi.tick(1)
        self.assertTrue(spi.clk_out.low)

    def test_prescaler_fx16_half_clock_is_8_ticks(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x82)  # enabled, SCL=10 (fX/16)
        spi.write(spi.SIO, 0x80)
        for _ in range(7):
            spi.tick(1)
            self.assertTrue(spi.clk_out.high)
        spi.tick(1)
        self.assertTrue(spi.clk_out.low)

    def test_prescaler_fx64_half_clock_is_32_ticks(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x83)  # enabled, SCL=11 (fX/64)
        spi.write(spi.SIO, 0x80)
        for _ in range(31):
            spi.tick(1)
            self.assertTrue(spi.clk_out.high)
        spi.tick(1)
        self.assertTrue(spi.clk_out.low)

    def test_prescaler_full_byte_fx8(self):
        spi = self._make_spi()
        spi.write(spi.CSIM, 0x81)  # enabled, SCL=01 (fX/8)
        spi.write(spi.SIO, 0xA5)
        # 8 bits * 2 half-clocks * 4 ticks = 64 ticks
        for _ in range(63):
            spi.tick(1)
        self.assertEqual(self.interrupts, [])
        spi.tick(1)
        self.assertEqual(len(self.interrupts), 1)


class BaudRateGeneratorDeviceTests(unittest.TestCase):

    def _make_brg(self):
        from premium5.digital import LogicOutput, Level
        brg = BaudRateGeneratorDevice("brg0")
        self._enable_driver = LogicOutput(Level.LOW)
        self._enable_driver.bind(brg.enable_in)
        return brg

    def _enable(self):
        self._enable_driver.set_high()

    def _disable(self):
        self._enable_driver.set_low()

    # initial state

    def test_ctor_does_not_run(self):
        brg = self._make_brg()
        self.assertTrue(brg.enable_in.low)
        self.assertTrue(brg.baud_clk_out.low)
        brg.tick(1000)
        self.assertTrue(brg.baud_clk_out.low)

    # reset

    def test_reset_clears_register(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)
        brg.reset()
        self.assertEqual(brg.read(brg.BRGC0), 0x00)

    def test_reset_stops_clock(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)

        self._enable()
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.high)

        brg.reset()
        self.assertTrue(brg.baud_clk_out.low)
        brg.tick(1000)
        self.assertTrue(brg.baud_clk_out.low)

    # brgc0 register read/write

    def test_brgc0_read_returns_written_value(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)
        self.assertEqual(brg.read(brg.BRGC0), 0x39)

    def test_brgc0_write_tps_zero_does_not_run(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x09)  # TPS=000 (unsupported), MDL=1001

        self._enable()
        brg.tick(999)
        self.assertTrue(brg.baud_clk_out.low)

    def test_brgc0_write_mdl_fifteen_does_not_run(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x3F)  # TPS=011, MDL=1111 (prohibited)

        self._enable()
        brg.tick(999)
        self.assertTrue(brg.baud_clk_out.low)

    # enable input

    def test_enable_rising_starts_clock(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)

        self._enable()
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.high)
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.low)

    def test_enable_falling_stops_clock(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)

        self._enable()
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.high)

        self._disable()
        self.assertTrue(brg.baud_clk_out.low)
        brg.tick(1000)
        self.assertTrue(brg.baud_clk_out.low)

    def test_enable_rising_after_stop_resumes(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)

        self._enable()
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.high)

        self._disable()
        self.assertTrue(brg.baud_clk_out.low)

        self._enable()
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.high)
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.low)

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
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)
        self._enable()

        # should not toggle before 200 ticks
        brg.tick(199)
        self.assertTrue(brg.baud_clk_out.low)

        # tick 200: rising edge (start of bit)
        brg.tick(1)
        self.assertTrue(brg.baud_clk_out.high)

        # tick 400: falling edge
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.low)

        # tick 600: rising edge (start of next bit)
        brg.tick(200)
        self.assertTrue(brg.baud_clk_out.high)

    def test_10400_baud_10_bits_in_4000_cycles(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x39)
        self._enable()

        rising_edges = 0
        last = brg.baud_clk_out.high
        for _ in range(4000):
            brg.tick(1)
            if brg.baud_clk_out.high and not last:
                rising_edges += 1
            last = brg.baud_clk_out.high

        self.assertEqual(rising_edges, 10)

    # Verify the formula works at a second baud rate: 9600 (BRGC0=0x3B)
    #   0x3B = TPS=011 (n=3), MDL=1011 (k=11)
    #   cycles_per_bit = 2^4 * 27 = 432
    #   baud = 4,190,000 / 432 = 9699 (≈9600)

    def test_9600_baud_10_bits_in_4320_cycles(self):
        brg = self._make_brg()
        brg.write(brg.BRGC0, 0x3B)
        self._enable()

        rising_edges = 0
        last = brg.baud_clk_out.high
        for _ in range(4320):
            brg.tick(1)
            if brg.baud_clk_out.high and not last:
                rising_edges += 1
            last = brg.baud_clk_out.high

        self.assertEqual(rising_edges, 10)


class UARTDeviceTests(unittest.TestCase):
    """Tests for UART0 transmit path.

    The UART is clocked by a BaudRateGeneratorDevice.  We wire them
    together here and tick the BRG to drive the UART.  At BRGC0=0x39
    (10400 baud at 4.19 MHz), one bit = 400 CPU cycles.
    """

    def _make_uart(self):
        self.brg = BaudRateGeneratorDevice("brg0")
        self.uart = UARTDevice("uart0")
        self.uart.bus = self
        self.interrupts = []

        # wire BRG clock to UART
        self.brg.baud_clk_out.bind(self.uart.brg_clk_in)

        # wire UART enable to BRG
        self.uart.brg_enable_out.bind(self.brg.enable_in)

        # configure BRG for 10400 baud
        self.brg.write(self.brg.BRGC0, 0x39)

        return self.uart

    def interrupt(self, device, int_num):
        self.interrupts.append((device, int_num))

    def _tick_one_bit(self):
        """Tick one full bit period (400 cycles at 10400 baud)."""
        self.brg.tick(400)

    def _capture_tx_bits(self, n):
        """Capture n bits from TxD0, one per bit period."""
        bits = []
        for _ in range(n):
            self._tick_one_bit()
            bits.append(int(self.uart.txd_out.high))
        return bits

    # initial state

    def test_ctor_txd_idles_high(self):
        uart = self._make_uart()
        self.assertTrue(uart.txd_out.high)

    def test_ctor_brg_disabled(self):
        uart = self._make_uart()
        self.assertTrue(uart.brg_enable_out.low)

    # enable

    def test_asim0_txe_enables_brg(self):
        uart = self._make_uart()
        uart.write(uart.ASIM0, 0xCA)  # TXE0=1, RXE0=1, 8N1
        self.assertTrue(uart.brg_enable_out.high)

    def test_asim0_clear_disables_brg(self):
        uart = self._make_uart()
        uart.write(uart.ASIM0, 0xCA)
        uart.write(uart.ASIM0, 0x00)
        self.assertTrue(uart.brg_enable_out.low)

    # transmit: 8N1 frame (0xCA = TX+RX enabled, no parity, 8 bits, 1 stop)

    def test_tx_8n1_frame(self):
        uart = self._make_uart()
        uart.write(uart.ASIM0, 0xCA)  # TX+RX, 8N1

        # transmit 0x55 (01010101)
        uart.write(uart.TXS0_RXB0, 0x55)

        # capture 10 bits: start(1) + data(8) + stop(1)
        bits = self._capture_tx_bits(10)

        # start bit = 0
        self.assertEqual(bits[0], 0)

        # data bits LSB first: 0x55 = 10101010 LSB first
        self.assertEqual(bits[1:9], [1, 0, 1, 0, 1, 0, 1, 0])

        # stop bit = 1
        self.assertEqual(bits[9], 1)

    def test_tx_fires_interrupt(self):
        uart = self._make_uart()
        uart.write(uart.ASIM0, 0xCA)
        uart.write(uart.TXS0_RXB0, 0x55)

        for _ in range(10):
            self._tick_one_bit()

        self.assertEqual(len(self.interrupts), 1)
        self.assertIs(self.interrupts[0][0], uart)
        self.assertEqual(self.interrupts[0][1], uart.INT_TX)

    def test_tx_returns_to_idle_after_frame(self):
        uart = self._make_uart()
        uart.write(uart.ASIM0, 0xCA)
        uart.write(uart.TXS0_RXB0, 0x55)

        for _ in range(10):
            self._tick_one_bit()

        # TxD should be high (idle/mark)
        self.assertTrue(uart.txd_out.high)

        # further ticking should not fire more interrupts
        for _ in range(10):
            self._tick_one_bit()
        self.assertEqual(len(self.interrupts), 1)

    def test_tx_disabled_does_not_send(self):
        uart = self._make_uart()
        # don't enable TX
        uart.write(uart.TXS0_RXB0, 0x55)

        self.brg.tick(4000)
        self.assertTrue(uart.txd_out.high)
        self.assertEqual(self.interrupts, [])
