"""Runs the real main.py against fake Pico hardware through a simulated fire.

No Pico needed: machine.Pin/SPI/WDT and MicroPython's time.ticks_* are faked,
and the fake SPI bus answers like a MAX6675 at whatever temperature the
scenario says it is.
"""
import contextlib
import io
import os
import runpy
import sys
import time as real_time
import types
import unittest

HERE = os.path.dirname(__file__)
PROJECT = os.path.join(HERE, "..")
sys.path.insert(0, PROJECT)


class StopSim(Exception):
    pass


class Sim:
    def __init__(self, scenario, duration_s, button_presses=()):
        self.ms = 0
        self.scenario = scenario          # fn(seconds) -> deg F, or None for "probe unplugged"
        self.duration_ms = duration_s * 1000
        self.button_presses = [p * 1000 for p in button_presses]
        self.pins = {}
        self.fan_history = []             # (seconds, pin value) every time the fan pin is written
        self.wdt_fed = 0

    # --- fake time module ---
    def ticks_ms(self):
        return self.ms

    def ticks_diff(self, a, b):
        return a - b

    def sleep_ms(self, n):
        self.ms += n
        if self.ms >= self.duration_ms:
            raise StopSim()

    def time_module(self):
        sim = self
        mod = types.ModuleType("time")
        mod.ticks_ms = sim.ticks_ms
        mod.ticks_diff = sim.ticks_diff
        mod.sleep_ms = sim.sleep_ms
        mod.sleep = lambda s: sim.sleep_ms(int(s * 1000))
        return mod

    # --- fake machine module ---
    def machine_module(self):
        sim = self

        class Pin:
            OUT, IN, PULL_UP = 1, 0, 2

            def __init__(self, pin_id, mode=None, pull=None, value=None):
                self.id = pin_id
                self._v = 1 if pull == Pin.PULL_UP else (value or 0)
                sim.pins[pin_id] = self

            def value(self, v=None):
                if v is None:
                    if self.id == 14:   # the button: held down for 200 ms per press
                        held = any(p <= sim.ms < p + 200 for p in sim.button_presses)
                        return 0 if held else 1
                    return self._v
                self._v = v
                if self.id == 15:
                    sim.fan_history.append((sim.ms / 1000, v))

            def toggle(self):
                self._v ^= 1

        class SPI:
            def __init__(self, *a, **kw):
                pass

            def readinto(self, buf):
                f = sim.scenario(sim.ms / 1000)
                if f is None:
                    raw = 0x0004                     # MAX6675 "thermocouple open"
                else:
                    raw = int(round((f - 32) * 5 / 9 / 0.25)) << 3
                buf[0], buf[1] = raw >> 8, raw & 0xFF

        class WDT:
            def __init__(self, timeout):
                assert timeout <= 8388, "RP2040 watchdog max is ~8.3 s"

            def feed(self):
                sim.wdt_fed += 1

        mod = types.ModuleType("machine")
        mod.Pin, mod.SPI, mod.WDT = Pin, SPI, WDT
        return mod

    def run(self):
        saved = {k: sys.modules.get(k) for k in ("time", "machine")}
        sys.modules["time"] = self.time_module()
        sys.modules["machine"] = self.machine_module()
        for name in ("config", "fan_control", "thermocouple"):
            sys.modules.pop(name, None)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                runpy.run_path(os.path.join(PROJECT, "main.py"), run_name="__main__")
        except StopSim:
            pass
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.log = out.getvalue()
        return self

    def fan_on_at(self, t_s):
        """Blower state at time t (config default: pin LOW = blower ON)."""
        state = None
        for when, v in self.fan_history:
            if when <= t_s:
                state = v
        return state == 0


def fire(t):
    """Room temp, light a fire at 60 s, heats to 300 F, fire out at 1200 s, cools back down."""
    if t < 60:
        return 70.0
    if t < 1200:
        return min(300.0, 70 + (t - 60) * 0.5)
    return max(70.0, 300 - (t - 1200) * 0.25)


class TestMainSimulation(unittest.TestCase):
    def test_full_fire_cycle(self):
        sim = Sim(fire, duration_s=2400).run()
        self.assertTrue(sim.fan_on_at(1), "blower should run during startup")
        self.assertFalse(sim.fan_on_at(30), "cold fireplace: blower off")
        # Expected switch times follow config.py: the fire heats 0.5 F/s from
        # 70 F starting at 60 s, and cools 0.25 F/s from 300 F starting at 1200 s.
        import config
        t_on = 60 + (config.FAN_ON_F - 70) / 0.5
        t_off = 1200 + (300 - config.FAN_OFF_F) / 0.25
        self.assertFalse(sim.fan_on_at(t_on - 5))
        self.assertTrue(sim.fan_on_at(t_on + 2))
        self.assertTrue(sim.fan_on_at(1500))
        self.assertTrue(sim.fan_on_at(t_off - 5))
        self.assertFalse(sim.fan_on_at(t_off + 5))
        self.assertGreater(sim.wdt_fed, 1000)
        self.assertIn("blower ON", sim.log)

    def test_unplugged_probe_forces_blower_on(self):
        def scenario(t):
            return 70.0 if t < 100 else None
        sim = Sim(scenario, duration_s=200).run()
        self.assertFalse(sim.fan_on_at(99))
        self.assertTrue(sim.fan_on_at(104))
        self.assertIn("SENSOR FAULT", sim.log)

    def test_button_toggles_always_on(self):
        sim = Sim(lambda t: 70.0, duration_s=400, button_presses=(50, 300)).run()
        self.assertFalse(sim.fan_on_at(40))
        self.assertTrue(sim.fan_on_at(52))
        self.assertTrue(sim.fan_on_at(299))
        # back to auto at 300 s; blower has run 250 s > 120 s minimum, so it stops
        self.assertFalse(sim.fan_on_at(303))
        self.assertEqual(sim.log.count("Button:"), 2, "each press should register exactly once")


if __name__ == "__main__":
    unittest.main()
