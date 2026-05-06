from k0emu.devices import BaseDevice
from premium5.digital import LogicInput, LogicOutput, Level


class PortDevice(BaseDevice):
    """GPIO port with 8 configurable pins
    """

    DATA = 0     # DATA (Pn)    output latch write, pin state read
    MODE = 1     # MODE (PMn)   0=output, 1=input
    PULLUP = 2   # PULLUP (PUn) 0=no pull-up, 1=pull-up

    def __init__(self, name):
        super().__init__(name)
        self.size = 3

        # internal state
        self._latch = 0x00   # output latch
        self._mode = 0xFF    # mode (0xFF=all inputs)
        self._pullup = 0x00  # pull-ups (0x00=no pull-ups)

        # i/o pins
        self.pins = []
        for i in range(8):
            self.pins.append(_PortDevicePin())

    def reset(self):
        self._latch = 0x00
        self._mode = 0xFF
        self._pullup = 0x00
        for pin_idx in range(8):
            self._configure_pin(pin_idx)

    def _configure_pin(self, pin_idx):
        pin = self.pins[pin_idx]
        mask = 1 << pin_idx
        pin.set_pullup(bool(self._pullup & mask))
        if self._mode & mask:
            pin.set_mode(_PortDevicePin.INPUT)
        else:
            pin.set_mode(_PortDevicePin.OUTPUT)
        if self._latch & mask:
            pin.set_output_level(Level.HIGH)
        else:
            pin.set_output_level(Level.LOW)

    def read(self, register):
        self._check_bounds(register)
        if register == self.DATA:
            result = 0
            for i in range(8):
                result |= (int(self.pins[i]) << i)
            return result
        elif register == self.MODE:
            return self._mode
        return self._pullup

    def write(self, register, value):
        self._check_bounds(register)
        if register == self.DATA:
            self._latch = value
        elif register == self.MODE:
            self._mode = value
        else:
            self._pullup = value
        for pin_idx in range(8):
            self._configure_pin(pin_idx)

class _PortDevicePin(object):
    """A bidirectional port pin with a LogicOutput (port driver)
    and a LogicInput (external input).

    Edge detection lives here, watching the resolved pin level.
    In input mode, external signal changes can trigger edges.
    In output mode, only output level changes can trigger edges."""

    INPUT = 0
    OUTPUT = 1

    _no_callback = staticmethod(lambda: None)

    def __init__(self):
        # electrical interface
        self.output = LogicOutput()
        self.input = LogicInput()

        # callbacks
        self.on_rising  = self._no_callback
        self.on_falling = self._no_callback

        # internal state
        self._mode = self.INPUT
        self._output_level = Level.LOW
        self._last_high = self.high

        # internal callbacks: logic input notifies us of its edges
        self.input.on_rising  = self._on_input_edge
        self.input.on_falling = self._on_input_edge

    def set_mode(self, mode):
        self._mode = mode
        self._update()
        self._check_edges()

    def set_pullup(self, enabled):
        if enabled:
            self.input.set_pull_level(Level.HIGH)
        else:
            self.input.set_pull_level(Level.FLOATING)

    def set_output_level(self, level):
        self._output_level = level
        self._update()
        self._check_edges()

    @property
    def high(self):
        if self._mode == self.OUTPUT:
            return self._output_level == Level.HIGH
        return self.input.high

    @property
    def low(self):
        if self._mode == self.OUTPUT:
            return self._output_level == Level.LOW
        return self.input.low

    def __int__(self):
        return int(self.high)

    def _on_input_edge(self):
        if self._mode == self.INPUT:
            self._check_edges()

    def _check_edges(self):
        current = self.high
        if current != self._last_high:
            self._last_high = current
            if current:
                self.on_rising()
            else:
                self.on_falling()

    def _update(self):
        if self._mode == self.INPUT:
            self.output.set_floating()
        elif self._output_level == Level.HIGH:
            self.output.set_high()
        else:
            self.output.set_low()


class Port0Device(PortDevice):
    """Port 0: 8-bit I/O port with external interrupt edge detection.
    P00/INTP0: input  MFSW (inverted; from HEF40106BT)
    P01/INTP1: input  Unknown (must be high or firmware power-on fails)
    P02/INTP2: input  Unknown (must be low or firmware stays in halt/sleep loop)
    P03/INTP3: input  Unknown (not used as INTP3)
    P04/INTP4: input  POWER key (0=pressed)
    P05/INTP5: input  uPD16432B KEYREQ (not used in firmware)
    P06/INTP6: input  STOP/EJECT key (0=pressed)
    P07/INTP7: input  Unknown
    Pull-up resistors on all pins.

    Also owns the EGP/EGN edge selection registers (0xFF48/0xFF49)
    which control which edges on P0 pins trigger INTP0-INTP7.
    """

    EGP = 3
    EGN = 4

    def __init__(self):
        super().__init__("p0")
        self.size = 5
        self._egp = 0x00
        self._egn = 0x00
        for i in range(8):
            idx = i
            self.pins[idx].on_rising = lambda idx=idx: self._on_pin_rising(idx)
            self.pins[idx].on_falling = lambda idx=idx: self._on_pin_falling(idx)

    def reset(self):
        super().reset()
        self._egp = 0x00
        self._egn = 0x00

    def read(self, register):
        if register == self.EGP:
            return self._egp
        if register == self.EGN:
            return self._egn
        return super().read(register)

    def write(self, register, value):
        if register == self.EGP:
            self._egp = value
        elif register == self.EGN:
            self._egn = value
        else:
            super().write(register, value)

    def _on_pin_rising(self, pin_idx):
        if self._egp & (1 << pin_idx):
            self.bus.interrupt(self, pin_idx)

    def _on_pin_falling(self, pin_idx):
        if self._egn & (1 << pin_idx):
            self.bus.interrupt(self, pin_idx)


class Port2Device(PortDevice):
    """Port 2: 8-bit I/O port.
    P20/SI31:  input   CDC DI (inverted; from HEF40106BT)
    P21/SO31:  output  Unknown
    P22/SCK31: output  CDC CLK (inverted; from HEF40106BT)
    P23:       input   Tape METAL sense (1=metal)
    P24/RxD0:  input   L9637D RX (K-line)
    P25/TxD0:  output  L9637D TX (K-line)
    P26:       output  K-line resistor (0=disconnected, 1=connected)
    P27:       output  Unknown
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p2")


class Port3Device(PortDevice):
    """Port 3: 7-bit I/O port (bit 7 fixed at 1).
    P30/SI30:  input   uPD16432B DAT in
    P31/SO30:  output  uPD16432B DAT out
    P32/SCK30: output  uPD16432B CLK
    P33:       output  Alarm LED (0=on, 1=off), N-ch open-drain
    P34/TO00:  output  Unknown
    P35/TI000: input   Unknown
    P36/TI010: unknown Unknown
    Pull-up resistors on P30-P32, P34-P36 (not P33)."""
    def __init__(self):
        super().__init__("p3")


class Port4Device(PortDevice):
    """Port 4: 8-bit I/O port.
    P40: input   Unknown
    P41: input   Unknown
    P42: input   Unknown
    P43: output  3LB bus isolation gate (0=isolated, 1=connected)
    P44: output  FIS ENA (3LB enable, active high)
    P45: input   FIS ENA readback (3LB enable from cluster)
    P46: output  uPD16432B /LCDOFF
    P47: output  uPD16432B STB
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p4")


class Port5Device(PortDevice):
    """Port 5: 8-bit I/O port, TTL level input.
    P50: output  Unknown
    P51: output  Unknown
    P52: output  Unknown
    P53: output  Unknown
    P54: output  Unknown
    P55: output  Unknown
    P56: unknown Unknown
    P57: output  CDC DO (inverted; to HEF40106BT)
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p5")


class Port6Device(PortDevice):
    """Port 6: 4-bit I/O port (P64-P67 only, lower 4 bits read as 1).
    P64: unknown Unknown
    P65: unknown Unknown
    P66: unknown Unknown
    P67: unknown Unknown
    Pull-up resistors on P64-P67."""
    def __init__(self):
        super().__init__("p6")


class Port7Device(PortDevice):
    """Port 7: 6-bit I/O port (bits 6-7 read as 1).
    P70/PCL:   unknown Unknown
    P71/SDA0:  output  I2C SDA, N-ch open-drain
    P72/SCL0:  output  I2C SCL, N-ch open-drain
    P73/TO01:  output  Bit-banged I2C SCL to TEA6840H NICE only
    P74/TI001: input   Bit-banged I2C SDA to TEA6840H NICE only
    P75/TI011: input   Unknown
    Pull-up resistors on P70, P73-P75 (not P71, P72)."""
    def __init__(self):
        super().__init__("p7")


class Port8Device(PortDevice):
    """Port 8: 8-bit I/O port.  No pull-up resistors.
    P80/ANI01: output  Switched 5V supply control (0=off, 1=on)
    P81/ANI11: output  Antenna phantom power out (0=off, 1=on)
    P82/ANI21: output  Monsoon amplifier power 12V out (0=off, 1=on)
    P83/ANI31: input   Unknown
    P84/ANI41: input   Unknown
    P85/ANI51: input   Unknown
    P86/ANI61: input   Unknown
    P87/ANI71: unknown Unknown"""
    def __init__(self):
        super().__init__("p8")

        # PortDevice has 3 registers (0=DATA, 1=MODE, 2=PULLUP) but this
        # port doesn't have pull-ups so we hide the PULLUP register
        self.size = 2


class Port9Device(PortDevice):
    """Port 9: 8-bit I/O port.  No pull-up resistors.
    P90/ANI00: input   S-Contact (0=off, 1=on)
    P91/ANI10: input   Terminal 30 Constant B+ analog input
    P92/ANI20: input   Terminal 58b Illumination analog input
    P93/ANI30: input   Unknown
    P94/ANI40: output  Unknown
    P95/ANI50: input   Unknown analog input
    P96/ANI60: input   Unknown
    P97/ANI70: output  Unknown"""
    def __init__(self):
        super().__init__("p9")

        # PortDevice has 3 registers (0=DATA, 1=MODE, 2=PULLUP) but this
        # port doesn't have pull-ups so we hide the PULLUP register
        self.size = 2


class SPIControllerDevice(BaseDevice):
    """3-wire serial I/O (clocked serial interface).

    Shifts out one bit per tick on clk_out and dat_out LogicOutputs.
    Reads dat_in LogicInput on each rising clock edge.

    Registers:
        0: SIO3x  - shift register
        1: CSIM3x - mode control
    """

    # registers
    SIO  = 0
    CSIM = 1

    # device-local interrupt id
    INT_TRANSFER = 0

    # clock phases
    _CLK_FALLING = 0
    _CLK_RISING = 1

    def __init__(self, name):
        super().__init__(name)
        self.size = 2
        self.clk_out = LogicOutput(Level.HIGH)
        self.dat_out = LogicOutput()
        self.dat_in = LogicInput(pull_level=Level.LOW)
        self.enabled_out = LogicOutput(Level.LOW)
        self.reset()

    def reset(self):
        # register defaults
        self._sio = 0x00
        self._csim = 0x00

        # prescaler
        self._cycles_per_sck_edge = 0    # total
        self._cycles_until_sck_edge = 0  # remaining

        # internal shifting state
        self._clk_phase = self._CLK_FALLING
        self._shift_out = 0x00
        self._shift_in = 0x00
        self._bits_remaining = 0

        # enable
        self.enabled_out.set_low()

    def read(self, register):
        self._check_bounds(register)

        if register == self.CSIM:
            return self._csim

        elif register == self.SIO:
            return self._sio

    def write(self, register, value):
        self._check_bounds(register)

        if register == self.CSIM:
            was_enabled = self._csim & 0x80
            self._csim = value
            
            if self._csim & 0x80:
                # now enabled
                self.enabled_out.set_high()
            else:
                # now disabled
                if was_enabled:
                    self._sio = 0x00
                    self._bits_remaining = 0
                self.enabled_out.set_low()

            # CPU ticks between each SCK edge (half the SPI clock period).
            # Each bit takes two half-periods: falling edge, then rising edge.
            self._cycles_per_sck_edge = (
                0,       # 0b00: External clock in from SCK30 (XXX not emulated)
                8  // 2, # 0b01: fX/8  (524 kHz)
                16 // 2, # 0b10: fX/16 (262 kHz)
                64 // 2, # 0b11: fX/64 (65.5 kHz)
            )[self._csim & 0x03]

        elif register == self.SIO:
            if self._csim & 0x80:
                # write to SIO while enabled starts a transfer
                self._shift_out = value
                self._shift_in = 0x00
                self._bits_remaining = 8
                self._clk_phase = self._CLK_FALLING
                self._cycles_until_sck_edge = self._cycles_per_sck_edge

    def tick(self, cycles):
        for _ in range(cycles):
            if self._bits_remaining == 0:
                return # nothing for the spi controller to do

            self._cycles_until_sck_edge -= 1
            if self._cycles_until_sck_edge > 0:
                continue # not time yet, loop to consume another cycle

            # it's time to shift a bit in/out
            if self._clk_phase == self._CLK_FALLING:
                # Falling edge: shift out MSB
                if self._shift_out & 0x80:
                    self.dat_out.set_high()
                else:
                    self.dat_out.set_low()
                self._shift_out = (self._shift_out << 1) & 0xFF

                self.clk_out.set_low()
                self._clk_phase = self._CLK_RISING

            else:
                # Rising edge: shift in from dat_in
                self._shift_in = (self._shift_in << 1) & 0xFF
                if self.dat_in.high:
                    self._shift_in |= 1

                self.clk_out.set_high()
                self._clk_phase = self._CLK_FALLING

                # decrement bits remaining, fire interrupt if done
                self._bits_remaining -= 1
                if self._bits_remaining == 0:
                    self._sio = self._shift_in
                    self.bus.interrupt(self, self.INT_TRANSFER)

            # bit has been shifted; reload to wait for the next bit
            self._cycles_until_sck_edge = self._cycles_per_sck_edge


class BaudRateGeneratorDevice(BaseDevice):
    """UART0 baud rate generator (BRGC0).

    Produces a clock signal on baud_clk_out that toggles at the configured
    baud rate.  The UART listens to this clock to time its bit shifting.

    Register:
        0: BRGC0 - baud rate generator control

    Baud rate = fX / (2^(TPS+1) * (16 + MDL))
    where TPS = bits 6:4, MDL = bits 3:0.
    """

    BRGC0 = 0

    def __init__(self, name):
        super().__init__(name)

        # register sizes
        self.size = 1

        # electrical interface
        self.enable_in = LogicInput(pull_level=Level.LOW)
        self.baud_clk_out = LogicOutput(Level.LOW)

        # internal callbacks
        self.enable_in.on_rising = self._on_enable
        self.enable_in.on_falling = self._on_disable

        self.reset()

    def reset(self):
        self._brgc0 = 0x00
        self._invalid = True
        self._cycles_per_toggle = 0    # total
        self._cycles_until_toggle = 0  # remaining
        self.baud_clk_out.set_low()

    def read(self, register):
        self._check_bounds(register)
        return self._brgc0

    def write(self, register, value):
        self._check_bounds(register)
        self._brgc0 = value

        tps = (self._brgc0 >> 4) & 0x07
        mdl = self._brgc0 & 0x0F

        # The baud rate generator output is a square wave.  One full
        # cycle (rising edge to rising edge) = one bit period.  The
        # UART shifts one bit on each rising edge.
        #
        # cycles_per_bit = 2^(TPS+1) * (16 + MDL)
        #
        # Example: BRGC0=0x39 at fX=4.19 MHz
        #   TPS=3, MDL=9
        #   cycles_per_bit = 2^4 * 25 = 400
        #   baud = 4,190,000 / 400 = 10,475 (~10400 baud)
        #   toggle every 200 cycles, rising edge every 400 cycles
        #
        cycles_per_bit = (1 << (tps + 1)) * (16 + mdl)
        self._cycles_per_toggle = cycles_per_bit // 2

        # TPS=0 is external clock (XXX not supported), MDL=15 is prohibited
        self._invalid = (tps == 0) or (mdl == 0x0F)

    def _on_enable(self):
        self.baud_clk_out.set_low()
        self._cycles_until_toggle = self._cycles_per_toggle

    def _on_disable(self):
        self.baud_clk_out.set_low()

    def tick(self, cycles):
        if self.enable_in.low or self._invalid:
            return

        for _ in range(cycles):
            self._cycles_until_toggle -= 1
            if self._cycles_until_toggle > 0:
                continue

            self._cycles_until_toggle = self._cycles_per_toggle
            self.baud_clk_out.toggle()
