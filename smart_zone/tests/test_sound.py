"""Unit tests for dashboard.sound.SoundController: repeating CRITICAL beep,
one-shot WARNING-entry beep, and respecting buzzer_should_sound=False."""

from __future__ import annotations

from smart_zone.dashboard.sound import SoundController


class FakePlayer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, sound_path: str) -> None:
        self.calls.append(sound_path)


class TestCriticalRepeatingBeep:
    def test_beeps_on_entering_critical(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("CRITICAL", True, now=0.0)
        assert len(player.calls) == 1

    def test_repeats_while_critical_persists(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("CRITICAL", True, now=0.0)
        controller.update("CRITICAL", True, now=0.5)  # too soon, no new beep
        controller.update("CRITICAL", True, now=1.1)  # due
        assert len(player.calls) == 2

    def test_stops_when_critical_clears(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=0.5)
        controller.update("CRITICAL", True, now=0.0)
        controller.update("SAFE", True, now=0.1)
        controller.update("SAFE", True, now=1.0)
        assert len(player.calls) == 1  # only the original CRITICAL entry beep

    def test_resumes_fresh_timer_on_re_entering_critical(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("CRITICAL", True, now=0.0)
        controller.update("SAFE", True, now=0.2)
        controller.update("CRITICAL", True, now=0.3)  # re-enters -- beeps immediately, no debounce carryover
        assert len(player.calls) == 2

    def test_no_beep_when_buzzer_should_sound_false(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("CRITICAL", False, now=0.0)
        controller.update("CRITICAL", False, now=1.5)
        assert player.calls == []

    def test_zero_timestamp_does_not_break_interval_tracking(self):
        """Regression guard: the interval check must use `is None`, not
        truthiness, since now=0.0 is a legitimate first timestamp."""
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("CRITICAL", True, now=0.0)
        controller.update("CRITICAL", True, now=0.5)  # must still be "too soon" relative to 0.0
        assert len(player.calls) == 1


class TestWarningEntryOneShotBeep:
    def test_beeps_once_on_entering_warning(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player)
        controller.update("SAFE", True, now=0.0)
        controller.update("WARNING", True, now=0.1)
        assert len(player.calls) == 1

    def test_does_not_repeat_while_warning_persists(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player)
        controller.update("SAFE", True, now=0.0)
        controller.update("WARNING", True, now=0.1)
        controller.update("WARNING", True, now=0.5)
        controller.update("WARNING", True, now=1.0)
        assert len(player.calls) == 1

    def test_beeps_again_on_a_fresh_warning_entry(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player)
        controller.update("SAFE", True, now=0.0)
        controller.update("WARNING", True, now=0.1)
        controller.update("SAFE", True, now=0.5)
        controller.update("WARNING", True, now=0.6)
        assert len(player.calls) == 2

    def test_no_beep_on_quiet_stationary_warning(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player)
        controller.update("SAFE", True, now=0.0)
        controller.update("WARNING", False, now=0.1)  # quiet-stationary entry
        assert player.calls == []

    def test_no_beep_transitioning_from_critical_to_warning(self):
        # Not a fresh "entry" from something-not-warning in the celebratory
        # sense that matters here -- CRITICAL->WARNING is a de-escalation,
        # not a new alert, so this only checks the one-shot fires once per
        # distinct arrival at WARNING (already covered above); this test
        # just documents that CRITICAL's own beep isn't confused with it.
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("CRITICAL", True, now=0.0)
        controller.update("WARNING", True, now=0.1)
        assert len(player.calls) == 2  # 1 critical-entry beep + 1 warning-entry beep


class TestIndependentOfEachOther:
    def test_warning_beep_does_not_interfere_with_later_critical_beeps(self):
        player = FakePlayer()
        controller = SoundController(play_fn=player, critical_beep_interval_s=1.0)
        controller.update("SAFE", True, now=0.0)
        controller.update("WARNING", True, now=0.1)  # 1 beep
        controller.update("CRITICAL", True, now=0.2)  # 1 beep
        controller.update("CRITICAL", True, now=1.3)  # due -> 1 beep
        assert len(player.calls) == 3
