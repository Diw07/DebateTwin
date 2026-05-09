"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, X } from "lucide-react";
import { useDebateStore } from "@/lib/store";
import DebateSetup from "@/components/debate/DebateSetup";
import DebateFeed from "@/components/debate/DebateFeed";
import Scoreboard from "@/components/scoreboard/Scoreboard";

// ---------------------------------------------------------------------------
// Error toast
// ---------------------------------------------------------------------------

function ErrorBanner() {
  const error = useDebateStore((s) => s.error);
  const reset = useDebateStore((s) => s.resetDebate);
  if (!error) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      className="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-rose-950 border border-rose-700 text-rose-200 rounded-lg px-4 py-3 text-sm font-mono shadow-2xl max-w-lg"
    >
      <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
      <span className="flex-1">{error}</span>
      <button onClick={reset} className="ml-2 text-rose-400 hover:text-rose-200">
        <X className="w-4 h-4" />
      </button>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// War Room header bar
// ---------------------------------------------------------------------------

function WarRoomHeader() {
  const session = useDebateStore((s) => s.session);
  if (!session) return null;

  return (
    <header className="h-14 border-b border-zinc-800 flex items-center px-6 gap-4 bg-zinc-950/90 backdrop-blur-sm shrink-0">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        <span className="text-xs font-mono uppercase tracking-widest text-zinc-500">
          War Room
        </span>
      </div>
      <div className="h-4 w-px bg-zinc-800" />
      <p className="text-sm text-zinc-300 font-medium line-clamp-1 flex-1">
        {session.topic}
      </p>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Arena — top-level page layout
// ---------------------------------------------------------------------------

export default function Arena() {
  const session = useDebateStore((s) => s.session);
  const error = useDebateStore((s) => s.error);

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Background grid pattern */}
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.015]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(6,182,212,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.5) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <AnimatePresence>
        {error && <ErrorBanner key="error" />}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {!session ? (
          /* Setup screen */
          <motion.div
            key="setup"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.3 }}
            className="flex-1 flex items-center justify-center p-8"
          >
            <DebateSetup />
          </motion.div>
        ) : (
          /* War room */
          <motion.div
            key="warroom"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
            className="flex flex-col flex-1 min-h-0"
          >
            <WarRoomHeader />

            <div className="flex flex-1 min-h-0">
              {/* Main debate area */}
              <main className="flex-1 min-w-0 p-6 overflow-hidden flex flex-col">
                <DebateFeed />
              </main>

              {/* Scoreboard sidebar */}
              <aside className="w-72 border-l border-zinc-800 bg-zinc-950/50 p-5 overflow-y-auto shrink-0">
                <Scoreboard />
              </aside>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
