"""MFSW (Multi-Function Steering Wheel) transmitter.

Emulates the steering wheel controller that sends key presses to
the radio over a single-wire NEC-like protocol.
"""
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

    def __init__(self):
        self._tx = NECTransmitter(0x82, 0x17, lambda: None)

        # SWC output is active-low (idle/space=HIGH, mark=LOW).
        # NECTransmitter is the opposite so its output is inverted
        self.swc_out = self._tx.data_out.inverted()

    def send(self, key_code):
        if self._tx.busy:
            raise MFSWBusyError()
        self._tx.send(key_code)

    def tick_1mhz(self, ticks=1):
        self._tx.tick_1mhz(ticks)

    @property
    def busy(self):
        return self._tx.busy


class MFSWBusyError(Exception):
    """ Attempt to send another MFSW byte while a MFSW packet is still
    being clocked out.  Callers should check the busy status before
    calling send() with another keycode. """
    pass
