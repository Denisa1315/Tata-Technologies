import React from 'react';
import { ShieldCheck, AlertTriangle, AlertOctagon, Timer, Zap } from 'lucide-react';
import { SafetyDecision, PerceptionSystem } from '../types';

interface StateBannerProps {
  decision: SafetyDecision;
  perception: PerceptionSystem;
  theme?: 'dark' | 'light';
}

export const StateBanner: React.FC<StateBannerProps> = ({ decision, perception, theme = 'dark' }) => {
  const { overallState, stopReason, debounceActive, debounceRemainingMs, highestRiskWorkerId } = decision;
  const isLight = theme === 'light';

  // DEGRADED FAIL-SAFE ALERT
  if (overallState === 'DEGRADED') {
    return (
      <div className={`w-full py-1.5 px-4 border-b flex items-center justify-between transition-all shrink-0 z-20 ${
        isLight
          ? 'bg-rose-100 border-rose-400 text-rose-950 shadow-sm'
          : 'bg-red-950/90 border-red-500/80 text-red-100 shadow-[0_0_20px_rgba(239,68,68,0.3)]'
      }`}>
        <div className="max-w-7xl mx-auto w-full flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded bg-red-600 flex items-center justify-center text-white shrink-0 animate-bounce">
              <Zap className="w-3.5 h-3.5" />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className={`font-black uppercase tracking-wider ${isLight ? 'text-red-900' : 'text-red-200'}`}>
                FAIL-SAFE ACTIVE:
              </span>
              <span className={`font-medium truncate max-w-sm md:max-w-md ${isLight ? 'text-red-800' : 'text-red-200'}`}>
                {stopReason || 'Optical sensor fault or inference frame drop. Machine slew locked in safe state.'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="px-2 py-0.5 rounded bg-red-600 text-white font-mono text-[11px] font-black uppercase tracking-wider animate-pulse">
              SLEW LOCKED (SAFE STATE)
            </span>
          </div>
        </div>
      </div>
    );
  }

  // CRITICAL EMERGENCY STOP ALERT
  if (overallState === 'CRITICAL') {
    return (
      <div className={`w-full py-1.5 px-4 border-b flex items-center justify-between transition-all shrink-0 z-20 ${
        isLight
          ? 'bg-red-100 border-red-500 text-red-950 shadow-sm'
          : 'bg-rose-950/95 border-rose-500 text-white shadow-[0_0_25px_rgba(244,63,94,0.4)]'
      }`}>
        <div className="max-w-7xl mx-auto w-full flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded bg-rose-600 flex items-center justify-center text-white shrink-0 animate-pulse">
              <AlertOctagon className="w-3.5 h-3.5" />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="font-black uppercase tracking-wider text-rose-500 dark:text-rose-300">
                EMERGENCY STOP:
              </span>
              <span className={`font-medium truncate max-w-sm md:max-w-md ${isLight ? 'text-red-900' : 'text-rose-100'}`}>
                {stopReason || `Worker ${highestRiskWorkerId || ''} entered dynamic danger zone.`}
              </span>
              {debounceActive && (
                <span className={`flex items-center gap-1 px-1.5 py-0.2 rounded border text-[10px] font-mono ${
                  isLight ? 'bg-amber-100 text-amber-900 border-amber-400' : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                }`}>
                  <Timer className="w-3 h-3 animate-spin" />
                  Debounce ({(debounceRemainingMs / 1000).toFixed(1)}s)
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="px-2 py-0.5 rounded bg-rose-600 text-white font-mono text-[11px] font-black uppercase tracking-wider shadow-[0_0_12px_#f43f5e] animate-pulse">
              HYDRAULIC SLEW LOCKED
            </span>
          </div>
        </div>
      </div>
    );
  }

  // WARNING CAUTION ALERT
  if (overallState === 'WARNING') {
    return (
      <div className={`w-full py-1.5 px-4 border-b flex items-center justify-between transition-all shrink-0 z-20 ${
        isLight
          ? 'bg-amber-100/90 border-amber-400 text-amber-950 shadow-sm'
          : 'bg-amber-950/80 border-amber-500/80 text-neutral-100 shadow-[0_0_15px_rgba(245,158,11,0.2)]'
      }`}>
        <div className="max-w-7xl mx-auto w-full flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded bg-amber-500 flex items-center justify-center text-neutral-950 shrink-0">
              <AlertTriangle className="w-3.5 h-3.5 animate-pulse" />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className={`font-black uppercase tracking-wider ${isLight ? 'text-amber-900' : 'text-amber-300'}`}>
                PROXIMITY WARNING:
              </span>
              <span className={`font-medium truncate max-w-sm md:max-w-md ${isLight ? 'text-amber-900' : 'text-amber-200'}`}>
                Worker entering caution zone · Dynamic swing trajectory monitored.
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`px-2 py-0.5 rounded font-mono text-[11px] font-bold uppercase tracking-wider ${
              isLight ? 'bg-amber-300 text-amber-950 border border-amber-400' : 'bg-amber-500 text-neutral-950'
            }`}>
              SWING CAUTION · ALERT SOUNDED
            </span>
          </div>
        </div>
      </div>
    );
  }

  // SAFE STATE (Slim, elegant single-line reassurance bar with 0 clutter)
  return (
    <div className={`w-full py-1 px-4 border-b flex items-center justify-between transition-all shrink-0 z-20 ${
      isLight
        ? 'bg-stone-100 border-stone-200 text-stone-700'
        : 'bg-neutral-950/80 border-neutral-800/80 text-neutral-400'
    }`}>
      <div className="max-w-7xl mx-auto w-full flex items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_#10b981]" />
          <span className={`font-bold ${isLight ? 'text-emerald-800' : 'text-emerald-400'}`}>
            PERIMETER NOMINAL:
          </span>
          <span className={`hidden sm:inline ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>
            All detected personnel outside dynamic swing perimeter. Standard slew authorized.
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <span className={`hidden md:inline ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>
            Fail-Safe Watchdog: <strong className={isLight ? 'text-emerald-700' : 'text-emerald-400'}>Active (19ms)</strong>
          </span>
          <span className={`px-2 py-0.2 rounded border font-semibold uppercase ${
            isLight ? 'bg-emerald-50 text-emerald-800 border-emerald-300' : 'bg-emerald-950/60 text-emerald-400 border-emerald-800/50'
          }`}>
            ACTION: MONITOR
          </span>
        </div>
      </div>
    </div>
  );
};
