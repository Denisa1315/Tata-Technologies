import React from 'react';
import { X, BarChart3, AlertOctagon, AlertTriangle, ShieldCheck, Camera, Users, Clock } from 'lucide-react';
import { IncidentStats } from '../types';

interface IncidentSummaryModalProps {
  isOpen: boolean;
  onClose: () => void;
  stats: IncidentStats;
  theme?: 'dark' | 'light';
}

export const IncidentSummaryModal: React.FC<IncidentSummaryModalProps> = ({
  isOpen,
  onClose,
  stats,
  theme = 'dark',
}) => {
  if (!isOpen) return null;
  const isLight = theme === 'light';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className={`w-full max-w-lg border rounded-xl shadow-2xl overflow-hidden font-mono transition-colors ${
        isLight ? 'bg-stone-50 border-stone-300 text-stone-900' : 'bg-neutral-900 border-neutral-700 text-neutral-200'
      }`}>
        {/* Header */}
        <div className={`px-5 py-3.5 border-b flex items-center justify-between ${
          isLight ? 'bg-stone-200 border-stone-300' : 'bg-neutral-950 border-neutral-800'
        }`}>
          <div className="flex items-center gap-2 text-cyan-600 dark:text-cyan-400">
            <BarChart3 className="w-5 h-5" />
            <h2 className={`text-sm font-bold uppercase tracking-wider ${isLight ? 'text-stone-900' : 'text-white'}`}>
              Incident Audit Summary · Run Telemetry
            </h2>
          </div>
          <button
            onClick={onClose}
            className={`p-1 rounded transition-colors ${
              isLight ? 'text-stone-600 hover:text-stone-950 hover:bg-stone-300' : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
            }`}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stats Grid */}
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className={`p-3 rounded-lg border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
              <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                <AlertTriangle className="w-4 h-4" />
                <span className="font-semibold">Caution Events</span>
              </div>
              <div className={`text-2xl font-bold mt-1 tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
                {stats.cautionEvents}
              </div>
              <div className={`text-[10px] mt-0.5 ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Early warnings issued</div>
            </div>

            <div className={`p-3 rounded-lg border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
              <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400">
                <AlertOctagon className="w-4 h-4" />
                <span className="font-semibold">Danger Events</span>
              </div>
              <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-1 tabular-nums">
                {stats.dangerEvents}
              </div>
              <div className={`text-[10px] mt-0.5 ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Direct zone penetrations</div>
            </div>

            <div className={`p-3 rounded-lg border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
              <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-500">
                <ShieldCheck className="w-4 h-4" />
                <span className="font-semibold">STOP Commands</span>
              </div>
              <div className={`text-2xl font-bold mt-1 tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
                {stats.stopCommands}
              </div>
              <div className={`text-[10px] mt-0.5 ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Hydraulic interlocks tripped</div>
            </div>

            <div className={`p-3 rounded-lg border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
              <div className="flex items-center gap-1.5 text-cyan-600 dark:text-cyan-400">
                <Clock className="w-4 h-4" />
                <span className="font-semibold">Time in Danger</span>
              </div>
              <div className={`text-2xl font-bold mt-1 tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
                {stats.timeInDangerSec.toFixed(1)} s
              </div>
              <div className={`text-[10px] mt-0.5 ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Cumulative hazard duration</div>
            </div>

            <div className={`p-3 rounded-lg border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
              <div className="flex items-center gap-1.5 text-purple-600 dark:text-purple-400">
                <Camera className="w-4 h-4" />
                <span className="font-semibold">Camera Faults</span>
              </div>
              <div className={`text-2xl font-bold mt-1 tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
                {stats.cameraFaults}
              </div>
              <div className={`text-[10px] mt-0.5 ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Fail-safe trip occurrences</div>
            </div>

            <div className={`p-3 rounded-lg border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
              <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                <Users className="w-4 h-4" />
                <span className="font-semibold">Workers Detected</span>
              </div>
              <div className={`text-2xl font-bold mt-1 tabular-nums ${isLight ? 'text-stone-900' : 'text-white'}`}>
                {stats.workersDetected}
              </div>
              <div className={`text-[10px] mt-0.5 ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Active trackable subjects</div>
            </div>
          </div>

          {/* Decision Latency Metric */}
          <div className={`p-3 rounded-lg border flex items-center justify-between text-xs ${
            isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'
          }`}>
            <div>
              <div className={`font-semibold ${isLight ? 'text-stone-700' : 'text-neutral-400'}`}>Average Decision Latency</div>
              <div className={`text-[10px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Edge closed-loop inference + risk cycle</div>
            </div>
            <div className={`text-xl font-bold tabular-nums ${isLight ? 'text-cyan-800' : 'text-cyan-300'}`}>
              {stats.avgDecisionLatencyMs} ms
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className={`px-5 py-3 border-t flex justify-end ${
          isLight ? 'bg-stone-200 border-stone-300' : 'bg-neutral-950 border-neutral-800'
        }`}>
          <button
            onClick={onClose}
            className={`px-4 py-1.5 rounded text-xs font-semibold transition-colors ${
              isLight ? 'bg-stone-300 hover:bg-stone-400 text-stone-900' : 'bg-neutral-800 hover:bg-neutral-700 text-white'
            }`}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
