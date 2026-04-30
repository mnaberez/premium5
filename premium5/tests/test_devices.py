import unittest
from premium5.devices import Port0Device, Port9Device


class Port0DeviceTests(unittest.TestCase):

    def test_name(self):
        p0 = Port0Device()
        self.assertEqual(p0.name, "p0")

    def test_has_edge_detection(self):
        p0 = Port0Device()
        self.assertTrue(hasattr(p0, 'set_external_input'))
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

    def test_s_contact_defaults_off(self):
        p9 = Port9Device()
        self.assertEqual(p9.external_inputs & 0x01, 0)

    def test_other_pins_default_high(self):
        p9 = Port9Device()
        self.assertEqual(p9.external_inputs & 0xFE, 0xFE)

    def test_reset_restores_s_contact_off(self):
        p9 = Port9Device()
        p9.external_inputs = 0xFF
        p9.reset()
        self.assertEqual(p9.external_inputs & 0x01, 0)
