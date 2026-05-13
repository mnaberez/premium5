from premium5.nec import NECTransmitter


class MFSW:
    """Multi-Function Steering Wheel
    
    Sends packets to the radio as the steering wheel buttons would.
    """

    # Key codes
    VOL_DOWN = 0x00
    VOL_UP   = 0x01
    UP       = 0x0A
    DOWN     = 0x0B

    # Repeat interval.  The radio's firmware accepts a repeat frame
    # up to 155ms after a command frame and up to 210ms after a
    # repeat frame.  We picked 100ms because it is within those.
    # TODO: study a real MFSW with a logic analyzer.
    REPEAT_TICKS = 100_000

    def __init__(self):
        self._tx = NECTransmitter(0x82, 0x17, lambda: None)

        # SWC output is active-low (idle/space=HIGH, mark=LOW).
        # NECTransmitter is the opposite so its output is inverted
        self.swc_out = self._tx.data_out.inverted()

        self._key_down = False
        self._ticks_until_repeat = self.REPEAT_TICKS

    def key_down(self, code):
        '''Call this only once as the key goes down.  The given code
        must be one of the key code constants.  A command frame will
        be sent with the key code.  The key repeat will be handled
        on tick.'''
        self._tx.send(code)

        self._key_down = True
        self._ticks_until_repeat = self.REPEAT_TICKS

    def key_up(self):
        '''Call this only once as the key comes back up.'''
        self._key_down = False

    def tick_1mhz(self, ticks=1):
        self._tx.tick_1mhz(ticks)

        if (not self._key_down) or (self._tx.busy):
            return

        self._ticks_until_repeat -= ticks
        if self._ticks_until_repeat <= 0:
            self._tx.repeat()
            self._ticks_until_repeat = self.REPEAT_TICKS
