import React from 'react';
import { Play, Pause, RotateCcw, FastForward, Film } from 'lucide-react';

interface GuidedDemoBarProps {
  isRunning: boolean;
  currentStepIndex: number;
  totalSteps: number;
  stepTitle: string;
  stepDescription: string;
  progressPercent: number;
  onStartDemo: () => void;
  onPauseDemo: () => void;
  onResumeDemo: () => void;
  onResetDemo: () => void;
  onSkipStep: () => void;
  onSelectScenario: (scenarioId: number) => void;
  theme?: 'dark' | 'light';
}

export const GuidedDemoBar: React.FC<GuidedDemoBarProps> = ({
  isRunning,
  currentStepIndex,
  totalSteps,
  stepTitle,
  stepDescription,
  progressPercent,
  onStartDemo,
  onPauseDemo,
  onResumeDemo,
  onResetDemo,
  onSkipStep,
  onSelectScenario,
  theme = 'dark',
}) => {
  const isLight = theme === 'light';

  return (
    <div className={`border-t px-3 sm:px-5 py-2 font-mono transition-colors shrink-0 z-20 ${
      isLight ? 'bg-stone-100 border-stone-300' : 'bg-neutral-900 border-neutral-800'
    }`}>
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-2.5">
        {/* 1. Quick Scenario Test Buttons (The 5 Key Conditions) */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className={`text-[10px] uppercase font-bold mr-1 flex items-center gap-1 ${
            isLight ? 'text-stone-600' : 'text-neutral-400'
          }`}>
            <Film className={`w-3.5 h-3.5 ${isLight ? 'text-cyan-800' : 'text-cyan-400'}`} />
            <span>Test Scenarios:</span>
          </span>

          <button
            onClick={() => onSelectScenario(1)}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
              isLight
                ? 'bg-stone-200 hover:bg-stone-300 text-stone-800 border-stone-300'
                : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border-neutral-700'
            }`}
            title="Scenario 1: Worker far outside perimeter (Standard nominal operation)"
          >
            1. All Clear
          </button>

          <button
            onClick={() => onSelectScenario(2)}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
              isLight
                ? 'bg-stone-200 hover:bg-stone-300 text-stone-800 border-stone-300'
                : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border-neutral-700'
            }`}
            title="Scenario 2: Rapid boom slew - watch dynamic safety zone expand"
          >
            2. Rapid Slew
          </button>

          <button
            onClick={() => onSelectScenario(3)}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
              isLight
                ? 'bg-amber-100 hover:bg-amber-200 text-amber-950 border-amber-300'
                : 'bg-amber-950/60 hover:bg-amber-900/60 text-amber-300 border-amber-800/50'
            }`}
            title="Scenario 3: Worker enters early caution zone"
          >
            3. Caution Alert
          </button>

          <button
            onClick={() => onSelectScenario(4)}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
              isLight
                ? 'bg-rose-100 hover:bg-rose-200 text-rose-950 border-rose-300'
                : 'bg-rose-950/60 hover:bg-rose-900/60 text-rose-300 border-rose-800/50'
            }`}
            title="Scenario 4: Worker penetrates danger zone - automatic emergency slew stop"
          >
            4. Danger Stop
          </button>

          <button
            onClick={() => onSelectScenario(6)}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
              isLight
                ? 'bg-purple-100 hover:bg-purple-200 text-purple-950 border-purple-300'
                : 'bg-purple-950/60 hover:bg-purple-900/60 text-purple-300 border-purple-800/50'
            }`}
            title="Scenario 5: Optical sensor failure - fail-safe locked safe state"
          >
            5. Fail-Safe Fault
          </button>
        </div>

        {/* 2. 60-Second Guided Demo Player (Executive Tour for Judges) */}
        <div className="flex items-center gap-2 w-full md:w-auto justify-end">
          {isRunning ? (
            <div className={`flex items-center gap-2.5 px-3 py-1 rounded-xl border shadow-sm ${
              isLight ? 'bg-white border-cyan-400' : 'bg-neutral-950 border-cyan-800/70'
            }`}>
              <div className="flex flex-col text-right">
                <div className={`text-xs font-bold flex items-center justify-end gap-1.5 ${
                  isLight ? 'text-cyan-900' : 'text-cyan-300'
                }`}>
                  <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
                  <span>
                    STEP {currentStepIndex + 1}/{totalSteps}: {stepTitle}
                  </span>
                </div>
                <div className={`text-[10px] truncate max-w-xs md:max-w-sm ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>
                  {stepDescription}
                </div>
              </div>

              {/* Progress bar */}
              <div className={`w-16 h-1.5 rounded-full overflow-hidden ${isLight ? 'bg-stone-200' : 'bg-neutral-800'}`}>
                <div
                  className="h-full bg-cyan-500 transition-all duration-200"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={onPauseDemo}
                  className={`p-1 rounded-lg ${isLight ? 'bg-stone-200 hover:bg-stone-300 text-stone-800' : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-300'}`}
                  title="Pause Demo"
                >
                  <Pause className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onSkipStep}
                  className={`p-1 rounded-lg ${isLight ? 'bg-stone-200 hover:bg-stone-300 text-stone-800' : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-300'}`}
                  title="Next Step"
                >
                  <FastForward className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onResetDemo}
                  className={`p-1 rounded-lg ${isLight ? 'bg-stone-200 hover:bg-stone-300 text-stone-800' : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-300'}`}
                  title="Exit Demo"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={onStartDemo}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-neutral-950 font-black text-xs shadow-md shadow-amber-950/20 transition-all cursor-pointer"
              title="Start an automated 60-second guided safety demonstration"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>RUN 60s GUIDED DEMO</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
