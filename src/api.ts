import type {
  AgentAvailability,
  Bootstrap,
  ComfyStatus,
  Conversation,
  EventPayload,
  Message,
  Settings,
  StatusPayload,
} from "./types";

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

type Unlisten = () => void;

export interface Api {
  bootstrap(): Promise<Bootstrap>;
  checkAgents(): Promise<AgentAvailability[]>;
  saveSettings(settings: Settings): Promise<void>;
  listConversations(characterId: string): Promise<Conversation[]>;
  getMessages(conversationId: string): Promise<Message[]>;
  deleteConversation(conversationId: string): Promise<void>;
  renameConversation(conversationId: string, title: string): Promise<void>;
  openWorkspace(characterId: string): Promise<void>;
  openFile(characterId: string, path: string): Promise<void>;
  existingFiles(characterId: string, paths: string[]): Promise<boolean[]>;
  cancelRun(characterId: string): Promise<void>;
  /** Image in her workspace as a data: URL (for previews). */
  readImage(characterId: string, path: string): Promise<string>;
  /** Copy a dropped file into her workspace; returns e.g. `inputs/foo.png`. */
  importFile(characterId: string, path: string): Promise<string>;
  /** Save pasted bytes into her workspace; returns e.g. `inputs/paste.png`. */
  saveUpload(characterId: string, name: string, data: Uint8Array): Promise<string>;
  checkComfyui(url?: string | null): Promise<ComfyStatus>;
  sendMessage(args: {
    characterId: string;
    conversationId: string | null;
    text: string;
  }): Promise<{ conversation: Conversation; userMessage: Message; runId: string }>;
  onAgentEvent(cb: (p: EventPayload) => void): Promise<Unlisten>;
  onAgentStatus(cb: (p: StatusPayload) => void): Promise<Unlisten>;
}

async function tauriApi(): Promise<Api> {
  const { invoke } = await import("@tauri-apps/api/core");
  const { listen } = await import("@tauri-apps/api/event");
  return {
    bootstrap: () => invoke("bootstrap"),
    checkAgents: () => invoke("check_agents"),
    saveSettings: (settings) => invoke("save_settings", { settings }),
    listConversations: (characterId) => invoke("list_conversations", { characterId }),
    getMessages: (conversationId) => invoke("get_messages", { conversationId }),
    deleteConversation: (conversationId) => invoke("delete_conversation", { conversationId }),
    renameConversation: (conversationId, title) =>
      invoke("rename_conversation", { conversationId, title }),
    openWorkspace: (characterId) => invoke("open_workspace", { characterId }),
    openFile: (characterId, path) => invoke("open_file", { characterId, path }),
    existingFiles: (characterId, paths) => invoke("existing_files", { characterId, paths }),
    cancelRun: (characterId) => invoke("cancel_run", { characterId }),
    readImage: (characterId, path) => invoke("read_image", { characterId, path }),
    importFile: (characterId, path) => invoke("import_file", { characterId, path }),
    saveUpload: (characterId, name, data) => invoke("save_upload", { characterId, name, data: Array.from(data) }),
    checkComfyui: (url) => invoke("check_comfyui", { url: url ?? null }),
    sendMessage: (args) => invoke("send_message", args),
    onAgentEvent: (cb) => listen<EventPayload>("agent-event", (e) => cb(e.payload)),
    onAgentStatus: (cb) => listen<StatusPayload>("agent-status", (e) => cb(e.payload)),
  };
}

/** In-browser mock so the UI can be previewed with plain `npm run dev`. */
async function mockApi(): Promise<Api> {
  const iris = (await import("../characters/iris/character.json")).default as any;
  const poppy = (await import("../characters/poppy/character.json")).default as any;
  const characters = [
    { ...iris, skills: [{ name: "reading-notes", description: "读书笔记" }, { name: "writing-polish", description: "润色" }] },
    { ...poppy, skills: [{ name: "painting", description: "画图、改图、拆图层" }, { name: "image-prompt-reverse", description: "反推提示词" }] },
  ];
  const convs: Conversation[] = [];
  const msgs: Record<string, Message[]> = {};
  let nextId = 1;
  const eventCbs: ((p: EventPayload) => void)[] = [];
  const statusCbs: ((p: StatusPayload) => void)[] = [];
  const now = () => new Date().toISOString();
  const add = (cid: string, role: Message["role"], content: string, meta: any = {}) => {
    const m: Message = { id: nextId++, conversationId: cid, role, content, meta, createdAt: now() };
    (msgs[cid] ||= []).push(m);
    return m;
  };
  return {
    bootstrap: async () => ({ characters, settings: { characters: {} }, dataDir: "(browser mock)", activeRuns: [] }),
    checkAgents: async () => [
      { provider: "claude", path: "/mock/claude", version: "mock" },
      { provider: "codex", path: null, version: null },
    ],
    saveSettings: async () => {},
    listConversations: async (cid) => convs.filter((c) => c.characterId === cid),
    getMessages: async (id) => msgs[id] || [],
    deleteConversation: async (id) => {
      const i = convs.findIndex((c) => c.id === id);
      if (i >= 0) convs.splice(i, 1);
    },
    renameConversation: async (id, title) => {
      const c = convs.find((c) => c.id === id);
      if (c) c.title = title;
    },
    openWorkspace: async () => {},
    openFile: async (_c, path) => alert(`(浏览器预览) 打开 ${path}`),
    existingFiles: async (_c, paths) => paths.map(() => true),
    cancelRun: async () => {},
    readImage: async () => "/characters/poppy/poses/reading.png",
    importFile: async (_c, path) => `inputs/${path.split(/[\\/]/).pop()}`,
    saveUpload: async (_c, name) => `inputs/${name}`,
    checkComfyui: async (url) => ({ url: url || "http://127.0.0.1:8188", ok: false, detail: "浏览器预览模式无法检测" }),
    sendMessage: async ({ characterId, conversationId, text }) => {
      let conv = convs.find((c) => c.id === conversationId);
      if (!conv) {
        conv = { id: crypto.randomUUID(), characterId, title: text.slice(0, 24), provider: "claude", createdAt: now(), updatedAt: now(), messageCount: 0 };
        convs.unshift(conv);
      }
      const userMessage = add(conv.id, "user", text);
      const runId = crypto.randomUUID();
      const c = conv;
      const base = { runId, characterId, conversationId: c.id };
      // mock: messages that sound like work use a tool, which flips her into the working pose
      const work = /整理|笔记|写|保存|文件|save|write/i.test(text);
      setTimeout(() => statusCbs.forEach((f) => f({ ...base, status: "running", worked: false, ok: true })), 10);
      if (work) setTimeout(() => statusCbs.forEach((f) => f({ ...base, status: "working", worked: true, ok: true })), 400);
      const reply = work ? "好的，这个任务交给我吧！我已经整理好了笔记，保存在 `outputs/读书笔记.pdf`。" : "嗯嗯，我在听哦～这是浏览器预览模式，真正的回复需要在桌面程序里运行。";
      let i = 0;
      const tick = setInterval(() => {
        if (i < reply.length) {
          eventCbs.forEach((f) => f({ ...base, event: { kind: "delta", text: reply.slice(i, i + 3) } }));
          i += 3;
          return;
        }
        clearInterval(tick);
        if (work) {
          const t = add(c.id, "tool", "outputs/读书笔记.pdf", { name: "Write", ok: true });
          eventCbs.forEach((f) => f({ ...base, event: { kind: "tool", name: "Write", summary: t.content }, message: t }));
        }
        const m = add(c.id, "assistant", reply);
        eventCbs.forEach((f) => f({ ...base, event: { kind: "message", text: reply }, message: m }));
        const d = add(c.id, "system", "done", { durationMs: 2400, costUsd: 0.01 });
        eventCbs.forEach((f) => f({ ...base, event: { kind: "done", ok: true, durationMs: 2400, costUsd: 0.01 }, message: d }));
        statusCbs.forEach((f) => f({ ...base, status: "finished", worked: work, ok: true }));
      }, work ? 120 : 40);
      return { conversation: c, userMessage, runId };
    },
    onAgentEvent: async (cb) => {
      eventCbs.push(cb);
      return () => eventCbs.splice(eventCbs.indexOf(cb), 1);
    },
    onAgentStatus: async (cb) => {
      statusCbs.push(cb);
      return () => statusCbs.splice(statusCbs.indexOf(cb), 1);
    },
  };
}

let apiPromise: Promise<Api> | null = null;
export function getApi(): Promise<Api> {
  return (apiPromise ||= isTauri ? tauriApi() : mockApi());
}
