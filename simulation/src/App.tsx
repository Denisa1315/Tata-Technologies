/**
 * SMART-ZONE EDGE GUARDIAN
 * Swing-Aware, Fail-Safe Risk Zone for Excavator Operator Safety
 * Main Application Orchestrator & Edge Simulation Loop
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  WorkerData,
  ExcavatorKinematics,
  PerceptionSystem,
  SafetyDecision,
  DynamicZones,
  AuditLogEntry,
  IncidentStats,
  DemoStep,
} from './types';
import { calculateDynamicZones } from './core/zoneEngine';
import { evaluateSystemRisk, DEBOUNCE_DURATION_MS } from './core/riskEngine';
import { soundSystem } from './core/audio';
import { Header } from './components/Header';
import { StateBanner } from './components/StateBanner';
import { DigitalTwin } from './components/DigitalTwin';
import { MachineControls } from './components/MachineControls';
import { PerceptionControls } from './components/PerceptionControls';
import { LiveTelemetry } from './components/LiveTelemetry';
import { AuditLog } from './components/AuditLog';
import { ExplainDecisionModal } from './components/ExplainDecisionModal';
import { IncidentSummaryModal } from './components/IncidentSummaryModal';
import { GuidedDemoBar } from './components/GuidedDemoBar';
import { Sliders, Activity, Camera, Layers } from 'lucide-react';

const INITIAL_WORKERS: WorkerData[] = [
  {
    id: 'W-01',
    name: 'Worker 01',
    role: 'Rigger / Spotter',
    x: 4.6,
    y: 1.8,
    machineDistance: 4.94,
    cameraDistance: 5.4,
    confidence: 94,
    confidenceLevel: 'HIGH',
    zone: 'OUTSIDE',
  },
  {
    id: 'W-02',
    name: 'Worker 02',
    role: 'Grade Checker',
    x: -3.8,
    y: 3.5,
    machineDistance: 5.17,
    cameraDistance: 4.2,
    confidence: 91,
    confidenceLevel: 'HIGH',
    zone: 'OUTSIDE',
  },
  {
    id: 'W-03',
    name: 'Worker 03',
    role: 'Survey Assistant',
    x: 1.5,
    y: 5.8,
    machineDistance: 5.99,
    cameraDistance: 6.2,
    confidence: 88,
    confidenceLevel: 'HIGH',
    zone: 'OUTSIDE',
  },
];

const INITIAL_MACHINE: ExcavatorKinematics = {
  swingAngle: 18,
  swingSpeed: 20,
  targetSpeed: 20,
  isSwinging: true,
  swingDirection: 'RIGHT',
  autoOscillate: true,
  minAngle: -60,
  maxAngle: 60,
  boomReach: 5.4,
  counterweightRadius: 1.8,
};

const INITIAL_PERCEPTION: PerceptionSystem = {
  cameraStatus: 'ONLINE',
  visibility: 'GOOD',
  fps: 30,
  fpsThreshold: 15,
  decisionLatencyMs: 19,
  cameraPos: { x: -0.9, y: 1.2 },
  cameraFovDeg: 110,
};

export default function App() {
  // 1. Core State
  const [machine, setMachine] = useState<ExcavatorKinematics>(INITIAL_MACHINE);
  const [workers, setWorkers] = useState<WorkerData[]>(INITIAL_WORKERS);
  const [perception, setPerception] = useState<PerceptionSystem>(INITIAL_PERCEPTION);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [isPresentationMode, setIsPresentationMode] = useState<boolean>(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [isLogDrawerOpen, setIsLogDrawerOpen] = useState<boolean>(false);
  const [isExplainOpen, setIsExplainOpen] = useState<boolean>(false);
  const [isSummaryOpen, setIsSummaryOpen] = useState<boolean>(false);
  const [activeRightTab, setActiveRightTab] = useState<'TELEMETRY' | 'MACHINE' | 'PERCEPTION'>('TELEMETRY');

  // Logs and Stats
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([
    {
      id: 'init-1',
      timestamp: new Date().toLocaleTimeString('en-GB'),
      timeMs: Date.now(),
      event: 'Edge Guardian Safety System Boot Sequence Completed',
      machineState: 'SAFE',
      action: 'MONITOR',
      type: 'RESUME',
    },
  ]);

  const [incidentStats, setIncidentStats] = useState<IncidentStats>({
    cautionEvents: 0,
    dangerEvents: 0,
    stopCommands: 0,
    timeInDangerSec: 0,
    cameraFaults: 0,
    workersDetected: 3,
    avgDecisionLatencyMs: 19,
  });

  // Dynamic Zones computation
  const dynamicZones = calculateDynamicZones(machine);

  // Safety Decision State
  const [safetyDecision, setSafetyDecision] = useState<SafetyDecision>({
    overallState: 'SAFE',
    action: 'MONITOR',
    highestRiskWorkerId: null,
    highestRiskLevel: 'OUTSIDE',
    isStopIssued: false,
    stopReason: null,
    debounceActive: false,
    debounceRemainingMs: 0,
    whyBreakdown: null,
  });

  // Guided Demo Orchestration State
  const [demoState, setDemoState] = useState<{
    isRunning: boolean;
    stepIndex: number;
    stepElapsedMs: number;
    stepDurationMs: number;
  }>({
    isRunning: false,
    stepIndex: 0,
    stepElapsedMs: 0,
    stepDurationMs: 4000,
  });

  // References for continuous loop
  const machineRef = useRef(machine);
  machineRef.current = machine;
  const workersRef = useRef(workers);
  workersRef.current = workers;
  const perceptionRef = useRef(perception);
  perceptionRef.current = perception;
  const decisionRef = useRef(safetyDecision);
  decisionRef.current = safetyDecision;
  const lastTimeRef = useRef<number>(performance.now());
  const demoStateRef = useRef(demoState);
  demoStateRef.current = demoState;

  // Helper to add audit log entries
  const addAuditLog = useCallback(
    (
      event: string,
      state: SafetyDecision['overallState'],
      action: string,
      type: AuditLogEntry['type'],
      workerId?: string,
      workerName?: string
    ) => {
      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0').slice(0, 2);
      const newEntry: AuditLogEntry = {
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
        timestamp: timeStr,
        timeMs: Date.now(),
        event,
        machineState: state,
        action,
        type,
        workerId,
        workerName,
      };

      setAuditLogs((prev) => [newEntry, ...prev.slice(0, 49)]);
    },
    []
  );

  // 16-Step Guided Demo Storyline
  const demoSteps: {
    title: string;
    description: string;
    durationMs: number;
    setup: () => void;
  }[] = [
    {
      title: 'Baseline State: SAFE',
      description: 'Machine stationary; workers maintain safe clearance outside the caution perimeter.',
      durationMs: 3800,
      setup: () => {
        setMachine((m) => ({ ...m, swingSpeed: 0, isSwinging: false, swingAngle: 0 }));
        setWorkers([
          { ...INITIAL_WORKERS[0], x: 5.8, y: 3.5 },
          { ...INITIAL_WORKERS[1], x: -5.2, y: 4.2 },
          { ...INITIAL_WORKERS[2], x: 2.2, y: 7.2 },
        ]);
        setPerception((p) => ({ ...p, cameraStatus: 'ONLINE', fps: 30, visibility: 'GOOD' }));
      },
    },
    {
      title: 'Worker Ingress: Approaching Machine',
      description: 'Worker 01 walks toward the excavator swing radius.',
      durationMs: 3500,
      setup: () => {
        setWorkers((ws) =>
          ws.map((w) => (w.id === 'W-01' ? { ...w, x: 4.4, y: 2.4 } : w))
        );
      },
    },
    {
      title: 'Caution Perimeter Penetration: Early Warning',
      description: 'Worker 01 crosses into the dynamic CAUTION boundary. Amber visual alert emitted; machine motion still authorized.',
      durationMs: 4000,
      setup: () => {
        setWorkers((ws) =>
          ws.map((w) => (w.id === 'W-01' ? { ...w, x: 3.6, y: 1.8 } : w))
        );
      },
    },
    {
      title: 'Machine Slew Begins: Dynamic Expansion',
      description: 'Operator initiates clockwise swing at 26°/s. Watch the safety zone expand and shift into the direction of motion.',
      durationMs: 4000,
      setup: () => {
        setMachine((m) => ({ ...m, isSwinging: true, swingSpeed: 28, targetSpeed: 28, swingDirection: 'RIGHT' }));
      },
    },
    {
      title: 'Dynamic Zone Sweeps Hazard Envelope',
      description: 'Because the swing-aware zone expands forward with velocity, the danger zone reaches Worker 01 before physical contact.',
      durationMs: 3600,
      setup: () => {
        setWorkers((ws) =>
          ws.map((w) => (w.id === 'W-01' ? { ...w, x: 3.2, y: 1.5 } : w))
        );
      },
    },
    {
      title: 'DANGER Zone Penetrated: STOP ISSUED',
      description: 'Critical threshold crossed! Deterministic edge engine commands immediate emergency hydraulic stop.',
      durationMs: 4200,
      setup: () => {
        setWorkers((ws) =>
          ws.map((w) => (w.id === 'W-01' ? { ...w, x: 2.2, y: 1.2 } : w))
        );
      },
    },
    {
      title: 'Worker Retreats from Danger Zone',
      description: 'Worker 01 steps back out of the danger radius into the caution band.',
      durationMs: 3600,
      setup: () => {
        setWorkers((ws) =>
          ws.map((w) => (w.id === 'W-01' ? { ...w, x: 3.8, y: 2.2 } : w))
        );
      },
    },
    {
      title: 'Debounce & Hysteresis Hold',
      description: 'System holds STOP command during 1.4s stabilization debounce to prevent hazardous chattering.',
      durationMs: 3200,
      setup: () => {
        // Debounce will countdown automatically
      },
    },
    {
      title: 'Debounce Cleared: Motion Resumes',
      description: 'Perimeter verified safe; emergency interlock releases and excavator resumes authorized swing.',
      durationMs: 3800,
      setup: () => {
        setWorkers((ws) =>
          ws.map((w) => (w.id === 'W-01' ? { ...w, x: 5.5, y: 3.8 } : w))
        );
      },
    },
    {
      title: 'Simulated Camera Fault: Optical Blockage',
      description: 'Camera lens obstructed or disconnected. System fails safe: perception loss forces DEGRADED STOP.',
      durationMs: 4500,
      setup: () => {
        setPerception((p) => ({ ...p, cameraStatus: 'BLOCKED' }));
      },
    },
    {
      title: 'Perception Restored: System Recovers',
      description: 'Optical feed re-established. Inference nominal; machine clears fail-safe condition.',
      durationMs: 3800,
      setup: () => {
        setPerception((p) => ({ ...p, cameraStatus: 'ONLINE' }));
      },
    },
    {
      title: 'Low Inference Rate (5 FPS) Fail-Safe',
      description: 'Simulating edge hardware throttle (5 FPS < 15 FPS threshold). Machine halts in safe state.',
      durationMs: 4000,
      setup: () => {
        setPerception((p) => ({ ...p, fps: 5 }));
      },
    },
    {
      title: 'Frame Rate Restored: 30 FPS Nominal',
      description: 'High-speed edge inference re-synchronized; nominal operation restored.',
      durationMs: 3600,
      setup: () => {
        setPerception((p) => ({ ...p, fps: 30 }));
      },
    },
    {
      title: 'Multi-Worker Complex Scenario',
      description: 'Multiple workers simultaneously on site. The highest-risk worker deterministically governs machine state.',
      durationMs: 4200,
      setup: () => {
        setWorkers([
          { ...INITIAL_WORKERS[0], x: 2.4, y: 1.4 }, // DANGER
          { ...INITIAL_WORKERS[1], x: -3.4, y: 2.8 }, // CAUTION
          { ...INITIAL_WORKERS[2], x: 4.8, y: 6.2 }, // OUTSIDE
        ]);
      },
    },
    {
      title: 'Clearance & Safe Return',
      description: 'All crew members step back outside caution perimeter. System confirms SAFE state.',
      durationMs: 4000,
      setup: () => {
        setWorkers([
          { ...INITIAL_WORKERS[0], x: 5.8, y: 2.5 },
          { ...INITIAL_WORKERS[1], x: -5.4, y: 3.5 },
          { ...INITIAL_WORKERS[2], x: 2.5, y: 7.0 },
        ]);
      },
    },
    {
      title: 'Demo Complete: Summary Metrics',
      description: 'All safety invariants verified. Edge Guardian closed-loop protection demonstrated.',
      durationMs: 4000,
      setup: () => {
        setIsSummaryOpen(true);
      },
    },
  ];

  // Apply scenario presets
  const handleApplyPreset = (presetName: string) => {
    if (presetName === 'FAR') {
      setWorkers([
        { ...INITIAL_WORKERS[0], x: 6.2, y: 2.8 },
        { ...INITIAL_WORKERS[1], x: -5.8, y: 3.6 },
        { ...INITIAL_WORKERS[2], x: 2.0, y: 7.2 },
      ]);
    } else if (presetName === 'APPROACH') {
      setWorkers((ws) =>
        ws.map((w) => (w.id === 'W-01' ? { ...w, x: 4.5, y: 2.2 } : w))
      );
    } else if (presetName === 'CAUTION') {
      setWorkers((ws) =>
        ws.map((w) => (w.id === 'W-01' ? { ...w, x: 3.5, y: 1.6 } : w))
      );
    } else if (presetName === 'DANGER') {
      setWorkers((ws) =>
        ws.map((w) => (w.id === 'W-01' ? { ...w, x: 2.1, y: 1.1 } : w))
      );
    } else if (presetName === 'MULTI') {
      setWorkers([
        { ...INITIAL_WORKERS[0], x: 2.2, y: 1.2 }, // DANGER
        { ...INITIAL_WORKERS[1], x: -3.5, y: 2.6 }, // CAUTION
        { ...INITIAL_WORKERS[2], x: 5.6, y: 5.8 }, // OUTSIDE
      ]);
    }
  };

  const handleSelectScenario = (scenarioId: number) => {
    // Stop guided demo if running
    setDemoState((d) => ({ ...d, isRunning: false }));

    if (scenarioId === 1) {
      // Safe
      demoSteps[0].setup();
    } else if (scenarioId === 2) {
      // Approach
      demoSteps[1].setup();
    } else if (scenarioId === 3) {
      // Caution
      demoSteps[2].setup();
    } else if (scenarioId === 4) {
      // Danger Stop
      demoSteps[5].setup();
    } else if (scenarioId === 5) {
      // Multi-worker
      demoSteps[13].setup();
    } else if (scenarioId === 6) {
      // Camera failure
      demoSteps[9].setup();
    }
  };

  // Start 60-Second Guided Demo
  const handleStartGuidedDemo = () => {
    setDemoState({
      isRunning: true,
      stepIndex: 0,
      stepElapsedMs: 0,
      stepDurationMs: demoSteps[0].durationMs,
    });
    demoSteps[0].setup();
    addAuditLog('60-Second Guided Demonstration Initiated', 'SAFE', 'START_DEMO', 'RESUME');
  };

  const handlePauseGuidedDemo = () => {
    setDemoState((prev) => ({ ...prev, isRunning: false }));
  };

  const handleResumeGuidedDemo = () => {
    setDemoState((prev) => ({ ...prev, isRunning: true }));
  };

  const handleResetGuidedDemo = () => {
    setDemoState({
      isRunning: false,
      stepIndex: 0,
      stepElapsedMs: 0,
      stepDurationMs: demoSteps[0].durationMs,
    });
    demoSteps[0].setup();
  };

  const handleSkipDemoStep = () => {
    const nextIdx = (demoState.stepIndex + 1) % demoSteps.length;
    setDemoState({
      isRunning: true,
      stepIndex: nextIdx,
      stepElapsedMs: 0,
      stepDurationMs: demoSteps[nextIdx].durationMs,
    });
    demoSteps[nextIdx].setup();
  };

  // Main 60 FPS deterministic simulation tick loop
  useEffect(() => {
    let animId: number;

    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - lastTimeRef.current) / 1000); // delta time in seconds
      lastTimeRef.current = now;
      const dtMs = dt * 1000;

      const currentMachine = machineRef.current;
      const currentWorkers = workersRef.current;
      const currentPerception = perceptionRef.current;
      const previousDecision = decisionRef.current;

      // 1. Excavator Kinematic Slew Update
      let nextSwingAngle = currentMachine.swingAngle;
      let nextDirection = currentMachine.swingDirection;

      if (currentMachine.isSwinging && !previousDecision.isStopIssued) {
        const speed = currentMachine.swingSpeed;
        const deltaAngle = speed * dt;

        if (currentMachine.swingDirection === 'RIGHT') {
          nextSwingAngle += deltaAngle;
          if (currentMachine.autoOscillate && nextSwingAngle >= currentMachine.maxAngle) {
            nextSwingAngle = currentMachine.maxAngle;
            nextDirection = 'LEFT';
          }
        } else if (currentMachine.swingDirection === 'LEFT') {
          nextSwingAngle -= deltaAngle;
          if (currentMachine.autoOscillate && nextSwingAngle <= currentMachine.minAngle) {
            nextSwingAngle = currentMachine.minAngle;
            nextDirection = 'RIGHT';
          }
        }

        // Clamp or normalize angle
        if (nextSwingAngle > 90) nextSwingAngle = 90;
        if (nextSwingAngle < -90) nextSwingAngle = -90;

        if (nextSwingAngle !== currentMachine.swingAngle || nextDirection !== currentMachine.swingDirection) {
          setMachine((m) => ({
            ...m,
            swingAngle: Number(nextSwingAngle.toFixed(2)),
            swingDirection: nextDirection,
          }));
        }
      }

      // 2. Deterministic Risk Engine Evaluation
      const { decision: newDecision, evaluatedWorkers } = evaluateSystemRisk(
        currentWorkers,
        {
          ...currentMachine,
          swingAngle: nextSwingAngle,
          swingDirection: nextDirection,
        },
        currentPerception,
        previousDecision,
        dtMs
      );

      // 3. Audio & State Transition Triggers
      const prevState = previousDecision.overallState;
      const nextState = newDecision.overallState;

      if (prevState !== nextState) {
        if (nextState === 'CRITICAL') {
          soundSystem.playCritical();
          setIncidentStats((s) => ({
            ...s,
            dangerEvents: s.dangerEvents + 1,
            stopCommands: s.stopCommands + 1,
          }));
          addAuditLog(
            `CRITICAL → STOP ISSUED (${newDecision.stopReason || ''})`,
            'CRITICAL',
            'STOP',
            'STOP',
            newDecision.highestRiskWorkerId || undefined
          );
        } else if (nextState === 'WARNING') {
          soundSystem.playWarning();
          setIncidentStats((s) => ({
            ...s,
            cautionEvents: s.cautionEvents + 1,
          }));
          addAuditLog(
            `Worker entered CAUTION zone`,
            'WARNING',
            'ALERT',
            'CAUTION',
            newDecision.highestRiskWorkerId || undefined
          );
        } else if (nextState === 'DEGRADED') {
          soundSystem.playDegraded();
          setIncidentStats((s) => ({
            ...s,
            cameraFaults: s.cameraFaults + 1,
            stopCommands: s.stopCommands + 1,
          }));
          addAuditLog(
            `CAMERA FAULT → DEGRADED (Fail-Safe Stop Active)`,
            'DEGRADED',
            'STOP',
            'FAULT'
          );
        } else if (nextState === 'SAFE' && prevState !== 'SAFE') {
          soundSystem.playResume();
          addAuditLog(
            `Perimeter Cleared → SAFE (Motion Authorized)`,
            'SAFE',
            'MONITOR',
            'RESUME'
          );
        }
      }

      // 4. Update Time in Danger stat if active
      if (newDecision.overallState === 'CRITICAL') {
        setIncidentStats((s) => ({
          ...s,
          timeInDangerSec: s.timeInDangerSec + dt,
        }));
      }

      // 5. Update Safety Decision & Evaluated Workers
      setSafetyDecision(newDecision);
      setWorkers(evaluatedWorkers);

      // 6. Guided Demo Step Progress Timer
      const currentDemo = demoStateRef.current;
      if (currentDemo.isRunning) {
        const nextElapsed = currentDemo.stepElapsedMs + dtMs;
        if (nextElapsed >= currentDemo.stepDurationMs) {
          // Advance to next step
          const nextIndex = currentDemo.stepIndex + 1;
          if (nextIndex < demoSteps.length) {
            setDemoState({
              isRunning: true,
              stepIndex: nextIndex,
              stepElapsedMs: 0,
              stepDurationMs: demoSteps[nextIndex].durationMs,
            });
            demoSteps[nextIndex].setup();
          } else {
            // Completed
            setDemoState((d) => ({ ...d, isRunning: false }));
          }
        } else {
          setDemoState((d) => ({ ...d, stepElapsedMs: nextElapsed }));
        }
      }

      animId = requestAnimationFrame(tick);
    };

    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [addAuditLog]);

  // Handle worker position update from pointer drag
  const handleUpdateWorkerPosition = (workerId: string, x: number, y: number) => {
    setWorkers((ws) =>
      ws.map((w) => (w.id === workerId ? { ...w, x, y } : w))
    );
  };

  // Toggle Mute
  const handleToggleMute = () => {
    const nextMuted = soundSystem.toggleMute();
    setIsMuted(nextMuted);
  };

  const currentStep = demoSteps[demoState.stepIndex] || demoSteps[0];
  const progressPercent = Math.min(
    100,
    (demoState.stepElapsedMs / demoState.stepDurationMs) * 100
  );

  const isLight = theme === 'light';

  // Calculate closest detected worker for immediate glanceable readout
  const closestWorker = workers.length > 0
    ? workers.reduce((prev, curr) => (prev.machineDistance < curr.machineDistance ? prev : curr))
    : null;

  return (
    <div className={`flex flex-col h-screen w-screen overflow-hidden font-sans transition-colors duration-200 ${
      isLight ? 'bg-stone-200 text-stone-900' : 'bg-[#07080b] text-neutral-100'
    }`}>
      {/* 1. Top Master In-Cab Cockpit Header */}
      <Header
        cameraStatus={perception.cameraStatus}
        machineState={safetyDecision.overallState}
        isStopIssued={safetyDecision.isStopIssued}
        nearestWorkerDistance={closestWorker ? closestWorker.machineDistance : null}
        slewSpeed={machine.swingSpeed}
        isMuted={isMuted}
        isPresentationMode={isPresentationMode}
        isSidebarOpen={isSidebarOpen}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        onToggleMute={handleToggleMute}
        onTogglePresentation={() => setIsPresentationMode(!isPresentationMode)}
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        onOpenSummary={() => setIsSummaryOpen(true)}
        onOpenExplain={() => setIsExplainOpen(true)}
      />

      {/* 2. Top Slim In-Cab Safety Status Alert Ribbon */}
      <StateBanner decision={safetyDecision} perception={perception} theme={theme} />

      {/* 3. Main Central Simulation Viewport */}
      <main className="flex-1 flex flex-col md:flex-row min-h-0 overflow-hidden relative">
        {/* Left / Center Digital Twin Canvas */}
        <div className="flex-1 h-full relative min-h-0">
          <DigitalTwin
            machine={machine}
            workers={workers}
            perception={perception}
            decision={safetyDecision}
            dynamicZones={dynamicZones}
            onUpdateWorkerPosition={handleUpdateWorkerPosition}
            onApplyPreset={handleApplyPreset}
            isPresentationMode={isPresentationMode}
            theme={theme}
          />

          {/* Presentation Mode Minimal Telemetry Badge */}
          {isPresentationMode && (
            <div className={`absolute top-3 right-3 p-3 rounded-lg backdrop-blur border font-mono text-xs space-y-1 shadow-lg pointer-events-none ${
              isLight ? 'bg-stone-100/95 border-stone-300 text-stone-900 shadow-stone-400/40' : 'bg-neutral-900/90 border-neutral-800 text-neutral-100'
            }`}>
              <div className={`font-bold ${isLight ? 'text-cyan-800' : 'text-cyan-400'}`}>DIGITAL TWIN · PRESENTATION</div>
              <div className={isLight ? 'text-stone-700' : 'text-neutral-300'}>
                Swing Speed: <strong className={isLight ? 'text-stone-950 font-bold' : 'text-white'}>{machine.swingSpeed}°/s</strong>
              </div>
              <div className={isLight ? 'text-stone-700' : 'text-neutral-300'}>
                Danger Radius: <strong className="text-rose-500 font-bold">{dynamicZones.effectiveDangerRadius.toFixed(2)}m</strong>
              </div>
              <div className={isLight ? 'text-stone-700' : 'text-neutral-300'}>
                Camera Health: <strong className={isLight ? 'text-stone-950 font-bold' : 'text-white'}>{perception.cameraStatus}</strong>
              </div>
              <div className={isLight ? 'text-stone-700' : 'text-neutral-300'}>
                Rate: <strong className={isLight ? 'text-cyan-800 font-bold' : 'text-cyan-300'}>{perception.fps} FPS</strong>
              </div>
            </div>
          )}
        </div>

        {/* Right Side Control Deck (Collapsible for maximum screen space) */}
        {!isPresentationMode && isSidebarOpen && (
          <aside className={`w-full md:w-80 lg:w-96 h-auto md:h-full border-l flex flex-col shrink-0 overflow-hidden transition-colors ${
            isLight ? 'bg-stone-100/95 border-stone-300 shadow-sm' : 'bg-neutral-950/95 border-neutral-800'
          }`}>
            {/* Control Tabs */}
            <div className={`grid grid-cols-3 border-b text-xs font-mono shrink-0 ${
              isLight ? 'border-stone-300 bg-stone-200/70' : 'border-neutral-800 bg-neutral-900/60'
            }`}>
              <button
                onClick={() => setActiveRightTab('TELEMETRY')}
                className={`py-2 px-1 text-center font-bold border-b-2 transition-colors flex items-center justify-center gap-1 cursor-pointer ${
                  activeRightTab === 'TELEMETRY'
                    ? isLight ? 'border-cyan-600 text-cyan-900 bg-stone-100' : 'border-cyan-500 text-cyan-300 bg-neutral-900'
                    : isLight ? 'border-transparent text-stone-600 hover:text-stone-950' : 'border-transparent text-neutral-400 hover:text-white'
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Telemetry</span>
              </button>
              <button
                onClick={() => setActiveRightTab('MACHINE')}
                className={`py-2 px-1 text-center font-bold border-b-2 transition-colors flex items-center justify-center gap-1 cursor-pointer ${
                  activeRightTab === 'MACHINE'
                    ? isLight ? 'border-cyan-600 text-cyan-900 bg-stone-100' : 'border-cyan-500 text-cyan-300 bg-neutral-900'
                    : isLight ? 'border-transparent text-stone-600 hover:text-stone-950' : 'border-transparent text-neutral-400 hover:text-white'
                }`}
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>Machine</span>
              </button>
              <button
                onClick={() => setActiveRightTab('PERCEPTION')}
                className={`py-2 px-1 text-center font-bold border-b-2 transition-colors flex items-center justify-center gap-1 cursor-pointer ${
                  activeRightTab === 'PERCEPTION'
                    ? isLight ? 'border-cyan-600 text-cyan-900 bg-stone-100' : 'border-cyan-500 text-cyan-300 bg-neutral-900'
                    : isLight ? 'border-transparent text-stone-600 hover:text-stone-950' : 'border-transparent text-neutral-400 hover:text-white'
                }`}
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Perception</span>
              </button>
            </div>

            {/* Tab Body */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {activeRightTab === 'TELEMETRY' && (
                <LiveTelemetry
                  machine={machine}
                  perception={perception}
                  decision={safetyDecision}
                  dynamicZones={dynamicZones}
                  workers={workers}
                  theme={theme}
                />
              )}

              {activeRightTab === 'MACHINE' && (
                <MachineControls
                  machine={machine}
                  onUpdateMachine={(partial) => setMachine((m) => ({ ...m, ...partial }))}
                  isStopIssued={safetyDecision.isStopIssued}
                  theme={theme}
                />
              )}

              {activeRightTab === 'PERCEPTION' && (
                <PerceptionControls
                  perception={perception}
                  onUpdatePerception={(partial) => setPerception((p) => ({ ...p, ...partial }))}
                  theme={theme}
                />
              )}
            </div>
          </aside>
        )}
      </main>

      {/* 4. Bottom Executive Guided Demo & Scenario Bar */}
      <GuidedDemoBar
        isRunning={demoState.isRunning}
        currentStepIndex={demoState.stepIndex}
        totalSteps={demoSteps.length}
        stepTitle={currentStep.title}
        stepDescription={currentStep.description}
        progressPercent={progressPercent}
        onStartDemo={handleStartGuidedDemo}
        onPauseDemo={handlePauseGuidedDemo}
        onResumeDemo={handleResumeGuidedDemo}
        onResetDemo={handleResetGuidedDemo}
        onSkipStep={handleSkipDemoStep}
        onSelectScenario={handleSelectScenario}
        theme={theme}
      />

      {/* 5. Bottom Incident Audit Log Tray (Collapsible drawer with live ticker) */}
      <AuditLog
        logs={auditLogs}
        onClearLogs={() => setAuditLogs([])}
        isOpen={isLogDrawerOpen}
        onToggleOpen={() => setIsLogDrawerOpen(!isLogDrawerOpen)}
        theme={theme}
      />

      {/* 6. Modals */}
      <ExplainDecisionModal
        isOpen={isExplainOpen}
        onClose={() => setIsExplainOpen(false)}
        decision={safetyDecision}
        machine={machine}
        workers={workers}
        theme={theme}
      />

      <IncidentSummaryModal
        isOpen={isSummaryOpen}
        onClose={() => setIsSummaryOpen(false)}
        stats={incidentStats}
        theme={theme}
      />
    </div>
  );
}
