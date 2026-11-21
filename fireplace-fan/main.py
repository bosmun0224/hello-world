# main.py -- fireplace blower controller for the Raspberry Pi Pico (MicroPython).
#
# The Pico runs this automatically at power-up. Settings live in config.py.

import time
from machine import Pin, SPI, WDT

import config
from fan_control import FanController, FORCED_ON
from thermocouple import MAX6675, MAX31855

SENSOR_READ_MS = 1000   # MAX6675 needs ~220 ms per conversion; once a second is plenty
LOOP_MS = 50
BUTTON_POLLS = 2        # button must read "pressed" this many polls in a row (debounce)


def c_to_f(c):
    return c * 9 / 5 + 32


def make_led():
    try:
        return Pin("LED", Pin.OUT)      # Pico, Pico W, Pico 2
    except Exception:
        return Pin(25, Pin.OUT)         # older firmware on a plain Pico


def make_sensor():
    spi = SPI(config.SPI_ID, baudrate=1000000, polarity=0, phase=0,
              sck=Pin(config.PIN_SCK), mosi=Pin(config.PIN_MOSI),
              miso=Pin(config.PIN_MISO))
    cs = Pin(config.PIN_CS, Pin.OUT, value=1)
    if config.SENSOR == "MAX6675":
        return MAX6675(spi, cs)
    if config.SENSOR == "MAX31855":
        return MAX31855(spi, cs)
    raise ValueError("config.SENSOR must be 'MAX6675' or 'MAX31855'")


def read_temp_f(sensor):
    try:
        c = sensor.read_c()
    except Exception:
        return None
    return None if c is None else c_to_f(c)


def led_level(ctrl, ms):
    if ctrl.fault:
        return (ms // 100) % 2          # fast flicker: sensor problem, blower forced on
    if ctrl.mode == FORCED_ON:
        return (ms // 500) % 2          # slow blink: button set blower to always on
    if ctrl.fan_on:
        return 1                        # solid: blower running
    return 1 if ms % 3000 < 100 else 0  # short blip every 3 s: idle, all good


def log(uptime_ms, ctrl):
    temp = "  ---  " if ctrl.temp_f is None else "%5.1f F" % ctrl.temp_f
    line = "[%7d s] %s  blower %-3s (%s)" % (
        uptime_ms // 1000, temp, "ON" if ctrl.fan_on else "OFF", ctrl.mode)
    if ctrl.fault:
        line += "  SENSOR FAULT - check the probe wiring; blower forced ON"
    print(line)


def run():
    fan_pin = Pin(config.PIN_FAN, Pin.OUT)

    def set_fan(on):
        fan_pin.value(1 if bool(on) == config.FAN_ON_WHEN_PIN_HIGH else 0)

    # Blower on while starting up. You'll hear it bump on for a few seconds
    # at power-up -- that's the self-test.
    set_fan(True)

    led = make_led()
    button = None
    if config.PIN_BUTTON is not None:
        button = Pin(config.PIN_BUTTON, Pin.IN, Pin.PULL_UP)

    ctrl = FanController(config.FAN_ON_F, config.FAN_OFF_F,
                         config.MIN_ON_SECONDS, config.VALID_MIN_F,
                         config.VALID_MAX_F, config.FAULT_READINGS)
    sensor = make_sensor()

    print("Fireplace blower controller: on at %d F, off at %d F, sensor %s."
          % (config.FAN_ON_F, config.FAN_OFF_F, config.SENSOR))
    if config.WATCHDOG:
        print("Press Stop / Ctrl-C in the next %d s if you want to edit files."
              % config.STARTUP_GRACE_SECONDS)
    for _ in range(config.STARTUP_GRACE_SECONDS * 10):
        led.toggle()
        time.sleep_ms(100)

    wdt = WDT(timeout=8000) if config.WATCHDOG else None

    uptime = 0
    last_tick = time.ticks_ms()
    next_read = 0
    next_log = 0
    pressed_polls = 0
    last_fan = None
    last_fault = None

    while True:
        now = time.ticks_ms()
        uptime += time.ticks_diff(now, last_tick)
        last_tick = now

        if button is not None:
            if button.value() == 0:
                pressed_polls += 1
                if pressed_polls == BUTTON_POLLS:
                    print("Button: blower mode is now %s" % ctrl.toggle_mode())
                    next_read = uptime          # act on it right away
            else:
                pressed_polls = 0

        if uptime >= next_read:
            next_read = uptime + SENSOR_READ_MS
            fan = ctrl.update(read_temp_f(sensor), uptime // 1000)
            set_fan(fan)
            if fan != last_fan or ctrl.fault != last_fault or uptime >= next_log:
                log(uptime, ctrl)
                next_log = uptime + config.LOG_EVERY_SECONDS * 1000
            last_fan = fan
            last_fault = ctrl.fault

        led.value(led_level(ctrl, uptime))
        if wdt is not None:
            wdt.feed()
        time.sleep_ms(LOOP_MS)


run()
