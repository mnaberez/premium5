from k0emu.devices import BaseDevice
from premium5.digital import LogicInput, LogicOutput, Level, Mux
from premium5.serial import AsyncSerialTransmitter, AsyncSerialReceiver, Parity


class CompareMatchTimerDevice(BaseDevice):
    """16-bit free-running timer with compare interrupt

    Consists of a free-running 16-bit counter (TM01) and a compare
    register (CR011).  Interrupt INTTM011 fires when the counter
    reaches the compare value.

    uPD78F0833Y subseries manual, Chapter 7:
        TM01 (FF14-FF15): 16-bit free-running timer counter (read-only)
        CR011 (FF12-FF13): 16-bit capture/compare register 011

    Bus mapping:
        register 0: CR011 low byte   (FF12)
        register 1: CR011 high byte  (FF13)
        register 2: TM01 low byte    (FF14, read-only)
        register 3: TM01 high byte   (FF15, read-only)
    """

    CR_LO = 0
    CR_HI = 1
    TM_LO = 2
    TM_HI = 3

    INT_COMPARE = 0

    def __init__(self, name):
        super().__init__(name)
        self.size = 4
        self._counter = 0   # TM01 free-running counter
        self._compare = 0   # CR011 compare register

    def read(self, register):
        self._check_bounds(register)

        if register == self.CR_LO:
            return self._compare & 0xFF
        elif register == self.CR_HI:
            return (self._compare >> 8) & 0xFF
        elif register == self.TM_LO:
            return self._counter & 0xFF
        else:
            return (self._counter >> 8) & 0xFF

    def write(self, register, value):
        self._check_bounds(register)

        if register == self.CR_LO:
            self._compare = (self._compare & 0xFF00) | value
        elif register == self.CR_HI:
            self._compare = (self._compare & 0x00FF) | (value << 8)

    def tick(self, cycles):
        for _ in range(cycles):
            self._counter = (self._counter + 1) & 0xFFFF
            if self._counter == self._compare:
                self.bus.interrupt(self, self.INT_COMPARE)


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
        self._on_rising  = self._no_callback
        self._on_falling = self._no_callback

        # internal state
        self._mode = self.INPUT
        self._output_level = Level.LOW
        self._last_high = self.high

        # internal callbacks: logic input notifies us of its edges
        self.input.on_rising(self._on_input_edge)
        self.input.on_falling(self._on_input_edge)

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
                self._on_rising()
            else:
                self._on_falling()

    def on_rising(self, callback):
        self._on_rising = callback
        return self

    def on_falling(self, callback):
        self._on_falling = callback
        return self

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
            self.pins[idx].on_rising(lambda idx=idx: self._on_pin_rising(idx))
            self.pins[idx].on_falling(lambda idx=idx: self._on_pin_falling(idx))

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

    One shift register clocked by falling/rising edges.  The clock
    source is either an internal prescaler (SCL=01/10/11) or an
    external signal on clk_in (SCL=00).  Both feed the same shift
    logic through callbacks.

    uPD78F0833Y subseries manual, Chapter 14:
        Data shifts out (SO) on the falling edge of SCK.
        Data latches in (SI) on the rising edge of SCK.
        MSB first, 8 bits per transfer.

    Registers:
        0: SIO3x  - shift register
        1: CSIM3x - mode control
    """

    # registers
    SIO  = 0
    CSIM = 1

    # device-local interrupt id
    INT_TRANSFER = 0

    def __init__(self, name):
        super().__init__(name)
        self.size = 2

        # electrical interface
        self.clk_in = LogicInput(pull_level=Level.HIGH)
        self.clk_out = LogicOutput(Level.HIGH)
        self.dat_in = LogicInput(pull_level=Level.LOW)
        self.dat_out = LogicOutput()
        self.enabled_out = LogicOutput(Level.LOW) # XXX does not handle receive-only

        # internal clock output that we'll generate ourselves in tick()
        self._internal_clk_out = LogicOutput(Level.HIGH)

        # clock multiplexer: switches between internal and external clock
        mux = Mux()
        self._internal_clk_out.drives(mux.input_a)
        self._ext_clk_to_mux = mux.input_b.driver()
        self.clk_in.on_rising(self._ext_clk_to_mux.set_high)
        self.clk_in.on_falling(self._ext_clk_to_mux.set_low)

        # control output to multiplexer: low=internal, high=external clock
        self._clk_select_out = LogicOutput(Level.LOW)
        self._clk_select_out.drives(mux.select_in)

        # state must be initialized before wiring callbacks
        self._init_state()

        # callbacks that fire when selected clock changes
        sck_in = mux.output.follower()
        sck_in.on_falling(self._on_clk_falling)
        sck_in.on_rising(self._on_clk_rising)

        self.reset()

    def _init_state(self):
        # register defaults
        self._sio = 0x00
        self._csim = 0x00

        # prescaler
        self._cycles_per_sck_edge = 0    # total
        self._cycles_until_sck_edge = 0  # remaining

        # internal shifting state
        self._shift_out = 0x00
        self._shift_in = 0x00
        self._bits_remaining = 0

    def reset(self):
        self._init_state()
        self.clk_out.set_high()
        self.enabled_out.set_low()

    def tick(self, cycles):
        """Advance the internal clock prescaler."""
        if self._is_external_clock():
            return

        for _ in range(cycles):
            if self._bits_remaining == 0:
                return  # nothing for the spi controller to do

            self._cycles_until_sck_edge -= 1
            if self._cycles_until_sck_edge > 0:
                continue # not time yet, loop to consume another cycle

            # it's time to shift a bit in/out
            self._cycles_until_sck_edge = self._cycles_per_sck_edge
            self._internal_clk_out.toggle()

    def _on_clk_falling(self):
        """Falling edge: shift out data, then drive clk_out low.
        Data is set before the clock edge so external devices
        see valid data when they latch on the falling edge."""
        if self._bits_remaining == 0:
            return

        if self._shift_out & 0x80:
            self.dat_out.set_high()
        else:
            self.dat_out.set_low()

        self._shift_out = (self._shift_out << 1) & 0xFF

        # only drive clk_out for internal clock; in external clock
        # mode the external device is already driving the pin
        if not self._is_external_clock():
            self.clk_out.set_low()

    def _on_clk_rising(self):
        """Rising edge: latch data from SI."""
        if self._bits_remaining == 0:
            return

        if not self._is_external_clock():
            self.clk_out.set_high()

        self._shift_in = (self._shift_in << 1) & 0xFF
        if self.dat_in.high:
            self._shift_in |= 1

        self._bits_remaining -= 1
        if self._bits_remaining == 0:
            self._sio = self._shift_in
            self.bus.interrupt(self, self.INT_TRANSFER)

    def read(self, register):
        self._check_bounds(register)

        if register == self.CSIM:
            return self._csim

        elif register == self.SIO:
            # uPD78F0833Y subseries manual: in receive-only mode (MODE=1),
            # reading SIO triggers the transfer.
            if (self._csim & 0x80) and self._is_receive_only():
                self._shift_out = 0x00
                self._start_transfer()
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

            # clock source selection
            if self._is_external_clock():
                self._clk_select_out.set_high()  # select external clock

                self._cycles_per_sck_edge = 0
            else:
                self._clk_select_out.set_low()   # select internal clock

                # CPU ticks between each SCK edge (half the SPI clock period).
                # Each bit takes two half-periods: falling edge, then rising edge.
                self._cycles_per_sck_edge = (
                    0,       # 0b00: (not used, external selected above)
                    8  // 2, # 0b01: fX/8  (524 kHz)
                    16 // 2, # 0b10: fX/16 (262 kHz)
                    64 // 2, # 0b11: fX/64 (65.5 kHz)
                )[self._csim & 0x03]

        elif register == self.SIO:
            # uPD78F0833Y subseries manual: in transmit/transmit-and-receive
            # mode (MODE=0), writing SIO triggers the transfer.
            if (self._csim & 0x80) and not self._is_receive_only():
                self._shift_out = value
                self._start_transfer()

    def _start_transfer(self):
        """Start an 8-bit transfer."""
        self._shift_in = 0x00
        self._bits_remaining = 8
        if not self._is_external_clock():
            self._cycles_until_sck_edge = self._cycles_per_sck_edge

    def _is_receive_only(self):
        return bool(self._csim & 0x04)

    def _is_external_clock(self):
        return (self._csim & 0x03) == 0x00


class UARTDevice(BaseDevice):
    """Asynchronous serial interface UART0.

    Registers (split address space):
        0: TXS0/RXB0 (FF18) - write=transmit, read=receive buffer
        1: ASIM0     (FFA0) - mode control
        2: ASIS0     (FFA1) - status (read-only)
        3: BRGC0     (FFA2) - baud rate generator control
    """

    # register offsets
    TXS0_RXB0 = 0
    ASIM0 = 1
    ASIS0 = 2
    BRGC0 = 3

    # interrupt sources
    INT_TX = 0   # INTST0:  transmit complete
    INT_RX = 1   # INTSR0:  receive complete
    INT_ERR = 2  # INTSER0: receive error


    def __init__(self, name):
        super().__init__(name)
        self.size = 4

        # electrical interface
        self.rxd_in = LogicInput(pull_level=Level.HIGH)
        self.txd_out = LogicOutput(Level.HIGH)
        self.tx_enabled_out = LogicOutput(Level.LOW) # for tx/gpio pin mux

        # transmitter
        self._tx = AsyncSerialTransmitter(self.txd_out, self._on_tx_complete)

        # receiver
        self._rx = AsyncSerialReceiver(self.rxd_in, self._on_rx_complete)
        self.rxd_in.on_falling(self._rx._on_rxd_falling)

        self.reset()

    def reset(self):
        self._brgc0 = 0x00
        self._asim0 = 0x00
        self._asis0 = 0x00

        self._rxb0 = 0xFF
        self._rxb0_read = True

        self._rx.reset()
        self._tx.reset()
        self.tx_enabled_out.set_low()

    def read(self, register):
        self._check_bounds(register)

        if register == self.TXS0_RXB0:
            # uPD78F0833Y subseries manual: reading RXB0 clears ASIS0
            self._rxb0_read = True
            self._asis0 = 0x00
            return self._rxb0

        elif register == self.ASIM0:
            return self._asim0

        elif register == self.ASIS0:
            return self._asis0

        elif register == self.BRGC0:
            return self._brgc0

    def write(self, register, value):
        self._check_bounds(register)

        if register == self.BRGC0:
            self._brgc0 = value

            tps = (value >> 4) & 0x07
            mdl = value & 0x0F

            # TPS=0 is external clock (not supported), MDL=15 is prohibited
            if (tps != 0) and (mdl != 0x0F):
                cycles_per_bit = (1 << (tps + 1)) * (16 + mdl)
                self._tx.configure_brg(cycles_per_bit)
                self._rx.configure_brg(cycles_per_bit)

        elif register == self.ASIM0:
            self._asim0 = value

            # ASIM0 frame settings
            cl0 = (value >> 3) & 1
            sl0 = (value >> 2) & 1
            ps  = (value >> 4) & 0x03

            # configure frame from ASIM0 settings
            data_bits = 7 + cl0   # CL0: 0=7 bits, 1=8 bits
            stop_bits = 1 + sl0   # SL0: 0=1 stop, 1=2 stop
            parity = (Parity.NONE, Parity.ZERO, Parity.ODD, Parity.EVEN)[ps]
            self._tx.configure_frame(data_bits, stop_bits, parity)
            self._rx.configure_frame(data_bits, stop_bits, parity)

            # transmit enable
            if value & 0x80:  # TXE0
                self._tx.enable()
                self.tx_enabled_out.set_high()
            else:
                self._tx.disable()
                self.tx_enabled_out.set_low()

            # receive enable
            if value & 0x40:  # RXE0
                self._rx.enable()
            else:
                self._rx.disable()

        elif register == self.TXS0_RXB0:
            if self._asim0 & 0x80:
                self._tx.transmit(value)

    def tick(self, cycles):
        # TX and RX must be interleaved, not batched: if they are not kept in
        # lockstep, the transmitter may overrun the receiver.
        for _ in range(cycles):
            self._tx.tick(1)
            self._rx.tick(1)

    def _on_tx_complete(self):
        self.bus.interrupt(self, self.INT_TX)

    def _on_rx_complete(self, data, error):
        # uPD78F0833Y subseries manual: ASIS0 is cleared when the next data is received
        self._asis0 = 0x00

        # upD78F0833Y subseries manual: "Even if an error has occurred, the receive
        # data in which the error occurred is still transferred to RXB0."
        if not self._rxb0_read:
            self._asis0 |= 0x01  # OVE0
        self._rxb0 = data
        self._rxb0_read = False

        if error is not None:
            if error.framing_error:
                self._asis0 |= 0x02  # FE0
            if error.parity_error:
                self._asis0 |= 0x04  # PE0
            self.bus.interrupt(self, self.INT_ERR)

        # uPD78F0833Y subseries manual: INTSER0 fires before INTSR0.
        # ISRM0=1 suppresses INTSR0 on error.
        if (error is None) or ((self._asim0 & 0x02) == 0):
            self.bus.interrupt(self, self.INT_RX)
