"""Hologram (sci-fi wireframe) rendering mode for the --sim dashboard.

Display only, same constraint as sim_view.py: reads a SimViewState /
WorkerViewState snapshot that app.py already computed and draws it. Does
NOT import safety.risk_engine, safety.zone, safety.confidence,
prediction.kalman, or prediction.ttc -- no decision logic here, only
drawing. (Verified by the same AST-based no-decision-logic test as
sim_view.py, applied to this module too.)

Technique: glowing elements (grid, zones, machine, workers) are drawn onto
a small low-resolution layer, blurred for the glow effect, upscaled back
to full window size, and additively blended onto a dark background --
text (banner, STOP ISSUED, summary panel) is drawn AFTER blending, at full
resolution, so it stays crisp and readable over the glow rather than
getting blurred itself. Rendering the glow layer at a reduced resolution
(GLOW_SCALE) keeps the blur cheap; see dashboard/sim_view.py's WINDOW_W/H
and layout constants, which this module reuses so both views share one
window size and one banner/panel/strip layout.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from smart_zone.dashboard.sim_view import (
    BANNER_H,
    BOTTOM_STRIP_H,
    INSET_H,
    INSET_W,
    MAIN_X0,
    MAIN_X1,
    MAIN_Y0,
    MAIN_Y1,
    RIGHT_PANEL_W,
    WINDOW_H,
    WINDOW_W,
    SimViewState,
)

GLOW_SCALE = 0.35  # glow layer rendered at this fraction of window resolution, then upscaled
GLOW_BLUR_KSIZE = 7  # must be odd; kept small since GLOW_SCALE already reduces the blur cost

PLOT_SCALE_PX_PER_M = 30.0
GRID_STEP_M = 1.0

COLOR_BG = (5, 5, 10)
COLOR_GRID = (120, 60, 0)  # cyan-ish in BGR (high B+G, low R) -- see _cyan()
COLOR_TEXT = (230, 255, 230)
COLOR_SCANLINE = (40, 20, 0)

STATE_GLOW_COLOR = {
    "SAFE": (255, 220, 40),      # cyan-ish
    "WARNING": (0, 165, 255),    # amber
    "CRITICAL": (0, 0, 255),     # red
    "DEGRADED": (140, 140, 140),  # gray
}

ZONE_LEVEL_GLOW_COLOR = {
    "DANGER": (0, 0, 255),
    "CAUTION": (0, 210, 255),
    "OUTSIDE": (255, 220, 40),
}


def _pulse(period_s: float = 0.6) -> float:
    """A smooth 0..1 pulse driven by wall-clock time, for the CRITICAL
    pulsing-red effect."""
    phase = (time.time() % period_s) / period_s
    return 0.5 + 0.5 * np.sin(2 * np.pi * phase)


class HologramView:
    """Renders the same SimViewState as sim_view.SimView.render(), but as a
    glowing wireframe hologram instead of the plain top-down dashboard.
    Call sites in app.py are expected to hold both renderers and pick one
    based on the 'h' toggle -- see SimView.hologram_enabled."""

    def __init__(self) -> None:
        self._plot_origin_px = (MAIN_X0 + (MAIN_X1 - MAIN_X0) // 2, MAIN_Y0 + (MAIN_Y1 - MAIN_Y0) // 2)
        glow_w = int(WINDOW_W * GLOW_SCALE)
        glow_h = int(WINDOW_H * GLOW_SCALE)
        self._glow_size = (glow_w, glow_h)
        self._glow_scale_px_per_m = PLOT_SCALE_PX_PER_M * GLOW_SCALE
        ox, oy = self._plot_origin_px
        self._glow_origin_px = (int(ox * GLOW_SCALE), int(oy * GLOW_SCALE))
        ksize = GLOW_BLUR_KSIZE
        if ksize % 2 == 0:
            ksize += 1
        self._blur_ksize = ksize

    def _world_to_glow_px(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        ox, oy = self._glow_origin_px
        return int(ox + x * self._glow_scale_px_per_m), int(oy - y * self._glow_scale_px_per_m)

    def _draw_scan_lines(self, canvas: np.ndarray) -> None:
        # Faint, widely-spaced scan lines -- a subtle texture, not a
        # dominant visual element competing with the actual content.
        overlay = canvas.copy()
        for y in range(MAIN_Y0, MAIN_Y1, 6):
            cv2.line(overlay, (MAIN_X0, y), (MAIN_X1, y), COLOR_SCANLINE, 1)
        cv2.addWeighted(overlay, 0.15, canvas, 0.85, 0, dst=canvas)

    def _draw_grid_glow(self, glow: np.ndarray) -> None:
        glow_x0, glow_x1 = int(MAIN_X0 * GLOW_SCALE), int(MAIN_X1 * GLOW_SCALE)
        glow_y0, glow_y1 = int(MAIN_Y0 * GLOW_SCALE), int(MAIN_Y1 * GLOW_SCALE)
        half_w_m = (MAIN_X1 - MAIN_X0) / 2 / PLOT_SCALE_PX_PER_M
        half_h_m = (MAIN_Y1 - MAIN_Y0) / 2 / PLOT_SCALE_PX_PER_M
        n_lines = int(max(half_w_m, half_h_m)) + 1

        cyan = (200, 160, 0)
        for i in range(-n_lines, n_lines + 1):
            offset_m = i * GRID_STEP_M
            x_px, _ = self._world_to_glow_px((offset_m, 0))
            if glow_x0 <= x_px <= glow_x1:
                cv2.line(glow, (x_px, glow_y0), (x_px, glow_y1), cyan, 1)
            _, y_px = self._world_to_glow_px((0, offset_m))
            if glow_y0 <= y_px <= glow_y1:
                cv2.line(glow, (glow_x0, y_px), (glow_x1, y_px), cyan, 1)

    def _draw_ellipse_glow(self, glow, center, orientation_deg, semi_major_m, semi_minor_m, color, thickness) -> None:
        center_px = self._world_to_glow_px(center)
        axes_px = (
            max(int(semi_major_m * self._glow_scale_px_per_m), 1),
            max(int(semi_minor_m * self._glow_scale_px_per_m), 1),
        )
        cv2.ellipse(glow, center_px, axes_px, -orientation_deg, 0, 360, color, thickness)

    def _draw_machine_glow(self, glow: np.ndarray, state: SimViewState) -> None:
        pivot_px = self._world_to_glow_px(state.machine_pivot)
        color = (255, 220, 40) if state.machine_running else (150, 150, 150)

        angle_rad = np.radians(state.machine_angle_deg)
        arm_len = state.machine_arm_length_m

        # A simple wireframe excavator silhouette: base (small square),
        # cab (circle above base), boom (line from cab out to the current
        # angle), bucket (small triangle at the boom tip).
        base_width_m = 0.6
        base_height_m = 0.18
        cab_radius_m = 0.28

        base_half_w = max(int(base_width_m * self._glow_scale_px_per_m / 2), 5)
        base_half_h = max(int(base_height_m * self._glow_scale_px_per_m / 2), 2)
        base_y = pivot_px[1] + base_half_h + 2  # tracks/undercarriage sit below the cab
        cv2.rectangle(glow, (pivot_px[0] - base_half_w, base_y - base_half_h),
                      (pivot_px[0] + base_half_w, base_y + base_half_h), color, 2)

        cab_radius_px = max(int(cab_radius_m * self._glow_scale_px_per_m), 4)
        cv2.circle(glow, pivot_px, cab_radius_px, color, 2)

        tip_x = state.machine_pivot[0] + arm_len * np.cos(angle_rad)
        tip_y = state.machine_pivot[1] + arm_len * np.sin(angle_rad)
        tip_px = self._world_to_glow_px((tip_x, tip_y))
        cv2.line(glow, pivot_px, tip_px, color, 3)

        # Bucket: a small triangle at the boom tip, perpendicular to the
        # boom direction.
        perp_rad = angle_rad + np.pi / 2
        bucket_size_m = 0.25
        bx = int(bucket_size_m * self._glow_scale_px_per_m * np.cos(perp_rad))
        by = int(bucket_size_m * self._glow_scale_px_per_m * np.sin(perp_rad))
        p1 = tip_px
        p2 = (tip_px[0] + bx, tip_px[1] - by)
        p3 = (tip_px[0] - bx, tip_px[1] + by)
        cv2.line(glow, p1, p2, color, 2)
        cv2.line(glow, p1, p3, color, 2)
        cv2.line(glow, p2, p3, color, 2)

    def _draw_workers_glow(self, glow: np.ndarray, state: SimViewState) -> None:
        for w in state.workers:
            pos_px = self._world_to_glow_px(w.position)
            color = ZONE_LEVEL_GLOW_COLOR.get(w.zone_level, (255, 255, 255))
            radius = max(int(6 * GLOW_SCALE), 4)

            # A minimal glowing "figure" outline: head circle + body line +
            # a pair of legs, rather than a filled dot, per the hologram
            # figure look.
            head_px = (pos_px[0], pos_px[1] - radius * 3)
            body_top = (head_px[0], head_px[1] + radius)
            cv2.circle(glow, head_px, radius, color, 2)
            cv2.line(glow, body_top, pos_px, color, 2)
            leg_spread = radius
            cv2.line(glow, pos_px, (pos_px[0] - leg_spread, pos_px[1] + radius * 2), color, 2)
            cv2.line(glow, pos_px, (pos_px[0] + leg_spread, pos_px[1] + radius * 2), color, 2)

            if w.position_confidence == "LOW":
                cv2.circle(glow, pos_px, radius * 2 + 6, color, 1)

    def _render_glow_layer(self, state: SimViewState) -> np.ndarray:
        glow = np.zeros((self._glow_size[1], self._glow_size[0], 3), dtype=np.uint8)

        self._draw_grid_glow(glow)

        state_color = STATE_GLOW_COLOR.get(state.risk_state, (255, 255, 255))
        if state.risk_state == "CRITICAL":
            pulse = _pulse()
            state_color = tuple(int(c * (0.4 + 0.6 * pulse)) for c in state_color)

        self._draw_ellipse_glow(glow, state.zone_center, state.zone_orientation_deg,
                                 state.zone_caution_semi_major_m, state.zone_caution_semi_minor_m,
                                 state_color, 2)
        self._draw_ellipse_glow(glow, state.zone_center, state.zone_orientation_deg,
                                 state.zone_danger_semi_major_m, state.zone_danger_semi_minor_m,
                                 state_color, 3)

        self._draw_machine_glow(glow, state)
        self._draw_workers_glow(glow, state)

        # Glow = blurred halo (soft, wide) + the sharp original lines added
        # back on top (crisp core), a standard cheap "neon glow" technique.
        blurred = cv2.GaussianBlur(glow, (self._blur_ksize, self._blur_ksize), 0)
        combined = cv2.add(blurred, glow)
        upscaled = cv2.resize(combined, (WINDOW_W, WINDOW_H), interpolation=cv2.INTER_LINEAR)
        return upscaled

    def _draw_worker_labels(self, canvas: np.ndarray, state: SimViewState) -> None:
        ox, oy = self._plot_origin_px
        for w in state.workers:
            px = int(ox + w.position[0] * PLOT_SCALE_PX_PER_M)
            py = int(oy - w.position[1] * PLOT_SCALE_PX_PER_M)
            label = f"[{w.zone_level}] {w.position_confidence}"
            cv2.putText(canvas, label, (px + 10, py - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COLOR_TEXT, 1)

    def _draw_banner(self, canvas: np.ndarray, state: SimViewState) -> None:
        color = STATE_GLOW_COLOR.get(state.risk_state, COLOR_TEXT)
        cv2.rectangle(canvas, (0, 0), (WINDOW_W, BANNER_H), (10, 10, 15), -1)
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

        cv2.rectangle(canvas, (0, 0), (WINDOW_W, BANNER_H), (150, 90, 0), 1)

    def _draw_right_panel(self, canvas: np.ndarray, state: SimViewState) -> None:
        x0, y0 = MAIN_X1, BANNER_H
        x1, y1 = WINDOW_W, MAIN_Y1
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (12, 8, 8), -1)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (150, 90, 0), 1)

        y = y0 + 30
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
            color = (0, 0, 255) if "LOST" in line else COLOR_TEXT
            cv2.putText(canvas, line, (x0 + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += 26

        if state.summary is not None:
            y += 10
            cv2.line(canvas, (x0 + 10, y), (x1 - 10, y), (150, 90, 0), 1)
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

    def _draw_webcam_inset(self, canvas: np.ndarray, state: SimViewState, show_webcam_inset: bool) -> None:
        if not show_webcam_inset or state.webcam_frame is None:
            return
        x0 = MAIN_X0 + 10
        y0 = MAIN_Y1 - INSET_H - 10
        resized = cv2.resize(state.webcam_frame, (INSET_W, INSET_H))
        canvas[y0:y0 + INSET_H, x0:x0 + INSET_W] = resized
        cv2.rectangle(canvas, (x0, y0), (x0 + INSET_W, y0 + INSET_H), (150, 90, 0), 2)
        cv2.putText(canvas, "LIVE CAMERA", (x0 + 8, y0 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)

    def _draw_bottom_strip(self, canvas: np.ndarray, state: SimViewState) -> None:
        y0 = WINDOW_H - BOTTOM_STRIP_H
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, WINDOW_H), (10, 10, 15), -1)
        cv2.rectangle(canvas, (0, y0), (WINDOW_W, WINDOW_H), (150, 90, 0), 1)

        cv2.putText(canvas, "Recent transitions:", (10, y0 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)

        recent = state.recent_transitions[-5:]
        for i, t in enumerate(recent):
            ttc_str = f"{t.ttc_s:.1f}s" if t.ttc_s is not None else "--"
            time_str = time.strftime("%H:%M:%S", time.localtime(t.timestamp))
            line = f"{time_str}  {t.from_state:>8s} -> {t.to_state:<8s}  ttc={ttc_str}"
            color = STATE_GLOW_COLOR.get(t.to_state, COLOR_TEXT)
            cv2.putText(canvas, line, (10, y0 + 38 + i * 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    def render(self, state: SimViewState, show_webcam_inset: bool = True) -> np.ndarray:
        """Compose one full hologram-mode frame from `state`. Pure drawing
        -- no decisions are made about what any value means."""
        canvas = np.full((WINDOW_H, WINDOW_W, 3), COLOR_BG, dtype=np.uint8)

        glow_layer = self._render_glow_layer(state)
        main_mask = np.zeros((WINDOW_H, WINDOW_W), dtype=np.uint8)
        cv2.rectangle(main_mask, (MAIN_X0, MAIN_Y0), (MAIN_X1, MAIN_Y1), 255, -1)
        canvas = cv2.add(canvas, cv2.bitwise_and(glow_layer, glow_layer, mask=main_mask))

        self._draw_scan_lines(canvas)
        self._draw_worker_labels(canvas, state)

        cv2.rectangle(canvas, (MAIN_X0, MAIN_Y0), (MAIN_X1, MAIN_Y1), (150, 90, 0), 1)

        self._draw_banner(canvas, state)
        self._draw_right_panel(canvas, state)
        self._draw_webcam_inset(canvas, state, show_webcam_inset)
        self._draw_bottom_strip(canvas, state)

        return canvas
