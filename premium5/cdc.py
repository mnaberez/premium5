from premium5.digital import LogicInput, LogicOutput
from premium5.nec import NECReceiver


class CDC:
    """Stub for the CD changer"""

    def __init__(self):
        self._rx = NECReceiver(0xCA, 0x34, self._on_command, lambda: None)

        # electrical interface
        self.cmd_in = self._rx.data_in
        self.clk_out = LogicOutput()
        self.dat_out = LogicOutput()

    def tick_1mhz(self, ticks):
        self._rx.tick_1mhz(ticks)

    def _on_command(self, cmd):
        import sys # XXX temporary hack
        sys.stderr.write("Radio->CDC: 0x%02X\n" % cmd)
