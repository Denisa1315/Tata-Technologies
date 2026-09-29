import React from 'react';
import { Play, Square, RotateCw, RotateCcw, Gauge, Compass } from 'lucide-react';
import { ExcavatorKinematics } from '../types';

interface MachineControlsProps {
  machine: ExcavatorKinematics;
  onUpdateMachine: (partial: Partial<ExcavatorKinematics>) => void;
  isStopIssued: boolean;
  theme?: 'dark' | 'light';
}

export const MachineControls: React.FC<MachineControlsProps> = ({
  machine,
  onUpdateMachine,
  isStopIssued,
  theme = 'dark',
}) => {
  const isLight = theme === 'light';
  const handleSpeedChange = (newSpeed: number) => {
    const clamped = Math.max(0, Math.min(60, newSpeed));
    onUpdateMachine({
      swingSpeed: clamped,
      targetSpeed: clamped,
      isSwinging: clamped > 0,
    });
  };

  const handleAngleChange = (newAngle: number) => {
    onUpdateMachine({ swingAngle: Math.max(-90, Math.min(90, newAngle)) });
  };

  const handleToggleSwing = () => {
    if (machine.isSwinging) {
      onUpdateMachine({ isSwinging: false, swingSpeed: 0 });
    } else {
      const speed = machine.targetSpeed > 0 ? machine.targetSpeed : 24;
      onUpdateMachine({ isSwinging: true, swingSpeed: speed, targetSpeed: speed });
    }
  };

  const handleToggleDirection = () => {
    const nextDir = machine.swingDirection === 'RIGHT' ? 'LEFT' : 'RIGHT';
    onUpdateMachine({ swingDirection: nextDir });
  };

  const handleToggleOscillate = () => {
    onUpdateMachine({ autoOscillate: !machine.autoOscillate });
  };

  return (
    <div className={`p-3 rounded-lg border space-y-3 transition-colors ${
      isLight ? 'bg-stone-100/90 border-stone-300' : 'bg-neutral-900/90 border-neutral-800'
    }`}>
      {/* Header */}
      <div className={`flex items-center justify-between border-b pb-2 ${isLight ? 'border-stone-300' : 'border-neutral-800'}`}>
        <div className="flex items-center gap-2">
          <Gauge className={`w-4 h-4 ${isLight ? 'text-cyan-800' : 'text-cyan-400'}`} />
          <h3 className={`text-xs font-bold uppercase tracking-wider ${isLight ? 'text-stone-800' : 'text-neutral-200'}`}>
            Excavator Slew & Arm Kinematics
          </h3>
        </div>
        <span
          className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
            isStopIssued
              ? isLight ? 'bg-rose-100 text-rose-800 border border-rose-300' : 'bg-rose-950 text-rose-400 border border-rose-800'
              : machine.isSwinging
              ? isLight ? 'bg-cyan-100 text-cyan-800 border border-cyan-300' : 'bg-cyan-950 text-cyan-400 border border-cyan-800'
              : isLight ? 'bg-stone-200 text-stone-600' : 'bg-neutral-800 text-neutral-400'
          }`}
        >
          {isStopIssued ? 'LOCKED (STOP)' : machine.isSwinging ? 'SLEWING ACTIVE' : 'STATIONARY'}
        </span>
      </div>

      {/* Primary Action Buttons */}
      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={handleToggleSwing}
          disabled={isStopIssued}
          className={`flex items-center justify-center gap-1.5 py-2 px-3 rounded font-mono text-xs font-bold transition-all ${
            isStopIssued
              ? 'bg-neutral-800/60 text-neutral-500 cursor-not-allowed border border-neutral-700/50'
              : machine.isSwinging
              ? 'bg-rose-950 text-rose-300 border border-rose-800 hover:bg-rose-900'
              : 'bg-cyan-600 text-white hover:bg-cyan-500 shadow-md shadow-cyan-950'
          }`}
        >
          {machine.isSwinging ? (
            <>
              <Square className="w-3.5 h-3.5" />
              <span>STOP SWING</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>START SWING</span>
            </>
          )}
        </button>

        <button
          onClick={handleToggleDirection}
          disabled={isStopIssued}
          className="flex items-center justify-center gap-1.5 py-2 px-3 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border border-neutral-700 text-xs font-mono font-medium transition-colors"
        >
          {machine.swingDirection === 'RIGHT' ? (
            <>
              <RotateCw className="w-3.5 h-3.5 text-cyan-400" />
              <span>DIR: CLOCKWISE (R)</span>
            </>
          ) : (
            <>
              <RotateCcw className="w-3.5 h-3.5 text-cyan-400" />
              <span>DIR: COUNTER-CW (L)</span>
            </>
          )}
        </button>
      </div>

      {/* Swing Speed Control */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-neutral-400">Swing Speed:</span>
          <div className="flex items-center gap-1">
            <span className="text-base font-bold text-white tabular-nums">
              {machine.swingSpeed}°/s
            </span>
            <span className="text-[10px] text-neutral-500">
              {machine.swingSpeed === 0
                ? '(Baseline zone)'
                : machine.swingSpeed > 35
                ? '(Max dynamic expansion)'
                : '(Dynamic expansion)'}
            </span>
          </div>
        </div>

        {/* Speed Slider with +/- buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSpeedChange(machine.swingSpeed - 5)}
            disabled={isStopIssued}
            className="w-7 h-7 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-200 font-mono text-xs flex items-center justify-center border border-neutral-700"
          >
            -
          </button>
          <input
            type="range"
            min="0"
            max="60"
            step="2"
            value={machine.swingSpeed}
            disabled={isStopIssued}
            onChange={(e) => handleSpeedChange(Number(e.target.value))}
            className="flex-1 accent-cyan-500 cursor-pointer h-1.5 bg-neutral-700 rounded-lg"
          />
          <button
            onClick={() => handleSpeedChange(machine.swingSpeed + 5)}
            disabled={isStopIssued}
            className="w-7 h-7 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-200 font-mono text-xs flex items-center justify-center border border-neutral-700"
          >
            +
          </button>
        </div>

        <div className="flex justify-between text-[9px] font-mono text-neutral-500">
          <span>0°/s (Minimal)</span>
          <span>20°/s</span>
          <span>40°/s</span>
          <span>60°/s (Full Slew)</span>
        </div>
      </div>

      {/* Swing Angle Slider (-90° to +90°) */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-neutral-400 flex items-center gap-1">
            <Compass className="w-3.5 h-3.5 text-cyan-400" />
            <span>Slew Angle (Boom Orientation):</span>
          </span>
          <span className="text-sm font-bold text-cyan-300 tabular-nums">
            {machine.swingAngle > 0 ? `+${machine.swingAngle}°` : `${machine.swingAngle}°`}
          </span>
        </div>

        <input
          type="range"
          min="-90"
          max="90"
          step="1"
          value={machine.swingAngle}
          disabled={isStopIssued}
          onChange={(e) => handleAngleChange(Number(e.target.value))}
          className="w-full accent-cyan-500 cursor-pointer h-1.5 bg-neutral-700 rounded-lg"
        />

        <div className="flex justify-between text-[9px] font-mono text-neutral-500">
          <span>-90° (Left)</span>
          <span>0° (Forward)</span>
          <span>+90° (Right)</span>
        </div>
      </div>

      {/* Auto-Oscillate Sweep Toggle */}
      <div className="flex items-center justify-between pt-1 border-t border-neutral-800/80">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={machine.autoOscillate}
            disabled={isStopIssued}
            onChange={handleToggleOscillate}
            className="rounded accent-cyan-500"
          />
          <span className="text-xs font-mono text-neutral-300">
            Auto-Oscillate Sweep (-60° ↔ +60°)
          </span>
        </label>
        <span className="text-[10px] font-mono text-neutral-500">
          {machine.autoOscillate ? 'SWEEPING' : 'MANUAL'}
        </span>
      </div>
    </div>
  );
};
