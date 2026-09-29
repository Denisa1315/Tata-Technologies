"""Display-only OpenCV dashboard for the --sim pipeline.

Draws one composed 1280x800 window per pipeline loop from a plain data
snapshot (SimViewState) that the caller (app.py) builds each frame. This
module makes NO decisions: it does not import safety.risk_engine, does not
compute zone geometry, does not run the Kalman filter, and does not decide
what state the system is in -- it only reads values that were already
computed elsewhere and draws them. It also does not decide what a key
press MEANS (e.g. toggling a camera fault, resetting the scenario) -- it
only reports which control keys were pressed this frame via poll_keys();
interpreting and acting on them is app.py's job, consistent with keeping
all decision logic out of this module.

Layout (industrial-HUD style, all readouts backed by real computed values
-- no fabricated terrain, hazards, or worker identities):
  - Top status bar: overall state pill, closest worker distance, swing
    speed, interlock action.
  - Main viewport: top-down metre grid, danger/caution rings colored by
    state, camera FOV rays, machine glyph (gray when stopped), workers as
    dots labeled with their distance to the machine, live webcam inset.
  - Right sidebar: Machine Telemetry / Perception Engine / Safety Risk
    Engine panels, plus a Worker Proximity Register listing every tracked
    worker's machine/camera distance, detection confidence, and zone.
  - Bottom strip: audit log of the last 5 state transitions.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

WINDOW_NAME = "Smart-Zone Edge Guardian - Sim View"
WINDOW_W, WINDOW_H = 1280, 800

STATUS_BAR_H = 46
BANNER_H = 56
BOTTOM_STRIP_H = 90
RIGHT_PANEL_W = 320
INSET_W, INSET_H = 260, 195

MAIN_X0, MAIN_Y0 = 0, STATUS_BAR_H + BANNER_H
MAIN_X1 = WINDOW_W - RIGHT_PANEL_W
MAIN_Y1 = WINDOW_H - BOTTOM_STRIP_H

PLOT_SCALE_PX_PER_M = 30.0
GRID_STEP_M = 1.0

# State/zone-meaning colors are fixed across both themes -- SAFE is always
# green, CRITICAL always red, etc, regardless of light or dark mode, so the
# color vocabulary never changes meaning for the operator.
COLOR_BY_STATE_NAME = {
    "SAFE": (0, 170, 0),       # green
    "WARNING": (0, 140, 230),  # amber
    "CRITICAL": (0, 0, 220),   # red
    "DEGRADED": (120, 120, 120),  # gray
}
ZONE_LEVEL_COLOR = {
    "DANGER": (0, 0, 220),
    "CAUTION": (0, 170, 230),
    "OUTSIDE": (140, 140, 140),
}


@dataclass(frozen=True)
class Theme:
    """A full palette for the plain view. All BGR tuples (OpenCV
    convention). Every non-state-meaning color used by SimView's drawing
    methods lives here, so switching themes never blindly inverts colors --
    each theme is its own deliberately chosen, readable palette."""
    name: str
    window_bg: tuple[int, int, int]
    main_bg: tuple[int, int, int]
    panel_bg: tuple[int, int, int]
    card_bg: tuple[int, int, int]
    status_bar_bg: tuple[int, int, int]
    banner_bg: tuple[int, int, int]
    strip_bg: tuple[int, int, int]
    text: tuple[int, int, int]
    text_dim: tuple[int, int, int]
    grid: tuple[int, int, int]
    axis: tuple[int, int, int]
    header_accent: tuple[int, int, int]  # panel section headers (e.g. "MACHINE TELEMETRY")
    arm_running: tuple[int, int, int]
    arm_stopped: tuple[int, int, int]
    forecast_line: tuple[int, int, int]
    fov_ray: tuple[int, int, int]
    fov_marker: tuple[int, int, int]
    buzzer_off: tuple[int, int, int]
    light_off: tuple[int, int, int]
    pill_bg: tuple[int, int, int]


DARK_THEME = Theme(
    name="dark",
    window_bg=(15, 15, 15),
    main_bg=(18, 18, 18),
    panel_bg=(28, 28, 28),
    card_bg=(38, 38, 38),
    status_bar_bg=(12, 12, 12),
    banner_bg=(15, 15, 15),
    strip_bg=(15, 15, 15),
    text=(235, 235, 235),
    text_dim=(150, 150, 150),
    grid=(45, 45, 45),
    axis=(90, 90, 90),
    header_accent=(255, 190, 140),
    arm_running=(255, 200, 0),
    arm_stopped=(120, 120, 120),
    forecast_line=(255, 160, 60),
    fov_ray=(90, 70, 30),
    fov_marker=(200, 160, 60),
    buzzer_off=(60, 60, 60),
    light_off=(55, 55, 55),
    pill_bg=(20, 20, 20),
)

# A real light theme -- warm off-white surfaces with dark, high-contrast
# text and borders, not a naive inversion of the dark palette (e.g. the
# grid and card borders are deliberately darker-than-background rather
# than "whatever the dark theme's grid color inverts to").
LIGHT_THEME = Theme(
    name="light",
    window_bg=(228, 236, 242),       # warm light gray-blue
    main_bg=(234, 240, 245),
    panel_bg=(214, 222, 229),
    card_bg=(198, 208, 217),
    status_bar_bg=(206, 216, 224),
    banner_bg=(216, 224, 231),
    strip_bg=(206, 216, 224),
    text=(35, 35, 35),
    text_dim=(105, 105, 105),
    grid=(196, 204, 212),
    axis=(120, 130, 140),
    header_accent=(150, 80, 20),      # dark amber -- readable on light bg
    arm_running=(20, 110, 190),       # amber wouldn't read well here; deep blue reads clearly on light bg
    arm_stopped=(140, 140, 140),
    forecast_line=(20, 90, 200),
    fov_ray=(190, 175, 150),
    fov_marker=(90, 70, 20),
    buzzer_off=(180, 180, 180),
    light_off=(190, 190, 190),
    pill_bg=(244, 248, 251),
)


@dataclass(frozen=True)
class WorkerViewState:
    track_id: int
    position: tuple[float, float]
    forecast_position: tuple[float, float]
    zone_level: str  # "OUTSIDE" / "CAUTION" / "DANGER" -- ZoneLevel.value, kept as a plain str so sim_view has no dependency on safety.zone's enum type
    position_confidence: str = "HIGH"  # "HIGH" / "LOW" -- PositionConfidence.value, plain str for the same reason
    distance_to_machine_m: float = 0.0  # ground-plane distance from the machine pivot (same value zone decisions use)
    distance_to_camera_m: float = 0.0   # ground-plane distance from the camera (localization-confidence context only)
    detection_confidence_pct: float = 0.0  # real YOLO detection confidence (0-100), from perception.tracking.TrackedDetection.confidence


@dataclass(frozen=True)
class SummaryViewState:
    """Mirrors logging.summary.RunSummary's public counters -- plain data
    only, so sim_view stays decoupled from that module too."""
    caution_events: int
    danger_events: int
    time_in_danger_s: float
    stop_commands: int
    camera_faults: int
    telemetry_faults: int
    latency_avg_ms: float
    latency_max_ms: float


@dataclass(frozen=True)
class TransitionRecord:
    timestamp: float
    from_state: str
    to_state: str
    ttc_s: float | None


@dataclass(frozen=True)
class SimViewState:
    """Everything sim_view needs to draw one frame -- plain data, already
    computed by app.py. sim_view reads this and nothing else."""
    risk_state: str  # "SAFE" / "WARNING" / "CRITICAL" / "DEGRADED"
    ttc_s: float | None
    use_prediction: bool  # when False, TTC and the forecast line are never drawn

    machine_pivot: tuple[float, float]
    machine_angle_deg: float
    machine_speed_deg_s: float
    machine_arm_length_m: float
    machine_running: bool  # False while stopped -- draw the arm gray

    zone_center: tuple[float, float]
    zone_orientation_deg: float
    zone_caution_semi_major_m: float
    zone_caution_semi_minor_m: float
    zone_danger_semi_major_m: float
    zone_danger_semi_minor_m: float

    workers: list[WorkerViewState]

    led_level: int
    buzzer_on: bool
    stop_active: bool

    fps: float
    camera_alive: bool
    telemetry_alive: bool
    camera_fault_simulated: bool

    recent_transitions: list[TransitionRecord]

    webcam_frame: np.ndarray | None  # already has detection boxes drawn on it, or None

    summary: SummaryViewState | None = None

    # Derived-but-not-computed-here display values (app.py derives these
    # from the same per-worker data it already has -- e.g. closest =
    # min(distance_to_machine_m across workers) -- no new decision logic,
    # just aggregation of values already computed).
    closest_distance_m: float | None = None
    highest_risk_worker_label: str | None = None
    interlock_action: str = "MONITOR"  # "MONITOR" or "STOP" -- mirrors stop_active as a display label

    camera_ground_position: tuple[float, float] | None = None  # for drawing FOV rays; None hides them


STATUS_LINE_BY_STATE = {
    "SAFE": "All detected personnel outside dynamic swing perimeter.",
    "WARNING": "Personnel within the caution ring. Reduced-speed advised.",
    "CRITICAL": "Personnel inside the danger zone. Machine stopped.",
    "DEGRADED": "Sensor or telemetry fault. Machine forced to STOP.",
}


class SimView:
    def __init__(self, show_webcam_inset: bool = True, theme: Theme = DARK_THEME) -> None:
        self.show_webcam_inset = show_webcam_inset
        self._plot_origin_px = (MAIN_X0 + (MAIN_X1 - MAIN_X0) // 2, MAIN_Y0 + (MAIN_Y1 - MAIN_Y0) // 2)
        self._theme = theme

    @property
    def theme(self) -> Theme:
        return self._theme

    def toggle_theme(self) -> Theme:
        """Switches between DARK_THEME and LIGHT_THEME and returns the new
        theme. The choice persists (in memory) across renders until toggled
        again -- there is no disk persistence, matching the requirement
        that in-memory-for-the-run is sufficient."""
        self._theme = LIGHT_THEME if self._theme is DARK_THEME else DARK_THEME
        return self._theme

    def _world_to_px(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        ox, oy = self._plot_origin_px
        return int(ox + x * PLOT_SCALE_PX_PER_M), int(oy - y * PLOT_SCALE_PX_PER_M)

    def _draw_grid(self, canvas: np.ndarray) -> None:
        t = self._theme
        ox, oy = self._plot_origin_px
        half_w_m = (MAIN_X1 - MAIN_X0) / 2 / PLOT_SCALE_PX_PER_M
        half_h_m = (MAIN_Y1 - MAIN_Y0) / 2 / PLOT_SCALE_PX_PER_M

        n_lines = int(max(half_w_m, half_h_m)) + 1
        for i in range(-n_lines, n_lines + 1):
            offset_m = i * GRID_STEP_M
            x_px, _ = self._world_to_px((offset_m, 0))
            if MAIN_X0 <= x_px <= MAIN_X1:
                cv2.line(canvas, (x_px, MAIN_Y0), (x_px, MAIN_Y1), t.grid, 1)
            _, y_px = self._world_to_px((0, offset_m))
            if MAIN_Y0 <= y_px <= MAIN_Y1:
                cv2.line(canvas, (MAIN_X0, y_px), (MAIN_X1, y_px), t.grid, 1)

        cv2.line(canvas, (MAIN_X0, oy), (MAIN_X1, oy), t.axis, 1)
        cv2.line(canvas, (ox, MAIN_Y0), (ox, MAIN_Y1), t.axis, 1)

    def _draw_ellipse(self, canvas: np.ndarray, center, orientation_deg, semi_major_m, semi_minor_m, color, thickness=2) -> None:
        center_px = self._world_to_px(center)
        axes_px = (int(semi_major_m * PLOT_SCALE_PX_PER_M), int(semi_minor_m * PLOT_SCALE_PX_PER_M))
        cv2.ellipse(canvas, center_px, axes_px, -orientation_deg, 0, 360, color, thickness)

    def _draw_fov_rays(self, canvas: np.ndarray, state: SimViewState) -> None:
        if state.camera_ground_position is None:
            return
        t = self._theme
        cam_px = self._world_to_px(state.camera_ground_position)
        # Rays toward the machine pivot and toward each tracked worker --
        # a real "what the camera can see" cue, not a fabricated FOV cone
        # (we don't model actual lens FOV angle anywhere).
        targets = [state.machine_pivot] + [w.position for w in state.workers]
        for target in targets:
            target_px = self._world_to_px(target)
            cv2.line(canvas, cam_px, target_px, t.fov_ray, 1, cv2.LINE_AA)
        cv2.drawMarker(canvas, cam_px, t.fov_marker, cv2.MARKER_TRIANGLE_UP, 12, 2)

    def _draw_machine(self, canvas: np.ndarray, state: SimViewState) -> None:
        t = self._theme
        pivot_px = self._world_to_px(state.machine_pivot)
        arm_color = t.arm_running if state.machine_running else t.arm_stopped

        angle_rad = np.radians(state.machine_angle_deg)
        tip_x = state.machine_pivot[0] + state.machine_arm_length_m * np.cos(angle_rad)
        tip_y = state.machine_pivot[1] + state.machine_arm_length_m * np.sin(angle_rad)
        tip_px = self._world_to_px((tip_x, tip_y))

        cv2.line(canvas, pivot_px, tip_px, arm_color, 4)
        cv2.circle(canvas, pivot_px, 9, arm_color, -1)
        cv2.circle(canvas, pivot_px, 9, t.main_bg, 1)
        cv2.circle(canvas, tip_px, 5, arm_color, -1)

    def _draw_workers(self, canvas: np.ndarray, state: SimViewState) -> None:
        t = self._theme
        for w in state.workers:
            pos_px = self._world_to_px(w.position)

            dot_color = ZONE_LEVEL_COLOR.get(w.zone_level, t.text)
            if w.position_confidence == "LOW":
                cv2.circle(canvas, pos_px, 11, dot_color, 1)
            cv2.circle(canvas, pos_px, 7, dot_color, -1)

            if state.use_prediction:
                forecast_px = self._world_to_px(w.forecast_position)
                cv2.line(canvas, pos_px, forecast_px, t.forecast_line, 2)

            cv2.putText(canvas, f"W-{w.track_id:02d}", (pos_px[0] + 10, pos_px[1] - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, dot_color, 1)
            dist_label = f"{w.distance_to_machine_m:.1f}m"
            if w.position_confidence == "LOW":
                dist_label += " LOW"
            cv2.putText(canvas, dist_label, (pos_px[0] + 10, pos_px[1] + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, t.text, 1)

    def _draw_main_area(self, canvas: np.ndarray, state: SimViewState) -> None:
        t = self._theme
        cv2.rectangle(canvas, (MAIN_X0, MAIN_Y0), (MAIN_X1, MAIN_Y1), t.main_bg, -1)
        self._draw_grid(canvas)
        self._draw_fov_rays(canvas, state)

        state_color = COLOR_BY_STATE_NAME.get(state.risk_state, t.text)
        self._draw_ellipse(canvas, state.zone_center, state.zone_orientation_deg,
                            state.zone_caution_semi_major_m, state.zone_caution_semi_minor_m, state_color, 2)
        self._draw_ellipse(canvas, state.zone_center, state.zone_orientation_deg,
                            state.zone_danger_semi_major_m, state.zone_danger_semi_minor_m, state_color, 1)

        self._draw_machine(canvas, state)
        self._draw_workers(canvas, state)

        cv2.rectangle(canvas, (MAIN_X0, MAIN_Y0), (MAIN_X1, MAIN_Y1), t.axis, 1)

    def _draw_status_bar(self, canvas: np.ndarray, state: SimViewState) -> None:
        """Top-most strip: state pill, closest distance, swing speed,
        interlock action -- the "at a glance" summary."""
        t = self._theme
        color = COLOR_BY_STATE_NAME.get(state.risk_state, t.text)
        cv2.rectangle(canvas, (0, 0), (WINDOW_W, STATUS_BAR_H), t.status_bar_bg, -1)

        pill_label = f"{state.risk_state}"
        (tw, th), _ = cv2.getTextSize(pill_label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        pill_x0, pill_y0 = 14, 10
        pill_w = tw + 40
        cv2.rectangle(canvas, (pill_x0, pill_y0), (pill_x0 + pill_w, pill_y0 + STATUS_BAR_H - 20), t.pill_bg, -1)
        cv2.rectangle(canvas, (pill_x0, pill_y0), (pill_x0 + pill_w, pill_y0 + STATUS_BAR_H - 20), color, 1)
        cv2.circle(canvas, (pill_x0 + 16, pill_y0 + 13), 5, color, -1)
        cv2.putText(canvas, pill_label, (pill_x0 + 30, pill_y0 + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        closest_str = f"{state.closest_distance_m:.1f}m" if state.closest_distance_m is not None else "--"
        cv2.putText(canvas, f"CLOSEST: {closest_str}", (pill_x0 + pill_w + 30, pill_y0 + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, t.text, 1)
        cv2.putText(canvas, f"SWING: {state.machine_speed_deg_s:.0f}deg/s",
                    (pill_x0 + pill_w + 200, pill_y0 + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.5, t.text, 1)

        action_color = COLOR_BY_STATE_NAME["CRITICAL"] if state.interlock_action == "STOP" else COLOR_BY_STATE_NAME["SAFE"]
        action_label = f"ACTION: {state.interlock_action}"
        (aw, _), _ = cv2.getTextSize(action_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        cv2.putText(canvas, action_label, (WINDOW_W - aw - 20, pill_y0 + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, action_color, 2)

        cv2.line(canvas, (0, STATUS_BAR_H), (WINDOW_W, STATUS_BAR_H), t.axis, 1)

    def _draw_banner(self, canvas: np.ndarray, state: SimViewState) -> None:
        """Second strip: a one-line plain-language description of the
        current state, plus TTC/PERSON IN ZONE/CAMERA FAULT call-outs."""
        t = self._theme
        y0 = STATUS_BAR_H
        color = COLOR_BY_STATE_NAME.get(state.risk_state, t.text)
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, y0 + BANNER_H), t.banner_bg, -1)

        status_line = STATUS_LINE_BY_STATE.get(state.risk_state, "")
        cv2.putText(canvas, status_line, (20, y0 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)

        next_x = 20
        tag_y = y0 + 46
        if state.use_prediction:
            ttc_str = f"{state.ttc_s:.1f}s" if state.ttc_s is not None else "--"
            cv2.putText(canvas, f"TTC: {ttc_str}", (next_x, tag_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, t.text, 1)
            next_x += 130

        if state.risk_state == "CRITICAL":
            cv2.putText(canvas, "PERSON IN ZONE", (next_x, tag_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            next_x += 190

        if state.camera_fault_simulated:
            cv2.putText(canvas, "CAMERA FAULT", (next_x, tag_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        COLOR_BY_STATE_NAME["CRITICAL"], 2)

        cv2.line(canvas, (0, y0 + BANNER_H), (WINDOW_W, y0 + BANNER_H), t.axis, 1)

    def _panel_header(self, canvas: np.ndarray, x0: int, y: int, x1: int, text: str) -> int:
        t = self._theme
        cv2.putText(canvas, text, (x0 + 14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, t.header_accent, 1)
        cv2.line(canvas, (x0 + 12, y + 5), (x1 - 12, y + 5), t.axis, 1)
        return y + 18

    def _kv_card(self, canvas: np.ndarray, x0: int, y: int, w: int, label: str, value: str,
                 value_color=None) -> None:
        t = self._theme
        if value_color is None:
            value_color = t.text
        cv2.rectangle(canvas, (x0, y), (x0 + w, y + 34), t.card_bg, -1)
        cv2.putText(canvas, label, (x0 + 7, y + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.32, t.text_dim, 1)
        cv2.putText(canvas, value, (x0 + 7, y + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.46, value_color, 1)

    def _draw_machine_telemetry_panel(self, canvas: np.ndarray, state: SimViewState, x0: int, x1: int, y: int) -> int:
        y = self._panel_header(canvas, x0, y, x1, "MACHINE TELEMETRY")
        col_w = (x1 - x0 - 36) // 2
        self._kv_card(canvas, x0 + 12, y, col_w, "SWING ANGLE", f"{state.machine_angle_deg:.1f} deg")
        self._kv_card(canvas, x0 + 24 + col_w, y, col_w, "SWING SPEED", f"{state.machine_speed_deg_s:.0f} deg/s")
        y += 38
        pivot_state = "RUNNING" if state.machine_running else "STOPPED"
        pivot_color = COLOR_BY_STATE_NAME["SAFE"] if state.machine_running else COLOR_BY_STATE_NAME["DEGRADED"]
        self._kv_card(canvas, x0 + 12, y, col_w, "PIVOT STATE", pivot_state, pivot_color)
        self._kv_card(canvas, x0 + 24 + col_w, y, col_w, "DANGER RADIUS", f"{state.zone_danger_semi_major_m:.2f} m",
                      COLOR_BY_STATE_NAME["CRITICAL"])
        return y + 42

    def _draw_perception_panel(self, canvas: np.ndarray, state: SimViewState, x0: int, x1: int, y: int) -> int:
        y = self._panel_header(canvas, x0, y, x1, "PERCEPTION ENGINE")
        col_w = (x1 - x0 - 36) // 2
        self._kv_card(canvas, x0 + 12, y, col_w, "WORKERS DETECTED", f"{len(state.workers)}")
        camera_color = COLOR_BY_STATE_NAME["SAFE"] if state.camera_alive else COLOR_BY_STATE_NAME["CRITICAL"]
        self._kv_card(canvas, x0 + 24 + col_w, y, col_w, "CAMERA STATE",
                      "ONLINE" if state.camera_alive else "LOST", camera_color)
        y += 38
        self._kv_card(canvas, x0 + 12, y, col_w, "PROCESSING RATE", f"{state.fps:.0f} FPS")
        avg_conf = (sum(w.detection_confidence_pct for w in state.workers) / len(state.workers)
                    if state.workers else 0.0)
        self._kv_card(canvas, x0 + 24 + col_w, y, col_w, "AVG CONFIDENCE", f"{avg_conf:.0f}%")
        return y + 42

    def _draw_risk_panel(self, canvas: np.ndarray, state: SimViewState, x0: int, x1: int, y: int) -> int:
        t = self._theme
        y = self._panel_header(canvas, x0, y, x1, "SAFETY RISK ENGINE")
        col_w = (x1 - x0 - 36) // 2
        highest_zone = max((w.zone_level for w in state.workers), key=lambda z: ["OUTSIDE", "CAUTION", "DANGER"].index(z), default="OUTSIDE")
        self._kv_card(canvas, x0 + 12, y, col_w, "HIGHEST ZONE", highest_zone,
                      ZONE_LEVEL_COLOR.get(highest_zone, t.text))
        action_color = COLOR_BY_STATE_NAME["CRITICAL"] if state.interlock_action == "STOP" else COLOR_BY_STATE_NAME["SAFE"]
        self._kv_card(canvas, x0 + 24 + col_w, y, col_w, "INTERLOCK ACTION", state.interlock_action, action_color)
        y += 38
        target = state.highest_risk_worker_label or "--"
        cv2.putText(canvas, f"HIGHEST RISK TARGET: {target}", (x0 + 14, y + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, t.text, 1)
        return y + 22

    def _draw_worker_register(self, canvas: np.ndarray, state: SimViewState, x0: int, x1: int, y0: int, y1: int) -> None:
        t = self._theme
        y = self._panel_header(canvas, x0, y0, x1, "WORKER PROXIMITY REGISTER")
        row_h = 40
        for i, w in enumerate(state.workers):
            if y + row_h > y1:
                remaining = len(state.workers) - i
                cv2.putText(canvas, f"+{remaining} more...", (x0 + 14, y + 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, t.text_dim, 1)
                break
            zone_color = ZONE_LEVEL_COLOR.get(w.zone_level, t.text)
            cv2.rectangle(canvas, (x0 + 10, y), (x1 - 10, y + row_h - 6), t.card_bg, -1)
            cv2.putText(canvas, f"W-{w.track_id:02d}", (x0 + 18, y + 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, t.text, 1)
            cv2.putText(canvas, w.zone_level, (x1 - 90, y + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.4, zone_color, 1)
            detail = (f"Machine: {w.distance_to_machine_m:.2f}m  Camera: {w.distance_to_camera_m:.2f}m  "
                      f"Conf: {w.detection_confidence_pct:.0f}%")
            conf_color = COLOR_BY_STATE_NAME["CRITICAL"] if w.position_confidence == "LOW" else t.text_dim
            cv2.putText(canvas, detail, (x0 + 18, y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.36, conf_color, 1)
            y += row_h

        if not state.workers:
            cv2.putText(canvas, "No workers currently tracked.", (x0 + 14, y + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, t.text_dim, 1)

    def _draw_right_panel(self, canvas: np.ndarray, state: SimViewState) -> None:
        t = self._theme
        x0, y0 = MAIN_X1, STATUS_BAR_H + BANNER_H
        x1, y1 = WINDOW_W, MAIN_Y1
        cv2.rectangle(canvas, (x0, y0), (x1, y1), t.panel_bg, -1)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), t.axis, 1)

        y = y0 + 16
        y = self._draw_machine_telemetry_panel(canvas, state, x0, x1, y)
        y = self._draw_perception_panel(canvas, state, x0, x1, y)
        y = self._draw_risk_panel(canvas, state, x0, x1, y)

        y += 10
        cv2.line(canvas, (x0 + 10, y), (x1 - 10, y), t.axis, 1)
        y += 4

        # Reserve room at the bottom of the panel for LED/buzzer/STOP and
        # the run summary, computed from what that footer actually draws
        # (see _draw_indicators_and_summary), not a guessed constant --
        # give the worker register whatever vertical space is left over.
        footer_h = self._indicators_and_summary_height(state)
        register_bottom = max(y1 - footer_h, y)
        self._draw_worker_register(canvas, state, x0, x1, y, register_bottom)

        self._draw_indicators_and_summary(canvas, state, x0, x1, register_bottom + 12, y1)

    def _indicators_and_summary_height(self, state: SimViewState) -> int:
        # Mirrors _draw_indicators_and_summary's own vertical deltas exactly
        # so the worker register above it is given all remaining space and
        # nothing more, with no overlap and no wasted gap.
        h = 16  # divider gap
        h += 22 + 30  # lights row height + gap to buzzer
        h += 22 + 8  # buzzer box + trailing gap (folded into the next section's leading offset)
        if state.stop_active:
            h += 22 + 8  # STOP ISSUED box + gap
        if state.summary is not None:
            h += 4 + 16 + 4 * 16  # divider gap + spacing + 4 summary lines
        return h

    def _draw_indicators_and_summary(self, canvas: np.ndarray, state: SimViewState, x0: int, x1: int, y: int, y1: int) -> None:
        t = self._theme
        cv2.line(canvas, (x0 + 10, y), (x1 - 10, y), t.axis, 1)
        y += 16

        cx = x0 + 35
        light_colors_on = [COLOR_BY_STATE_NAME["SAFE"], COLOR_BY_STATE_NAME["WARNING"], COLOR_BY_STATE_NAME["CRITICAL"]]
        for i, on_color in enumerate(light_colors_on):
            lx = cx + i * 50
            lit = state.led_level == i or (state.led_level >= 3 and i == 2)
            color = on_color if lit else t.light_off
            cv2.circle(canvas, (lx, y), 12, color, -1)
            cv2.circle(canvas, (lx, y), 12, t.axis, 2)

        buzzer_y = y + 22
        buzzer_color = COLOR_BY_STATE_NAME["CRITICAL"] if (state.buzzer_on and int(time.time() * 4) % 2 == 0) else t.buzzer_off
        cv2.rectangle(canvas, (x0 + 15, buzzer_y), (x1 - 15, buzzer_y + 22), buzzer_color, -1)
        cv2.putText(canvas, "BUZZER", (x0 + 24, buzzer_y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, t.text, 1)

        y = buzzer_y + 30
        if state.stop_active:
            cv2.rectangle(canvas, (x0 + 15, y), (x1 - 15, y + 22), COLOR_BY_STATE_NAME["CRITICAL"], -1)
            cv2.putText(canvas, "STOP ISSUED", (x0 + 24, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 2)
            y += 30

        if state.summary is not None:
            y += 4
            cv2.line(canvas, (x0 + 10, y), (x1 - 10, y), t.axis, 1)
            y += 16
            s = state.summary
            summary_lines = [
                f"CAUTION events: {s.caution_events}   DANGER events: {s.danger_events}",
                f"time in DANGER: {s.time_in_danger_s:.1f}s   STOP cmds: {s.stop_commands}",
                f"cam/telem faults: {s.camera_faults}/{s.telemetry_faults}",
                f"latency avg/max: {s.latency_avg_ms:.0f}/{s.latency_max_ms:.0f}ms",
            ]
            for line in summary_lines:
                if y + 16 > y1:
                    break
                cv2.putText(canvas, line, (x0 + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, t.text_dim, 1)
                y += 18

    def _draw_webcam_inset(self, canvas: np.ndarray, state: SimViewState) -> None:
        if not self.show_webcam_inset or state.webcam_frame is None:
            return
        t = self._theme
        x0 = MAIN_X0 + 10
        y0 = MAIN_Y1 - INSET_H - 10
        resized = cv2.resize(state.webcam_frame, (INSET_W, INSET_H))
        canvas[y0:y0 + INSET_H, x0:x0 + INSET_W] = resized
        cv2.rectangle(canvas, (x0, y0), (x0 + INSET_W, y0 + INSET_H), t.axis, 2)
        cv2.putText(canvas, "LIVE CAMERA", (x0 + 8, y0 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, t.text, 1)

    def _draw_control_hints(self, canvas: np.ndarray) -> None:
        t = self._theme
        hints = "[Q] Quit  [C] Fault  [R] Reset  [+/-] Speed  [S] Snapshot  [H] Hologram  [D] Theme  [W] Web Simulation"
        (hw, _), _ = cv2.getTextSize(hints, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
        cv2.putText(canvas, hints, (WINDOW_W - hw - 10, WINDOW_H - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, t.text_dim, 1)

    def _draw_bottom_strip(self, canvas: np.ndarray, state: SimViewState) -> None:
        t = self._theme
        y0 = WINDOW_H - BOTTOM_STRIP_H
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, WINDOW_H), t.strip_bg, -1)
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, WINDOW_H), t.axis, 1)

        n_logged = len(state.recent_transitions)
        cv2.putText(canvas, f"SAFETY AUDIT LOG  ({n_logged} logged)", (10, y0 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, t.text, 1)

        recent = state.recent_transitions[-5:]
        for i, transition in enumerate(recent):
            ttc_str = f"{transition.ttc_s:.1f}s" if transition.ttc_s is not None else "--"
            time_str = time.strftime("%H:%M:%S", time.localtime(transition.timestamp))
            line = f"[{time_str}]  {transition.from_state:>8s} -> {transition.to_state:<8s}  ttc={ttc_str}"
            color = COLOR_BY_STATE_NAME.get(transition.to_state, t.text)
            cv2.putText(canvas, line, (10, y0 + 38 + i * 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        self._draw_control_hints(canvas)

    def render(self, state: SimViewState) -> np.ndarray:
        """Compose one full dashboard frame from `state`. Pure drawing --
        no decisions are made about what any value means."""
        canvas = np.full((WINDOW_H, WINDOW_W, 3), self._theme.window_bg, dtype=np.uint8)

        self._draw_main_area(canvas, state)
        self._draw_status_bar(canvas, state)
        self._draw_banner(canvas, state)
        self._draw_right_panel(canvas, state)
        self._draw_webcam_inset(canvas, state)
        self._draw_bottom_strip(canvas, state)

        return canvas

    def show(self, canvas: np.ndarray) -> None:
        cv2.imshow(WINDOW_NAME, canvas)

    def poll_keys(self, wait_ms: int = 1) -> str | None:
        """Returns a single-character key label for a recognized control key
        pressed this frame ('q', 'c', 'r', '+', '-', 's', 'h', 'd', 'w'), or
        None. Does NOT interpret or act on the key -- that's app.py's job
        (though this class does own toggle_theme() itself, called by app.py
        when it sees 'd' -- see its docstring). 'w' (launch the web
        simulation) is likewise just reported here; app.py decides what to
        do with it, via dashboard.web_launcher.WebSimLauncher."""
        key = cv2.waitKey(wait_ms) & 0xFF
        if key == 255:
            return None
        char = chr(key) if key < 128 else None
        if char in {"q", "c", "r", "s", "h", "d", "w"}:
            return char
        if char in {"+", "="}:  # '=' so it works without needing shift on most layouts
            return "+"
        if char == "-":
            return "-"
        return None

    def close(self) -> None:
        cv2.destroyWindow(WINDOW_NAME)
