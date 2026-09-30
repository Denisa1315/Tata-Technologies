import React from 'react';
import { Camera, Eye, Sliders, ShieldAlert } from 'lucide-react';
import { PerceptionSystem, CameraStatus, VisibilityMode } from '../types';

interface PerceptionControlsProps {
  perception: PerceptionSystem;
  onUpdatePerception: (partial: Partial<PerceptionSystem>) => void;
  theme?: 'dark' | 'light';
}

export const PerceptionControls: React.FC<PerceptionControlsProps> = ({
  perception,
  onUpdatePerception,
  theme = 'dark',
}) => {
  const isLight = theme === 'light';
  const handleCameraStatus = (status: CameraStatus) => {
    onUpdatePerception({ cameraStatus: status });
  };

  const handleVisibility = (visibility: VisibilityMode) => {
    onUpdatePerception({ visibility });
  };

  const handleFpsChange = (fps: number) => {
    onUpdatePerception({ fps });
  };

  return (
    <div className={`p-3 rounded-lg border space-y-3 transition-colors ${
      isLight ? 'bg-stone-100/90 border-stone-300' : 'bg-neutral-900/90 border-neutral-800'
    }`}>
      {/* Header */}
      <div className={`flex items-center justify-between border-b pb-2 ${isLight ? 'border-stone-300' : 'border-neutral-800'}`}>
        <div className="flex items-center gap-2">
          <Camera className={`w-4 h-4 ${isLight ? 'text-cyan-800' : 'text-cyan-400'}`} />
          <h3 className={`text-xs font-bold uppercase tracking-wider ${isLight ? 'text-stone-800' : 'text-neutral-200'}`}>
            Perception Health & Edge Sensors
          </h3>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              perception.cameraStatus === 'ONLINE' && perception.fps >= perception.fpsThreshold
                ? 'bg-emerald-500 shadow-[0_0_6px_#10b981]'
                : 'bg-rose-500 shadow-[0_0_6px_#ef4444] animate-ping'
            }`}
          />
          <span className={`text-[10px] font-mono ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>
            {perception.cameraStatus === 'ONLINE' && perception.fps >= perception.fpsThreshold
              ? 'NOMINAL'
              : 'DEGRADED'}
          </span>
        </div>
      </div>

      {/* Camera Health Selector */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-neutral-400">Optical Camera Stream:</span>
          <span
            className={`font-bold ${
              perception.cameraStatus === 'ONLINE'
                ? 'text-cyan-400'
                : perception.cameraStatus === 'BLOCKED'
                ? 'text-amber-400'
                : 'text-rose-400'
            }`}
          >
            {perception.cameraStatus}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={() => handleCameraStatus('ONLINE')}
            className={`py-1.5 px-2 rounded font-mono text-xs font-semibold border transition-all ${
              perception.cameraStatus === 'ONLINE'
                ? 'bg-cyan-950 text-cyan-300 border-cyan-700 shadow-sm'
                : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            ONLINE
          </button>
          <button
            onClick={() => handleCameraStatus('BLOCKED')}
            className={`py-1.5 px-2 rounded font-mono text-xs font-semibold border transition-all ${
              perception.cameraStatus === 'BLOCKED'
                ? 'bg-amber-950 text-amber-300 border-amber-600 shadow-sm'
                : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            BLOCKED
          </button>
          <button
            onClick={() => handleCameraStatus('DISCONNECTED')}
            className={`py-1.5 px-2 rounded font-mono text-xs font-semibold border transition-all ${
              perception.cameraStatus === 'DISCONNECTED'
                ? 'bg-rose-950 text-rose-300 border-rose-700 shadow-sm'
                : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            DISCONNECT
          </button>
        </div>
      </div>

      {/* Environmental Visibility */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-neutral-400 flex items-center gap-1">
            <Eye className="w-3.5 h-3.5 text-cyan-400" />
            <span>Site Visibility (Dust / Light):</span>
          </span>
          <span className="font-bold text-neutral-200">{perception.visibility}</span>
        </div>

        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={() => handleVisibility('GOOD')}
            className={`py-1.5 px-2 rounded font-mono text-xs font-medium border transition-all ${
              perception.visibility === 'GOOD'
                ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            GOOD
          </button>
          <button
            onClick={() => handleVisibility('PARTIAL')}
            className={`py-1.5 px-2 rounded font-mono text-xs font-medium border transition-all ${
              perception.visibility === 'PARTIAL'
                ? 'bg-amber-950 text-amber-300 border-amber-700'
                : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            PARTIAL
          </button>
          <button
            onClick={() => handleVisibility('POOR')}
            className={`py-1.5 px-2 rounded font-mono text-xs font-medium border transition-all ${
              perception.visibility === 'POOR'
                ? 'bg-rose-950 text-rose-300 border-rose-700'
                : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            POOR (Fog/Dust)
          </button>
        </div>
      </div>

      {/* Simulated Edge Inference FPS */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-neutral-400 flex items-center gap-1">
            <Sliders className="w-3.5 h-3.5 text-cyan-400" />
            <span>Edge Inference Rate:</span>
          </span>
          <span
            className={`font-bold tabular-nums ${
              perception.fps < perception.fpsThreshold ? 'text-rose-400 font-black' : 'text-cyan-300'
            }`}
          >
            {perception.fps} FPS{' '}
            {perception.fps < perception.fpsThreshold && '(BELOW THRESHOLD)'}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={() => handleFpsChange(30)}
            className={`py-1 px-1.5 rounded font-mono text-xs font-medium border transition-all ${
              perception.fps === 30
                ? 'bg-neutral-800 text-white border-cyan-600'
                : 'bg-neutral-800/60 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            30 FPS (Nominal)
          </button>
          <button
            onClick={() => handleFpsChange(15)}
            className={`py-1 px-1.5 rounded font-mono text-xs font-medium border transition-all ${
              perception.fps === 15
                ? 'bg-neutral-800 text-white border-amber-600'
                : 'bg-neutral-800/60 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            15 FPS (Limit)
          </button>
          <button
            onClick={() => handleFpsChange(5)}
            className={`py-1 px-1.5 rounded font-mono text-xs font-medium border transition-all ${
              perception.fps === 5
                ? 'bg-rose-950 text-rose-300 border-rose-600'
                : 'bg-neutral-800/60 text-neutral-400 border-neutral-700 hover:bg-neutral-700'
            }`}
          >
            5 FPS (Fault)
          </button>
        </div>
      </div>

      {/* Fail-Safe Explanation Note */}
      <div className="p-2 rounded bg-neutral-950/80 border border-neutral-800 text-[11px] font-mono text-neutral-400 flex items-start gap-1.5">
        <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
        <span>
          <strong>Fail-Safe Invariant:</strong> If optical input or frame rate drops below safety threshold, the system immediately degrades to FAIL-SAFE STOP.
        </span>
      </div>
    </div>
  );
};
