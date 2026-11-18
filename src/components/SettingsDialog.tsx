import { useEffect, useState } from "react";
import { useStore } from "../store";
import type { AgentAvailability } from "../types";

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { state, dispatch, api } = useStore();
  const [agents, setAgents] = useState<AgentAvailability[] | null>(null);
  const [claudePath, setClaudePath] = useState(state.settings.claudePath ?? "");
  const [codexPath, setCodexPath] = useState(state.settings.codexPath ?? "");
  const [saved, setSaved] = useState(false);

  const check = () => {
    setAgents(null);
    api?.checkAgents().then(setAgents);
  };
  useEffect(check, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    const next = { ...state.settings, claudePath: claudePath.trim() || null, codexPath: codexPath.trim() || null };
    await api?.saveSettings(next);
    dispatch({ type: "settings", settings: next });
    setSaved(true);
    check();
  };

  const row = (id: "claude" | "codex", label: string, value: string, set: (v: string) => void) => {
    const a = agents?.find((x) => x.provider === id);
    return (
      <div className="agent-row">
        <div className="agent-head">
          <b>{label}</b>
          {agents === null ? (
            <span className="pill ghost">检测中…</span>
          ) : a?.path ? (
            <span className="pill ok">✓ {a.version ?? "已找到"}</span>
          ) : (
            <span className="pill bad">未找到</span>
          )}
        </div>
        <input value={value} placeholder={a?.path ?? `自动在 PATH 中查找 ${id}`} onChange={(e) => { set(e.target.value); setSaved(false); }} />
      </div>
    );
  };

  return (
    <div className="modal-back" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <header>
          <h3>客厅设置</h3>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </header>
        <section>
          <h4>Agent Harness 命令行</h4>
          {row("claude", "Claude Code", claudePath, setClaudePath)}
          {row("codex", "Codex", codexPath, setCodexPath)}
          <p className="muted">每个角色可在「关于她」里选择使用哪一个 harness。DeepSeek harness 将在后续版本支持。</p>
        </section>
        <section>
          <h4>数据位置</h4>
          <p className="muted mono">{state.dataDir}</p>
          <p className="muted">对话记录保存在 living_room.db（SQLite），每个角色的工作目录在 workspaces/&lt;角色&gt;/。</p>
        </section>
        <footer>
          {saved && <span className="muted">已保存</span>}
          <button className="btn" onClick={save}>保存</button>
        </footer>
      </div>
    </div>
  );
}
