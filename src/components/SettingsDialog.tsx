import { useEffect, useState } from "react";
import { useStore } from "../store";
import type { AgentAvailability, ComfyStatus } from "../types";

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { state, dispatch, api } = useStore();
  const [agents, setAgents] = useState<AgentAvailability[] | null>(null);
  const [claudePath, setClaudePath] = useState(state.settings.claudePath ?? "");
  const [codexPath, setCodexPath] = useState(state.settings.codexPath ?? "");
  const [deepseekPath, setDeepseekPath] = useState(state.settings.deepseekPath ?? "");
  const [comfyUrl, setComfyUrl] = useState(state.settings.comfyuiUrl ?? "");
  const [comfy, setComfy] = useState<ComfyStatus | null | "checking">(null);
  const [saved, setSaved] = useState(false);

  const checkComfy = (url?: string) => {
    setComfy("checking");
    api?.checkComfyui(url ?? (comfyUrl.trim() || null)).then(setComfy).catch((e) => setComfy({ url: "", ok: false, detail: String(e) }));
  };
  useEffect(() => checkComfy(), [api]); // eslint-disable-line react-hooks/exhaustive-deps

  const check = () => {
    setAgents(null);
    api?.checkAgents().then(setAgents);
  };
  useEffect(check, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    const next = {
      ...state.settings,
      claudePath: claudePath.trim() || null,
      codexPath: codexPath.trim() || null,
      deepseekPath: deepseekPath.trim() || null,
      comfyuiUrl: comfyUrl.trim() || null,
    };
    await api?.saveSettings(next);
    dispatch({ type: "settings", settings: next });
    setSaved(true);
    check();
    checkComfy();
  };

  const row = (id: "claude" | "codex" | "deepseek", bin: string, label: string, value: string, set: (v: string) => void) => {
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
        <input value={value} placeholder={a?.path ?? `自动在 PATH 中查找 ${bin}`} onChange={(e) => { set(e.target.value); setSaved(false); }} />
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
          {row("claude", "claude", "Claude Code", claudePath, setClaudePath)}
          {row("codex", "codex", "Codex", codexPath, setCodexPath)}
          {row("deepseek", "dsh", "DeepSeek Harness", deepseekPath, setDeepseekPath)}
          <p className="muted">每个角色可在「关于她」里选择使用哪一个 harness。DeepSeek Harness 以 <code>dsh --profile headless</code> 运行，API Key 读取环境变量或 <code>~/.dsh/.env</code> 里的 <code>DEEPSEEK_API_KEY</code>。</p>
        </section>
        <section>
          <h4>ComfyUI（画图）</h4>
          <div className="agent-row">
            <div className="agent-head">
              <b>服务地址</b>
              {comfy === "checking" || comfy === null ? (
                <span className="pill ghost">检测中…</span>
              ) : comfy.ok ? (
                <span className="pill ok">✓ {comfy.detail}</span>
              ) : (
                <span className="pill bad" title={comfy.detail}>连不上</span>
              )}
            </div>
            <input
              value={comfyUrl}
              placeholder="http://127.0.0.1:8188"
              onChange={(e) => { setComfyUrl(e.target.value); setSaved(false); }}
              onBlur={() => checkComfy()}
            />
          </div>
          <p className="muted">使用 Claude Code 或 DeepSeek Harness 的角色（例如 Poppy）通过这个 ComfyUI 画图、改图、反推提示词、拆图层；使用 Codex 时改用 Codex 内建的画图功能。</p>
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
