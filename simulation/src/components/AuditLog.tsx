import React, { useRef, useEffect } from 'react';
import { Terminal, Trash2, ChevronUp, ChevronDown, ArrowUpRight } from 'lucide-react';
import { AuditLogEntry } from '../types';

interface AuditLogProps {
  logs: AuditLogEntry[];
  onClearLogs: () => void;
  isOpen: boolean;
  onToggleOpen: () => void;
  theme?: 'dark' | 'light';
}

export const AuditLog: React.FC<AuditLogProps> = ({
  logs,
  onClearLogs,
  isOpen,
  onToggleOpen,
  theme = 'dark',
}) => {
  const isLight = theme === 'light';
  const scrollRef = useRef<HTMLDivElement>(null);
  const latestEntry = logs[logs.length - 1];

  // Auto-scroll when new logs arrive
  useEffect(() => {
    if (scrollRef.current && isOpen) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isOpen]);

  return (
    <div className={`border-t font-mono transition-all duration-200 select-none ${
      isLight ? 'bg-stone-100 border-stone-300' : 'bg-neutral-900 border-neutral-800'
    } ${isOpen ? 'h-40 flex flex-col' : 'h-8 shrink-0'}`}>
      {/* 1. Bar Header / Collapsed Ticker Strip */}
      <div className={`h-8 px-4 flex items-center justify-between shrink-0 text-xs cursor-pointer ${
        isLight ? 'bg-stone-200/90 text-stone-800' : 'bg-neutral-950 text-neutral-300'
      }`} onClick={onToggleOpen}>
        <div className="flex items-center gap-2.5 overflow-hidden">
          <Terminal className={`w-3.5 h-3.5 shrink-0 ${isLight ? 'text-cyan-800' : 'text-cyan-400'}`} />
          <span className="font-bold uppercase tracking-wider text-[11px] shrink-0">
            SAFETY BLACKBOX
          </span>
          <span className={`text-[10px] shrink-0 ${isLight ? 'text-stone-600' : 'text-neutral-500'}`}>
            ({logs.length} logged)
          </span>

          {/* Collapsed live ticker showing the most recent event */}
          {!isOpen && latestEntry && (
            <div className="flex items-center gap-2 text-[11px] truncate opacity-90 pl-2 border-l border-neutral-700/50">
              <span className={`font-mono text-[10px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>
                [{latestEntry.timestamp}]
              </span>
              <span className={`font-bold ${
                latestEntry.machineState === 'CRITICAL' || latestEntry.machineState === 'DEGRADED'
                  ? 'text-rose-500'
                  : latestEntry.machineState === 'WARNING'
                  ? 'text-amber-500'
                  : isLight ? 'text-emerald-800' : 'text-emerald-400'
              }`}>
                {latestEntry.event}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
          {isOpen && (
            <button
              onClick={onClearLogs}
              className={`flex items-center gap-1 text-[11px] px-2 py-0.5 rounded transition-colors ${
                isLight ? 'text-stone-600 hover:text-stone-900 hover:bg-stone-300' : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
              }`}
              title="Clear Event Log"
            >
              <Trash2 className="w-3 h-3" />
              <span>Clear</span>
            </button>
          )}

          <button
            onClick={onToggleOpen}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border transition-all ${
              isOpen
                ? isLight ? 'bg-stone-300 border-stone-400 text-stone-900' : 'bg-neutral-800 border-neutral-700 text-white'
                : isLight ? 'bg-stone-100 border-stone-300 text-stone-700 hover:bg-stone-200' : 'bg-neutral-900 border-neutral-800 text-neutral-400 hover:text-white'
            }`}
          >
            <span>{isOpen ? 'Minimize' : 'View Audit Log'}</span>
            {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* 2. Expanded Event List (Only rendered when open) */}
      {isOpen && (
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-2 space-y-1 text-xs select-text"
        >
          {logs.length === 0 ? (
            <div className={`text-center py-4 italic text-xs ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>
              Zero safety incidents logged. Edge Guardian loop nominal.
            </div>
          ) : (
            logs.map((entry) => {
              const isDangerOrStop = entry.type === 'DANGER' || entry.type === 'STOP';
              const isCaution = entry.type === 'CAUTION';
              const isFault = entry.type === 'FAULT';
              const isResume = entry.type === 'RESUME';

              return (
                <div
                  key={entry.id}
                  className={`px-2.5 py-1 rounded border flex items-center justify-between text-xs transition-all ${
                    isDangerOrStop
                      ? isLight ? 'bg-rose-50 border-rose-300 text-rose-950 font-medium' : 'bg-rose-950/40 border-rose-800/80 text-rose-200'
                      : isFault
                      ? isLight ? 'bg-purple-50 border-purple-300 text-purple-950 font-medium' : 'bg-purple-950/40 border-purple-800/80 text-purple-200'
                      : isCaution
                      ? isLight ? 'bg-amber-50 border-amber-300 text-amber-950 font-medium' : 'bg-amber-950/30 border-amber-800/60 text-amber-200'
                      : isResume
                      ? isLight ? 'bg-emerald-50 border-emerald-300 text-emerald-950 font-medium' : 'bg-emerald-950/30 border-emerald-800/60 text-emerald-200'
                      : isLight ? 'bg-white border-stone-300 text-stone-800' : 'bg-neutral-950/40 border-neutral-800 text-neutral-300'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className={`text-[11px] tabular-nums ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>
                      [{entry.timestamp}]
                    </span>

                    {entry.workerId && (
                      <span className={`font-bold uppercase text-[11px] ${isLight ? 'text-stone-900' : 'text-white'}`}>
                        {entry.workerName || entry.workerId}
                      </span>
                    )}

                    <span className="flex items-center gap-1 font-semibold">
                      <ArrowUpRight className={`w-3 h-3 ${isLight ? 'text-stone-500' : 'text-neutral-400'}`} />
                      <span>{entry.event}</span>
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        entry.machineState === 'CRITICAL' || entry.machineState === 'DEGRADED'
                          ? 'bg-rose-500 text-white'
                          : entry.machineState === 'WARNING'
                          ? 'bg-amber-500 text-neutral-950'
                          : isLight ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                      }`}
                    >
                      {entry.machineState}
                    </span>

                    <span className={`text-[10px] font-mono hidden sm:inline ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>
                      {entry.action}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
