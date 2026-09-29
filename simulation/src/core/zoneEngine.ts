/**
 * SMART-ZONE EDGE GUARDIAN
 * Dynamic Risk Zone Engine
 * Computes swing-aware risk envelopes based on excavator angular velocity and direction.
 */

import { ExcavatorKinematics, DynamicZones, ZoneLevel } from '../types';

export const BASELINE_DANGER_RADIUS = 2.8; // meters
export const BASELINE_CAUTION_RADIUS = 4.8; // meters
export const MAX_SPEED_EXPANSION_DANGER = 1.8; // meters at 60 deg/sec
export const MAX_SPEED_EXPANSION_CAUTION = 2.4; // meters at 60 deg/sec
export const MAX_LEAD_ANGLE_DEG = 38; // degrees directional lead at 60 deg/sec

/**
 * Calculates current dynamic zones parameters based on machine kinematics
 */
export function calculateDynamicZones(machine: ExcavatorKinematics): DynamicZones {
  const speedRatio = Math.min(1, Math.max(0, machine.swingSpeed / 60));
  
  // Danger & Caution radial expansion
  const effectiveDangerRadius = BASELINE_DANGER_RADIUS + speedRatio * MAX_SPEED_EXPANSION_DANGER;
  const effectiveCautionRadius = BASELINE_CAUTION_RADIUS + speedRatio * MAX_SPEED_EXPANSION_CAUTION;
  
  // Directional angular lead
  let directionSign = 0;
  if (machine.isSwinging) {
    if (machine.swingDirection === 'RIGHT') directionSign = 1;
    else if (machine.swingDirection === 'LEFT') directionSign = -1;
  }
  
  const swingLeadAngle = directionSign * speedRatio * MAX_LEAD_ANGLE_DEG;
  
  // Hazard arc sector centered around arm angle + lead
  const centerAngle = machine.swingAngle + swingLeadAngle;
  // Span widens with speed
  const halfSpan = 65 + speedRatio * 35; // degrees on either side of active swing vector
  
  return {
    baseDangerRadius: BASELINE_DANGER_RADIUS,
    baseCautionRadius: BASELINE_CAUTION_RADIUS,
    effectiveDangerRadius,
    effectiveCautionRadius,
    swingLeadAngle,
    speedExpansionFactor: speedRatio,
    hazardArcStart: centerAngle - halfSpan,
    hazardArcEnd: centerAngle + halfSpan,
  };
}

/**
 * Evaluates which zone a point (x, y) falls into relative to the machine pivot.
 * Takes into account radial distance, angular velocity, and swing trajectory lead.
 */
export function evaluatePointZone(
  x: number,
  y: number,
  machine: ExcavatorKinematics,
  conservativeBuffer: number = 0 // additional buffer in meters for low-confidence detections
): {
  zone: ZoneLevel;
  distanceToMachine: number;
  dangerThresholdAtAngle: number;
  cautionThresholdAtAngle: number;
} {
  // Machine pivot is at (0, 0).
  // Calculate polar coordinates: distance r and angle theta
  const distance = Math.hypot(x, y);
  
  // Angle in degrees where 0° is forward (+Y axis), 90° is right (+X axis), -90° is left (-X axis)
  // Math.atan2(y, x): 0 is +X, 90 is +Y
  // We align with excavator forward = 0° (along +Y axis):
  const angleRad = Math.atan2(x, y); // 0 at +Y, +pi/2 at +X (right), -pi/2 at -X (left)
  const angleDeg = (angleRad * 180) / Math.PI;

  const speedRatio = Math.min(1, Math.max(0, machine.swingSpeed / 60));
  
  // Directional bias: determine how aligned this point is with the swing direction
  let directionSign = 0;
  if (machine.isSwinging) {
    if (machine.swingDirection === 'RIGHT') directionSign = 1;
    else if (machine.swingDirection === 'LEFT') directionSign = -1;
  }
  
  const swingLead = directionSign * speedRatio * MAX_LEAD_ANGLE_DEG;
  const activeVector = machine.swingAngle + swingLead;
  
  // Angular difference between worker and the active swing direction (-180 to +180)
  let diffAngle = Math.abs(angleDeg - activeVector);
  while (diffAngle > 180) diffAngle = Math.abs(diffAngle - 360);
  
  // Alignment factor: 1.0 when directly in swing trajectory, drops smoothly to 0.4 for rear counterweight
  const alignmentFactor = 0.5 + 0.5 * Math.cos((diffAngle * Math.PI) / 180);
  
  // Dynamic threshold at this specific angle:
  // Base circle + speed expansion modulated by trajectory alignment
  const dangerThreshold =
    BASELINE_DANGER_RADIUS +
    speedRatio * MAX_SPEED_EXPANSION_DANGER * (0.6 + 0.4 * alignmentFactor) +
    conservativeBuffer;
    
  const cautionThreshold =
    BASELINE_CAUTION_RADIUS +
    speedRatio * MAX_SPEED_EXPANSION_CAUTION * (0.6 + 0.4 * alignmentFactor) +
    conservativeBuffer;

  let zone: ZoneLevel = 'OUTSIDE';
  if (distance <= dangerThreshold) {
    zone = 'DANGER';
  } else if (distance <= cautionThreshold) {
    zone = 'CAUTION';
  }

  return {
    zone,
    distanceToMachine: distance,
    dangerThresholdAtAngle: dangerThreshold,
    cautionThresholdAtAngle: cautionThreshold,
  };
}

/**
 * Generates an SVG path for the dynamic glowing zone.
 * Uses polar sampling to build a smooth, organic dynamic envelope that swells in the swing direction.
 */
export function generateZoneSvgPath(
  zoneType: 'DANGER' | 'CAUTION',
  machine: ExcavatorKinematics,
  metersToPixels: number,
  centerX: number,
  centerY: number,
  conservativeBuffer: number = 0
): string {
  const points: { x: number; y: number }[] = [];
  const samples = 64;
  
  for (let i = 0; i <= samples; i++) {
    const frac = i / samples;
    const angleRad = frac * 2 * Math.PI; // 0 to 2pi
    const xUnit = Math.sin(angleRad);
    const yUnit = Math.cos(angleRad);
    
    // Evaluate boundary at this ray
    const evalResult = evaluatePointZone(
      xUnit * 10, // far enough along ray
      yUnit * 10,
      machine,
      conservativeBuffer
    );
    
    const radiusMeters =
      zoneType === 'DANGER'
        ? evalResult.dangerThresholdAtAngle
        : evalResult.cautionThresholdAtAngle;
        
    // Convert to pixel coordinates
    // In SVG, +Y is downward, so invert yUnit for top-down display
    const px = centerX + xUnit * radiusMeters * metersToPixels;
    const py = centerY - yUnit * radiusMeters * metersToPixels;
    
    points.push({ x: px, y: py });
  }
  
  if (points.length === 0) return '';
  
  let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 1; i < points.length; i++) {
    d += ` L ${points[i].x.toFixed(1)} ${points[i].y.toFixed(1)}`;
  }
  d += ' Z';
  
  return d;
}
