import unittest
from premium5.mfsw import MFSW
from premium5.nec import NECReceiver


class MFSWTests(unittest.TestCase):

    def setUp(self):
        self.commands = []
        self.repeats = []
        self.tx = MFSW()
        self.rx = NECReceiver(0x82, 0x17, self.commands.append,
                              lambda: self.repeats.append(True))
        self.tx.swc_out.inverted().drives(self.rx.data_in)

    def _tick(self, ticks):
        for _ in range(ticks):
            self.tx.tick_1mhz(1)
            self.rx.tick_1mhz(1)

    # ctor

    def test_wire_is_initially_high_for_idle_state(self):
        self.assertTrue(self.tx.swc_out.high)

    # sending each key

    def test_sends_vol_up(self):
        self.tx.key_down(MFSW.VOL_UP)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x01])
        self.assertTrue(self.tx.swc_out.high) # idle

    def test_sends_vol_down(self):
        self.tx.key_down(MFSW.VOL_DOWN)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x00])
        self.assertTrue(self.tx.swc_out.high) # idle

    def test_sends_up(self):
        self.tx.key_down(MFSW.UP)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x0A])
        self.assertTrue(self.tx.swc_out.high) # idle

    def test_sends_down(self):
        self.tx.key_down(MFSW.DOWN)
        self._tick(1_000_000)
        self.assertEqual(self.commands, [0x0B])
        self.assertTrue(self.tx.swc_out.high) # idle

    # consecutive, non-repeating keys

    def test_back_to_back_keys(self):
        self.tx.key_down(MFSW.UP)
        self._tick(MFSW.REPEAT_TICKS - 1)
        self.tx.key_up()

        self.tx.key_down(MFSW.DOWN)
        self._tick(MFSW.REPEAT_TICKS - 1)
        self.tx.key_up()

        self.assertEqual(self.commands, [0x0A, 0x0B])
        self.assertEqual(len(self.repeats), 0)

    # key repeat

    def test_repeat_lifecycle(self):
        # key down sends command frame
        self.tx.key_down(MFSW.UP)
        self._tick(MFSW.REPEAT_TICKS)
        self.assertEqual(self.commands, [0x0A])
        self.assertEqual(len(self.repeats), 0)

        # first repeat
        self._tick(MFSW.REPEAT_TICKS)
        self.assertEqual(len(self.repeats), 1)

        # second repeat
        self._tick(MFSW.REPEAT_TICKS)
        self.assertEqual(len(self.repeats), 2)

        # key up stops repeating
        self.tx.key_up()
        self._tick(MFSW.REPEAT_TICKS * 10)
        self.assertEqual(len(self.repeats), 2)
