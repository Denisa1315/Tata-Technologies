/**
 * SMART-ZONE EDGE GUARDIAN
 * Core Data Structures and Interfaces
 */

export type ZoneLevel = 'OUTSIDE' | 'CAUTION' | 'DANGER';

export type MachineRiskState = 'SAFE' | 'WARNING' | 'CRITICAL' | 'DEGRADED';

export type CameraStatus = 'ONLINE' | 'BLOCKED' | 'DISCONNECTED';

export type VisibilityMode = 'GOOD' | 'PARTIAL' | 'POOR';

export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW';

export type ThemeMode = 'dark' | 'light';

export interface WorkerData {
  id: string;
  name: string;
  role: string;
  x: number; // meters from machine pivot (positive = right, negative = left)
  y: number; // meters from machine pivot (positive = forward, negative = rear)
  machineDistance: number; // meters to machine pivot center
  cameraDistance: number; // meters to cabin camera sensor
  confidence: number; // 0 - 100 percentage
  confidenceLevel: ConfidenceLevel;
  zone: ZoneLevel;
  isOccluded?: boolean;
  conservativeApplied?: boolean;
  color?: string;
}

export interface ExcavatorKinematics {
  swingAngle: number; // degrees, 0 = forward, negative = left, positive = right
  swingSpeed: number; // degrees per second (0 to 60)
  targetSpeed: number; // user requested speed
  isSwinging: boolean;
  swingDirection: 'LEFT' | 'RIGHT' | 'STOPPED';
  autoOscillate: boolean;
  minAngle: number;
  maxAngle: number;
  boomReach: number; // meters (~5.4m)
  counterweightRadius: number; // meters (~1.8m)
}

export interface DynamicZones {
  baseDangerRadius: number;
  baseCautionRadius: number;
  effectiveDangerRadius: number;
  effectiveCautionRadius: number;
  swingLeadAngle: number; // degrees lead in swing direction
  speedExpansionFactor: number; // 0 to 1
  hazardArcStart: number;
  hazardArcEnd: number;
}

export interface PerceptionSystem {
  cameraStatus: CameraStatus;
  visibility: VisibilityMode;
  fps: number;
  fpsThreshold: number;
  decisionLatencyMs: number;
  cameraPos: { x: number; y: number }; // relative to pivot, e.g. cabin front-left
  cameraFovDeg: number;
}

export interface SafetyDecision {
  overallState: MachineRiskState;
  action: 'MONITOR' | 'ALERT' | 'STOP';
  highestRiskWorkerId: string | null;
  highestRiskLevel: ZoneLevel;
  isStopIssued: boolean;
  stopReason: string | null;
  debounceActive: boolean;
  debounceRemainingMs: number;
  whyBreakdown: {
    workerId: string;
    machineDistance: number;
    dangerThreshold: number;
    cautionThreshold: number;
    swingSpeedContribution: number;
    confidence: number;
    confidenceLevel: ConfidenceLevel;
    conservativeSafetyBuffer: number;
    evalResult: string;
    ruleCode: string;
  } | null;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  timeMs: number;
  workerId?: string;
  workerName?: string;
  event: string;
  machineState: MachineRiskState;
  action: string;
  type: 'CAUTION' | 'DANGER' | 'STOP' | 'RESUME' | 'FAULT' | 'RECOVERY';
  details?: string;
}

export interface IncidentStats {
  cautionEvents: number;
  dangerEvents: number;
  stopCommands: number;
  timeInDangerSec: number;
  cameraFaults: number;
  workersDetected: number;
  avgDecisionLatencyMs: number;
}

export interface DemoStep {
  id: number;
  title: string;
  description: string;
  durationMs: number;
  narrative: string;
  actionSummary: string;
  applyState: () => void;
}
