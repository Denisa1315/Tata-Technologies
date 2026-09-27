"""Constant-velocity Kalman filter for ground-plane worker position tracking.

Deliberate architectural decision (per project spec, not a placeholder to
upgrade): trajectory prediction here is a hand-tunable constant-velocity
Kalman filter, not any trained/deep model. State = [x, y, vx, vy] with a
linear constant-velocity transition; this is the right amount of model for
sparse, noisy ground-plane position observations at video frame rate, and
keeps the whole prediction path auditable and deterministic -- no
LSTM/Transformer/trained model is used or imported anywhere in this module.

One filter instance per tracked worker, keyed by track ID from perception.
The key itself is just a lookup convenience for this dict of independent
filters -- the risk engine (Section 4) must evaluate by ground-plane
position, not by track ID, so an ID switch there must never change system
state. If a track ID is dropped and a new one appears at the same physical
location, that's simply a new KalmanWorkerTracker starting cold; nothing
here assumes ID continuity carries meaning beyond "which filter to update."
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from filterpy.kalman import KalmanFilter

# Process noise: how much we trust the constant-velocity assumption itself
# (higher = filter adapts faster to real velocity changes, but is noisier).
DEFAULT_PROCESS_NOISE_STD = 0.5
# Measurement noise: how much we trust each raw homography-projected position.
DEFAULT_MEASUREMENT_NOISE_STD = 0.15
DEFAULT_FORECAST_HORIZON_S = 1.5


@dataclass(frozen=True)
class KalmanEstimate:
    x: float
    y: float
    vx: float
    vy: float
    forecast_x: float
    forecast_y: float
    forecast_horizon_s: float


class WorkerKalmanFilter:
    """One constant-velocity Kalman filter for a single tracked worker."""

    def __init__(
        self,
        initial_position: tuple[float, float],
        process_noise_std: float = DEFAULT_PROCESS_NOISE_STD,
        measurement_noise_std: float = DEFAULT_MEASUREMENT_NOISE_STD,
        forecast_horizon_s: float = DEFAULT_FORECAST_HORIZON_S,
    ) -> None:
        self.forecast_horizon_s = forecast_horizon_s

        kf = KalmanFilter(dim_x=4, dim_z=2)
        x0, y0 = initial_position
        kf.x = np.array([x0, y0, 0.0, 0.0])  # start with zero velocity guess

        # H: we only observe position, not velocity.
        kf.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])

        # Initial state uncertainty: position known-ish, velocity unknown.
        kf.P = np.diag([measurement_noise_std**2, measurement_noise_std**2, 4.0, 4.0])

        kf.R = np.eye(2) * measurement_noise_std**2
        self._process_noise_std = process_noise_std

        self._kf = kf
        self._last_dt: float | None = None

    def _set_transition_for_dt(self, dt: float) -> None:
        # F: constant-velocity model, x' = x + vx*dt, vx' = vx.
        self._kf.F = np.array([
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])

        q = self._process_noise_std**2
        dt2, dt3, dt4 = dt**2, dt**3, dt**4
        # Discrete white-noise-acceleration process noise for a CV model.
        self._kf.Q = q * np.array([
            [dt4 / 4, 0.0, dt3 / 2, 0.0],
            [0.0, dt4 / 4, 0.0, dt3 / 2],
            [dt3 / 2, 0.0, dt2, 0.0],
            [0.0, dt3 / 2, 0.0, dt2],
        ])
        self._last_dt = dt

    def update(self, position: tuple[float, float], dt: float) -> KalmanEstimate:
        """Feed one new ground-plane position observation, dt seconds after
        the previous update, and return the filtered position/velocity plus
        a short-horizon forecast position."""
        if dt <= 0:
            raise ValueError("dt must be > 0")

        if dt != self._last_dt:
            self._set_transition_for_dt(dt)

        self._kf.predict()
        self._kf.update(np.array(position))

        x, y, vx, vy = self._kf.x
        forecast_x = x + vx * self.forecast_horizon_s
        forecast_y = y + vy * self.forecast_horizon_s

        return KalmanEstimate(
            x=float(x), y=float(y), vx=float(vx), vy=float(vy),
            forecast_x=float(forecast_x), forecast_y=float(forecast_y),
            forecast_horizon_s=self.forecast_horizon_s,
        )

    @property
    def position(self) -> tuple[float, float]:
        return float(self._kf.x[0]), float(self._kf.x[1])

    @property
    def velocity(self) -> tuple[float, float]:
        return float(self._kf.x[2]), float(self._kf.x[3])


class WorkerKalmanBank:
    """Manages one WorkerKalmanFilter per tracked worker, keyed by track ID.

    Purely a bookkeeping convenience for routing updates to the right filter
    instance -- see module docstring re: track-ID independence of the risk
    engine downstream.
    """

    def __init__(
        self,
        process_noise_std: float = DEFAULT_PROCESS_NOISE_STD,
        measurement_noise_std: float = DEFAULT_MEASUREMENT_NOISE_STD,
        forecast_horizon_s: float = DEFAULT_FORECAST_HORIZON_S,
    ) -> None:
        self._process_noise_std = process_noise_std
        self._measurement_noise_std = measurement_noise_std
        self._forecast_horizon_s = forecast_horizon_s
        self._filters: dict[int, WorkerKalmanFilter] = {}

    def update(self, track_id: int, position: tuple[float, float], dt: float) -> KalmanEstimate:
        if track_id not in self._filters:
            self._filters[track_id] = WorkerKalmanFilter(
                initial_position=position,
                process_noise_std=self._process_noise_std,
                measurement_noise_std=self._measurement_noise_std,
                forecast_horizon_s=self._forecast_horizon_s,
            )
            # First observation: seed state directly, don't run a predict/update
            # cycle against a zero-velocity prior for dt (would bias forecast).
            kf = self._filters[track_id]
            return KalmanEstimate(
                x=position[0], y=position[1], vx=0.0, vy=0.0,
                forecast_x=position[0], forecast_y=position[1],
                forecast_horizon_s=kf.forecast_horizon_s,
            )

        return self._filters[track_id].update(position, dt)

    def drop(self, track_id: int) -> None:
        self._filters.pop(track_id, None)

    def active_track_ids(self) -> set[int]:
        return set(self._filters.keys())
