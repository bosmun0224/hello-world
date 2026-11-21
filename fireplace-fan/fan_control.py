# fan_control.py -- decides when the blower should run.
#
# Plain Python with no hardware imports, so the same file runs on the Pico
# and in the tests on a PC.

AUTO = "auto"
FORCED_ON = "always on"


class FanController:
    """Thermostat with hysteresis, a minimum run time, and fail-safe behaviour.

    Rules:
      * at or above on_f            -> blower on
      * at or below off_f           -> blower off (once it has run min_on_s)
      * in between                  -> keep doing whatever it was doing
      * fault_readings bad readings -> sensor fault, blower forced on
      * one or two bad readings     -> ignored, blower holds its current state
      * first good reading at boot  -> on if warmer than off_f (we can't tell
                                       whether the fire is heating or cooling)
    """

    def __init__(self, on_f, off_f, min_on_s=120, valid_min_f=10,
                 valid_max_f=900, fault_readings=3):
        if off_f >= on_f:
            raise ValueError("FAN_OFF_F must be lower than FAN_ON_F")
        self.on_f = on_f
        self.off_f = off_f
        self.min_on_s = min_on_s
        self.valid_min_f = valid_min_f
        self.valid_max_f = valid_max_f
        self.fault_readings = fault_readings

        self.mode = AUTO
        self.fan_on = True      # run the blower until the first good reading says otherwise
        self.temp_f = None      # last good reading
        self.fault = False
        self._bad_count = 0
        self._started = False   # True after the first good reading
        self._on_since = None   # when the blower last switched on (None = at boot)

    def toggle_mode(self):
        self.mode = FORCED_ON if self.mode == AUTO else AUTO
        return self.mode

    def update(self, temp_f, now_s):
        """Feed one reading (None if the sensor read failed). Returns True if the blower should run."""
        good = (temp_f is not None
                and self.valid_min_f <= temp_f <= self.valid_max_f)
        if good:
            self._bad_count = 0
            self.fault = False
            self.temp_f = temp_f
        else:
            self._bad_count += 1
            if self._bad_count >= self.fault_readings:
                self.fault = True

        if self.fault or self.mode == FORCED_ON:
            want = True
        elif not good:
            want = self.fan_on                 # brief glitch: hold steady
        elif not self._started:
            want = temp_f > self.off_f
        elif temp_f >= self.on_f:
            want = True
        elif temp_f <= self.off_f:
            want = False
        else:
            want = self.fan_on                 # inside the hysteresis band

        if good:
            self._started = True

        if want and not self.fan_on:
            self.fan_on = True
            self._on_since = now_s
        elif not want and self.fan_on:
            ran_long_enough = (self._on_since is None
                               or now_s - self._on_since >= self.min_on_s)
            if ran_long_enough:
                self.fan_on = False
                self._on_since = None

        return self.fan_on
