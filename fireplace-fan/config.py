# config.py -- settings for the fireplace blower controller.
#
# Edit these, save this file to the Pico, then unplug/replug the Pico
# (or press Ctrl-D in Thonny) for the changes to take effect.

# ---- When the blower runs (degrees Fahrenheit) ----------------------------
# The stock snap-disc fan switch on most fireplaces closes around 120F and
# opens around 90F. These numbers are measured wherever YOU mount the probe,
# so watch a real fire and tune them (see "Tune it" in the README).
FAN_ON_F = 110      # blower turns on at or above this (stock disc is 120; lower here because the flame is weak)
FAN_OFF_F = 90      # blower turns off at or below this (must be lower than FAN_ON_F)

# Once the blower turns on, keep it on at least this long (stops on/off chatter).
MIN_ON_SECONDS = 120

# ---- Temperature sensor -----------------------------------------------------
SENSOR = "MAX6675"  # "MAX6675" or "MAX31855" -- whichever thermocouple board you bought
SPI_ID = 0
PIN_SCK = 18        # board SCK / CLK  -> Pico pin 24
PIN_MISO = 16       # board SO / DO    -> Pico pin 21
PIN_CS = 17         # board CS         -> Pico pin 22
PIN_MOSI = 19       # not connected to anything; the SPI bus just needs a pin assigned

# A reading outside this range means a broken or unplugged probe, not a real temperature.
VALID_MIN_F = 10
VALID_MAX_F = 900
# This many bad readings in a row (one per second) = sensor fault -> blower forced ON.
FAULT_READINGS = 3

# ---- Blower output ----------------------------------------------------------
PIN_FAN = 15        # -> IoT Relay "+" input, Pico pin 20
# Which way the output works:
#   False -> blower plugged into the IoT Relay's "normally ON" outlet (recommended).
#            If the Pico dies or a wire falls off, the blower RUNS instead of staying off.
#   True  -> blower in a "normally OFF" outlet, or a typical relay module / SSR.
FAN_ON_WHEN_PIN_HIGH = False

# ---- Optional push button ---------------------------------------------------
# Momentary button between GP14 (Pico pin 19) and GND. Each press toggles
# AUTO <-> ALWAYS ON. Set to None if you don't wire a button.
PIN_BUTTON = 14

# ---- Housekeeping -----------------------------------------------------------
LOG_EVERY_SECONDS = 10      # print the temperature over USB this often (see it in Thonny)
WATCHDOG = True             # reboot the Pico automatically if the program ever freezes
STARTUP_GRACE_SECONDS = 5   # after power-up, time to press Stop in Thonny before the watchdog arms
