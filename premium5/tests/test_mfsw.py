import unittest
from premium5.mfsw import MFSW, MFSWBusyError
from premium5.nec import NECReceiver, TIMEOUT_TICKS


class MFSWTests(unittest.TestCase):

    def setUp(self):
        self.commands = []
        self.tx = MFSW()
        self.rx = NECReceiver(0x82, 0x17, self.commands.append)
        self.tx.swc_out.inverted().drives(self.rx.data_in)

    def test_wire_idles_high(self):
        self.assertTrue(self.tx.swc_out.high)

    def test_send_while_busy_raises(self):
        self.tx.send(MFSW.UP)
        with self.assertRaises(MFSWBusyError):
            self.tx.send(MFSW.DOWN)

    def test_wire_goes_low_on_send(self):
        self.tx.send(MFSW.UP)
        self.tx.tick_1mhz()
        self.assertTrue(self.tx.swc_out.low)

    def test_sends_vol_up(self):
        self._send_and_receive(MFSW.VOL_UP)
        self.assertEqual(self.commands, [0x01])

    def test_sends_vol_down(self):
        self._send_and_receive(MFSW.VOL_DOWN)
        self.assertEqual(self.commands, [0x00])

    def test_sends_up(self):
        self._send_and_receive(MFSW.UP)
        self.assertEqual(self.commands, [0x0A])

    def test_sends_down(self):
        self._send_and_receive(MFSW.DOWN)
        self.assertEqual(self.commands, [0x0B])

    def _send_and_receive(self, key_code):
        self.tx.send(key_code)
        for _ in range(1_000_000):
            self.tx.tick_1mhz()
            self.rx.tick_1mhz(1)
        self.rx.tick_1mhz(TIMEOUT_TICKS + 1)
