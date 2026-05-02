import unittest
from premium5.devices import Port0Device, Port9Device


class Port0DeviceTests(unittest.TestCase):

    def test_name(self):
        p0 = Port0Device()
        self.assertEqual(p0.name, "p0")

    def test_has_edge_detection(self):
        p0 = Port0Device()
        self.assertTrue(hasattr(p0, '_egp'))
        self.assertTrue(hasattr(p0, '_egn'))

    def test_has_pullups(self):
        p0 = Port0Device()
        self.assertTrue(hasattr(p0, '_pullup'))

    def test_size_includes_egp_egn(self):
        p0 = Port0Device()
        self.assertEqual(p0.size, 5)


class Port9DeviceTests(unittest.TestCase):

    def test_name(self):
        p9 = Port9Device()
        self.assertEqual(p9.name, "p9")

    def test_pins_default_low_no_pullups(self):
        p9 = Port9Device()
        for i in range(8):
            self.assertFalse(p9.pins[i].high)
