import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { isTauri } from "../api";
import { agentAvailable, baseActivity, labelFor, providerName, useStore } from "../store";
import type { AgentConfig, Character, Conversation, Message } from "../types";
import { Markdown } from "./Markdown";
import { extractFiles, FileCards, ImageThumb } from "./FileCards";

type Tab = "chat" | "history" | "profile";

const modelHint: Record<string, string> = { claude: "sonnet / opus", codex: "gpt-5", deepseek: "deepseek-flash / deepseek-v4-pro" };

function fmtTime(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const suggestions: Record<string, string[]> = {
  iris: [
    "推荐一本适合周末读的小说",
    "帮我把这段话润色得更自然：",
    "读一下 https://example.com 这篇文章，整理成读书笔记",
  ],
  claire: [
    "AAPL 最近四周走势怎么样？现在能买吗？",
    "帮我分析一下贵州茅台（600519）和腾讯（0700）",
    "降息对股市和普通人的钱包有什么影响？",
  ],
  poppy: [
    "画一只在窗台上晒太阳的橘猫，水彩风格",
    "（把图片拖进来）帮我反推这张图的提示词",
    "（把图片拖进来）把背景改成樱花盛开的公园",
  ],
};

/** Pasted clipboard images have generic names; give them a timestamped one. */
function pasteName(f: File) {
  const ext = (f.type.split("/")[1] || "png").replace("jpeg", "jpg");
  const t = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `paste-${t.getFullYear()}${p(t.getMonth() + 1)}${p(t.getDate())}-${p(t.getHours())}${p(t.getMinutes())}${p(t.getSeconds())}.${ext}`;
}

export function ChatPanel({ character }: { character: Character }) {
  const { state, dispatch, api } = useStore();
  const [tab, setTab] = useState<Tab>("chat");
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  /** Files the user dropped/pasted, already copied into her workspace (`inputs/...`). */
  const [attachments, setAttachments] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const convId = state.activeConversation[character.id] ?? null;
  const messages = (convId && state.messages[convId]) || [];
  const streaming = convId ? state.streaming[convId] : undefined;
  const run = state.runs[character.id];
  const runningHere = !!run && run.conversationId === convId;
  const activity = baseActivity(state, character.id);
  const agentCfg: AgentConfig = state.settings.characters[character.id] ?? character.agent;
  const agentMissing = agentAvailable(state, agentCfg.provider) === false;
  const optLabel = (id: string) => `${providerName[id]}${agentAvailable(state, id) === false ? "（本机未安装）" : ""}`;

  const refreshConversations = useCallback(async () => {
    if (!api) return;
    setConversations(await api.listConversations(character.id));
  }, [api, character.id]);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations, state.convVersion]);

  // Load messages of the active conversation.
  useEffect(() => {
    if (!api || !convId || state.messages[convId]) return;
    api.getMessages(convId).then((m) => dispatch({ type: "setMessages", conversationId: convId, messages: m }));
  }, [api, convId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Stick to bottom.
  useLayoutEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, streaming, tab, convId]);

  useEffect(() => {
    if (tab === "chat") inputRef.current?.focus();
  }, [tab, convId]);

  const attach = useCallback(
    async (job: () => Promise<string>) => {
      try {
        const rel = await job();
        setAttachments((a) => (a.includes(rel) ? a : [...a, rel]));
        inputRef.current?.focus();
      } catch (e) {
        setError(String(e));
      }
    },
    [],
  );

  // Files dropped on the window while her panel is open (Tauri gives real paths).
  useEffect(() => {
    if (!isTauri || !api) return;
    let un: (() => void) | undefined;
    let alive = true;
    import("@tauri-apps/api/webview").then(({ getCurrentWebview }) =>
      getCurrentWebview()
        .onDragDropEvent((e) => {
          const p = e.payload;
          if (p.type === "enter" || p.type === "over") setDragOver(true);
          else if (p.type === "leave") setDragOver(false);
          else if (p.type === "drop") {
            setDragOver(false);
            setTab("chat");
            for (const path of p.paths) attach(() => api.importFile(character.id, path));
          }
        })
        .then((f) => (alive ? (un = f) : f())),
    );
    return () => {
      alive = false;
      un?.();
    };
  }, [api, character.id, attach]);

  const uploadFiles = (files: File[]) => {
    if (!api) return;
    for (const f of files) {
      const name = !f.name || /^image\.\w+$/.test(f.name) ? pasteName(f) : f.name;
      attach(async () => api.saveUpload(character.id, name, new Uint8Array(await f.arrayBuffer())));
    }
  };

  const send = async () => {
    let body = text.trim();
    if ((!body && attachments.length === 0) || !api || sending || run) return;
    if (attachments.length > 0) {
      body = `${body || "请看附件。"}\n\n附件：${attachments.map((a) => `\`${a}\``).join("、")}`;
    }
    setSending(true);
    setError(null);
    try {
      const res = await api.sendMessage({ characterId: character.id, conversationId: convId, text: body });
      if (!convId) {
        dispatch({ type: "setMessages", conversationId: res.conversation.id, messages: [res.userMessage] });
        dispatch({ type: "setActiveConversation", characterId: character.id, conversationId: res.conversation.id });
      } else {
        dispatch({ type: "upsertMessage", message: res.userMessage });
      }
      setText("");
      setAttachments([]);
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  };

  const openConversation = (id: string | null) => {
    dispatch({ type: "setActiveConversation", characterId: character.id, conversationId: id });
    setTab("chat");
  };

  const saveAgent = async (patch: Partial<AgentConfig>) => {
    if (!api) return;
    const next = {
      ...state.settings,
      characters: { ...state.settings.characters, [character.id]: { ...agentCfg, ...patch } },
    };
    await api.saveSettings(next);
    dispatch({ type: "settings", settings: next });
  };

  const close = () => dispatch({ type: "open", characterId: null });

  return (
    <aside className="panel" style={{ ["--theme" as any]: character.theme.color, ["--soft" as any]: character.theme.soft }}>
      <header className="panel-head">
        <img className="avatar lg" src={`/characters/${character.id}/avatar.png`} alt="" />
        <div className="who">
          <div className="name">
            {character.name}
            {character.nameZh && <small>{character.nameZh}</small>}
          </div>
          <div className="title">{character.title}</div>
          <div className="badges">
            <span className={`pill s-${activity}`}>{labelFor(character, activity)}</span>
            <span className={`pill ${agentMissing ? "bad" : "ghost"}`} title={agentMissing ? "本机没找到这个 harness 的命令行" : undefined}>
              {providerName[agentCfg.provider] ?? agentCfg.provider}{agentMissing && " · 未安装"}
            </span>
          </div>
        </div>
        <div className="head-actions">
          <button className="icon-btn" title="打开她的工作目录" onClick={() => api?.openWorkspace(character.id)}>📁</button>
          <button className="icon-btn" title="关闭" onClick={close}>✕</button>
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === "chat" ? "on" : ""} onClick={() => setTab("chat")}>对话</button>
        <button className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>
          历史记录 <span className="count">{conversations.length}</span>
        </button>
        <button className={tab === "profile" ? "on" : ""} onClick={() => setTab("profile")}>关于她</button>
        {tab === "chat" && (
          <button className="new-conv" onClick={() => openConversation(null)} disabled={!convId}>＋ 新对话</button>
        )}
      </nav>

      {tab === "chat" && (
        <>
          <div className="messages" ref={listRef}>
            {!convId && (
              <div className="welcome">
                <div className="msg assistant">
                  <img className="avatar" src={`/characters/${character.id}/avatar.png`} alt="" />
                  <div className="bubble-msg">{character.greeting}</div>
                </div>
                <div className="suggest">
                  {(suggestions[character.id] ?? []).map((s) => (
                    <button
                      key={s}
                      onClick={() => {
                        setText(s);
                        inputRef.current?.focus();
                      }}
                    >
                      💬 {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {groupTools(messages).map((g, i, all) =>
              Array.isArray(g) ? (
                <ActivityRow key={g[0].id} steps={g} live={runningHere && i === all.length - 1} />
              ) : (
                <MessageRow key={g.id} m={g} character={character} />
              ),
            )}
            {runningHere && (
              <div className="msg assistant">
                <img className="avatar" src={`/characters/${character.id}/avatar.png`} alt="" />
                <div className="bubble-msg streaming">
                  {streaming ? <Markdown text={extractFiles(streaming).text} /> : <span className="typing"><i /><i /><i /></span>}
                </div>
              </div>
            )}
          </div>

          {run && !runningHere && (
            <div className="busy-note">
              {character.name} 正在另一个对话里忙着呢…
              <button onClick={() => openConversation(run.conversationId)}>去看看</button>
            </div>
          )}
          {error && <div className="error-note" onClick={() => setError(null)}>{error}</div>}

          <div className="composer">
            <div className="composer-hint">
              Enter 发送 · Shift+Enter 换行 · 可拖入或粘贴图片
            </div>
            {attachments.length > 0 && (
              <div className="attachments">
                {attachments.map((a) => (
                  <span key={a} className="attachment" title={a}>
                    <ImageThumb characterId={character.id} path={a} />
                    <span className="attachment-name">{a.replace(/^inputs\//, "")}</span>
                    <button className="icon-btn" title="移除" onClick={() => setAttachments((x) => x.filter((y) => y !== a))}>✕</button>
                  </span>
                ))}
              </div>
            )}
            <div
              className={`input-row ${dragOver ? "drag-over" : ""}`}
              onDragOver={(e) => {
                if (isTauri) return;
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => !isTauri && setDragOver(false)}
              onDrop={(e) => {
                if (isTauri) return;
                e.preventDefault();
                setDragOver(false);
                uploadFiles(Array.from(e.dataTransfer.files));
              }}
            >
              <textarea
                ref={inputRef}
                value={text}
                rows={2}
                placeholder={`和 ${character.name} 说点什么，或交给她一件事…`}
                onChange={(e) => setText(e.target.value)}
                onPaste={(e) => {
                  const files = Array.from(e.clipboardData.files);
                  if (files.length === 0) return;
                  e.preventDefault();
                  uploadFiles(files);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
              {run ? (
                <button className="send stop" onClick={() => api?.cancelRun(character.id)}>停止</button>
              ) : (
                <button className="send" onClick={() => send()} disabled={(!text.trim() && attachments.length === 0) || sending}>
                  发送
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {tab === "history" && (
        <div className="history">
          {conversations.length === 0 && <div className="empty">还没有对话记录</div>}
          {conversations.map((c) => (
            <HistoryRow
              key={c.id}
              c={c}
              active={c.id === convId}
              running={run?.conversationId === c.id}
              onOpen={() => openConversation(c.id)}
              onRename={async (title) => {
                await api?.renameConversation(c.id, title);
                refreshConversations();
              }}
              onDelete={async () => {
                try {
                  await api?.deleteConversation(c.id);
                  if (c.id === convId) openConversation(null);
                  setTab("history");
                  refreshConversations();
                } catch (e) {
                  setError(String(e));
                }
              }}
            />
          ))}
        </div>
      )}

      {tab === "profile" && (
        <div className="profile">
          <p className="bio">{character.bio}</p>
          <h4>擅长</h4>
          <div className="chips">
            {character.specialties.map((s) => <span key={s} className="chip">{s}</span>)}
          </div>
          <h4>技能 Skills</h4>
          <ul className="skills">
            {character.skills.map((s) => (
              <li key={s.name}><code>{s.name}</code><span>{s.description}</span></li>
            ))}
            {character.skills.length === 0 && <li className="empty">暂无</li>}
          </ul>
          <h4>Agent 设置</h4>
          <div className="form">
            <label>
              Harness
              {/* model names don't carry over between harnesses, so switching clears it */}
              <select value={agentCfg.provider} onChange={(e) => saveAgent({ provider: e.target.value, model: null })}>
                <option value="claude">{optLabel("claude")}</option>
                <option value="codex">{optLabel("codex")}</option>
                <option value="deepseek">{optLabel("deepseek")}</option>
              </select>
            </label>
            <label>
              模型
              <input
                key={agentCfg.provider}
                defaultValue={agentCfg.model ?? ""}
                placeholder={`默认（例如 ${modelHint[agentCfg.provider] ?? "sonnet / gpt-5"}）`}
                onBlur={(e) => saveAgent({ model: e.target.value.trim() || null })}
              />
            </label>
            <label>
              权限
              <select value={agentCfg.permissionMode} onChange={(e) => saveAgent({ permissionMode: e.target.value })}>
                <option value="default">只读为主（default）</option>
                <option value="acceptEdits">允许编辑工作目录文件（acceptEdits）</option>
                <option value="bypassPermissions">完全放开（bypassPermissions，慎用）</option>
              </select>
            </label>
          </div>
          <details className="persona">
            <summary>人设提示词</summary>
            <pre>{character.persona}</pre>
          </details>
        </div>
      )}
    </aside>
  );
}

function MessageRow({ m, character }: { m: Message; character: Character }) {
  if (m.role === "user") {
    return (
      <div className="msg user">
        <div className="bubble-msg">
          {m.meta?.mode === "task" && <span className="task-tag">📋 任务</span>}
          <UserBody text={m.content} characterId={character.id} />
        </div>
      </div>
    );
  }
  if (m.role === "assistant") {
    return (
      <div className="msg assistant">
        <img className="avatar" src={`/characters/${character.id}/avatar.png`} alt="" />
        <AssistantBody text={m.content} characterId={character.id} />
      </div>
    );
  }
  if (m.role === "error") {
    return <div className="sys-row error">⚠️ {m.content}</div>;
  }
  const secs = m.meta?.durationMs ? `${(m.meta.durationMs / 1000).toFixed(1)}s` : "";
  const cost = m.meta?.costUsd ? `$${Number(m.meta.costUsd).toFixed(3)}` : "";
  return <div className="sys-row">✓ 完成 {[secs, cost].filter(Boolean).join(" · ")}</div>;
}

function HistoryRow(props: {
  c: Conversation;
  active: boolean;
  running: boolean;
  onOpen: () => void;
  onRename: (t: string) => void;
  onDelete: () => void;
}) {
  const { c } = props;
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  return (
    <div className={`hist ${props.active ? "active" : ""}`}>
      {editing ? (
        <input
          autoFocus
          defaultValue={c.title}
          onBlur={(e) => {
            setEditing(false);
            if (e.target.value.trim() && e.target.value !== c.title) props.onRename(e.target.value);
          }}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        />
      ) : (
        <button className="hist-main" onClick={props.onOpen}>
          <span className="hist-title">{props.running && "⏳ "}{c.title}</span>
          <span className="hist-meta">
            {fmtTime(c.updatedAt)} · {c.messageCount} 条 · {providerName[c.provider] ?? c.provider}
          </span>
        </button>
      )}
      <div className="hist-actions">
        <button title="重命名" onClick={() => setEditing(true)}>✎</button>
        {confirm ? (
          <button className="danger" onClick={props.onDelete} onBlur={() => setConfirm(false)} autoFocus>确认删除</button>
        ) : (
          <button title="删除" onClick={() => setConfirm(true)}>🗑</button>
        )}
      </div>
    </div>
  );
}

/** Friendly, non-technical description of what a tool call means. */
function friendlyTool(name: string = ""): { icon: string; text: string } {
  const n = name.toLowerCase();
  if (/^(read|glob|grep|ls|notebookread)$/.test(n)) return { icon: "📖", text: "翻阅资料" };
  if (/^(write|edit|multiedit|notebookedit|apply_patch)$/.test(n)) return { icon: "✍️", text: "动笔写写改改" };
  if (/^(bash|shell|powershell|bashoutput|killshell|monitor)$/.test(n)) return { icon: "🛠️", text: "动手处理" };
  if (n === "websearch") return { icon: "🔎", text: "上网查资料" };
  if (n === "webfetch") return { icon: "🌐", text: "阅读网页" };
  if (n === "skill") return { icon: "📚", text: "翻开技能手册" };
  if (n === "task" || n === "agent") return { icon: "🤝", text: "请帮手一起做" };
  if (n === "todowrite") return { icon: "📝", text: "列计划" };
  return { icon: "✨", text: "忙着准备" };
}

/** Collapse consecutive tool messages into one group. */
function groupTools(messages: Message[]): (Message | Message[])[] {
  const out: (Message | Message[])[] = [];
  for (const m of messages) {
    if (m.role !== "tool") out.push(m);
    else {
      const last = out[out.length - 1];
      if (Array.isArray(last)) last.push(m);
      else out.push([m]);
    }
  }
  return out;
}

/** One quiet line telling the user she is busy — no commands, paths or tool names. */
function ActivityRow({ steps, live }: { steps: Message[]; live: boolean }) {
  const kinds: { icon: string; text: string }[] = [];
  for (const s of steps) {
    const f = friendlyTool(s.meta?.name);
    if (!kinds.some((k) => k.text === f.text)) kinds.push(f);
  }
  const current = friendlyTool(steps[steps.length - 1].meta?.name);
  return (
    <div className={`activity-row ${live ? "live" : ""}`}>
      {live ? (
        <>
          <span className="activity-dot" />
          正在{current.text}… <span className="activity-count">第 {steps.length} 步</span>
        </>
      ) : (
        <>
          {kinds.map((k) => (
            <span key={k.text} className="activity-kind">{k.icon} {k.text}</span>
          ))}
          {steps.length > 1 && <span className="activity-count">共 {steps.length} 步</span>}
        </>
      )}
    </div>
  );
}

function UserBody({ text, characterId }: { text: string; characterId: string }) {
  const { files } = useMemo(() => extractFiles(text), [text]);
  return (
    <>
      {text}
      <FileCards files={files} characterId={characterId} />
    </>
  );
}

function AssistantBody({ text, characterId }: { text: string; characterId: string }) {
  const { text: body, files } = useMemo(() => extractFiles(text), [text]);
  return (
    <div className="bubble-msg">
      {body && <Markdown text={body} />}
      <FileCards files={files} characterId={characterId} />
    </div>
  );
}
