"""Unit tests for prediction.kalman: constant-velocity filter convergence."""

from __future__ import annotations

import numpy as np
import pytest

from smart_zone.prediction.kalman import WorkerKalmanBank, WorkerKalmanFilter

DT_S = 1.0 / 20.0  # matches 20Hz telemetry cadence used elsewhere


def _generate_noisy_constant_velocity_track(
    start: tuple[float, float],
    velocity: tuple[float, float],
    n_steps: int,
    noise_std: float,
    seed: int = 42,
) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    x0, y0 = start
    vx, vy = velocity
    positions = []
    for step in range(n_steps):
        t = step * DT_S
        true_x = x0 + vx * t
        true_y = y0 + vy * t
        noisy_x = true_x + rng.normal(0, noise_std)
        noisy_y = true_y + rng.normal(0, noise_std)
        positions.append((noisy_x, noisy_y))
    return positions


class TestWorkerKalmanFilterConvergence:
    def test_converges_to_known_constant_velocity(self):
        true_velocity = (1.5, -0.8)  # m/s
        track = _generate_noisy_constant_velocity_track(
            start=(0.0, 0.0), velocity=true_velocity, n_steps=200, noise_std=0.1,
        )

        kf = WorkerKalmanFilter(initial_position=track[0])
        estimate = None
        for position in track:
            estimate = kf.update(position, dt=DT_S)

        assert estimate is not None
        assert estimate.vx == pytest.approx(true_velocity[0], abs=0.15)
        assert estimate.vy == pytest.approx(true_velocity[1], abs=0.15)

    def test_converges_to_zero_velocity_when_stationary(self):
        track = _generate_noisy_constant_velocity_track(
            start=(3.0, 3.0), velocity=(0.0, 0.0), n_steps=150, noise_std=0.08,
        )

        kf = WorkerKalmanFilter(initial_position=track[0])
        estimate = None
        for position in track:
            estimate = kf.update(position, dt=DT_S)

        assert estimate.vx == pytest.approx(0.0, abs=0.1)
        assert estimate.vy == pytest.approx(0.0, abs=0.1)

    def test_forecast_extrapolates_along_converged_velocity(self):
        true_velocity = (2.0, 0.0)
        track = _generate_noisy_constant_velocity_track(
            start=(0.0, 0.0), velocity=true_velocity, n_steps=200, noise_std=0.05,
        )

        kf = WorkerKalmanFilter(initial_position=track[0], forecast_horizon_s=1.0)
        estimate = None
        for position in track:
            estimate = kf.update(position, dt=DT_S)

        # after converging near (x, 0) moving at ~2 m/s, forecast 1s ahead
        # should land roughly 2m further along x than the filtered position.
        assert (estimate.forecast_x - estimate.x) == pytest.approx(2.0, abs=0.3)
        assert estimate.forecast_y == pytest.approx(estimate.y, abs=0.2)

    def test_raises_on_nonpositive_dt(self):
        kf = WorkerKalmanFilter(initial_position=(0.0, 0.0))
        with pytest.raises(ValueError):
            kf.update((1.0, 1.0), dt=0.0)


class TestWorkerKalmanBank:
    def test_first_observation_seeds_zero_velocity(self):
        bank = WorkerKalmanBank()
        estimate = bank.update(track_id=1, position=(5.0, 5.0), dt=DT_S)
        assert estimate.x == pytest.approx(5.0)
        assert estimate.y == pytest.approx(5.0)
        assert estimate.vx == pytest.approx(0.0)
        assert estimate.vy == pytest.approx(0.0)

    def test_independent_tracks_do_not_interfere(self):
        bank = WorkerKalmanBank()
        track_a = _generate_noisy_constant_velocity_track((0, 0), (1.0, 0.0), 100, 0.05, seed=1)
        track_b = _generate_noisy_constant_velocity_track((10, 10), (-1.0, 0.0), 100, 0.05, seed=2)

        est_a = est_b = None
        for pos_a, pos_b in zip(track_a, track_b):
            est_a = bank.update(track_id=1, position=pos_a, dt=DT_S)
            est_b = bank.update(track_id=2, position=pos_b, dt=DT_S)

        assert est_a.vx == pytest.approx(1.0, abs=0.15)
        assert est_b.vx == pytest.approx(-1.0, abs=0.15)

    def test_dropping_and_recreating_track_id_starts_cold(self):
        # Simulates an ID switch: dropping id=1 and creating a "new" id=1
        # later must behave identically to any fresh track -- no memory leak
        # of stale velocity, and nothing here treats ID continuity as meaningful.
        bank = WorkerKalmanBank()
        bank.update(track_id=1, position=(0.0, 0.0), dt=DT_S)
        for _ in range(50):
            bank.update(track_id=1, position=(1.0, 1.0), dt=DT_S)

        bank.drop(track_id=1)
        assert 1 not in bank.active_track_ids()

        fresh_estimate = bank.update(track_id=1, position=(50.0, 50.0), dt=DT_S)
        assert fresh_estimate.x == pytest.approx(50.0)
        assert fresh_estimate.vx == pytest.approx(0.0)
