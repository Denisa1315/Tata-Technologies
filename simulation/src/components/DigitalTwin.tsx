import React, { useRef, useState, useEffect, useCallback } from 'react';
import {
  WorkerData,
  ExcavatorKinematics,
  PerceptionSystem,
  SafetyDecision,
  DynamicZones,
  ThemeMode,
} from '../types';
import { generateZoneSvgPath } from '../core/zoneEngine';
import { CONSERVATIVE_BUFFER_METERS } from '../core/riskEngine';
import { RealisticSurroundings } from './RealisticSurroundings';
import { AlertOctagon, Eye, Ruler, UserCheck, RotateCw, Layers } from 'lucide-react';

interface DigitalTwinProps {
  machine: ExcavatorKinematics;
  workers: WorkerData[];
  perception: PerceptionSystem;
  decision: SafetyDecision;
  dynamicZones: DynamicZones;
  onUpdateWorkerPosition: (workerId: string, x: number, y: number) => void;
  onApplyPreset: (presetName: string) => void;
  isPresentationMode: boolean;
  theme?: ThemeMode;
}

export const DigitalTwin: React.FC<DigitalTwinProps> = ({
  machine,
  workers,
  perception,
  decision,
  dynamicZones,
  onUpdateWorkerPosition,
  onApplyPreset,
  isPresentationMode,
  theme = 'dark',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const isLight = theme === 'light';
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [draggedWorkerId, setDraggedWorkerId] = useState<string | null>(null);
  const [showRays, setShowRays] = useState(true);
  const [showFov, setShowFov] = useState(true);
  const [showSurroundings, setShowSurroundings] = useState(true);

  // Resize observer to keep canvas responsive and centered
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Scale: 1 meter = 46 pixels (responsive: adjusts slightly based on viewport height)
  const scale = Math.min(54, Math.max(34, dimensions.height / 14));
  const centerX = dimensions.width / 2;
  const centerY = dimensions.height / 2 + 30; // slightly down to leave room for arm forward extension

  // Coordinates conversion: World meters (0,0 is machine pivot, +Y forward, +X right) to SVG pixels
  const metersToPixels = (x: number, y: number) => {
    return {
      px: centerX + x * scale,
      py: centerY - y * scale, // SVG Y is inverted
    };
  };

  const pixelsToMeters = (px: number, py: number) => {
    return {
      x: (px - centerX) / scale,
      y: (centerY - py) / scale,
    };
  };

  // Dragging logic for workers
  const handlePointerDown = (workerId: string, e: React.PointerEvent) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    setDraggedWorkerId(workerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!draggedWorkerId || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;

    const { x, y } = pixelsToMeters(px, py);
    // Clamp to simulation arena bounds (-8m to +8m X, -4m to +9m Y)
    const clampedX = Math.max(-7.5, Math.min(7.5, x));
    const clampedY = Math.max(-3.5, Math.min(8.5, y));

    onUpdateWorkerPosition(draggedWorkerId, clampedX, clampedY);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (draggedWorkerId) {
      try {
        (e.target as Element).releasePointerCapture(e.pointerId);
      } catch {
        // Ignore
      }
      setDraggedWorkerId(null);
    }
  };

  // Generate SVG path strings for dynamic danger and caution zones
  const dangerPath = generateZoneSvgPath(
    'DANGER',
    machine,
    scale,
    centerX,
    centerY,
    0
  );

  const cautionPath = generateZoneSvgPath(
    'CAUTION',
    machine,
    scale,
    centerX,
    centerY,
    0
  );

  // Machine angle in SVG rotation: 0° is straight up (+Y), rotation around (centerX, centerY)
  const swingAngleDeg = machine.swingAngle;

  // Active swing vector lead angle for visual arrow
  let directionSign = 0;
  if (machine.isSwinging) {
    if (machine.swingDirection === 'RIGHT') directionSign = 1;
    else if (machine.swingDirection === 'LEFT') directionSign = -1;
  }
  const leadAngleDeg = swingAngleDeg + directionSign * dynamicZones.swingLeadAngle;

  // Camera world coordinates
  const cameraPix = metersToPixels(perception.cameraPos.x, perception.cameraPos.y);

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full overflow-hidden select-none cursor-crosshair transition-colors duration-200 ${
        isLight ? 'site-ground-light radar-grid-light' : 'site-ground-dark radar-grid'
      }`}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      {/* SVG Digital Twin Scene */}
      <svg
        className="w-full h-full pointer-events-none"
        viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
      >
        <defs>
          {/* Radial glow for danger zone */}
          <radialGradient id="dangerGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ef4444" stopOpacity="0.45" />
            <stop offset="70%" stopColor="#dc2626" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#b91c1c" stopOpacity="0.08" />
          </radialGradient>

          {/* Radial glow for caution zone */}
          <radialGradient id="cautionGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.0" />
            <stop offset="65%" stopColor="#f59e0b" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.26" />
          </radialGradient>

          {/* Camera sensor FOV gradient */}
          <linearGradient id="cameraFovGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
          </linearGradient>

          {/* Pulsing glow filter */}
          <filter id="glowFilter" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Realistic Worksites Elements (Trenches, soil mounds, barricades, ruts, survey pegs) */}
        {showSurroundings && (
          <RealisticSurroundings
            scale={scale}
            centerX={centerX}
            centerY={centerY}
            theme={isLight ? 'light' : 'dark'}
          />
        )}

        {/* 1. Ground Coordinate Metric Rings */}
        {[2, 4, 6, 8].map((radiusMeters) => (
          <g key={radiusMeters}>
            <circle
              cx={centerX}
              cy={centerY}
              r={radiusMeters * scale}
              fill="none"
              stroke={isLight ? '#a8a29e' : '#27272a'}
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            {/* Metric distance label */}
            <text
              x={centerX + 6}
              y={centerY - radiusMeters * scale + 13}
              fill={isLight ? '#57534e' : '#71717a'}
              fontSize="10"
              fontFamily="JetBrains Mono"
              fontWeight="600"
            >
              {radiusMeters}m
            </text>
          </g>
        ))}

        {/* Axis Crosshairs */}
        <line
          x1={centerX}
          y1={centerY - 9 * scale}
          x2={centerX}
          y2={centerY + 4 * scale}
          stroke={isLight ? 'rgba(0,0,0,0.1)' : '#18181b'}
          strokeWidth="1"
        />
        <line
          x1={centerX - 8 * scale}
          y1={centerY}
          x2={centerX + 8 * scale}
          y2={centerY}
          stroke={isLight ? 'rgba(0,0,0,0.1)' : '#18181b'}
          strokeWidth="1"
        />

        {/* 2. Camera Field of View (FOV) Scan Cone */}
        {showFov && perception.cameraStatus === 'ONLINE' && (
          <g
            transform={`translate(${cameraPix.px}, ${cameraPix.py}) rotate(${swingAngleDeg * 0.4})`}
            opacity="0.8"
          >
            <path
              d={`M 0 0 L ${-Math.tan((55 * Math.PI) / 180) * 7.5 * scale} ${-7.5 * scale} A ${7.5 * scale} ${7.5 * scale} 0 0 1 ${Math.tan((55 * Math.PI) / 180) * 7.5 * scale} ${-7.5 * scale} Z`}
              fill="url(#cameraFovGrad)"
              stroke="#06b6d4"
              strokeWidth="0.8"
              strokeDasharray="3 3"
            />
          </g>
        )}

        {/* 3. Dynamic CAUTION Zone (Outer Glowing Band) */}
        <path
          d={cautionPath}
          fill="url(#cautionGlow)"
          stroke="#f59e0b"
          strokeWidth={decision.overallState === 'WARNING' ? '2.5' : '1.5'}
          strokeDasharray="6 4"
          filter={decision.overallState === 'WARNING' ? 'url(#glowFilter)' : undefined}
          className="transition-all duration-150"
        />

        {/* 4. Dynamic DANGER Zone (Inner Glowing Core) */}
        <path
          d={dangerPath}
          fill="url(#dangerGlow)"
          stroke="#ef4444"
          strokeWidth={decision.overallState === 'CRITICAL' ? '3.5' : '2'}
          filter={decision.overallState === 'CRITICAL' ? 'url(#glowFilter)' : undefined}
          className="transition-all duration-150"
        />

        {/* Dynamic Zone Annotations */}
        <g>
          {/* Dynamic danger boundary radius indicator */}
          <text
            x={centerX - dynamicZones.effectiveDangerRadius * scale - 10}
            y={centerY}
            fill="#ef4444"
            fontSize="10"
            fontFamily="JetBrains Mono"
            fontWeight="bold"
            textAnchor="end"
          >
            DANGER: {dynamicZones.effectiveDangerRadius.toFixed(2)}m
          </text>

          {/* Dynamic caution boundary radius indicator */}
          <text
            x={centerX - dynamicZones.effectiveCautionRadius * scale - 10}
            y={centerY - 16}
            fill="#f59e0b"
            fontSize="10"
            fontFamily="JetBrains Mono"
            fontWeight="bold"
            textAnchor="end"
          >
            CAUTION: {dynamicZones.effectiveCautionRadius.toFixed(2)}m
          </text>
        </g>

        {/* 5. Active Swing Direction Vector Arrow */}
        {machine.isSwinging && (
          <g transform={`translate(${centerX}, ${centerY}) rotate(${leadAngleDeg})`}>
            {/* Extended directional hazard vector ray */}
            <line
              x1="0"
              y1="0"
              x2="0"
              y2={-dynamicZones.effectiveCautionRadius * scale * 1.15}
              stroke={machine.swingDirection === 'RIGHT' ? '#06b6d4' : '#06b6d4'}
              strokeWidth="2"
              strokeDasharray="4 3"
            />
            {/* Arrowhead */}
            <polygon
              points={`0,${-dynamicZones.effectiveCautionRadius * scale * 1.18} -6,${-dynamicZones.effectiveCautionRadius * scale * 1.12} 6,${-dynamicZones.effectiveCautionRadius * scale * 1.12}`}
              fill="#06b6d4"
            />
          </g>
        )}

        {/* 6. Measurement Rays from Workers to Machine Pivot & Camera */}
        {showRays &&
          workers.map((w) => {
            const wPix = metersToPixels(w.x, w.y);
            const strokeColor =
              w.zone === 'DANGER'
                ? '#ef4444'
                : w.zone === 'CAUTION'
                ? '#f59e0b'
                : '#3f3f46';

            return (
              <g key={`ray-${w.id}`}>
                {/* Ray to machine pivot */}
                <line
                  x1={centerX}
                  y1={centerY}
                  x2={wPix.px}
                  y2={wPix.py}
                  stroke={strokeColor}
                  strokeWidth="1.2"
                  strokeDasharray="2 2"
                  opacity={w.zone === 'OUTSIDE' ? 0.4 : 0.85}
                />

                {/* Ray to camera sensor (dashed cyan) */}
                {perception.cameraStatus === 'ONLINE' && (
                  <line
                    x1={cameraPix.px}
                    y1={cameraPix.py}
                    x2={wPix.px}
                    y2={wPix.py}
                    stroke="#06b6d4"
                    strokeWidth="0.8"
                    strokeDasharray="3 3"
                    opacity={0.35}
                  />
                )}
              </g>
            );
          })}

        {/* 7. EXCAVATOR CHASSIS & CRAWLER TRACKS (Fixed Ground Reference) */}
        {/* Left crawler track */}
        <rect
          x={centerX - 1.45 * scale}
          y={centerY - 1.9 * scale}
          width={0.7 * scale}
          height={3.8 * scale}
          rx={4}
          fill="#1c1917"
          stroke="#44403c"
          strokeWidth="1.5"
        />
        {/* Track grousers / ribs */}
        {[-1.6, -1.2, -0.8, -0.4, 0, 0.4, 0.8, 1.2, 1.6].map((offset) => (
          <line
            key={`track-l-${offset}`}
            x1={centerX - 1.45 * scale}
            y1={centerY + offset * scale}
            x2={centerX - 0.75 * scale}
            y2={centerY + offset * scale}
            stroke="#292524"
            strokeWidth="2"
          />
        ))}

        {/* Right crawler track */}
        <rect
          x={centerX + 0.75 * scale}
          y={centerY - 1.9 * scale}
          width={0.7 * scale}
          height={3.8 * scale}
          rx={4}
          fill="#1c1917"
          stroke="#44403c"
          strokeWidth="1.5"
        />
        {[-1.6, -1.2, -0.8, -0.4, 0, 0.4, 0.8, 1.2, 1.6].map((offset) => (
          <line
            key={`track-r-${offset}`}
            x1={centerX + 0.75 * scale}
            y1={centerY + offset * scale}
            x2={centerX + 1.45 * scale}
            y2={centerY + offset * scale}
            stroke="#292524"
            strokeWidth="2"
          />
        ))}

        {/* Lower Carbody / Center X-Frame */}
        <rect
          x={centerX - 0.85 * scale}
          y={centerY - 1.1 * scale}
          width={1.7 * scale}
          height={2.2 * scale}
          rx={3}
          fill="#262626"
          stroke="#404040"
          strokeWidth="1.5"
        />

        {/* Slewing Ring / Slew Bearing */}
        <circle
          cx={centerX}
          cy={centerY}
          r={0.9 * scale}
          fill="#171717"
          stroke="#eab308"
          strokeWidth="1"
          strokeDasharray="3 3"
        />

        {/* 8. ROTATING UPPER STRUCTURE (CABIN, ENGINE, BOOM, STICK, BUCKET) */}
        {/* Rotates smoothly with machine.swingAngle */}
        <g
          transform={`translate(${centerX}, ${centerY}) rotate(${swingAngleDeg})`}
          className="transition-transform duration-75 ease-linear"
        >
          {/* Rear Counterweight (heavy steel block at rear of house) */}
          <path
            d={`M ${-1.15 * scale} ${0.6 * scale} L ${1.15 * scale} ${0.6 * scale} L ${1.25 * scale} ${1.85 * scale} Q 0 ${2.05 * scale} ${-1.25 * scale} ${1.85 * scale} Z`}
            fill="#d97706"
            stroke="#b45309"
            strokeWidth="1.5"
          />
          {/* Reflective hazard chevron stripes on counterweight */}
          <rect
            x={-1.0 * scale}
            y={1.45 * scale}
            width={2.0 * scale}
            height={0.3 * scale}
            fill="#171717"
            stroke="#f59e0b"
            strokeWidth="0.8"
          />

          {/* Engine Compartment Hood & Grilles */}
          <rect
            x={-0.95 * scale}
            y={-0.35 * scale}
            width={1.9 * scale}
            height={1.0 * scale}
            rx={2}
            fill="#262626"
            stroke="#525252"
            strokeWidth="1.2"
          />
          {/* Exhaust Pipe stack */}
          <circle
            cx={0.65 * scale}
            cy={0.8 * scale}
            r={0.16 * scale}
            fill="#09090b"
            stroke="#71717a"
            strokeWidth="1.5"
          />

          {/* Operator Cabin (Left side of revolving superstructure) */}
          <rect
            x={-1.15 * scale}
            y={-1.65 * scale}
            width={0.95 * scale}
            height={1.6 * scale}
            rx={3}
            fill="#18181b"
            stroke="#0ea5e9"
            strokeWidth="1.2"
          />
          {/* Glass Windshield / Cab Roof Window */}
          <rect
            x={-1.05 * scale}
            y={-1.55 * scale}
            width={0.75 * scale}
            height={0.95 * scale}
            rx={2}
            fill="#0284c7"
            fillOpacity="0.45"
            stroke="#38bdf8"
            strokeWidth="0.8"
          />
          {/* Operator silhouette in cabin */}
          <circle
            cx={-0.65 * scale}
            cy={-1.0 * scale}
            r={0.22 * scale}
            fill="#facc15"
          />

          {/* Cabin Edge AI Camera Sensor Mount (Front-Left Corner of House) */}
          <g transform={`translate(${-1.05 * scale}, ${-1.75 * scale})`}>
            <rect
              x="-4"
              y="-4"
              width="8"
              height="8"
              rx="1.5"
              fill={perception.cameraStatus === 'ONLINE' ? '#06b6d4' : '#ef4444'}
              stroke="#ffffff"
              strokeWidth="1"
            />
            {perception.cameraStatus === 'ONLINE' && (
              <circle
                cx="0"
                cy="0"
                r="6"
                fill="none"
                stroke="#06b6d4"
                strokeWidth="1"
                className="animate-ping"
              />
            )}
          </g>

          {/* Main Boom Mount & Boom Arm extending forward */}
          {/* Boom Foot Bracket */}
          <rect
            x={-0.18 * scale}
            y={-0.8 * scale}
            width={0.5 * scale}
            height={0.9 * scale}
            rx={2}
            fill="#451a03"
            stroke="#f59e0b"
            strokeWidth="1.2"
          />

          {/* Boom (Heavy Steel Girder extending forward) */}
          <path
            d={`M ${-0.2 * scale} ${-0.5 * scale} L ${-0.12 * scale} ${-3.5 * scale} L ${0.32 * scale} ${-3.5 * scale} L ${0.4 * scale} ${-0.5 * scale} Z`}
            fill="#d97706"
            stroke="#78350f"
            strokeWidth="1.5"
          />
          {/* Boom hydraulic cylinder */}
          <rect
            x={0.04 * scale}
            y={-2.2 * scale}
            width={0.12 * scale}
            height={1.5 * scale}
            fill="#e5e7eb"
            stroke="#9ca3af"
            strokeWidth="0.8"
          />

          {/* Arm / Stick (Dipper) */}
          <path
            d={`M ${-0.1 * scale} ${-3.5 * scale} L ${-0.08 * scale} ${-4.9 * scale} L ${0.28 * scale} ${-4.9 * scale} L ${0.3 * scale} ${-3.5 * scale} Z`}
            fill="#b45309"
            stroke="#78350f"
            strokeWidth="1.2"
          />

          {/* Excavator Bucket with teeth */}
          <g transform={`translate(${0.1 * scale}, ${-5.0 * scale})`}>
            {/* Bucket body */}
            <path
              d={`M ${-0.35 * scale} 0 L ${0.35 * scale} 0 L ${0.45 * scale} ${-0.5 * scale} L ${-0.45 * scale} ${-0.5 * scale} Z`}
              fill="#18181b"
              stroke="#52525b"
              strokeWidth="1.5"
            />
            {/* Bucket teeth */}
            {[-0.3, -0.15, 0, 0.15, 0.3].map((tooth) => (
              <polygon
                key={`tooth-${tooth}`}
                points={`${tooth * scale - 2},${-0.5 * scale} ${tooth * scale + 2},${-0.5 * scale} ${tooth * scale},${-0.65 * scale}`}
                fill="#facc15"
              />
            ))}
          </g>

          {/* Machine Pivot Point Crosshair */}
          <circle cx="0" cy="0" r="4" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
        </g>
      </svg>

      {/* 9. Interactive Draggable Workers Overlay (HTML DOM layer for perfect pointer dragging) */}
      <div className="absolute inset-0 pointer-events-none">
        {workers.map((w) => {
          const wPix = metersToPixels(w.x, w.y);
          const isDragging = draggedWorkerId === w.id;

          // Color coding by safety zone
          const zoneBg =
            w.zone === 'DANGER'
              ? 'bg-rose-600 border-rose-400 shadow-rose-950/80 text-white'
              : w.zone === 'CAUTION'
              ? 'bg-amber-500 border-amber-300 shadow-amber-950/80 text-neutral-950'
              : 'bg-emerald-500 border-emerald-300 shadow-emerald-950/80 text-white';

          const haloRing =
            w.zone === 'DANGER'
              ? 'ring-4 ring-rose-500/50 shadow-[0_0_20px_#f43f5e]'
              : w.zone === 'CAUTION'
              ? 'ring-2 ring-amber-500/40 shadow-[0_0_12px_#f59e0b]'
              : 'ring-1 ring-emerald-500/30';

          return (
            <div
              key={w.id}
              style={{
                transform: `translate(${wPix.px}px, ${wPix.py}px)`,
                touchAction: 'none',
              }}
              onPointerDown={(e) => handlePointerDown(w.id, e)}
              className={`absolute -translate-x-1/2 -translate-y-1/2 pointer-events-auto cursor-grab active:cursor-grabbing transition-transform ${
                isDragging ? 'scale-115 z-40' : 'z-20 hover:scale-105'
              }`}
            >
              {/* Conservative Safety Buffer Visual Indicator Ring if LOW confidence */}
              {w.conservativeApplied && (
                <div
                  className="absolute rounded-full border-2 border-dashed border-cyan-400/80 bg-cyan-500/10 pointer-events-none -translate-x-1/2 -translate-y-1/2 animate-pulse"
                  style={{
                    left: 0,
                    top: 0,
                    width: `${CONSERVATIVE_BUFFER_METERS * 2 * scale}px`,
                    height: `${CONSERVATIVE_BUFFER_METERS * 2 * scale}px`,
                  }}
                />
              )}

              {/* Sleek Tactical Radar Marker */}
              <div className="relative flex flex-col items-center group">
                {/* Tactical circular blip */}
                <div
                  className={`w-7 h-7 rounded-full border-2 flex items-center justify-center font-mono font-black text-[11px] select-none transition-all ${zoneBg} ${haloRing} ${
                    w.zone === 'DANGER' ? 'animate-pulse' : ''
                  }`}
                >
                  {w.id}
                </div>

                {/* Clean, high-contrast distance chip attached below */}
                <div className={`mt-1 px-2 py-0.5 rounded-full border text-center shadow-md whitespace-nowrap transition-colors flex items-center gap-1 ${
                  w.zone === 'DANGER'
                    ? 'bg-rose-600 text-white border-rose-400 font-black text-[10px]'
                    : w.zone === 'CAUTION'
                    ? isLight ? 'bg-amber-100 text-amber-950 border-amber-400 font-bold text-[10px]' : 'bg-amber-500 text-neutral-950 border-amber-400 font-bold text-[10px]'
                    : isLight ? 'bg-stone-100 text-stone-800 border-stone-300 font-medium text-[10px]' : 'bg-neutral-900/90 text-neutral-200 border-neutral-700 font-medium text-[10px]'
                }`}>
                  <span className="font-mono">{w.machineDistance.toFixed(1)}m</span>
                  {w.zone === 'DANGER' && <span className="text-[9px] uppercase tracking-wider font-extrabold">STOP</span>}
                </div>

                {/* Tactical Inspection Hover Card (shows on hover or drag) */}
                <div className={`absolute top-full mt-1.5 opacity-0 group-hover:opacity-100 ${isDragging ? 'opacity-100' : ''} pointer-events-none transition-opacity duration-150 z-50 p-2 rounded-lg border font-mono text-[10px] space-y-0.5 shadow-xl whitespace-nowrap ${
                  isLight ? 'bg-white/95 border-stone-300 text-stone-800 shadow-stone-400/40' : 'bg-neutral-950/95 border-neutral-800 text-neutral-200'
                }`}>
                  <div className="font-bold flex items-center justify-between gap-2 border-b pb-0.5">
                    <span>{w.name} ({w.role})</span>
                    <span className={`px-1 rounded text-[9px] font-bold ${
                      w.zone === 'DANGER' ? 'bg-rose-500 text-white' : w.zone === 'CAUTION' ? 'bg-amber-500 text-neutral-950' : 'bg-emerald-500 text-white'
                    }`}>{w.zone}</span>
                  </div>
                  <div>Machine Dist: <strong>{w.machineDistance}m</strong></div>
                  <div>Optical Dist: <strong>{w.cameraDistance}m</strong></div>
                  <div>Confidence: <strong>{w.confidence}%</strong> ({w.confidenceLevel})</div>
                  {w.conservativeApplied && (
                    <div className="text-cyan-500 font-bold pt-0.5">+1.0m Safety Margin Applied</div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 10. High-Visibility Sleek Emergency STOP Bar (Non-Obtrusive to Excavator View) */}
      {decision.isStopIssued && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 pointer-events-none z-30 flex flex-col items-center">
          <div className="px-5 py-2 rounded-xl bg-gradient-to-r from-red-600 via-rose-600 to-red-600 text-white border-2 border-white/40 shadow-[0_0_40px_rgba(244,63,94,0.7)] flex items-center gap-3 animate-pulse">
            <AlertOctagon className="w-6 h-6 text-white shrink-0 animate-spin" style={{ animationDuration: '3s' }} />
            <div>
              <div className="text-sm md:text-base font-black tracking-widest uppercase">
                EMERGENCY SLEW LOCK ENGAGED
              </div>
              <div className="text-[11px] font-mono font-medium text-rose-100">
                {decision.stopReason || 'Dynamic safety perimeter penetrated'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 11. Sleek Top-Left Glass Toolbar (View Layers & Drag Hint) */}
      <div className="absolute top-3 left-3 z-20 flex items-center gap-1.5 flex-wrap">
        <div className={`flex items-center gap-1 p-1 rounded-xl backdrop-blur-md border shadow-md ${
          isLight ? 'bg-white/80 border-stone-300 text-stone-800' : 'bg-neutral-900/80 border-neutral-800 text-neutral-200'
        }`}>
          <button
            onClick={() => setShowSurroundings(!showSurroundings)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
              showSurroundings
                ? isLight ? 'bg-amber-100 text-amber-900 shadow-sm border border-amber-300' : 'bg-neutral-800 text-amber-300 border border-amber-600/50'
                : isLight ? 'text-stone-500 hover:text-stone-900' : 'text-neutral-400 hover:text-white'
            }`}
            title="Toggle Worksite Terrain"
          >
            <Layers className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Terrain</span>
          </button>
          <button
            onClick={() => setShowRays(!showRays)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
              showRays
                ? isLight ? 'bg-cyan-100 text-cyan-900 shadow-sm border border-cyan-300' : 'bg-neutral-800 text-cyan-300 border border-cyan-700/50'
                : isLight ? 'text-stone-500 hover:text-stone-900' : 'text-neutral-400 hover:text-white'
            }`}
            title="Toggle Metric Rays"
          >
            <Ruler className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Rays</span>
          </button>
          <button
            onClick={() => setShowFov(!showFov)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
              showFov
                ? isLight ? 'bg-cyan-100 text-cyan-900 shadow-sm border border-cyan-300' : 'bg-neutral-800 text-cyan-300 border border-cyan-700/50'
                : isLight ? 'text-stone-500 hover:text-stone-900' : 'text-neutral-400 hover:text-white'
            }`}
            title="Toggle Camera FOV Cone"
          >
            <Eye className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">FOV</span>
          </button>
        </div>

        {/* Tactile drag hint pill */}
        <div className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-[11px] font-mono select-none ${
          isLight ? 'bg-white/70 text-stone-600 border-stone-300' : 'bg-neutral-950/70 text-neutral-400 border-neutral-800'
        }`}>
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-ping" />
          <span>Drag W1, W2, W3 to test zones</span>
        </div>
      </div>
    </div>
  );
};
