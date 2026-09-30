Project: Smart-Zone Edge Guardian — a predictive, fail-safe collision-awareness
system for excavators/heavy machinery, built for Tata Technologies InnoVent
Round 2. Python 3.10+.

Folder structure (create/extend exactly this, don't restructure it):
smart_zone/
├── perception/     detection.py, tracking.py
├── spatial/        calibration.py, homography.py
├── machine/        telemetry.py, mock_telemetry.py, kinematics.py
├── prediction/     kalman.py, ttc.py
├── safety/         zone.py, risk_engine.py
├── hardware/       outputs.py
├── logging/        event_logger.py
├── config/         calibration.yaml, thresholds.yaml
├── tests/
├── requirements.txt
└── app.py

Hard architectural constraints — do not deviate from these without asking me:
- Trajectory prediction is a constant-velocity Kalman filter (worker) + a
  kinematic model driven by real machine telemetry (machine). Do NOT use
  LSTM/Transformer/any trained deep model for prediction.
- The dynamic safety zone is a heading-and-speed-scaled ellipse oriented
  along the machine's current motion direction. Not a fixed circle, not a
  full swept-path polygon.
- The risk engine evaluates by ground-plane POSITION, never by tracker ID —
  an ID switch must never change system state.
- Risk states are SAFE / WARNING / CRITICAL / DEGRADED, with hysteresis:
  escalate immediately, de-escalate only after the triggering condition has
  cleared continuously for a debounce period (~1s).
- DEGRADED overrides every other state on any sensor/telemetry/compute fault
  (camera heartbeat lost, machine telemetry heartbeat lost, FPS below floor)
  and forces STOP regardless of the computed risk level.
- Essential packages only: opencv-python, ultralytics, numpy, filterpy (or a
  hand-rolled Kalman filter), pyserial, pandas. Do NOT install torch training
  pipelines, TensorRT, ROS/ROS2, or any LLM/agent framework in this phase —
  those are out of scope for the core pipeline.

The machine telemetry serial contract (already implemented, do not change
it) is: commands SPEED:<deg_per_sec> / STOP / RESUME / LED:<level> /
BUZZER:<ON|OFF> sent to the ESP32, and telemetry lines received at 20Hz in
the format "T,<millis>,<angle_deg>,<speed_deg_per_sec>,<state>".

At the end of each section below, run whatever you built and show me it
actually working (webcam window, printed values, or a simple plot) before
declaring the section done. Write unit tests for pure-math modules
(homography, Kalman, zone geometry, risk-engine transitions) as you go —
don't leave them for the end.



Project: Smart-Zone Edge Guardian (InnoVent Round 2, virtual POC). The core
pipeline is already built and tested: perception, spatial (homography),
machine (telemetry, mock_telemetry, kinematics), prediction (Kalman, TTC),
safety (zone, risk_engine), hardware/outputs.py, logging, and app.py.

Goal now: a software simulation mode so the whole system can be demoed with
no hardware. Real webcam, detection, tracking, homography, Kalman, zone, TTC
and risk engine keep running for real. Only the machine is simulated.

Rules:
- Do NOT change perception, prediction, zone, or risk engine logic.
- Keep the hardware path working. --mock-hardware and the real serial path
  must behave exactly as before.
- Run everything as python -m smart_zone.xxx from the parent directory
  (the logging/ folder shadows stdlib logging otherwise).
- No new dependencies beyond what is already in requirements.txt.
- Work on a branch called feature/sim-view.

After each section, run what you built and show me it working before
declaring it done.


Project: Smart-Zone Edge Guardian (InnoVent Round 2, virtual POC). The
pipeline already exists and passes its tests: perception, spatial
(homography), machine (telemetry, mock_telemetry, kinematics), prediction
(Kalman, TTC), safety (zone, risk_engine), hardware (outputs, sim_outputs),
dashboard/sim_view.py, logging, and app.py with --sim and --record.

Refinement goal: a swing-aware risk zone sized from stopping distance, a
graded per-worker zone status (outside, caution, danger), fail-safe
DEGRADED behavior, position-confidence handling, a CSV audit log, and a
hologram-style digital twin view. The decision does NOT use worker
prediction.

Rules:
- Do not delete existing code. Kalman, TTC and ghost/proximity ideas stay
  in the repo, switched off behind config flags.
- Keep internal state names SAFE, WARNING, CRITICAL, DEGRADED so existing
  tests and interfaces keep working. On screen and in logs, show them as
  SAFE, CAUTION, DANGER, DEGRADED.
- Do not change detection, tracking, or homography math.
- The risk engine decides by ground-plane position, never by track ID.
- sim_view stays display only and must not import decision logic (the
  existing AST test must still pass).
- No new dependencies. Run as python -m smart_zone.xxx from the parent
  directory.
- Keep the hardware path (--mock-hardware and real serial) working.
- After each section, run the full test suite and show me it working
  before declaring it done.