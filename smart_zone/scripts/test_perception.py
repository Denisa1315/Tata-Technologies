"""Live webcam smoke test for perception.detection + perception.tracking.

Run from the Tata-Technologies/ parent directory (not from inside smart_zone/,
to avoid smart_zone/logging/ shadowing the stdlib logging module):

    cd Tata-Technologies
    source smart_zone/.venv/bin/activate
    python -m smart_zone.scripts.test_perception

Draws bounding boxes + track IDs, marks trusted tracks green vs. unconfirmed
yellow, and prints live FPS to the console. Press 'q' to quit.
"""

from __future__ import annotations

import time

import cv2

from smart_zone.perception.tracking import PersonTracker

TRUSTED_COLOR = (0, 200, 0)      # green: trusted (>= persistence_frames)
UNCONFIRMED_COLOR = (0, 200, 255)  # yellow: seen, not yet trusted


def main() -> None:
    tracker = PersonTracker()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open default webcam (index 0).")

    prev_time = time.time()
    fps = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Frame grab failed, stopping.")
                break

            tracked = tracker.update(frame)

            now = time.time()
            dt = now - prev_time
            prev_time = now
            if dt > 0:
                fps = 1.0 / dt

            for t in tracked:
                x1, y1, x2, y2 = (int(v) for v in t.bbox_xyxy)
                color = TRUSTED_COLOR if t.is_trusted else UNCONFIRMED_COLOR
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"ID {t.track_id} ({t.consecutive_frames}) {t.confidence:.2f}"
                cv2.putText(
                    frame, label, (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
                )

            cv2.putText(
                frame, f"FPS: {fps:.1f}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
            )
            print(f"\rFPS: {fps:5.1f} | tracked: {len(tracked)}", end="", flush=True)

            cv2.imshow("Smart-Zone Edge Guardian - Perception Test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        print()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
