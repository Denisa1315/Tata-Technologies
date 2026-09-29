import React from 'react';

interface RealisticSurroundingsProps {
  scale: number;
  centerX: number;
  centerY: number;
  theme: 'dark' | 'light';
}

/**
 * Clean & Elegant Operator Worksite Surroundings:
 * - Architectural excavation trench with stepped bench contours and shoring
 * - Subtle earth spoil mounds with soft textural aggregate
 * - Dual crawler track ruts behind undercarriage
 * - Soft ground contact shadow grounding the excavator
 * - Low-profile precast Jersey barriers and retroreflective site cones
 * - Subtle utility boundary markings (HV Electric & Gas) without loud text clutter
 */
export const RealisticSurroundings: React.FC<RealisticSurroundingsProps> = ({
  scale,
  centerX,
  centerY,
  theme,
}) => {
  const isLight = theme === 'light';

  // Subtle architectural colors
  const trenchPitFill = isLight ? '#544435' : '#08080a';
  const trenchBenchFill = isLight ? '#8a7964' : '#141312';
  const trenchSlopeStroke = isLight ? '#423425' : '#1f1e1c';
  const spoilPileFill = isLight ? '#b09f87' : '#1e1c19';
  const spoilHighlight = isLight ? '#cfc0a9' : '#2d2924';
  const jerseyBarrierFill = isLight ? '#cbd5e1' : '#27272a';
  const jerseyBarrierStroke = isLight ? '#94a3b8' : '#18181b';
  const tireRutColor = isLight ? 'rgba(90, 70, 50, 0.22)' : 'rgba(0, 0, 0, 0.45)';
  const steelPlateFill = isLight ? '#94a3b8' : '#27272a';
  const steelPlateStroke = isLight ? '#64748b' : '#3f3f46';

  return (
    <g className="realistic-surroundings pointer-events-none select-none">
      <defs>
        {/* Soft shadow for the excavator */}
        <radialGradient id="excavator-ground-shadow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={isLight ? 'rgba(30,20,10,0.38)' : 'rgba(0,0,0,0.85)'} />
          <stop offset="65%" stopColor={isLight ? 'rgba(30,20,10,0.18)' : 'rgba(0,0,0,0.40)'} />
          <stop offset="100%" stopColor="rgba(0,0,0,0)" />
        </radialGradient>

        {/* Subtle gravel pattern */}
        <pattern id="gravel-pattern" width="16" height="16" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="4" r="1" fill={isLight ? '#6e5e48' : '#141416'} />
          <circle cx="11" cy="6" r="1.2" fill={isLight ? '#8a7860' : '#1a191c'} />
          <circle cx="7" cy="12" r="0.8" fill={isLight ? '#574834' : '#101012'} />
          <circle cx="14" cy="13" r="1.1" fill={isLight ? '#99866e' : '#222125'} />
        </pattern>
      </defs>

      {/* 1. Excavator Ground Drop Shadow */}
      <ellipse
        cx={centerX}
        cy={centerY + 0.15 * scale}
        rx={2.0 * scale}
        ry={1.6 * scale}
        fill="url(#excavator-ground-shadow)"
      />

      {/* 2. Heavy Crawler Track Ruts & Compaction Lines */}
      <g opacity={isLight ? 0.75 : 0.6}>
        <path
          d={`M ${centerX - 1.15 * scale} ${centerY + 1.1 * scale} Q ${centerX - 1.3 * scale} ${centerY + 2.8 * scale} ${centerX - 3.0 * scale} ${centerY + 5.0 * scale}`}
          fill="none"
          stroke={tireRutColor}
          strokeWidth={0.52 * scale}
          strokeDasharray="6 4"
        />
        <path
          d={`M ${centerX + 1.15 * scale} ${centerY + 1.1 * scale} Q ${centerX + 1.0 * scale} ${centerY + 2.8 * scale} ${centerX - 0.7 * scale} ${centerY + 5.0 * scale}`}
          fill="none"
          stroke={tireRutColor}
          strokeWidth={0.52 * scale}
          strokeDasharray="6 4"
        />
      </g>

      {/* 3. Buried Utility Boundary Markers (Muted CAD style, no noisy slogans) */}
      <g opacity={isLight ? 0.65 : 0.45}>
        {/* Gas Main */}
        <path
          d={`M ${centerX - 7.5 * scale} ${centerY - 1.8 * scale} L ${centerX + 7.5 * scale} ${centerY - 1.8 * scale}`}
          fill="none"
          stroke="#eab308"
          strokeWidth="1.2"
          strokeDasharray="6 6"
        />
        <text
          x={centerX - 7.0 * scale}
          y={centerY - 2.0 * scale}
          fill="#ca8a04"
          fontSize="6.5"
          fontFamily="JetBrains Mono"
          fontWeight="bold"
          opacity="0.85"
        >
          GAS MAIN [-1.4m]
        </text>

        {/* 11kV Power Cable */}
        <path
          d={`M ${centerX - 7.5 * scale} ${centerY + 1.6 * scale} L ${centerX - 2.5 * scale} ${centerY + 1.6 * scale} L ${centerX - 2.0 * scale} ${centerY + 6.0 * scale}`}
          fill="none"
          stroke="#ef4444"
          strokeWidth="1.2"
          strokeDasharray="5 5"
        />
        <text
          x={centerX - 7.0 * scale}
          y={centerY + 1.35 * scale}
          fill="#dc2626"
          fontSize="6.5"
          fontFamily="JetBrains Mono"
          fontWeight="bold"
          opacity="0.85"
        >
          11kV POWER CABLE
        </text>
      </g>

      {/* 4. Active Excavation Trench / Pit (Top Right Quadrant) */}
      <g>
        {/* Outer Top Bench */}
        <path
          d={`M ${centerX + 1.8 * scale} ${centerY - 2.8 * scale} 
              L ${centerX + 5.8 * scale} ${centerY - 2.8 * scale} 
              L ${centerX + 6.4 * scale} ${centerY - 6.8 * scale} 
              L ${centerX + 2.2 * scale} ${centerY - 6.8 * scale} Z`}
          fill={trenchBenchFill}
          stroke={trenchSlopeStroke}
          strokeWidth="1.5"
        />

        {/* Deep Trench Pit Floor */}
        <path
          d={`M ${centerX + 2.4 * scale} ${centerY - 3.4 * scale} 
              L ${centerX + 5.2 * scale} ${centerY - 3.4 * scale} 
              L ${centerX + 5.7 * scale} ${centerY - 6.2 * scale} 
              L ${centerX + 2.7 * scale} ${centerY - 6.2 * scale} Z`}
          fill={trenchPitFill}
          stroke={isLight ? '#3b2f21' : '#000000'}
          strokeWidth="1.2"
        />

        {/* Pit floor gravel fill */}
        <path
          d={`M ${centerX + 2.5 * scale} ${centerY - 3.5 * scale} 
              L ${centerX + 5.1 * scale} ${centerY - 3.5 * scale} 
              L ${centerX + 5.6 * scale} ${centerY - 6.1 * scale} 
              L ${centerX + 2.8 * scale} ${centerY - 6.1 * scale} Z`}
          fill="url(#gravel-pattern)"
          opacity={isLight ? 0.35 : 0.25}
        />

        {/* Shoring Struts */}
        <rect
          x={centerX + 2.6 * scale}
          y={centerY - 4.1 * scale}
          width={2.8 * scale}
          height={0.12 * scale}
          fill="#d97706"
          stroke="#78350f"
          strokeWidth="0.8"
          rx="1"
        />
        <rect
          x={centerX + 2.8 * scale}
          y={centerY - 5.4 * scale}
          width={2.7 * scale}
          height={0.12 * scale}
          fill="#d97706"
          stroke="#78350f"
          strokeWidth="0.8"
          rx="1"
        />

        <text
          x={centerX + 4.0 * scale}
          y={centerY - 4.7 * scale}
          fill={isLight ? '#ece6d8' : '#71717a'}
          fontSize="7"
          fontFamily="JetBrains Mono"
          fontWeight="bold"
          textAnchor="middle"
          opacity="0.8"
        >
          EXCAVATION PIT (-2.8m)
        </text>
      </g>

      {/* 5. Clean Earth Spoil Piles (Left Flank) */}
      <g>
        <path
          d={`M ${centerX - 3.8 * scale} ${centerY - 2.2 * scale} 
              Q ${centerX - 5.8 * scale} ${centerY - 5.2 * scale} ${centerX - 3.8 * scale} ${centerY - 6.2 * scale} 
              Q ${centerX - 2.0 * scale} ${centerY - 4.2 * scale} ${centerX - 3.8 * scale} ${centerY - 2.2 * scale} Z`}
          fill={spoilPileFill}
          stroke={isLight ? '#8a7964' : '#27272a'}
          strokeWidth="1.2"
        />
        <path
          d={`M ${centerX - 3.8 * scale} ${centerY - 3.0 * scale} 
              Q ${centerX - 4.6 * scale} ${centerY - 4.5 * scale} ${centerX - 3.6 * scale} ${centerY - 5.5 * scale}`}
          fill="none"
          stroke={spoilHighlight}
          strokeWidth="2.5"
          opacity="0.5"
        />
        <text
          x={centerX - 3.8 * scale}
          y={centerY - 4.1 * scale}
          fill={isLight ? '#45382b' : '#71717a'}
          fontSize="7"
          fontFamily="JetBrains Mono"
          fontWeight="bold"
          textAnchor="middle"
          opacity="0.8"
        >
          SPOIL MOUND
        </text>
      </g>

      {/* 6. Trench Steel Crossing Plate */}
      <g transform={`translate(${centerX + 0.2 * scale}, ${centerY - 6.2 * scale})`}>
        <rect
          x="-1.0 * scale"
          y="-0.35 * scale"
          width={2.0 * scale}
          height={0.7 * scale}
          fill={steelPlateFill}
          stroke={steelPlateStroke}
          strokeWidth="1"
          rx="2"
        />
        <text
          x="0"
          y="2.5"
          fill={isLight ? '#1e293b' : '#a1a1aa'}
          fontSize="6"
          fontFamily="JetBrains Mono"
          fontWeight="bold"
          textAnchor="middle"
          opacity="0.9"
        >
          ROAD PLATE 35T
        </text>
      </g>

      {/* 7. Perimeter Concrete Jersey Barriers (Clean Muted Line) */}
      <g>
        {[-4.5, -3.2, -1.9, 1.8, 3.1, 4.4, 5.7].map((barrierX, idx) => (
          <g key={`barrier-t-${idx}`} transform={`translate(${centerX + barrierX * scale}, ${centerY - 7.2 * scale})`}>
            <rect
              x="-15"
              y="-4"
              width="30"
              height="8"
              rx="1.5"
              fill={jerseyBarrierFill}
              stroke={jerseyBarrierStroke}
              strokeWidth="0.8"
            />
            <rect
              x="-11"
              y="-2"
              width="22"
              height="4"
              fill={idx % 2 === 0 ? '#ef4444' : '#ffffff'}
              opacity="0.85"
            />
          </g>
        ))}
      </g>

      {/* 8. Construction Traffic Cones (High-Vis Tactical Dots) */}
      <g>
        {[
          { x: -1.8, y: -2.8 },
          { x: 1.6, y: -2.2 },
          { x: 5.6, y: -2.2 },
          { x: 5.6, y: -6.8 },
          { x: -3.0, y: 1.4 },
          { x: 4.6, y: 3.0 },
        ].map((cone, idx) => (
          <g
            key={`cone-${idx}`}
            transform={`translate(${centerX + cone.x * scale}, ${centerY - cone.y * scale})`}
          >
            <rect x="-6" y="-6" width="12" height="12" rx="1.5" fill="#18181b" />
            <circle cx="0" cy="0" r="4.5" fill="#f97316" />
            <circle cx="0" cy="0" r="2.8" fill="#ffffff" />
            <circle cx="0" cy="0" r="1.4" fill="#ea580c" />
          </g>
        ))}
      </g>
    </g>
  );
};
