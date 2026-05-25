"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Brain, FileSearch, Swords, Crown, Clock, Wifi } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDebateStore } from "@/lib/store";
import { JudgeRubric } from "@/types/debate";

// ---------------------------------------------------------------------------
// Score bar
// ---------------------------------------------------------------------------

interface ScoreComparisonBarProps {
  label: string;
  icon: React.ReactNode;
  twinScore: number;
  challengerScore: number;
  maxScore?: number;
}

function ScoreComparisonBar({ label, icon, twinScore, challengerScore, maxScore = 10 }: ScoreComparisonBarProps) {
  const twinPct = (twinScore / maxScore) * 100;
  const challengerPct = (challengerScore / maxScore) * 100;
  return (
    <div className="space-y-2 rounded-md border border-zinc-800 bg-zinc-950/30 p-2.5">
      <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-mono uppercase tracking-widest">
        {icon}
        {label}
      </div>
      
      {/* Twin Score */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px]">
          <span className="text-cyan-400 font-mono uppercase tracking-wider">Your Twin</span>
          <span className="font-bold text-cyan-400 tabular-nums">{twinScore}/10</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-cyan-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${twinPct}%` }}
            transition={{ duration: 1.2, ease: [0.25, 0.46, 0.45, 0.94], delay: 0.2 }}
          />
        </div>
      </div>

      {/* Challenger Score */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px]">
          <span className="text-rose-400 font-mono uppercase tracking-wider">Challenger</span>
          <span className="font-bold text-rose-400 tabular-nums">{challengerScore}/10</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-rose-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${challengerPct}%` }}
            transition={{ duration: 1.2, ease: [0.25, 0.46, 0.45, 0.94], delay: 0.2 }}
          />
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Winner banner
// ---------------------------------------------------------------------------

function WinnerBanner({ rubric }: { rubric: JudgeRubric }) {
  const isUserTwin = rubric.winner === "user_twin";
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 200, damping: 20 }}
      className={cn(
        "rounded-lg border p-4 text-center space-y-1",
        isUserTwin
          ? "border-cyan-500/30 bg-cyan-500/5"
          : "border-rose-500/30 bg-rose-500/5"
      )}
    >
      <div className="flex items-center justify-center gap-2">
        <Crown className={cn("w-4 h-4", isUserTwin ? "text-cyan-400" : "text-rose-400")} />
        <span className={cn("text-xs font-mono uppercase tracking-[0.2em]", isUserTwin ? "text-cyan-400" : "text-rose-400")}>
          Winner
        </span>
      </div>
      <div className={cn("text-lg font-black tracking-tight", isUserTwin ? "text-cyan-300" : "text-rose-300")}>
        {isUserTwin ? "Your Twin" : "Challenger"}
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Round indicators
// ---------------------------------------------------------------------------

function RoundPips({ current, max }: { current: number; max: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-zinc-500 uppercase tracking-widest">Round</span>
      <div className="flex gap-1.5">
        {Array.from({ length: max }, (_, i) => (
          <motion.div
            key={i}
            className={cn(
              "w-2 h-2 rounded-full border",
              i < current
                ? "bg-amber-400 border-amber-400"
                : i === current - 1 && current <= max
                ? "bg-amber-400/60 border-amber-500 animate-pulse"
                : "bg-zinc-800 border-zinc-700"
            )}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: i * 0.1 }}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live status badge
// ---------------------------------------------------------------------------

function StatusBadge() {
  const session = useDebateStore((s) => s.session);
  const isConnected = useDebateStore((s) => s.isConnected);

  if (!session) return null;

  const statusMap = {
    pending: { label: "Preparing", color: "text-zinc-400" },
    running: { label: "Live Debate", color: "text-emerald-400" },
    judging: { label: "Judging…", color: "text-amber-400" },
    completed: { label: "Concluded", color: "text-cyan-400" },
    error: { label: "Error", color: "text-rose-400" },
  };

  const { label, color } = statusMap[session.status];

  return (
    <div className="flex items-center gap-2">
      <Wifi className={cn("w-3 h-3", isConnected ? "text-emerald-400" : "text-zinc-600")} />
      <span className={cn("text-xs font-mono uppercase tracking-widest", color)}>
        {label}
      </span>
      {session.status === "running" && (
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Scoreboard
// ---------------------------------------------------------------------------

export default function Scoreboard() {
  const session = useDebateStore((s) => s.session);
  const sendConcede = useDebateStore((s) => s.sendConcede);
  const resetDebate = useDebateStore((s) => s.resetDebate);

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
        <Trophy className="w-8 h-8" />
        <p className="text-xs font-mono uppercase tracking-widest">No active debate</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-6 p-1">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-mono uppercase tracking-widest text-zinc-400">Scoreboard</span>
          </div>
          <StatusBadge />
        </div>

        {/* Topic */}
        <div className="rounded-md bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[11px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Topic</p>
          <p className="text-xs text-zinc-200 leading-relaxed line-clamp-3">{session.topic}</p>
        </div>

        <RoundPips current={session.currentRound} max={session.max_rounds} />
      </div>

      {/* Divider */}
      <div className="h-px bg-zinc-800" />

      {/* Score rubric */}
      <AnimatePresence>
        {session.scores ? (
          <motion.div
            key="scores"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-5"
          >
            <WinnerBanner rubric={session.scores} />

            <div className="space-y-4">
              <ScoreComparisonBar
                label="Logic"
                icon={<Brain className="w-3 h-3" />}
                twinScore={session.scores.twin_logic}
                challengerScore={session.scores.challenger_logic}
              />
              <ScoreComparisonBar
                label="Evidence"
                icon={<FileSearch className="w-3 h-3" />}
                twinScore={session.scores.twin_evidence}
                challengerScore={session.scores.challenger_evidence}
              />
              <ScoreComparisonBar
                label="Rebuttal"
                icon={<Swords className="w-3 h-3" />}
                twinScore={session.scores.twin_rebuttal}
                challengerScore={session.scores.challenger_rebuttal}
              />
            </div>

            {/* Total */}
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-zinc-800 bg-cyan-950/10 p-3 flex flex-col justify-between">
                <span className="text-[10px] font-mono text-cyan-500 uppercase tracking-widest">Twin Total</span>
                <span className="text-xl font-black text-cyan-400 tabular-nums">
                  {session.scores.twin_logic + session.scores.twin_evidence + session.scores.twin_rebuttal}
                  <span className="text-zinc-600 text-xs font-normal">/30</span>
                </span>
              </div>
              <div className="rounded-md border border-zinc-800 bg-rose-950/10 p-3 flex flex-col justify-between">
                <span className="text-[10px] font-mono text-rose-500 uppercase tracking-widest">Challenger Total</span>
                <span className="text-xl font-black text-rose-400 tabular-nums">
                  {session.scores.challenger_logic + session.scores.challenger_evidence + session.scores.challenger_rebuttal}
                  <span className="text-zinc-600 text-xs font-normal">/30</span>
                </span>
              </div>
            </div>


            {/* Summary */}
            <div className="rounded-md border border-zinc-800 bg-zinc-900/50 p-3">
              <p className="text-[11px] font-mono text-zinc-500 uppercase tracking-widest mb-2">Judge Summary</p>
              <p className="text-xs text-zinc-300 leading-relaxed">{session.scores.summary}</p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="pending-scores"
            className="flex flex-col items-center justify-center gap-3 py-8 text-zinc-700"
          >
            <Clock className="w-6 h-6 animate-spin" style={{ animationDuration: "3s" }} />
            <p className="text-xs font-mono uppercase tracking-widest">Awaiting verdict</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Actions */}
      <div className="mt-auto space-y-2">
        {session.status === "running" && (
          <button
            onClick={sendConcede}
            className="w-full text-xs font-mono uppercase tracking-widest border border-rose-900/50 text-rose-500 hover:bg-rose-950/30 rounded-md py-2 transition-colors"
          >
            Concede
          </button>
        )}
        {(session.status === "completed" || session.status === "error") && (
          <button
            onClick={resetDebate}
            className="w-full text-xs font-mono uppercase tracking-widest border border-zinc-700 text-zinc-300 hover:bg-zinc-800 rounded-md py-2 transition-colors"
          >
            New Debate
          </button>
        )}
      </div>
    </div>
  );
}
