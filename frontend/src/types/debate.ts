// types/debate.ts — mirrors backend schemas/models.py

export type AgentRole = "user_twin" | "challenger" | "judge" | "system";

export type DebateStatus = "pending" | "running" | "judging" | "completed" | "error";

export type StreamEventType =
  | "token"
  | "turn_start"
  | "turn_end"
  | "scores"
  | "status"
  | "error";

export interface StreamEvent {
  event_type: StreamEventType;
  role?: AgentRole;
  round_number?: number;
  data?: string | Record<string, unknown>;
}

export interface JudgeRubric {
  winner: AgentRole;
  twin_logic: number;
  twin_evidence: number;
  twin_rebuttal: number;
  challenger_logic: number;
  challenger_evidence: number;
  challenger_rebuttal: number;
  summary: string;
}


export interface AgentTurn {
  role: AgentRole;
  round_number: number;
  content: string;
  rag_sources: string[];
  isStreaming?: boolean;  // ephemeral UI flag
}

export interface DebateSession {
  topic: string;
  persona_id: string;
  max_rounds: number;
  status: DebateStatus;
  history: AgentTurn[];
  scores: JudgeRubric | null;
  currentStreamingRole: AgentRole | null;
  currentRound: number;
  streamingContent: Record<AgentRole, string>;  // live partial text per agent
}

export interface DebateStartPayload {
  topic: string;
  persona_id: string;
  max_rounds: number;
}
