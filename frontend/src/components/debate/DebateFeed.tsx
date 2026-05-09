"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, User, Scale, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDebateStore } from "@/lib/store";
import { AgentTurn } from "@/types/debate";

// ---------------------------------------------------------------------------
// Typing cursor
// ---------------------------------------------------------------------------

function TypingCursor() {
  return (
    <motion.span
      className="inline-block w-0.5 h-4 bg-current ml-0.5 align-middle"
      animate={{ opacity: [1, 0, 1] }}
      transition={{ repeat: Infinity, duration: 0.8 }}
    />
  );
}

// ---------------------------------------------------------------------------
// Agent avatar + label
// ---------------------------------------------------------------------------

function AgentHeader({ role, round }: { role: AgentTurn["role"]; round: number }) {
  const config = {
    user_twin: {
      icon: <User className="w-3.5 h-3.5" />,
      label: "Your Twin",
      color: "text-cyan-400",
      bg: "bg-cyan-500/10 border-cyan-500/20",
    },
    challenger: {
      icon: <Bot className="w-3.5 h-3.5" />,
      label: "Challenger",
      color: "text-rose-400",
      bg: "bg-rose-500/10 border-rose-500/20",
    },
    judge: {
      icon: <Scale className="w-3.5 h-3.5" />,
      label: "Judge",
      color: "text-amber-400",
      bg: "bg-amber-500/10 border-amber-500/20",
    },
    system: {
      icon: <Sparkles className="w-3.5 h-3.5" />,
      label: "System",
      color: "text-zinc-400",
      bg: "bg-zinc-800 border-zinc-700",
    },
  };

  const { icon, label, color, bg } = config[role] ?? config.system;

  return (
    <div className="flex items-center gap-2 mb-2">
      <div className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-mono uppercase tracking-widest", bg, color)}>
        {icon}
        {label}
      </div>
      <span className="text-[10px] font-mono text-zinc-600">Round {round}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

interface BubbleProps {
  turn: AgentTurn;
  isStreaming?: boolean;
  streamText?: string;
}

function Bubble({ turn, isStreaming, streamText }: BubbleProps) {
  const isLeft = turn.role === "user_twin";
  const displayText = isStreaming ? (streamText ?? "") : turn.content;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={cn("w-full", isLeft ? "" : "flex flex-col items-end")}
    >
      <div className={cn("max-w-[88%]", isLeft ? "" : "")}>
        <AgentHeader role={turn.role} round={turn.round_number} />
        <div
          className={cn(
            "rounded-xl px-4 py-3 text-sm leading-relaxed border",
            turn.role === "user_twin" && "bg-cyan-950/20 border-cyan-900/30 text-zinc-200",
            turn.role === "challenger" && "bg-rose-950/20 border-rose-900/30 text-zinc-200",
            turn.role === "judge" && "bg-amber-950/20 border-amber-900/30 text-zinc-200",
            turn.role === "system" && "bg-zinc-900 border-zinc-800 text-zinc-400 italic",
          )}
        >
          <span className="whitespace-pre-wrap font-sans">{displayText}</span>
          {isStreaming && <TypingCursor />}
        </div>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Streaming ghost bubble (agent currently speaking)
// ---------------------------------------------------------------------------

function StreamingBubble() {
  const session = useDebateStore((s) => s.session);
  if (!session?.currentStreamingRole) return null;

  const role = session.currentStreamingRole;
  const text = session.streamingContent[role] ?? "";
  if (!text && role !== "judge") return null; // Don't show empty ghost for non-judge

  return (
    <Bubble
      turn={{
        role,
        round_number: session.currentRound,
        content: text,
        rag_sources: [],
        isStreaming: true,
      }}
      isStreaming
      streamText={text}
    />
  );
}

// ---------------------------------------------------------------------------
// Column header
// ---------------------------------------------------------------------------

function ColumnHeader({ side }: { side: "twin" | "challenger" }) {
  return (
    <div className={cn(
      "flex items-center gap-2 pb-3 border-b border-zinc-800 mb-4",
      side === "challenger" && "flex-row-reverse"
    )}>
      <div className={cn(
        "w-2 h-2 rounded-full",
        side === "twin" ? "bg-cyan-400" : "bg-rose-400"
      )} />
      <span className="text-xs font-mono uppercase tracking-widest text-zinc-500">
        {side === "twin" ? "Your Twin" : "Challenger"}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Debate Feed (split-screen)
// ---------------------------------------------------------------------------

export default function DebateFeed() {
  const session = useDebateStore((s) => s.session);
  const twinBottomRef = useRef<HTMLDivElement>(null);
  const challengerBottomRef = useRef<HTMLDivElement>(null);
  const judgeBottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll
  useEffect(() => {
    twinBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    challengerBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    judgeBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.history.length, session?.streamingContent]);

  if (!session) return null;

  const twinTurns = session.history.filter((t) => t.role === "user_twin");
  const challengerTurns = session.history.filter((t) => t.role === "challenger");
  const judgeTurns = session.history.filter((t) => t.role === "judge");

  const streamingRole = session.currentStreamingRole;

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Split debate columns */}
      <div className="flex-1 grid grid-cols-2 gap-4 min-h-0">
        {/* Twin column */}
        <div className="flex flex-col min-h-0">
          <ColumnHeader side="twin" />
          <div className="flex-1 overflow-y-auto space-y-4 pr-2 scrollbar-thin scrollbar-track-zinc-950 scrollbar-thumb-zinc-800">
            <AnimatePresence mode="popLayout">
              {twinTurns.map((turn, i) => (
                <Bubble key={`twin-${i}`} turn={turn} />
              ))}
              {streamingRole === "user_twin" && <StreamingBubble key="twin-stream" />}
            </AnimatePresence>
            <div ref={twinBottomRef} />
          </div>
        </div>

        {/* Challenger column */}
        <div className="flex flex-col min-h-0">
          <ColumnHeader side="challenger" />
          <div className="flex-1 overflow-y-auto space-y-4 pl-2 scrollbar-thin scrollbar-track-zinc-950 scrollbar-thumb-zinc-800">
            <AnimatePresence mode="popLayout">
              {challengerTurns.map((turn, i) => (
                <Bubble key={`challenger-${i}`} turn={turn} />
              ))}
              {streamingRole === "challenger" && <StreamingBubble key="challenger-stream" />}
            </AnimatePresence>
            <div ref={challengerBottomRef} />
          </div>
        </div>
      </div>

      {/* Judge panel — full width below */}
      {(judgeTurns.length > 0 || streamingRole === "judge") && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="border-t border-amber-900/30 pt-4"
        >
          <div className="flex items-center gap-2 mb-3">
            <Scale className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-xs font-mono uppercase tracking-widest text-amber-500">
              Judge Deliberation
            </span>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-3 scrollbar-thin scrollbar-track-zinc-950 scrollbar-thumb-zinc-800">
            {judgeTurns.map((turn, i) => (
              <Bubble key={`judge-${i}`} turn={turn} />
            ))}
            {streamingRole === "judge" && <StreamingBubble key="judge-stream" />}
            <div ref={judgeBottomRef} />
          </div>
        </motion.div>
      )}
    </div>
  );
}
