"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Swords, ChevronRight, User, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDebateStore } from "@/lib/store";

const EXAMPLE_TOPICS = [
  "Universal Basic Income would reduce poverty more effectively than targeted welfare programs.",
  "Remote work fundamentally improves software engineering team productivity.",
  "Open-source AI models are more beneficial to society than closed proprietary systems.",
  "Electric vehicles are currently the most practical path to sustainable transportation.",
];

export default function DebateSetup() {
  const [topic, setTopic] = useState("");
  const [personaId, setPersonaId] = useState("default");
  const [maxRounds, setMaxRounds] = useState(3);
  const startDebate = useDebateStore((s) => s.startDebate);
  const isConnected = useDebateStore((s) => s.isConnected);

  const handleSubmit = () => {
    const trimmed = topic.trim();
    if (trimmed.length < 10) return;
    startDebate({ topic: trimmed, persona_id: personaId, max_rounds: maxRounds });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="max-w-2xl mx-auto w-full space-y-8"
    >
      {/* Logo mark */}
      <div className="text-center space-y-3">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-zinc-900 border border-zinc-800">
          <Swords className="w-7 h-7 text-cyan-400" />
        </div>
        <div>
          <h1 className="text-3xl font-black tracking-tight text-zinc-100">
            Debate<span className="text-cyan-400">Twin</span>
          </h1>
          <p className="text-sm text-zinc-500 font-mono mt-1">
            Multi-agent · RAG-grounded · Real-time
          </p>
        </div>
      </div>

      {/* Form card */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 backdrop-blur-sm p-6 space-y-6">

        {/* Topic input */}
        <div className="space-y-2">
          <label className="text-xs font-mono uppercase tracking-widest text-zinc-500">
            Debate Topic
          </label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Enter a thesis statement or debate motion…"
            rows={3}
            className={cn(
              "w-full rounded-lg bg-zinc-900 border text-sm text-zinc-200 placeholder-zinc-600",
              "px-4 py-3 font-mono resize-none outline-none transition-colors",
              "focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20",
              topic.trim().length > 0 ? "border-zinc-700" : "border-zinc-800"
            )}
          />
          {/* Example topics */}
          <div className="space-y-1">
            <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest">Examples</p>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLE_TOPICS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTopic(t)}
                  className="text-[10px] font-mono text-zinc-500 hover:text-cyan-400 border border-zinc-800 hover:border-cyan-500/30 rounded px-2 py-1 transition-colors text-left line-clamp-1 max-w-[200px]"
                >
                  {t.slice(0, 40)}…
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Configuration row */}
        <div className="grid grid-cols-2 gap-4">
          {/* Persona ID */}
          <div className="space-y-2">
            <label className="text-xs font-mono uppercase tracking-widest text-zinc-500 flex items-center gap-1.5">
              <User className="w-3 h-3" /> Persona ID
            </label>
            <input
              value={personaId}
              onChange={(e) => setPersonaId(e.target.value)}
              className={cn(
                "w-full rounded-lg bg-zinc-900 border border-zinc-800 text-sm text-zinc-200",
                "px-3 py-2 font-mono outline-none transition-colors",
                "focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20"
              )}
              placeholder="default"
            />
            <p className="text-[10px] text-zinc-600 font-mono">Must match your ingested persona</p>
          </div>

          {/* Max rounds */}
          <div className="space-y-2">
            <label className="text-xs font-mono uppercase tracking-widest text-zinc-500 flex items-center gap-1.5">
              <Layers className="w-3 h-3" /> Rounds
            </label>
            <div className="flex gap-2">
              {[1, 2, 3, 4, 5].map((r) => (
                <button
                  key={r}
                  onClick={() => setMaxRounds(r)}
                  className={cn(
                    "flex-1 rounded-md border text-sm font-mono py-2 transition-colors",
                    maxRounds === r
                      ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-300"
                      : "border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                  )}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={topic.trim().length < 10 || isConnected}
          className={cn(
            "w-full flex items-center justify-center gap-2 rounded-lg py-3 text-sm font-mono font-bold uppercase tracking-widest transition-all",
            topic.trim().length >= 10 && !isConnected
              ? "bg-cyan-500 text-zinc-950 hover:bg-cyan-400 active:scale-[0.99]"
              : "bg-zinc-900 text-zinc-600 cursor-not-allowed border border-zinc-800"
          )}
        >
          {isConnected ? (
            <>Connecting<span className="animate-pulse">…</span></>
          ) : (
            <>Enter the War Room <ChevronRight className="w-4 h-4" /></>
          )}
        </button>
      </div>
    </motion.div>
  );
}
