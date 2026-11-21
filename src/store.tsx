import { createContext, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { getApi, type Api } from "./api";
import type { Activity, ActiveRun, AgentAvailability, AgentConfig, Character, Message, Settings, StatusPayload } from "./types";

export interface Toast {
  id: number;
  characterId: string;
  text: string;
  kind: "done" | "error" | "info";
}

interface State {
  ready: boolean;
  error?: string;
  characters: Character[];
  settings: Settings;
  dataDir: string;
  runs: Record<string, ActiveRun>;
  /** Result of the last finished task, shown in the room until the user looks at it. */
  results: Record<string, { ok: boolean; conversationId: string }>;
  /** Messages per conversation (only for conversations that have been loaded). */
  messages: Record<string, Message[]>;
  /** Live streaming text per conversation. */
  streaming: Record<string, string>;
  openCharacterId: string | null;
  /** Conversation currently shown for each character (null = new conversation). */
  activeConversation: Record<string, string | null>;
  toasts: Toast[];
  /** Which harness CLIs were found on this machine (null until checked). */
  agents: AgentAvailability[] | null;
  /** Bumped whenever the conversation list of a character might have changed. */
  convVersion: number;
}

type Action =
  | { type: "boot"; characters: Character[]; settings: Settings; dataDir: string; runs: ActiveRun[] }
  | { type: "bootError"; error: string }
  | { type: "setMessages"; conversationId: string; messages: Message[] }
  | { type: "upsertMessage"; message: Message }
  | { type: "delta"; conversationId: string; text: string }
  | { type: "clearStream"; conversationId: string }
  | { type: "status"; payload: StatusPayload }
  | { type: "open"; characterId: string | null }
  | { type: "setActiveConversation"; characterId: string; conversationId: string | null }
  | { type: "settings"; settings: Settings }
  | { type: "agents"; agents: AgentAvailability[] }
  | { type: "toast"; toast: Omit<Toast, "id"> }
  | { type: "dismissToast"; id: number }
  | { type: "clearResult"; characterId: string };

let toastSeq = 1;

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "boot":
      return {
        ...s,
        ready: true,
        characters: a.characters,
        settings: a.settings,
        dataDir: a.dataDir,
        runs: Object.fromEntries(a.runs.map((r) => [r.characterId, r])),
      };
    case "bootError":
      return { ...s, error: a.error };
    case "setMessages":
      return { ...s, messages: { ...s.messages, [a.conversationId]: a.messages } };
    case "upsertMessage": {
      const list = s.messages[a.message.conversationId] || [];
      const idx = list.findIndex((m) => m.id === a.message.id);
      const next = idx >= 0 ? list.map((m, i) => (i === idx ? a.message : m)) : [...list, a.message];
      return { ...s, messages: { ...s.messages, [a.message.conversationId]: next } };
    }
    case "delta":
      return {
        ...s,
        streaming: { ...s.streaming, [a.conversationId]: (s.streaming[a.conversationId] || "") + a.text },
      };
    case "clearStream": {
      const { [a.conversationId]: _, ...rest } = s.streaming;
      return { ...s, streaming: rest };
    }
    case "status": {
      const p = a.payload;
      if (p.status === "working") {
        const run = s.runs[p.characterId];
        return run ? { ...s, runs: { ...s.runs, [p.characterId]: { ...run, working: true } } } : s;
      }
      if (p.status === "running") {
        const { [p.characterId]: _r, ...results } = s.results;
        return {
          ...s,
          results,
          runs: { ...s.runs, [p.characterId]: { characterId: p.characterId, conversationId: p.conversationId, runId: p.runId, working: false } },
          convVersion: s.convVersion + 1,
        };
      }
      const { [p.characterId]: _, ...runs } = s.runs;
      const { [p.conversationId]: _s, ...streaming } = s.streaming;
      const watching = s.openCharacterId === p.characterId;
      const results =
        (p.worked || !p.ok) && !watching
          ? { ...s.results, [p.characterId]: { ok: p.ok, conversationId: p.conversationId } }
          : s.results;
      return { ...s, runs, streaming, results, convVersion: s.convVersion + 1 };
    }
    case "open": {
      if (!a.characterId) return { ...s, openCharacterId: null };
      const res = s.results[a.characterId];
      const { [a.characterId]: _, ...results } = s.results;
      const activeConversation = res
        ? { ...s.activeConversation, [a.characterId]: res.conversationId }
        : s.activeConversation;
      return { ...s, openCharacterId: a.characterId, results, activeConversation };
    }
    case "setActiveConversation":
      return { ...s, activeConversation: { ...s.activeConversation, [a.characterId]: a.conversationId } };
    case "settings":
      return { ...s, settings: a.settings };
    case "agents":
      return { ...s, agents: a.agents };
    case "toast":
      return { ...s, toasts: [...s.toasts, { ...a.toast, id: toastSeq++ }].slice(-4) };
    case "dismissToast":
      return { ...s, toasts: s.toasts.filter((t) => t.id !== a.id) };
    case "clearResult": {
      const { [a.characterId]: _, ...results } = s.results;
      return { ...s, results };
    }
  }
}

const initial: State = {
  ready: false,
  characters: [],
  settings: { characters: {} },
  dataDir: "",
  runs: {},
  results: {},
  messages: {},
  streaming: {},
  openCharacterId: null,
  activeConversation: {},
  toasts: [],
  agents: null,
  convVersion: 0,
};

interface Ctx {
  state: State;
  dispatch: React.Dispatch<Action>;
  api: Api | null;
}

const StoreContext = createContext<Ctx | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const apiRef = useRef<Api | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    let unlisten: (() => void)[] = [];
    let cancelled = false;
    (async () => {
      try {
        const api = await getApi();
        apiRef.current = api;
        const b = await api.bootstrap();
        if (cancelled) return;
        dispatch({ type: "boot", characters: b.characters, settings: b.settings, dataDir: b.dataDir, runs: b.activeRuns });
        unlisten.push(
          await api.onAgentEvent((p) => {
            if (p.event.kind === "delta") {
              dispatch({ type: "delta", conversationId: p.conversationId, text: p.event.text });
            }
            if (p.event.kind === "message" || p.event.kind === "tool" || p.event.kind === "done") {
              dispatch({ type: "clearStream", conversationId: p.conversationId });
            }
            if (p.message) dispatch({ type: "upsertMessage", message: p.message });
          }),
        );
        unlisten.push(
          await api.onAgentStatus((p) => {
            dispatch({ type: "status", payload: p });
            if (p.status !== "finished") return;
            const c = stateRef.current.characters.find((c) => c.id === p.characterId);
            const watching = stateRef.current.openCharacterId === p.characterId;
            if (!c || watching) return;
            if (!p.ok) {
              dispatch({ type: "toast", toast: { characterId: c.id, kind: "error", text: `${c.name} 遇到了问题，点她看看吧` } });
            } else if (p.worked) {
              dispatch({ type: "toast", toast: { characterId: c.id, kind: "done", text: `${c.name} 完成了任务！` } });
            } else {
              dispatch({ type: "toast", toast: { characterId: c.id, kind: "info", text: `${c.name} 回复了你` } });
            }
          }),
        );
      } catch (e) {
        dispatch({ type: "bootError", error: String(e) });
      }
    })();
    return () => {
      cancelled = true;
      unlisten.forEach((u) => u());
    };
  }, []);

  // Detect the harness CLIs at startup, and again whenever their configured paths change.
  const { claudePath, codexPath, deepseekPath } = state.settings;
  useEffect(() => {
    const api = apiRef.current;
    if (!state.ready || !api) return;
    let stale = false;
    api
      .checkAgents()
      .then((agents) => !stale && dispatch({ type: "agents", agents }))
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [state.ready, claudePath, codexPath, deepseekPath]);

  const value = useMemo(() => ({ state, dispatch, api: apiRef.current }), [state]);
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("StoreProvider missing");
  return ctx;
}

export const providerName: Record<string, string> = { claude: "Claude Code", codex: "Codex", deepseek: "DeepSeek Harness" };
export const providerBinary: Record<string, string> = { claude: "claude", codex: "codex", deepseek: "dsh" };

export function agentConfigFor(state: Pick<State, "settings">, c: Character): AgentConfig {
  return state.settings.characters[c.id] ?? c.agent;
}

/** Whether the harness CLI is installed; undefined while still checking. */
export function agentAvailable(state: Pick<State, "agents">, provider: string): boolean | undefined {
  if (!state.agents) return undefined;
  return !!state.agents.find((a) => a.provider === provider)?.path;
}

/** Characters whose configured harness isn't installed on this machine. */
export function missingAgents(state: Pick<State, "agents" | "settings" | "characters">) {
  if (!state.agents) return [];
  return state.characters
    .map((c) => ({ character: c, provider: agentConfigFor(state, c).provider }))
    .filter((m) => agentAvailable(state, m.provider) === false);
}

/** Activity derived from runs/results; "bored" is layered on top by the sprite's idle timer. */
export function baseActivity(state: State, characterId: string): Activity {
  const run = state.runs[characterId];
  if (run) return run.working ? "working" : "chatting";
  const res = state.results[characterId];
  if (res) return res.ok ? "done" : "error";
  return "reading";
}

export const activityLabel: Record<Activity, string> = {
  reading: "看书中",
  bored: "发呆中",
  working: "工作中",
  chatting: "回复中",
  done: "完成啦",
  error: "出错了",
};

/** Status label, with per-character wording (e.g. Poppy paints instead of reads). */
export function labelFor(c: { activityLabels?: Partial<Record<Activity, string>> }, a: Activity) {
  return c.activityLabels?.[a] ?? activityLabel[a];
}
