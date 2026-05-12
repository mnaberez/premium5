"""Asynchronous serial transmitter, receiver, and baud rate generator.

This module is used to build async serial devices that run within the
emulator.  It is used by the emulation of the 78F0831Y's USART0
(UARTDevice) but not coupled to it.  It's possible, for example, to use
the AsyncSerialTransmitter in this module to transmit data into USART0's
receiver.  Under the hood, USART0 receives logic levels that change
at the correct times, just as the real USART0 does over a physical wire.
"""

from collections import namedtuple
from premium5.digital import LogicInput, LogicOutput, Level


class Parity:
    NONE = 0
    ZERO = 1
    ODD = 2
    EVEN = 3


class AsyncSerialTransmitter:
    """Async serial transmit shift register.

    Builds a serial frame (start + data + parity + stop) and
    shifts it out on txd_out.  Fires a callback when complete.
    """

    def __init__(self, txd_out, on_complete):
        self._txd_out = txd_out
        self.on_complete = on_complete

        self._brg = BaudRateGenerator()
        self._brg_clk_in = LogicInput()
        self._brg.baud_clk_out.drives(self._brg_clk_in)
        self._brg_clk_in.on_rising(self._on_baud_clk_rising)

        self.reset()

    def reset(self):
        self._data_bits = 8
        self._parity = Parity.NONE
        self._stop_bits = 1

        self._shift = 0
        self._bits_remaining = 0

        self._txd_out.set_high()
        self._brg.reset()

    def configure_frame(self, data_bits, stop_bits, parity):
        self._data_bits = data_bits
        self._parity = parity
        self._stop_bits = stop_bits

    def configure_brg(self, cycles_per_bit):
        self._brg.configure(cycles_per_bit)

    def tick(self, cycles):
        self._brg.tick(cycles)

    def enable(self):
        self._brg.enable()

    def disable(self):
        if self.transmitting:
            # The uPD78F0833Y subseries manual says not to disable the UART
            # mid-transmission but doesn't say what happens if you do.  We've
            # chosen to shut down cleanly on disable.
            self._shift = 0
            self._bits_remaining = 0
            self._txd_out.set_high()
        self._brg.disable()

    @property
    def transmitting(self):
        return self._bits_remaining > 0

    def transmit(self, data):
        if self.transmitting:
            # The uPD78F0833Y subseries manual says not to write to the TX
            # register while a TX is already in process but doesn't say what
            # happens if you do.  We've chosen to ignore second transmission.
            return

        # Assemble frame LSB first: start + data + parity + stops
        frame = 0
        bit_pos = 0

        # start bit
        bit_pos += 1  # bit 0 is already 0

        # data bits (LSB first)
        ones = 0
        for i in range(self._data_bits):
            bit = (data >> i) & 1
            ones += bit
            frame |= (bit << bit_pos)
            bit_pos += 1

        # parity bit
        if self._parity != Parity.NONE:
            if self._parity == Parity.ZERO:
                p = 0
            elif self._parity == Parity.EVEN:
                p = ones & 1
            elif self._parity == Parity.ODD:
                p = (ones & 1) ^ 1
            frame |= (p << bit_pos)
            bit_pos += 1

        # stop bit(s)
        for _ in range(self._stop_bits):
            frame |= (1 << bit_pos)
            bit_pos += 1

        self._shift = frame
        self._bits_remaining = bit_pos

    def _on_baud_clk_rising(self):
        if not self.transmitting:
            return

        self._txd_out.set_level_from(self._shift & 1)

        self._shift >>= 1
        self._bits_remaining -= 1

        if self._bits_remaining == 0:
            self._txd_out.set_high()
            self.on_complete()


class AsyncSerialReceiver:
    """Async serial receive shift register.

    Receives bits on rxd_in.  When a frame is complete,
    on_complete(data, error) is called.  error is None on
    success, or a ReceiveError on framing/parity error.
    Data is always valid — even on error, the received byte
    is delivered.
    """

    def __init__(self, rxd_in, on_complete):
        self._rxd_in = rxd_in
        self.on_complete = on_complete

        self._brg = BaudRateGenerator()
        self._brg_clk_in = LogicInput()
        self._brg.baud_clk_out.drives(self._brg_clk_in)
        self._brg_clk_in.on_rising(self._on_baud_clk_rising)

        self.reset()

    def reset(self):
        self._data_bits = 8
        self._parity = Parity.NONE
        self._stop_bits = 1

        self._shift = 0
        self._bits_remaining = 0
        self._bits_received = 0
        self._enabled = False

        self._brg.reset()

    def configure_frame(self, data_bits, stop_bits, parity):
        self._data_bits = data_bits
        self._parity = parity
        self._stop_bits = stop_bits

    def configure_brg(self, cycles_per_bit):
        self._brg.configure(cycles_per_bit)

    def tick(self, cycles):
        self._brg.tick(cycles)

    def enable(self):
        self._enabled = True

    def disable(self):
        self._shift = 0
        self._bits_remaining = 0
        self._enabled = False
        self._brg.disable()

    @property
    def receiving(self):
        return self._bits_remaining > 0

    def _on_rxd_falling(self):
        """Start bit detection:

        The receiver samples exactly in the middle of each bit.  To
        achieve this, its BRG is started fresh on each frame.

        RxD idles high.  The first falling edge on RxD is the beginning
        of the start bit.  We start the BRG on this edge.  The BRG
        outputs a square wave where one bit period is the time between
        rising edges.  When the BRG starts, it is guaranteed to be low
        for exactly one half bit period.  This means that each rising
        edge of the BRG will be exactly in the middle of a bit:

             ____
        RxD:     |_____start_____|______D0______|______D1______|
                 ^       ^              ^              ^
            we are      BRG            BRG            BRG
             here      rise #1        rise #2        rise #3  ...
                     (mid-start)     (mid-D0)       (mid-D1)
        """

        if not self._enabled:
            return

        # can't be the start bit if we are already receiving bits
        if self.receiving:
            return

        # it's the beginning of the start bit (receiver always uses 1 stop bit)
        self._bits_remaining = 1 + self._data_bits + 1
        if self._parity != Parity.NONE:
            self._bits_remaining += 1
        self._shift = 0
        self._bits_received = 0
        self._brg.enable()

    def _on_baud_clk_rising(self):
        """BRG rising edge means we're in the middle of a bit so it's
        time to sample RxD and shift it into the frame."""

        if not self.receiving:
            return

        self._bits_received += 1

        # uPD78F0833Y subseries manual: the start bit is confirmed at
        # mid-bit.  If RxD is not still low, the frame is abandoned.
        # This is presumably to filter out line glitches.
        if self._bits_received == 1:
            if self._rxd_in.high:
                self._bits_remaining = 0
                self._brg.disable()
                return

        self._shift >>= 1
        if self._rxd_in.high:
            total_bits = 1 + self._data_bits + 1
            if self._parity != Parity.NONE:
                total_bits += 1
            self._shift |= (1 << (total_bits - 1))

        self._bits_remaining -= 1

        if self._bits_remaining == 0:
            self._brg.disable()
            self._deliver_frame()

    def _deliver_frame(self):
        frame = self._shift
        bit_pos = 0

        # uPD78F0833Y subseries manual: if the start bit is not 0
        # at mid-bit, the receiver silently discards the frame.
        start_bit = (frame >> bit_pos) & 1
        bit_pos += 1
        if start_bit != 0:
            return

        # data bits (LSB first)
        data, ones = 0, 0
        for i in range(self._data_bits):
            bit = (frame >> bit_pos) & 1
            data |= (bit << i)
            ones += bit
            bit_pos += 1

        # parity bit
        parity_error = False
        if self._parity != Parity.NONE:
            p = (frame >> bit_pos) & 1
            bit_pos += 1
            if self._parity == Parity.ZERO:
                # uPD78F0833Y subseries manual: zero parity is not checked
                # on receive, so parity errors never occur for zero parity.
                pass
            elif self._parity == Parity.EVEN:
                parity_error = (p != (ones & 1))
            elif self._parity == Parity.ODD:
                parity_error = (p != ((ones & 1) ^ 1))

        # uPD78F0833Y subseries manual: the receiver only checks one
        # stop bit for framing errors, regardless of the SL0 setting.
        stop_bit = (frame >> bit_pos) & 1
        framing_error = (stop_bit != 1)
        bit_pos += 1

        if framing_error or parity_error:
            error = ReceiveError(framing_error, parity_error)
        else:
            error = None
        self.on_complete(data, error)


ReceiveError = namedtuple('ReceiveError', ['framing_error', 'parity_error'])


class BaudRateGenerator:
    """Baud rate clock generator.

    Produces a square wave on baud_clk_out at a configured rate.
    One full cycle (rising edge to rising edge) = one bit period.
    The clock output is low on reset or after being stopped.
    After being started, the clock goes high after one half bit period.
    """

    def __init__(self):
        self.baud_clk_out = LogicOutput(Level.LOW)
        self._cycles_per_toggle = 0
        self._cycles_until_toggle = 0
        self._enabled = False

    def reset(self):
        self._cycles_per_toggle = 0
        self._cycles_until_toggle = 0
        self._enabled = False
        self.baud_clk_out.set_low()

    def configure(self, cycles_per_bit):
        """Configure the baud rate.

        cycles_per_bit is the number of clock cycles per bit period.
        The BRG toggles every cycles_per_bit/2 cycles, producing a
        rising edge every cycles_per_bit cycles.
        """
        self._cycles_per_toggle = cycles_per_bit // 2

    def enable(self):
        """Enable the BRG.  There are two non-obvious contracts that
        the BRG has with the rest of the system:

        1. For the receiver and transmitter, the enable behavior
           is always deterministic and used for synchronization:
           On enable, BRG's output will be low for exactly one half
           bit period.  The output will then go high and continue
           to toggle (invert) every half bit period.  

        2. For the UART device, enable() becomes a no-op if 0 cycles
           per bit have been configured.  This is what the device
           sets when its registers are invalid.  The output stays low.
        """
        self.baud_clk_out.set_low()
        if self._cycles_per_toggle > 0:
            self._enabled = True
            self._cycles_until_toggle = self._cycles_per_toggle

    def disable(self):
        self._enabled = False
        self.baud_clk_out.set_low()

    def tick(self, cycles):
        if not self._enabled:
            return

        for _ in range(cycles):
            self._cycles_until_toggle -= 1
            if self._cycles_until_toggle > 0:
                continue

            self._cycles_until_toggle = self._cycles_per_toggle
            self.baud_clk_out.toggle()
