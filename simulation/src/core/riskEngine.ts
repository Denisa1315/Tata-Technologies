/**
 * SMART-ZONE EDGE GUARDIAN
 * Deterministic Fail-Safe Risk Engine
 * Computes safety states, debounces de-escalations, and enforces fail-safe degradation.
 */

import {
  WorkerData,
  ExcavatorKinematics,
  PerceptionSystem,
  SafetyDecision,
  ZoneLevel,
  MachineRiskState,
  ConfidenceLevel,
} from '../types';
import { evaluatePointZone } from './zoneEngine';

export const LOW_CONFIDENCE_THRESHOLD = 65;
export const HIGH_CONFIDENCE_THRESHOLD = 85;
export const CONSERVATIVE_BUFFER_METERS = 0.85; // Extra buffer added when perception confidence is low
export const DEBOUNCE_DURATION_MS = 1400; // Delay before clearing STOP after hazard removal

/**
 * Calculates simulated perception confidence for a worker
 */
export function calculateWorkerConfidence(
  workerX: number,
  workerY: number,
  cameraPos: { x: number; y: number },
  visibility: 'GOOD' | 'PARTIAL' | 'POOR',
  isOccluded: boolean = false
): {
  cameraDistance: number;
  confidence: number;
  confidenceLevel: ConfidenceLevel;
} {
  const cameraDistance = Math.hypot(workerX - cameraPos.x, workerY - cameraPos.y);

  // Confidence decay curve based on camera distance (meters)
  // At 2m: ~95%, at 5m: ~85%, at 8m: ~65%
  let rawScore = 100 - cameraDistance * 4.2;

  // Visibility multiplier
  if (visibility === 'PARTIAL') {
    rawScore *= 0.80;
  } else if (visibility === 'POOR') {
    rawScore *= 0.54;
  }

  // Occlusion penalty
  if (isOccluded) {
    rawScore *= 0.65;
  }

  const confidence = Math.round(Math.min(99, Math.max(15, rawScore)));

  let confidenceLevel: ConfidenceLevel = 'HIGH';
  if (confidence < LOW_CONFIDENCE_THRESHOLD) {
    confidenceLevel = 'LOW';
  } else if (confidence < HIGH_CONFIDENCE_THRESHOLD) {
    confidenceLevel = 'MEDIUM';
  }

  return {
    cameraDistance,
    confidence,
    confidenceLevel,
  };
}

/**
 * Evaluates all workers against dynamic machine zones and camera status
 */
export function evaluateSystemRisk(
  workers: WorkerData[],
  machine: ExcavatorKinematics,
  perception: PerceptionSystem,
  previousDecision: SafetyDecision | null,
  deltaMs: number
): {
  decision: SafetyDecision;
  evaluatedWorkers: WorkerData[];
} {
  // 1. Fail-Safe Perception Health Check
  const isCameraHealthy = perception.cameraStatus === 'ONLINE';
  const isFpsAcceptable = perception.fps >= perception.fpsThreshold;

  if (!isCameraHealthy || !isFpsAcceptable) {
    let faultReason = 'Perception stream unavailable';
    if (perception.cameraStatus === 'BLOCKED') {
      faultReason = 'Optical path obstructed (Camera BLOCKED)';
    } else if (perception.cameraStatus === 'DISCONNECTED') {
      faultReason = 'Camera sensor DISCONNECTED';
    } else if (!isFpsAcceptable) {
      faultReason = `Inference rate degraded (${perception.fps} FPS < ${perception.fpsThreshold} FPS threshold)`;
    }

    const decision: SafetyDecision = {
      overallState: 'DEGRADED',
      action: 'STOP',
      highestRiskWorkerId: null,
      highestRiskLevel: 'OUTSIDE',
      isStopIssued: true,
      stopReason: `FAIL-SAFE STOP ACTIVE: ${faultReason}`,
      debounceActive: false,
      debounceRemainingMs: 0,
      whyBreakdown: {
        workerId: 'SYSTEM-WIDE',
        machineDistance: 0,
        dangerThreshold: 0,
        cautionThreshold: 0,
        swingSpeedContribution: machine.swingSpeed,
        confidence: 0,
        confidenceLevel: 'LOW',
        conservativeSafetyBuffer: 0,
        evalResult: 'FAIL-SAFE TRIPPED: Perception input compromised. Machine motion prohibited.',
        ruleCode: 'RULE-FS-01: PERCEPTION_UNAVAILABLE_EMERGENCY_STOP',
      },
    };

    return {
      decision,
      evaluatedWorkers: workers,
    };
  }

  // 2. Evaluate each worker deterministically
  const evaluatedWorkers: WorkerData[] = workers.map((w) => {
    const { cameraDistance, confidence, confidenceLevel } = calculateWorkerConfidence(
      w.x,
      w.y,
      perception.cameraPos,
      perception.visibility,
      w.isOccluded
    );

    // Apply conservative safety buffer if perception confidence is LOW
    const applyConservative = confidenceLevel === 'LOW';
    const safetyBuffer = applyConservative ? CONSERVATIVE_BUFFER_METERS : 0;

    const evalZone = evaluatePointZone(w.x, w.y, machine, safetyBuffer);

    return {
      ...w,
      machineDistance: Number(evalZone.distanceToMachine.toFixed(2)),
      cameraDistance: Number(cameraDistance.toFixed(2)),
      confidence,
      confidenceLevel,
      zone: evalZone.zone,
      conservativeApplied: applyConservative,
    };
  });

  // 3. Determine Highest Risk Level across all workers
  let rawHighestLevel: ZoneLevel = 'OUTSIDE';
  let highestWorker: WorkerData | null = null;

  for (const w of evaluatedWorkers) {
    if (w.zone === 'DANGER') {
      rawHighestLevel = 'DANGER';
      highestWorker = w;
      break; // Danger is top tier
    } else if (w.zone === 'CAUTION' && rawHighestLevel === 'OUTSIDE') {
      rawHighestLevel = 'CAUTION';
      highestWorker = w;
    }
  }

  if (!highestWorker && evaluatedWorkers.length > 0) {
    // Pick worker closest to machine as baseline reference
    highestWorker = [...evaluatedWorkers].sort((a, b) => a.machineDistance - b.machineDistance)[0];
  }

  // 4. Raw target state before debounce
  let rawTargetState: MachineRiskState = 'SAFE';
  let action: 'MONITOR' | 'ALERT' | 'STOP' = 'MONITOR';
  let stopReason: string | null = null;

  if (rawHighestLevel === 'DANGER') {
    rawTargetState = 'CRITICAL';
    action = 'STOP';
    stopReason = `Worker ${highestWorker?.name || ''} entered DANGER zone`;
  } else if (rawHighestLevel === 'CAUTION') {
    rawTargetState = 'WARNING';
    action = 'ALERT';
  } else {
    rawTargetState = 'SAFE';
    action = 'MONITOR';
  }

  // 5. Debounce / Hysteresis Management
  // Escalations (SAFE -> WARNING, WARNING -> CRITICAL) are IMMEDIATE
  // De-escalations (CRITICAL -> WARNING/SAFE) must endure debounce delay
  let overallState: MachineRiskState = rawTargetState;
  let isStopIssued = rawTargetState === 'CRITICAL';
  let debounceActive = false;
  let debounceRemainingMs = 0;

  const wasCriticalOrDegraded =
    previousDecision?.overallState === 'CRITICAL' ||
    previousDecision?.overallState === 'DEGRADED';

  if (rawTargetState === 'CRITICAL') {
    // Immediate escalation
    overallState = 'CRITICAL';
    isStopIssued = true;
    debounceActive = false;
    debounceRemainingMs = 0;
  } else if (wasCriticalOrDegraded) {
    // De-escalation attempt from CRITICAL: apply debounce
    const currentRemaining = previousDecision?.debounceRemainingMs ?? DEBOUNCE_DURATION_MS;
    const newRemaining = currentRemaining - deltaMs;

    if (newRemaining > 0) {
      // Still in debounce cooldown: retain STOP command for operator safety
      overallState = 'CRITICAL';
      isStopIssued = true;
      debounceActive = true;
      debounceRemainingMs = Math.max(0, newRemaining);
      stopReason = `Debounce stabilization (${(newRemaining / 1000).toFixed(1)}s remaining)`;
    } else {
      // Debounce expired: safe to transition down
      overallState = rawTargetState;
      isStopIssued = false;
      debounceActive = false;
      debounceRemainingMs = 0;
    }
  }

  // Build Explainable AI Breakdown for the highest risk worker
  let whyBreakdown = null;
  if (highestWorker) {
    const conservativeBuffer = highestWorker.conservativeApplied ? CONSERVATIVE_BUFFER_METERS : 0;
    const zoneEval = evaluatePointZone(highestWorker.x, highestWorker.y, machine, conservativeBuffer);

    let ruleCode = 'RULE-RZ-01: DIST_M > CAUTION_THRESHOLD => CLEAR';
    let evalText = 'Worker safely positioned outside dynamic safety envelope.';

    if (highestWorker.zone === 'DANGER') {
      ruleCode = 'RULE-RZ-03: DIST_M <= DANGER_THRESHOLD => IMMEDIATE CRITICAL STOP';
      evalText = `Worker inside dynamic danger boundary (${highestWorker.machineDistance}m <= ${zoneEval.dangerThresholdAtAngle.toFixed(2)}m). Machine swing halted immediately.`;
    } else if (highestWorker.zone === 'CAUTION') {
      ruleCode = 'RULE-RZ-02: DIST_M <= CAUTION_THRESHOLD => OPERATOR EARLY WARNING';
      evalText = `Worker encroaching caution perimeter (${highestWorker.machineDistance}m <= ${zoneEval.cautionThresholdAtAngle.toFixed(2)}m). Visual and audio pulse active; swing permitted.`;
    }

    if (highestWorker.conservativeApplied) {
      evalText += ` Note: Applied +${CONSERVATIVE_BUFFER_METERS}m conservative safety margin due to LOW perception confidence (${highestWorker.confidence}%).`;
    }

    whyBreakdown = {
      workerId: highestWorker.id,
      machineDistance: highestWorker.machineDistance,
      dangerThreshold: Number(zoneEval.dangerThresholdAtAngle.toFixed(2)),
      cautionThreshold: Number(zoneEval.cautionThresholdAtAngle.toFixed(2)),
      swingSpeedContribution: Number((machine.swingSpeed * 0.03).toFixed(2)),
      confidence: highestWorker.confidence,
      confidenceLevel: highestWorker.confidenceLevel,
      conservativeSafetyBuffer: conservativeBuffer,
      evalResult: evalText,
      ruleCode,
    };
  }

  const decision: SafetyDecision = {
    overallState,
    action: isStopIssued ? 'STOP' : action,
    highestRiskWorkerId: highestWorker ? highestWorker.id : null,
    highestRiskLevel: rawHighestLevel,
    isStopIssued,
    stopReason,
    debounceActive,
    debounceRemainingMs,
    whyBreakdown,
  };

  return {
    decision,
    evaluatedWorkers,
  };
}
