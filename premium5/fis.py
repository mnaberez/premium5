from premium5.digital import Level, LogicInput, LogicOutput


class FISReceiver(object):
    """Instrument cluster side of the 3LB (FIS) bus.

    Receives bytes from the radio via CLK/DAT, with ENA handshaking.
    After the radio sends the first byte (signaled by ENA pulse on
    P4.4), the cluster drives ENA high on P4.5 to request each
    subsequent byte.

    SPI settings (confirmed by a logic analyzer capture of
                  the 3LB lines on the back of a cluster):

        CPOL=1: CLK idles HIGH
        CPHA=1: DAT is read on the falling (trailing) CLK edge
        MSB first, 8 bits per transfer

    CLK/DAT could in theory be directly connected to the radio's SPI controller 
    CSI30.  In practice, they need to be connected through a transparent mux
    (CSI30Mux) because CSI30 is also used to drive the uPD16432B.
    """

    # Timing in ticks at 1 MHz (1 tick = 1 us)
    # ticks before driving ENA high after receiving a byte
    ENA_RESPONSE_DELAY_CYCLES = 120  # guess

    def __init__(self):
        # electrical interface
        self.clk_in = LogicInput()
        self.dat_in = LogicInput()
        self.ena_in = LogicInput()
        self.ena_out = LogicOutput(Level.LOW)

        # received display data
        self.radio_data = bytearray()

        # shift register / packet assembly
        self._shift_in = 0x00
        self._shift_count = 0
        self._packet = bytearray()
        self._bytes_expected = 0

        # ENA timing
        self._ena_delay_cycles = 0

        # callbacks
        self.clk_in.on_falling = self._on_clk_falling
        self.ena_in.on_rising = self._on_ena_rising

    def tick_1mhz(self, cycles=1):
        if self._ena_delay_cycles > 0:
            self._ena_delay_cycles -= cycles
            if self._ena_delay_cycles <= 0:
                self._ena_delay_cycles = 0
                self.ena_out.set_high()

    # callbacks: electrical

    # TODO detecting the rising edge works but the cluster probably
    # times the pulse so we should do that here, too.
    def _on_ena_rising(self):
        """Radio pulsed ENA high: first byte is coming"""
        self._shift_in = 0x00
        self._shift_count = 0
        self._packet = bytearray()
        self._bytes_expected = 0

    def _on_clk_falling(self):
        """Falling CLK edge: shift in a bit"""
        # receiving a byte, pull ENA low
        if self.ena_out.high:
            self.ena_out.set_low()

        self._shift_in = (self._shift_in << 1) | int(self.dat_in)
        self._shift_count += 1
        if self._shift_count == 8:
            self._on_byte(self._shift_in & 0xFF)
            self._shift_in = 0x00
            self._shift_count = 0

    # callbacks: our internal ones called after a byte is received

    # TODO we probably want some kind of timeout in case only
    # a partial packet is received.
    def _on_byte(self, byte):
        """A complete byte has been received"""
        self._packet.append(byte)

        if len(self._packet) == 2:
            # second byte is the length
            self._bytes_expected = byte + 2  # cmd + length + checksum

        if len(self._packet) == self._bytes_expected:
            self._on_packet()
        else:
            # schedule ENA high after a delay
            self._ena_delay_cycles = self.ENA_RESPONSE_DELAY_CYCLES

    def _on_packet(self):
        """Full packet received, extract display data"""

        # validate packet length (cmd + length + checksum)
        if len(self._packet) < 3:
            return

        # validate packet checksum
        csum = 0
        for b in self._packet[:-1]:
            csum ^= b
        if self._packet[-1] != ((csum - 1) & 0xFF):
            return

        # good packet; update radio data
        if self._packet[0] == 0x81:
            self.radio_data = bytearray(self._packet[2:-1])
