import React from 'react';
import { X, CheckCircle, AlertTriangle, AlertOctagon, HelpCircle, ShieldAlert } from 'lucide-react';
import { SafetyDecision, ExcavatorKinematics, WorkerData } from '../types';

interface ExplainDecisionModalProps {
  isOpen: boolean;
  onClose: () => void;
  decision: SafetyDecision;
  machine: ExcavatorKinematics;
  workers: WorkerData[];
  theme?: 'dark' | 'light';
}

export const ExplainDecisionModal: React.FC<ExplainDecisionModalProps> = ({
  isOpen,
  onClose,
  decision,
  machine,
  workers,
  theme = 'dark',
}) => {
  if (!isOpen) return null;
  const isLight = theme === 'light';

  const breakdown = decision.whyBreakdown;
  const targetWorker = workers.find((w) => w.id === breakdown?.workerId) || workers[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className={`w-full max-w-2xl border rounded-xl shadow-2xl overflow-hidden font-mono transition-colors ${
        isLight ? 'bg-stone-50 border-stone-300 text-stone-900' : 'bg-neutral-900 border-neutral-700 text-neutral-200'
      }`}>
        {/* Header */}
        <div className={`px-5 py-3.5 border-b flex items-center justify-between ${
          isLight ? 'bg-stone-200 border-stone-300' : 'bg-neutral-950 border-neutral-800'
        }`}>
          <div className="flex items-center gap-2 text-cyan-600 dark:text-cyan-400">
            <HelpCircle className="w-5 h-5" />
            <h2 className={`text-sm font-bold uppercase tracking-wider ${isLight ? 'text-stone-900' : 'text-white'}`}>
              Explainable AI Risk Engine · Decision Rationale
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

        {/* Content Body */}
        <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
          {/* Top Banner Decision State */}
          <div
            className={`p-3 rounded-lg border flex items-start gap-3 ${
              decision.overallState === 'CRITICAL'
                ? isLight ? 'bg-rose-100 border-rose-300 text-rose-950' : 'bg-rose-950/40 border-rose-800/80 text-rose-200'
                : decision.overallState === 'DEGRADED'
                ? isLight ? 'bg-purple-100 border-purple-300 text-purple-950' : 'bg-purple-950/40 border-purple-800/80 text-purple-200'
                : decision.overallState === 'WARNING'
                ? isLight ? 'bg-amber-100 border-amber-300 text-amber-950' : 'bg-amber-950/40 border-amber-800/80 text-amber-200'
                : isLight ? 'bg-emerald-100 border-emerald-300 text-emerald-950' : 'bg-emerald-950/40 border-emerald-800/80 text-emerald-200'
            }`}
          >
            {decision.overallState === 'CRITICAL' ? (
              <AlertOctagon className="w-6 h-6 text-rose-500 shrink-0 mt-0.5" />
            ) : decision.overallState === 'WARNING' ? (
              <AlertTriangle className="w-6 h-6 text-amber-500 shrink-0 mt-0.5" />
            ) : (
              <CheckCircle className="w-6 h-6 text-emerald-500 shrink-0 mt-0.5" />
            )}
            <div>
              <div className={`text-sm font-bold uppercase tracking-wider ${isLight ? 'text-stone-900' : 'text-white'}`}>
                Decision: {decision.overallState} · Action: {decision.action}
              </div>
              <p className={`text-xs mt-1 ${isLight ? 'text-stone-700' : 'text-neutral-300'}`}>
                {breakdown?.evalResult || 'All workers outside dynamic hazard perimeters.'}
              </p>
              {breakdown?.ruleCode && (
                <div className={`text-[10px] mt-1.5 px-2 py-0.5 rounded inline-block border ${
                  isLight ? 'bg-white text-cyan-800 border-cyan-300' : 'bg-black/40 text-cyan-300 border-neutral-700'
                }`}>
                  {breakdown.ruleCode}
                </div>
              )}
            </div>
          </div>

          {/* Mathematical Proof Matrix */}
          {breakdown && targetWorker && (
            <div className="space-y-2">
              <h3 className={`text-xs uppercase font-bold tracking-wider ${isLight ? 'text-stone-700' : 'text-neutral-400'}`}>
                Parameter Evaluation Matrix ({targetWorker.name} / {targetWorker.id})
              </h3>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                <div className={`p-2 rounded border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
                  <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Machine-Relative Distance</div>
                  <div className={`text-base font-bold mt-0.5 ${isLight ? 'text-stone-900' : 'text-white'}`}>
                    {breakdown.machineDistance} m
                  </div>
                  <div className={`text-[9px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>True ground-plane offset</div>
                </div>

                <div className={`p-2 rounded border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
                  <div className="text-[10px] text-rose-500 font-semibold">Danger Boundary</div>
                  <div className="text-base font-bold text-rose-600 mt-0.5">
                    {breakdown.dangerThreshold} m
                  </div>
                  <div className={`text-[9px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Includes swing expansion</div>
                </div>

                <div className={`p-2 rounded border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
                  <div className="text-[10px] text-amber-600 font-semibold">Caution Boundary</div>
                  <div className="text-base font-bold text-amber-600 mt-0.5">
                    {breakdown.cautionThreshold} m
                  </div>
                  <div className={`text-[9px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Early warning threshold</div>
                </div>

                <div className={`p-2 rounded border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
                  <div className={`text-[10px] ${isLight ? 'text-cyan-800 font-semibold' : 'text-cyan-400'}`}>Swing Speed Factor</div>
                  <div className={`text-base font-bold mt-0.5 ${isLight ? 'text-cyan-900' : 'text-cyan-300'}`}>
                    {machine.swingSpeed}°/s (+{breakdown.swingSpeedContribution}m)
                  </div>
                  <div className={`text-[9px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Kinematic lead applied</div>
                </div>

                <div className={`p-2 rounded border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
                  <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Camera-to-Worker Distance</div>
                  <div className={`text-base font-bold mt-0.5 ${isLight ? 'text-stone-900' : 'text-white'}`}>
                    {targetWorker.cameraDistance} m
                  </div>
                  <div className={`text-[9px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Used for uncertainty weight</div>
                </div>

                <div className={`p-2 rounded border ${isLight ? 'bg-stone-200/60 border-stone-300' : 'bg-neutral-950 border-neutral-800'}`}>
                  <div className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-neutral-400'}`}>Position Confidence</div>
                  <div className={`text-base font-bold mt-0.5 ${isLight ? 'text-stone-900' : 'text-white'}`}>
                    {breakdown.confidence}% ({breakdown.confidenceLevel})
                  </div>
                  <div className={`text-[9px] ${isLight ? 'text-stone-500' : 'text-neutral-500'}`}>Optical clarity factor</div>
                </div>
              </div>
            </div>
          )}

          {/* Conservative Safety Margin Note */}
          {breakdown?.conservativeSafetyBuffer ? (
            <div className={`p-2.5 rounded border text-xs flex items-start gap-2 ${
              isLight ? 'bg-cyan-100 border-cyan-300 text-cyan-900' : 'bg-cyan-950/40 border-cyan-800/80 text-cyan-200'
            }`}>
              <ShieldAlert className={`w-4 h-4 shrink-0 mt-0.5 ${isLight ? 'text-cyan-800' : 'text-cyan-400'}`} />
              <div>
                <strong>Conservative Safety Mode Engaged:</strong> Due to low confidence ({breakdown.confidence}%), the risk engine automatically expanded safety margins by +{breakdown.conservativeSafetyBuffer}m to prevent false negatives.
              </div>
            </div>
          ) : null}

          {/* Verification Protocol */}
          <div className={`p-3 rounded border text-[11px] space-y-1 ${
            isLight ? 'bg-stone-200/80 border-stone-300 text-stone-700' : 'bg-neutral-950/70 border-neutral-800 text-neutral-400'
          }`}>
            <div className={`font-bold uppercase tracking-wider ${isLight ? 'text-stone-900' : 'text-neutral-300'}`}>
              Safety Verification Invariant:
            </div>
            <ul className="list-disc pl-4 space-y-0.5">
              <li>Deterministic risk calculation running locally on the edge loop.</li>
              <li>Immediate escalation to CRITICAL / STOP; hysteresis debouncing on hazard clearance.</li>
              <li>Perception loss (camera blocked/disconnected or FPS drop) enforces immediate fail-safe stop.</li>
            </ul>
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
            Close Breakdown
          </button>
        </div>
      </div>
    </div>
  );
};
