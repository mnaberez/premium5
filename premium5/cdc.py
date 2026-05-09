from premium5.digital import LogicInput, LogicOutput


class CDC:
    """Stub for the CD changer"""

    def __init__(self):
        # electrical interface
        self.cmd_in = LogicInput()
        self.clk_out = LogicOutput()
        self.dat_out = LogicOutput()

    def tick_1mhz(self, ticks):
        pass
