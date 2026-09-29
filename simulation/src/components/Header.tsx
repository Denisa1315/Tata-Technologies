import React from 'react';
import {
  Volume2,
  VolumeX,
  ShieldCheck,
  AlertTriangle,
  AlertOctagon,
  Zap,
  MonitorPlay,
  BarChart3,
  HelpCircle,
  Sun,
  Moon,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import { CameraStatus, MachineRiskState, ThemeMode } from '../types';

interface HeaderProps {
  cameraStatus: CameraStatus;
  machineState: MachineRiskState;
  isStopIssued: boolean;
  nearestWorkerDistance: number | null;
  slewSpeed: number;
  isMuted: boolean;
  isPresentationMode: boolean;
  isSidebarOpen: boolean;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onToggleMute: () => void;
  onTogglePresentation: () => void;
  onToggleSidebar: () => void;
  onOpenSummary: () => void;
  onOpenExplain: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  cameraStatus,
  machineState,
  isStopIssued,
  nearestWorkerDistance,
  slewSpeed,
  isMuted,
  isPresentationMode,
  isSidebarOpen,
  theme,
  onToggleTheme,
  onToggleMute,
  onTogglePresentation,
  onToggleSidebar,
  onOpenSummary,
  onOpenExplain,
}) => {
  const isCameraOk = cameraStatus === 'ONLINE';
  const isLight = theme === 'light';

  // Get Primary Glanceable Badge config
  const getStatusBadge = () => {
    if (machineState === 'DEGRADED') {
      return {
        label: 'FAIL-SAFE STOP',
        sub: 'Sensor Degraded · Slew Locked',
        bg: isLight ? 'bg-rose-100 text-rose-900 border-rose-400' : 'bg-red-950/80 text-rose-200 border-rose-600',
        dot: 'bg-rose-500 animate-ping',
        icon: <Zap className="w-4 h-4 text-rose-500" />,
      };
    }
    if (machineState === 'CRITICAL' || isStopIssued) {
      return {
        label: 'EMERGENCY STOP',
        sub: 'Worker in Danger Zone · Slew Locked',
        bg: isLight ? 'bg-red-100 text-red-900 border-red-500 shadow-red-200' : 'bg-rose-950/90 text-rose-200 border-rose-500 shadow-[0_0_15px_rgba(244,63,94,0.4)]',
        dot: 'bg-rose-500 animate-pulse',
        icon: <AlertOctagon className="w-4 h-4 text-rose-500 animate-spin" style={{ animationDuration: '4s' }} />,
      };
    }
    if (machineState === 'WARNING') {
      return {
        label: 'PROXIMITY CAUTION',
        sub: 'Worker Approaching · Slew Alert',
        bg: isLight ? 'bg-amber-100 text-amber-950 border-amber-400' : 'bg-amber-950/70 text-amber-200 border-amber-500/70 shadow-[0_0_12px_rgba(245,158,11,0.25)]',
        dot: 'bg-amber-500 animate-pulse',
        icon: <AlertTriangle className="w-4 h-4 text-amber-500" />,
      };
    }
    return {
      label: 'ALL CLEAR · NOMINAL',
      sub: 'Perimeter Safe · Slew Authorized',
      bg: isLight ? 'bg-emerald-50 text-emerald-900 border-emerald-400' : 'bg-emerald-950/60 text-emerald-300 border-emerald-600/60 shadow-[0_0_12px_rgba(16,185,129,0.2)]',
      dot: 'bg-emerald-500 shadow-[0_0_6px_#10b981]',
      icon: <ShieldCheck className="w-4 h-4 text-emerald-500" />,
    };
  };

  const status = getStatusBadge();

  return (
    <header className={`h-14 px-3 sm:px-5 backdrop-blur-md border-b flex items-center justify-between z-30 shrink-0 select-none transition-colors duration-200 ${
      isLight 
        ? 'bg-stone-100/95 border-stone-300 text-stone-900 shadow-sm' 
        : 'bg-neutral-900/90 border-neutral-800 text-neutral-100'
    }`}>
      {/* 1. Left: Machine ID & Edge AI Health */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center shadow-md shadow-amber-950/30 shrink-0">
          <ShieldCheck className="w-5 h-5 text-neutral-950 font-bold" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className={`text-xs sm:text-sm font-extrabold tracking-tight ${isLight ? 'text-stone-900' : 'text-white'}`}>
              SMART-ZONE <span className="text-amber-500">EDGE GUARDIAN</span>
            </h1>
            <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded border font-semibold hidden md:inline-block ${
              isLight ? 'bg-stone-200 text-stone-700 border-stone-400' : 'bg-neutral-800 text-neutral-300 border-neutral-700'
            }`}>
              EX-210 LC
            </span>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono">
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              EDGE AI 19ms
            </span>
            <span className="text-neutral-400 hidden lg:inline">·</span>
            <span className={`hidden lg:inline ${isCameraOk ? (isLight ? 'text-stone-600' : 'text-neutral-400') : 'text-rose-500 font-bold'}`}>
              OPTICAL: {cameraStatus}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Center: PRIMARY GLANCEABLE SAFETY STATUS BADGE (Hero of the Cockpit) */}
      <div className="flex items-center gap-3">
        <div className={`flex items-center gap-2.5 px-3 py-1 rounded-full border shadow-sm transition-all duration-300 ${status.bg}`}>
          {status.icon}
          <div className="flex flex-col text-left">
            <div className="flex items-center gap-1.5 leading-none">
              <span className={`w-2 h-2 rounded-full ${status.dot}`} />
              <span className="text-xs font-black tracking-wider uppercase">
                {status.label}
              </span>
            </div>
            <span className="text-[10px] font-mono opacity-85 leading-tight hidden sm:block">
              {status.sub}
            </span>
          </div>
        </div>

        {/* Quick-glance nearest worker telemetry chip */}
        {nearestWorkerDistance !== null && (
          <div className={`hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-lg border font-mono text-xs ${
            nearestWorkerDistance <= 3.0
              ? 'bg-rose-500/10 border-rose-500/50 text-rose-500 font-bold'
              : nearestWorkerDistance <= 5.0
              ? 'bg-amber-500/10 border-amber-500/50 text-amber-500 font-semibold'
              : isLight ? 'bg-stone-200 border-stone-300 text-stone-700' : 'bg-neutral-800/80 border-neutral-700 text-neutral-300'
          }`}>
            <span className="text-[10px] opacity-75 uppercase">Closest:</span>
            <span className="font-bold text-xs">{nearestWorkerDistance.toFixed(1)}m</span>
          </div>
        )}

        {/* Slew Speed Chip */}
        <div className={`hidden xl:flex items-center gap-1 px-2.5 py-1 rounded-lg border font-mono text-xs ${
          isLight ? 'bg-stone-200 border-stone-300 text-stone-700' : 'bg-neutral-800/80 border-neutral-700 text-neutral-300'
        }`}>
          <span className="text-[10px] opacity-75 uppercase">Slew:</span>
          <span className="font-bold">{slewSpeed > 0 ? `${slewSpeed}°/s` : '0°/s (HOLD)'}</span>
        </div>
      </div>

      {/* 3. Right: Operator Cockpit Tools & Controls */}
      <div className="flex items-center gap-1.5 sm:gap-2">
        {/* Why this decision? Button */}
        <button
          onClick={onOpenExplain}
          className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
            isLight
              ? 'bg-cyan-50 hover:bg-cyan-100 text-cyan-900 border-cyan-300'
              : 'text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/60 border-cyan-800/70'
          }`}
          title="Explain active safety decision & formula breakdown"
        >
          <HelpCircle className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Explain</span>
        </button>

        {/* Run Metrics Button */}
        <button
          onClick={onOpenSummary}
          className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
            isLight
              ? 'bg-stone-200 hover:bg-stone-300 text-stone-800 border-stone-300'
              : 'text-neutral-300 bg-neutral-800 hover:bg-neutral-700 border-neutral-700'
          }`}
          title="Incident Metrics & Compliance Statistics"
        >
          <BarChart3 className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Metrics</span>
        </button>

        {/* White / Dark Theme Switcher */}
        <button
          onClick={onToggleTheme}
          className={`p-1.5 rounded-lg border transition-all ${
            isLight
              ? 'bg-stone-200 hover:bg-stone-300 text-stone-800 border-stone-400'
              : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border-neutral-700'
          }`}
          title={isLight ? 'Switch to Dark Cockpit Mode' : 'Switch to White (Light) Display'}
        >
          {isLight ? <Moon className="w-4 h-4 text-indigo-600" /> : <Sun className="w-4 h-4 text-amber-400" />}
        </button>

        {/* Audio Mute/Unmute */}
        <button
          onClick={onToggleMute}
          className={`p-1.5 rounded-lg border transition-all ${
            isMuted
              ? isLight ? 'text-stone-400 bg-stone-200 border-stone-300' : 'text-neutral-500 bg-neutral-800/80 border-neutral-700'
              : isLight ? 'text-cyan-800 bg-cyan-100 border-cyan-300' : 'text-cyan-400 bg-cyan-950/60 border-cyan-800'
          }`}
          title={isMuted ? 'Unmute Audio Alarms' : 'Mute Audio Alarms'}
        >
          {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>

        {/* Presentation Mode Toggle */}
        <button
          onClick={onTogglePresentation}
          className={`p-1.5 rounded-lg border transition-all ${
            isPresentationMode
              ? 'bg-amber-500/20 text-amber-400 border-amber-500/60 shadow-[0_0_8px_rgba(245,158,11,0.3)]'
              : isLight ? 'bg-stone-200 hover:bg-stone-300 text-stone-800 border-stone-300' : 'bg-neutral-800 text-neutral-200 border-neutral-700 hover:bg-neutral-700'
          }`}
          title="Toggle Fullscreen Presentation Mode"
        >
          <MonitorPlay className="w-4 h-4" />
        </button>

        {/* Sidebar Collapse/Expand Toggle */}
        {!isPresentationMode && (
          <button
            onClick={onToggleSidebar}
            className={`p-1.5 rounded-lg border transition-all ${
              isSidebarOpen
                ? isLight ? 'bg-stone-200 text-stone-800 border-stone-300' : 'bg-neutral-800 text-cyan-400 border-neutral-700'
                : isLight ? 'bg-cyan-100 text-cyan-800 border-cyan-300' : 'bg-neutral-800 text-neutral-400 border-neutral-700'
            }`}
            title={isSidebarOpen ? 'Collapse Right Instrument Panel' : 'Expand Right Instrument Panel'}
          >
            {isSidebarOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </button>
        )}
      </div>
    </header>
  );
};
