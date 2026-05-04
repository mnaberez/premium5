import time


class Governor:
    """Emulator system clock speed governor"""

    def __init__(self, system_clock_hz):
        self._system_clock_hz = system_clock_hz
        self.reset()

    def reset(self):
        self._epoch_timer = _CycleTimer()
        self._batch_timer = _CycleTimer()

    @property
    def real_mhz(self):
        """Actual speed the emulator is running at, computed over the
        entire time it has been running since last reset()."""
        return self._epoch_timer.mhz

    @property
    def potential_mhz(self):
        """Potential maximum speed of the emulator, computed by timing the
        execution of the last batch of instructions before throttling."""
        return self._batch_timer.snapshot_mhz

    def advance(self, cycles):
        """Inform the throttler that the emulator has executed X cycles"""
        self._epoch_timer.advance(cycles)
        self._batch_timer.advance(cycles)

    def batch(self):
        """Inform the throttler that the emulator has started running
        a new batch of instructions."""
        self._batch_timer.snapshot()
        self._batch_timer.start()

    def throttle(self):
        """If the emulator is running too fast, sleep() before the next
        batch of instructions are run in order to make the execution
        time as close to the target frequency as possible."""
        self._batch_timer.stop()
        time.sleep(self._delay_seconds())

    def _delay_seconds(self):
        """How long to sleep to keep the emulator at the target speed.
        Returns seconds based on how far ahead or behind we are."""
        target_hz = self._system_clock_hz
        target_wall = self._epoch_timer.total_cycles / target_hz
        actual_wall = time.monotonic() - self._epoch_timer._time
        return max(0, target_wall - actual_wall)


class ReferenceTick:
    """Parts of the system without access to the MCU's system clock
    sometimes need a timing reference.  This reference does not need
    to be the CPU clock frequency but must be synchronized to the
    CPU clock, e.g. to allow single-step to work.  For these use
    cases, a 1 MHz reference clock is provided."""

    FREQUENCY_HZ = 1_000_000  # always 1 MHz

    def __init__(self, system_clock_hz):
        if system_clock_hz < self.FREQUENCY_HZ:
            raise ValueError("System clock %r Hz < 1 MHz" % system_clock_hz)

        self._system_clock_hz = system_clock_hz
        self._remainder = 0
        self._listeners = []

    def add_listener(self, listener):
        """Register an object to receive reference clock ticks.
        The object must have a tick_1mhz(ticks) method."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def advance(self, inst_cycles):
        """Inform the reference clock that the CPU has advanced
        inst_cycles at the system clock frequency.  Listeners of
        the reference clock will be ticked if it is time."""

        # Accumulate fractional reference ticks as a remainder.  When
        # enough system cycles have accumulated to produce a whole number
        # of reference ticks, listeners are notified with the count and
        # the leftover is kept for the next call.
        self._remainder += inst_cycles * self.FREQUENCY_HZ
        ticks = self._remainder // self._system_clock_hz
        self._remainder %= self._system_clock_hz
        if ticks > 0:
            for listener in self._listeners:
                listener.tick_1mhz(ticks)


class _CycleTimer:
    """Measures CPU cycles elapsed over wall-clock time.

    Tracks cycle count and monotonic wall-clock time.  Starts running
    on instantiation, can be stopped to freeze the clock."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Start a new measurement from zero, clearing all samples."""
        self._stop_sample = _CycleTimerSample()
        self._snapshot_sample = _CycleTimerSample()
        self.start()

    def start(self):
        """Restart the timer without clearing saved samples."""
        self._time = time.monotonic()
        self.total_cycles = 0
        self._stopped = False

    def advance(self, cycles):
        """Add cycles to the count."""
        if not self._stopped:
            self.total_cycles += cycles

    def stop(self):
        """Freeze the measurement at the current time and cycle count."""
        self._stop_sample = self._take_sample()
        self._stopped = True

    def snapshot(self):
        """Save the current interval and start a new one.
        If stopped, the snapshot uses the frozen values and
        the timer remains stopped."""
        if self._stopped:
            self._snapshot_sample = self._stop_sample
        else:
            self._snapshot_sample = self._take_sample()
            self._time = time.monotonic()
            self.total_cycles = 0

    def _take_sample(self):
        return _CycleTimerSample(self.total_cycles, time.monotonic() - self._time)

    @property
    def mhz(self):
        """Cycles per second, in megahertz."""
        if self._stopped:
            return self._stop_sample.mhz
        return self._take_sample().mhz

    @property
    def snapshot_mhz(self):
        """MHz from the last snapshot interval."""
        return self._snapshot_sample.mhz


class _CycleTimerSample:
    """A frozen measurement of cycles and elapsed time."""
    def __init__(self, cycles=0, elapsed=0.0):
        self.cycles = cycles
        self.elapsed = elapsed

    @property
    def mhz(self):
        if self.elapsed > 0:
            return self.cycles / self.elapsed / 1_000_000
        return 0.0
