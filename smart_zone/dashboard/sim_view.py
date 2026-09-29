"""Display-only OpenCV dashboard for the --sim pipeline.

Draws one composed 1280x720 window per pipeline loop from a plain data
snapshot (SimViewState) that the caller (app.py) builds each frame. This
module makes NO decisions: it does not import safety.risk_engine, does not
compute zone geometry, does not run the Kalman filter, and does not decide
what state the system is in -- it only reads values that were already
computed elsewhere and draws them. It also does not decide what a key
press MEANS (e.g. toggling a camera fault, resetting the scenario) -- it
only reports which control keys were pressed this frame via poll_keys();
interpreting and acting on them is app.py's job, consistent with keeping
all decision logic out of this module.

Layout (see module docstring in the task): top-down site view with metre
grid, top banner with state+TTC, right indicator panel, bottom-left webcam
inset, bottom strip of the last 5 transitions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

WINDOW_NAME = "Smart-Zone Edge Guardian - Sim View"
WINDOW_W, WINDOW_H = 1280, 720

BANNER_H = 70
BOTTOM_STRIP_H = 90
RIGHT_PANEL_W = 260
INSET_W, INSET_H = 280, 210

MAIN_X0, MAIN_Y0 = 0, BANNER_H
MAIN_X1 = WINDOW_W - RIGHT_PANEL_W
MAIN_Y1 = WINDOW_H - BOTTOM_STRIP_H

PLOT_SCALE_PX_PER_M = 30.0
GRID_STEP_M = 1.0

COLOR_BY_STATE_NAME = {
    "SAFE": (0, 200, 0),       # green
    "WARNING": (0, 165, 255),  # amber
    "CRITICAL": (0, 0, 255),   # red
    "DEGRADED": (140, 140, 140),  # gray
}
COLOR_TEXT = (240, 240, 240)
COLOR_GRID = (50, 50, 50)
COLOR_AXIS = (90, 90, 90)
COLOR_ARM_RUNNING = (255, 200, 0)
COLOR_ARM_STOPPED = (120, 120, 120)
COLOR_FORECAST = (255, 160, 60)

ZONE_LEVEL_COLOR = {
    "DANGER": (0, 0, 255),
    "CAUTION": (0, 210, 255),
    "OUTSIDE": (255, 255, 255),
}
COLOR_BG = (20, 20, 20)
COLOR_PANEL_BG = (30, 30, 30)


@dataclass(frozen=True)
class WorkerViewState:
    track_id: int
    position: tuple[float, float]
    forecast_position: tuple[float, float]
    zone_level: str  # "OUTSIDE" / "CAUTION" / "DANGER" -- ZoneLevel.value, kept as a plain str so sim_view has no dependency on safety.zone's enum type
    position_confidence: str = "HIGH"  # "HIGH" / "LOW" -- PositionConfidence.value, plain str for the same reason


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


class SimView:
    def __init__(self, show_webcam_inset: bool = True) -> None:
        self.show_webcam_inset = show_webcam_inset
        self._plot_origin_px = (MAIN_X0 + (MAIN_X1 - MAIN_X0) // 2, MAIN_Y0 + (MAIN_Y1 - MAIN_Y0) // 2)

    def _world_to_px(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        ox, oy = self._plot_origin_px
        return int(ox + x * PLOT_SCALE_PX_PER_M), int(oy - y * PLOT_SCALE_PX_PER_M)

    def _draw_grid(self, canvas: np.ndarray) -> None:
        ox, oy = self._plot_origin_px
        half_w_m = (MAIN_X1 - MAIN_X0) / 2 / PLOT_SCALE_PX_PER_M
        half_h_m = (MAIN_Y1 - MAIN_Y0) / 2 / PLOT_SCALE_PX_PER_M

        n_lines = int(max(half_w_m, half_h_m)) + 1
        for i in range(-n_lines, n_lines + 1):
            offset_m = i * GRID_STEP_M
            x_px, _ = self._world_to_px((offset_m, 0))
            if MAIN_X0 <= x_px <= MAIN_X1:
                cv2.line(canvas, (x_px, MAIN_Y0), (x_px, MAIN_Y1), COLOR_GRID, 1)
            _, y_px = self._world_to_px((0, offset_m))
            if MAIN_Y0 <= y_px <= MAIN_Y1:
                cv2.line(canvas, (MAIN_X0, y_px), (MAIN_X1, y_px), COLOR_GRID, 1)

        cv2.line(canvas, (MAIN_X0, oy), (MAIN_X1, oy), COLOR_AXIS, 1)
        cv2.line(canvas, (ox, MAIN_Y0), (ox, MAIN_Y1), COLOR_AXIS, 1)

    def _draw_ellipse(self, canvas: np.ndarray, center, orientation_deg, semi_major_m, semi_minor_m, color, thickness=2) -> None:
        center_px = self._world_to_px(center)
        axes_px = (int(semi_major_m * PLOT_SCALE_PX_PER_M), int(semi_minor_m * PLOT_SCALE_PX_PER_M))
        cv2.ellipse(canvas, center_px, axes_px, -orientation_deg, 0, 360, color, thickness)

    def _draw_machine(self, canvas: np.ndarray, state: SimViewState) -> None:
        pivot_px = self._world_to_px(state.machine_pivot)
        arm_color = COLOR_ARM_RUNNING if state.machine_running else COLOR_ARM_STOPPED

        angle_rad = np.radians(state.machine_angle_deg)
        tip_x = state.machine_pivot[0] + state.machine_arm_length_m * np.cos(angle_rad)
        tip_y = state.machine_pivot[1] + state.machine_arm_length_m * np.sin(angle_rad)
        tip_px = self._world_to_px((tip_x, tip_y))

        cv2.line(canvas, pivot_px, tip_px, arm_color, 4)
        cv2.circle(canvas, pivot_px, 7, arm_color, -1)
        cv2.circle(canvas, tip_px, 5, arm_color, -1)

    def _draw_workers(self, canvas: np.ndarray, state: SimViewState) -> None:
        for w in state.workers:
            pos_px = self._world_to_px(w.position)

            dot_color = ZONE_LEVEL_COLOR.get(w.zone_level, (255, 255, 255))
            # LOW confidence draws a thin outline ring around the dot, so
            # it's visually distinguishable without needing a second color.
            if w.position_confidence == "LOW":
                cv2.circle(canvas, pos_px, 11, dot_color, 1)
            cv2.circle(canvas, pos_px, 7, dot_color, -1)

            if state.use_prediction:
                forecast_px = self._world_to_px(w.forecast_position)
                cv2.line(canvas, pos_px, forecast_px, COLOR_FORECAST, 2)

            label = f"id={w.track_id} [{w.zone_level}]"
            if w.position_confidence == "LOW":
                label += " (LOW conf)"
            cv2.putText(canvas, label, (pos_px[0] + 10, pos_px[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)

    def _draw_main_area(self, canvas: np.ndarray, state: SimViewState) -> None:
        cv2.rectangle(canvas, (MAIN_X0, MAIN_Y0), (MAIN_X1, MAIN_Y1), COLOR_BG, -1)
        self._draw_grid(canvas)

        state_color = COLOR_BY_STATE_NAME.get(state.risk_state, COLOR_TEXT)
        self._draw_ellipse(canvas, state.zone_center, state.zone_orientation_deg,
                            state.zone_caution_semi_major_m, state.zone_caution_semi_minor_m, state_color, 2)
        self._draw_ellipse(canvas, state.zone_center, state.zone_orientation_deg,
                            state.zone_danger_semi_major_m, state.zone_danger_semi_minor_m, state_color, 1)

        self._draw_machine(canvas, state)
        self._draw_workers(canvas, state)

        cv2.rectangle(canvas, (MAIN_X0, MAIN_Y0), (MAIN_X1, MAIN_Y1), COLOR_AXIS, 1)

    def _draw_banner(self, canvas: np.ndarray, state: SimViewState) -> None:
        color = COLOR_BY_STATE_NAME.get(state.risk_state, COLOR_TEXT)
        cv2.rectangle(canvas, (0, 0), (WINDOW_W, BANNER_H), (15, 15, 15), -1)
        cv2.putText(canvas, state.risk_state, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3)

        next_x = 330
        if state.use_prediction:
            ttc_str = f"{state.ttc_s:.1f}s" if state.ttc_s is not None else "--"
            cv2.putText(canvas, f"TTC: {ttc_str}", (next_x, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, COLOR_TEXT, 2)
            next_x += 220

        if state.risk_state == "CRITICAL":
            cv2.putText(canvas, "PERSON IN ZONE", (next_x, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        if state.camera_fault_simulated:
            cv2.putText(canvas, "CAMERA FAULT", (WINDOW_W - 500, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

        cv2.rectangle(canvas, (0, 0), (WINDOW_W, BANNER_H), COLOR_AXIS, 1)

    def _draw_right_panel(self, canvas: np.ndarray, state: SimViewState) -> None:
        x0, y0 = MAIN_X1, BANNER_H
        x1, y1 = WINDOW_W, MAIN_Y1
        cv2.rectangle(canvas, (x0, y0), (x1, y1), COLOR_PANEL_BG, -1)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), COLOR_AXIS, 1)

        cx = x0 + 40
        light_y = y0 + 40
        # Three lamps: green=SAFE(0), yellow=WARNING(1), red=CRITICAL(2).
        # DEGRADED (led_level=3) is the most severe fault state, so it lights
        # the red lamp too rather than showing nothing.
        light_colors_on = [(0, 255, 0), (0, 220, 255), (0, 0, 255)]
        light_colors_off = (55, 55, 55)
        for i, on_color in enumerate(light_colors_on):
            lx = cx + i * 60
            lit = state.led_level == i or (state.led_level >= 3 and i == 2)
            color = on_color if lit else light_colors_off
            cv2.circle(canvas, (lx, light_y), 18, color, -1)
            cv2.circle(canvas, (lx, light_y), 18, COLOR_AXIS, 2)

        buzzer_y = light_y + 55
        buzzer_color = (0, 0, 255) if (state.buzzer_on and int(time.time() * 4) % 2 == 0) else (60, 60, 60)
        cv2.rectangle(canvas, (x0 + 15, buzzer_y), (x1 - 15, buzzer_y + 35), buzzer_color, -1)
        cv2.putText(canvas, "BUZZER", (x0 + 30, buzzer_y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        y = buzzer_y + 60
        if state.stop_active:
            cv2.rectangle(canvas, (x0 + 15, y), (x1 - 15, y + 35), (0, 0, 200), -1)
            cv2.putText(canvas, "STOP ISSUED", (x0 + 25, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y += 55

        lines = [
            f"angle: {state.machine_angle_deg:6.1f} deg",
            f"speed: {state.machine_speed_deg_s:6.1f} deg/s",
            f"FPS:   {state.fps:5.1f}",
            f"camera:    {'OK' if state.camera_alive else 'LOST'}",
            f"telemetry: {'OK' if state.telemetry_alive else 'LOST'}",
        ]
        for line in lines:
            color = COLOR_TEXT
            if "LOST" in line:
                color = (0, 0, 255)
            cv2.putText(canvas, line, (x0 + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += 26

        if state.summary is not None:
            y += 10
            cv2.line(canvas, (x0 + 10, y), (x1 - 10, y), COLOR_AXIS, 1)
            y += 20
            s = state.summary
            summary_lines = [
                f"CAUTION events: {s.caution_events}",
                f"DANGER events:  {s.danger_events}",
                f"time in DANGER: {s.time_in_danger_s:.1f}s",
                f"STOP commands:  {s.stop_commands}",
                f"cam/telem flts: {s.camera_faults}/{s.telemetry_faults}",
                f"latency avg/max:{s.latency_avg_ms:.0f}/{s.latency_max_ms:.0f}ms",
            ]
            for line in summary_lines:
                cv2.putText(canvas, line, (x0 + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COLOR_TEXT, 1)
                y += 22

    def _draw_webcam_inset(self, canvas: np.ndarray, state: SimViewState) -> None:
        if not self.show_webcam_inset or state.webcam_frame is None:
            return
        x0 = MAIN_X0 + 10
        y0 = MAIN_Y1 - INSET_H - 10
        resized = cv2.resize(state.webcam_frame, (INSET_W, INSET_H))
        canvas[y0:y0 + INSET_H, x0:x0 + INSET_W] = resized
        cv2.rectangle(canvas, (x0, y0), (x0 + INSET_W, y0 + INSET_H), COLOR_AXIS, 2)
        cv2.putText(canvas, "LIVE CAMERA", (x0 + 8, y0 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)

    def _draw_bottom_strip(self, canvas: np.ndarray, state: SimViewState) -> None:
        y0 = WINDOW_H - BOTTOM_STRIP_H
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, WINDOW_H), (15, 15, 15), -1)
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, WINDOW_H), COLOR_AXIS, 1)

        cv2.putText(canvas, "Recent transitions:", (10, y0 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)

        recent = state.recent_transitions[-5:]
        for i, t in enumerate(recent):
            ttc_str = f"{t.ttc_s:.1f}s" if t.ttc_s is not None else "--"
            time_str = time.strftime("%H:%M:%S", time.localtime(t.timestamp))
            line = f"{time_str}  {t.from_state:>8s} -> {t.to_state:<8s}  ttc={ttc_str}"
            color = COLOR_BY_STATE_NAME.get(t.to_state, COLOR_TEXT)
            cv2.putText(canvas, line, (10, y0 + 38 + i * 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    def render(self, state: SimViewState) -> np.ndarray:
        """Compose one full dashboard frame from `state`. Pure drawing --
        no decisions are made about what any value means."""
        canvas = np.full((WINDOW_H, WINDOW_W, 3), 15, dtype=np.uint8)

        self._draw_main_area(canvas, state)
        self._draw_banner(canvas, state)
        self._draw_right_panel(canvas, state)
        self._draw_webcam_inset(canvas, state)
        self._draw_bottom_strip(canvas, state)

        return canvas

    def show(self, canvas: np.ndarray) -> None:
        cv2.imshow(WINDOW_NAME, canvas)

    def poll_keys(self, wait_ms: int = 1) -> str | None:
        """Returns a single-character key label for a recognized control key
        pressed this frame ('q', 'c', 'r', '+', '-', 's', 'h'), or None. Does
        NOT interpret or act on the key -- that's app.py's job."""
        key = cv2.waitKey(wait_ms) & 0xFF
        if key == 255:
            return None
        char = chr(key) if key < 128 else None
        if char in {"q", "c", "r", "s", "h"}:
            return char
        if char in {"+", "="}:  # '=' so it works without needing shift on most layouts
            return "+"
        if char == "-":
            return "-"
        return None

    def close(self) -> None:
        cv2.destroyWindow(WINDOW_NAME)
