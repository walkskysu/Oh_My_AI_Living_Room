export type Activity = "reading" | "bored" | "working" | "chatting" | "done" | "error";
export type ProviderId = "claude" | "codex";

/** A pose: either a still image (animated with CSS) or a sprite sheet (TexturePacker JSON hash). */
export interface SpriteDef {
  image?: string;
  sheet?: string;
  fps?: number;
}

export interface AgentConfig {
  provider: ProviderId | string;
  model?: string | null;
  permissionMode: string;
}

export interface Character {
  id: string;
  name: string;
  nameZh?: string;
  title: string;
  bio: string;
  specialties: string[];
  greeting: string;
  persona: string;
  agent: AgentConfig;
  theme: { color?: string; soft?: string };
  boredAfterSec?: number;
  scene: {
    x: number;
    y: number;
    width: number;
    z?: number;
    bubbleAnchor?: { x: number; y: number };
  };
  sprites: Partial<Record<"reading" | "bored" | "working" | "done", SpriteDef>>;
  lines?: Partial<Record<Activity, string[]>>;
  skills: { name: string; description: string }[];
}

export interface Settings {
  claudePath?: string | null;
  codexPath?: string | null;
  characters: Record<string, AgentConfig>;
}

export interface Conversation {
  id: string;
  characterId: string;
  title: string;
  provider: string;
  agentSessionId?: string | null;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

export interface Message {
  id: number;
  conversationId: string;
  role: "user" | "assistant" | "tool" | "error" | "system";
  content: string;
  meta: Record<string, any>;
  createdAt: string;
}

export type AgentEvent =
  | { kind: "session"; sessionId: string }
  | { kind: "delta"; text: string }
  | { kind: "message"; text: string }
  | { kind: "tool"; name: string; summary: string }
  | { kind: "toolResult"; ok: boolean; output: string }
  | { kind: "done"; ok: boolean; error?: string | null; costUsd?: number | null; durationMs?: number | null };

export interface EventPayload {
  runId: string;
  characterId: string;
  conversationId: string;
  event: AgentEvent;
  message?: Message | null;
}

export interface StatusPayload {
  characterId: string;
  conversationId: string;
  runId: string;
  /** running = replying; working = real work (tool use or long run); finished */
  status: "running" | "working" | "finished";
  /** The run turned into work at some point. */
  worked: boolean;
  ok: boolean;
}

export interface ActiveRun {
  characterId: string;
  conversationId: string;
  runId: string;
  working: boolean;
}

export interface Bootstrap {
  characters: Character[];
  settings: Settings;
  dataDir: string;
  activeRuns: ActiveRun[];
}

export interface AgentAvailability {
  provider: ProviderId;
  path?: string | null;
  version?: string | null;
}
