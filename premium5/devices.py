from k0emu.devices import BaseDevice, BasePortDevice, PortWithPullupsDevice, PortWithEdgeDetectionDevice
from premium5.digital import LogicInput, LogicOutput, Level


class Port2Device(PortWithPullupsDevice):
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


class PortPin(object):
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
            self.input.set_default(Level.HIGH)
        else:
            self.input.set_default(Level.FLOATING)

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


class PortDevice(BaseDevice):
    """GPIO port with PortPins.

    Registers:
        0: DATA (Pn)   - output latch write, pin state read
        1: MODE (PMn)   - 0=output, 1=input
        2: PULLUP (PUn) - 0=no pull-up, 1=pull-up
    """

    DATA = 0
    MODE = 1
    PULLUP = 2

    def __init__(self, name):
        super().__init__(name)
        self.size = 3
        self._latch = 0x00
        self._mode = 0xFF  # all inputs
        self._pullup = 0x00
        self.pins = []
        for i in range(8):
            self.pins.append(PortPin())

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
            pin.set_mode(PortPin.INPUT)
        else:
            pin.set_mode(PortPin.OUTPUT)
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


class Port0Device(PortDevice):
    """Port 0: 8-bit I/O port with external interrupt edge detection.
    P00/INTP0: input  MFSW (inverted; from HEF40106BT)
    P01/INTP1: input  Unknown
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


class Port5Device(PortWithPullupsDevice):
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


class Port6Device(PortWithPullupsDevice):
    """Port 6: 4-bit I/O port (P64-P67 only, lower 4 bits read as 1).
    P64: unknown Unknown
    P65: unknown Unknown
    P66: unknown Unknown
    P67: unknown Unknown
    Pull-up resistors on P64-P67."""
    def __init__(self):
        super().__init__("p6")


class Port7Device(PortWithPullupsDevice):
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


class Port8Device(BasePortDevice):
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


class Port9Device(BasePortDevice):
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
        self.external_inputs = 0xFE  # P9.0=0: S-Contact off (ignition off)
    def reset(self):
        super().reset()
        self.external_inputs = 0xFE  # P9.0=0: S-Contact off (ignition off)


class SPIControllerDevice(BaseDevice):
    """3-wire serial I/O (clocked serial interface).

    Shifts out one bit per tick on clk_out and dat_out LogicOutputs.
    Reads dat_in LogicInput on each rising clock edge.

    Registers:
        0: SIO3x  - shift register
        1: CSIM3x - mode control
    """

    SIO  = 0
    CSIM = 1

    INT_TRANSFER = 0

    def __init__(self, name):
        super().__init__(name)
        self.size = 2
        self.clk_out = LogicOutput()
        self.clk_out.set_high()
        self.dat_out = LogicOutput()
        self.dat_in = LogicInput(default=Level.LOW)
        self.reset()

    def reset(self):
        self._sio = 0x00
        self._csim = 0x00
        self._shift_out = 0x00
        self._shift_in = 0x00
        self._bit_count = 0
        self._clk_phase = 0
        self._transferring = False

    def read(self, register):
        self._check_bounds(register)
        if register == self.SIO:
            return self._sio
        return self._csim

    def write(self, register, value):
        self._check_bounds(register)
        if register == self.CSIM:
            self._csim = value
            return

        self._shift_out = value
        self._shift_in = 0x00
        self._bit_count = 0
        self._transferring = True

    def tick(self, cycles):
        if not self._transferring:
            return

        if self._bit_count >= 8:
            self._sio = self._shift_in
            self._transferring = False
            self.bus.interrupt(self, self.INT_TRANSFER)
            return

        if self._clk_phase == 0:
            # Falling edge: shift out data bit (MSB first)
            bit = (self._shift_out >> (7 - self._bit_count)) & 1
            if bit:
                self.dat_out.set_high()
            else:
                self.dat_out.set_low()
            self.clk_out.set_low()
            self._clk_phase = 1
        else:
            # Rising edge: latch input data bit
            self._shift_in |= (int(self.dat_in) << (7 - self._bit_count))
            self.clk_out.set_high()
            self._clk_phase = 0
            self._bit_count += 1
