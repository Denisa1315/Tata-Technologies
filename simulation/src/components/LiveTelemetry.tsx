import React from 'react';
import { Activity, Cpu, ShieldAlert, Users, Radio } from 'lucide-react';
import {
  ExcavatorKinematics,
  PerceptionSystem,
  SafetyDecision,
  DynamicZones,
  WorkerData,
} from '../types';

interface LiveTelemetryProps {
  machine: ExcavatorKinematics;
  perception: PerceptionSystem;
  decision: SafetyDecision;
  dynamicZones: DynamicZones;
  workers: WorkerData[];
  onSelectWorker?: (workerId: string) => void;
  theme?: 'dark' | 'light';
}

export const LiveTelemetry: React.FC<LiveTelemetryProps> = ({
  machine,
  perception,
  decision,
  dynamicZones,
  workers,
  theme = 'dark',
}) => {
  const isLight = theme === 'light';

  // Compute average confidence across workers
  const avgConfidence =
    workers.length > 0
      ? Math.round(workers.reduce((acc, w) => acc + w.confidence, 0) / workers.length)
      : 0;

  return (
    <div className={`p-3 rounded-lg border space-y-3 transition-colors ${
      isLight ? 'bg-stone-100/90 border-stone-300' : 'bg-neutral-900/90 border-neutral-800'
    }`}>
      {/* 1. Machine Telemetry Card */}
      <div className="space-y-1.5">
        <div className={`flex items-center justify-between text-xs font-mono border-b pb-1 ${
          isLight ? 'border-stone-300' : 'border-neutral-800'
        }`}>
          <span className={`font-bold uppercase tracking-wider flex items-center gap-1.5 ${
            isLight ? 'text-cyan-800' : 'text-cyan-400'
          }`}>
            <Activity className="w-3.5 h-3.5" />
            Machine Telemetry
          </span>
          <span className={`text-[10px] ${isLight ? 'text-stone-500' : 'text-neutral-400'}`}>EDGE BUS: ACTIVE</span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Swing Angle</div>
            <div className={`text-sm font-bold tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
              {machine.swingAngle > 0 ? `+${machine.swingAngle}°` : `${machine.swingAngle}°`}
            </div>
          </div>

          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Swing Speed</div>
            <div className={`text-sm font-bold tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
              {machine.swingSpeed}°/s
            </div>
          </div>

          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Pivot State</div>
            <div
              className={`text-xs font-bold ${
                decision.isStopIssued
                  ? 'text-rose-600'
                  : machine.isSwinging
                  ? isLight ? 'text-cyan-800' : 'text-cyan-300'
                  : isLight ? 'text-stone-500' : 'text-neutral-400'
              }`}
            >
              {decision.isStopIssued ? 'E-STOP HALT' : machine.isSwinging ? 'ACTIVE' : 'IDLE'}
            </div>
          </div>

          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Danger Zone Radius</div>
            <div className="text-sm font-bold text-rose-500 tabular-nums">
              {dynamicZones.effectiveDangerRadius.toFixed(2)} m
            </div>
          </div>
        </div>
      </div>

      {/* 2. Perception Telemetry Card */}
      <div className="space-y-1.5">
        <div className={`flex items-center justify-between text-xs font-mono border-b pb-1 ${
          isLight ? 'border-stone-300' : 'border-neutral-800'
        }`}>
          <span className={`font-bold uppercase tracking-wider flex items-center gap-1.5 ${
            isLight ? 'text-cyan-800' : 'text-cyan-400'
          }`}>
            <Cpu className="w-3.5 h-3.5" />
            Perception Engine
          </span>
          <span className={`text-[10px] ${isLight ? 'text-stone-500' : 'text-neutral-400'}`}>YOLO-EDGE SIM</span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Workers Detected</div>
            <div className={`text-sm font-bold tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
              {workers.length} Humans
            </div>
          </div>

          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Camera State</div>
            <div
              className={`text-xs font-bold ${
                perception.cameraStatus === 'ONLINE' ? 'text-emerald-600' : 'text-rose-600'
              }`}
            >
              {perception.cameraStatus}
            </div>
          </div>

          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Processing Rate</div>
            <div
              className={`text-sm font-bold tabular-nums ${
                perception.fps < perception.fpsThreshold ? 'text-rose-600' : isLight ? 'text-cyan-800' : 'text-cyan-300'
              }`}
            >
              {perception.fps} FPS
            </div>
          </div>

          <div className={`p-1.5 rounded border ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Avg Confidence</div>
            <div className={`text-sm font-bold tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
              {avgConfidence}%
            </div>
          </div>
        </div>
      </div>

      {/* 3. Safety Decision Logic Card */}
      <div className="space-y-1.5">
        <div className={`flex items-center justify-between text-xs font-mono border-b pb-1 ${
          isLight ? 'border-stone-300' : 'border-neutral-800'
        }`}>
          <span className={`font-bold uppercase tracking-wider flex items-center gap-1.5 ${
            isLight ? 'text-cyan-800' : 'text-cyan-400'
          }`}>
            <ShieldAlert className="w-3.5 h-3.5" />
            Safety Risk Engine
          </span>
          <span className={`text-[10px] ${isLight ? 'text-stone-500' : 'text-neutral-400'}`}>CYCLE: {perception.decisionLatencyMs}ms</span>
        </div>

        <div className="grid grid-cols-3 gap-1.5 text-xs font-mono">
          <div className={`p-1.5 rounded border text-center ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Highest Zone</div>
            <div
              className={`text-xs font-black mt-0.5 ${
                decision.highestRiskLevel === 'DANGER'
                  ? 'text-rose-600'
                  : decision.highestRiskLevel === 'CAUTION'
                  ? 'text-amber-600'
                  : 'text-emerald-600'
              }`}
            >
              {decision.highestRiskLevel}
            </div>
          </div>

          <div className={`p-1.5 rounded border text-center ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Risk Level</div>
            <div
              className={`text-xs font-black mt-0.5 ${
                decision.overallState === 'CRITICAL' || decision.overallState === 'DEGRADED'
                  ? 'text-rose-600'
                  : decision.overallState === 'WARNING'
                  ? 'text-amber-600'
                  : 'text-emerald-600'
              }`}
            >
              {decision.overallState}
            </div>
          </div>

          <div className={`p-1.5 rounded border text-center ${
            isLight ? 'bg-stone-200/80 border-stone-300' : 'bg-neutral-950/70 border-neutral-800/80'
          }`}>
            <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Interlock Action</div>
            <div
              className={`text-xs font-black mt-0.5 ${
                decision.action === 'STOP'
                  ? 'text-rose-600'
                  : decision.action === 'ALERT'
                  ? 'text-amber-600'
                  : isLight ? 'text-cyan-800' : 'text-cyan-300'
              }`}
            >
              {decision.action}
            </div>
          </div>
        </div>

        {decision.highestRiskWorkerId && (
          <div className={`px-2 py-1 rounded border text-[11px] font-mono flex items-center justify-between ${
            isLight ? 'bg-stone-200 border-stone-300 text-stone-800' : 'bg-neutral-950/80 border-neutral-800 text-neutral-300'
          }`}>
            <span>HIGHEST RISK TARGET:</span>
            <span className={`font-bold uppercase ${isLight ? 'text-stone-900' : 'text-white'}`}>{decision.highestRiskWorkerId}</span>
          </div>
        )}
      </div>

      {/* 4. Worker Telemetry Breakdown */}
      <div className="space-y-1.5">
        <div className={`flex items-center justify-between text-xs font-mono ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>
          <span className="flex items-center gap-1">
            <Users className="w-3.5 h-3.5" />
            <span>Worker Proximity Register</span>
          </span>
          <span className="text-[10px]">GROUND-PLANE</span>
        </div>

        <div className="space-y-1">
          {workers.map((w) => {
            const isDanger = w.zone === 'DANGER';
            const isCaution = w.zone === 'CAUTION';

            return (
              <div
                key={w.id}
                className={`p-1.5 rounded border text-xs font-mono flex items-center justify-between transition-colors ${
                  isDanger
                    ? isLight ? 'bg-rose-100 border-rose-300 text-rose-900' : 'bg-rose-950/40 border-rose-800/80 text-rose-200'
                    : isCaution
                    ? isLight ? 'bg-amber-100 border-amber-300 text-amber-900' : 'bg-amber-950/30 border-amber-800/60 text-amber-200'
                    : isLight ? 'bg-stone-200/60 border-stone-300 text-stone-800' : 'bg-neutral-950/50 border-neutral-800 text-neutral-300'
                }`}
              >
                <div>
                  <div className={`font-bold flex items-center gap-1.5 ${isLight ? 'text-stone-950' : 'text-white'}`}>
                    <span>{w.name}</span>
                    <span className={`text-[10px] font-normal ${isLight ? 'text-stone-500' : 'text-neutral-400'}`}>({w.role})</span>
                  </div>
                  <div className={`text-[10px] flex items-center gap-2 mt-0.5 ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>
                    <span>Machine: <strong className={isLight ? 'text-stone-950' : 'text-white'}>{w.machineDistance}m</strong></span>
                    <span>Camera: {w.cameraDistance}m</span>
                    <span>Conf: {w.confidence}%</span>
                  </div>
                </div>

                <div className="text-right">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                      isDanger
                        ? 'bg-rose-600 text-white'
                        : isCaution
                        ? 'bg-amber-500 text-neutral-950'
                        : isLight ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                    }`}
                  >
                    {w.zone}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
