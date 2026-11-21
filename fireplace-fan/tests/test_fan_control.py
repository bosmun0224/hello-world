import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fan_control import FanController, AUTO, FORCED_ON  # noqa: E402
from thermocouple import decode_max6675, decode_max31855  # noqa: E402


def make(**kw):
    args = dict(on_f=120, off_f=90, min_on_s=120, valid_min_f=10,
                valid_max_f=900, fault_readings=3)
    args.update(kw)
    return FanController(**args)


class TestFanController(unittest.TestCase):
    def test_rejects_backwards_thresholds(self):
        with self.assertRaises(ValueError):
            make(on_f=90, off_f=120)

    def test_cold_boot_turns_blower_off(self):
        c = make()
        self.assertTrue(c.fan_on)              # on until the first reading
        self.assertFalse(c.update(70, 0))

    def test_warm_boot_runs_blower(self):
        # Rebooted mid-fire, inside the band: can't tell heating from cooling, so run.
        self.assertTrue(make().update(105, 0))

    def test_hysteresis(self):
        c = make()
        c.update(70, 0)
        self.assertFalse(c.update(119, 10))
        self.assertTrue(c.update(120, 20))
        self.assertTrue(c.update(95, 500))     # inside band: stays on
        self.assertFalse(c.update(90, 510))
        self.assertFalse(c.update(110, 520))   # inside band: stays off

    def test_minimum_run_time(self):
        c = make(min_on_s=120)
        c.update(70, 0)
        c.update(125, 100)
        self.assertTrue(c.update(80, 150))     # only ran 50 s
        self.assertTrue(c.update(80, 219))
        self.assertFalse(c.update(80, 220))

    def test_single_glitch_holds_state(self):
        c = make()
        c.update(70, 0)
        self.assertFalse(c.update(None, 1))
        self.assertFalse(c.update(None, 2))
        self.assertFalse(c.fault)
        c.update(130, 3)
        self.assertTrue(c.update(None, 4))
        self.assertTrue(c.update(5000, 5))     # absurd value counts as bad

    def test_sensor_fault_forces_on_then_recovers(self):
        c = make()
        c.update(70, 0)
        c.update(None, 1)
        c.update(None, 2)
        self.assertTrue(c.update(None, 3))
        self.assertTrue(c.fault)
        # Probe fixed: fault clears; it ran because of the fault, so the
        # minimum run time applies before it shuts off.
        self.assertTrue(c.update(70, 4))
        self.assertFalse(c.fault)
        self.assertFalse(c.update(70, 3 + 120))

    def test_out_of_range_readings_count_as_faults(self):
        c = make()
        c.update(70, 0)
        for t in (1, 2, 3):
            c.update(-40, t)
        self.assertTrue(c.fault)
        self.assertTrue(c.fan_on)

    def test_forced_on_mode(self):
        c = make()
        c.update(70, 0)
        self.assertEqual(c.toggle_mode(), FORCED_ON)
        self.assertTrue(c.update(70, 1))
        self.assertEqual(c.toggle_mode(), AUTO)
        self.assertTrue(c.update(70, 2))       # minimum run time still applies
        self.assertFalse(c.update(70, 1 + 120))


class TestDecoders(unittest.TestCase):
    def test_max6675(self):
        self.assertEqual(decode_max6675((400 << 3)), 100.0)  # 400 counts x 0.25 C
        self.assertEqual(decode_max6675((1 << 3)), 0.25)
        self.assertIsNone(decode_max6675((400 << 3) | 0x4))  # probe open
        self.assertIsNone(decode_max6675(0xFFFF))            # floating bus
        self.assertIsNone(decode_max6675(0x0000))            # board missing

    def test_max31855(self):
        self.assertEqual(decode_max31855(400 << 18), 100.0)
        neg = ((-40 & 0x3FFF) << 18)                         # -10 C
        self.assertEqual(decode_max31855(neg), -10.0)
        self.assertIsNone(decode_max31855((400 << 18) | 0x10001))  # open circuit
        self.assertIsNone(decode_max31855((400 << 18) | 0x10002))  # short to GND
        self.assertIsNone(decode_max31855(0xFFFFFFFF))
        self.assertIsNone(decode_max31855(0))


if __name__ == "__main__":
    unittest.main()
