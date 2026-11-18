import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { isTauri } from "./api";
import { CharacterSprite } from "./components/CharacterSprite";
import { ChatPanel } from "./components/ChatPanel";
import { SettingsDialog } from "./components/SettingsDialog";
import { useStore } from "./store";

const STAGE_W = 1672;
const STAGE_H = 941;

function useStageScale(ref: React.RefObject<HTMLDivElement | null>) {
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      // "cover" the window (the room art has generous margins)
      setScale(Math.max(r.width / STAGE_W, r.height / STAGE_H));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return scale;
}

export default function App() {
  const { state, dispatch } = useStore();
  const wrap = useRef<HTMLDivElement>(null);
  const scale = useStageScale(wrap);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const open = state.characters.find((c) => c.id === state.openCharacterId);

  // Open links from chat in the system browser.
  useEffect(() => {
    const onClick = async (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest("a");
      if (!a || !a.href || !/^https?:|^mailto:/.test(a.href)) return;
      e.preventDefault();
      if (isTauri) {
        const { openUrl } = await import("@tauri-apps/plugin-opener");
        openUrl(a.href);
      } else {
        window.open(a.href, "_blank");
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  // Auto-dismiss toasts.
  useEffect(() => {
    if (state.toasts.length === 0) return;
    const t = setTimeout(() => dispatch({ type: "dismissToast", id: state.toasts[0].id }), 6000);
    return () => clearTimeout(t);
  }, [state.toasts, dispatch]);

  // Escape closes the panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (settingsOpen) setSettingsOpen(false);
        else dispatch({ type: "open", characterId: null });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [settingsOpen, dispatch]);

  return (
    <div className={`app ${open ? "panel-open" : ""}`}>
      <div className="room" ref={wrap} onClick={(e) => e.target === e.currentTarget && dispatch({ type: "open", characterId: null })}>
        <div
          className="stage"
          style={{ width: STAGE_W, height: STAGE_H, transform: `translate(-50%, -50%) scale(${scale})` }}
          onClick={(e) => {
            if ((e.target as HTMLElement).classList.contains("stage-bg")) dispatch({ type: "open", characterId: null });
          }}
        >
          <img className="stage-bg" src="/background.jpg" alt="" draggable={false} />
          {state.characters.map((c) => (
            <CharacterSprite key={c.id} character={c} />
          ))}
        </div>
      </div>

      <div className="logo" aria-label="Oh My AI Living Room">
        <div className="logo-main">Oh My AI</div>
        <div className="logo-sub"><span>❦</span> Living Room <span>❦</span></div>
      </div>

      <div className="topbar">
        <button className="icon-btn glass" title="设置" onClick={() => setSettingsOpen(true)}>⚙</button>
      </div>

      {!state.ready && !state.error && <div className="loading">正在打开客厅的门…</div>}
      {state.error && <div className="loading error">启动失败：{state.error}</div>}

      {open && <ChatPanel key={open.id} character={open} />}
      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}

      <div className="toasts">
        {state.toasts.map((t) => {
          const c = state.characters.find((c) => c.id === t.characterId);
          return (
            <button
              key={t.id}
              className={`toast ${t.kind}`}
              onClick={() => {
                dispatch({ type: "open", characterId: t.characterId });
                dispatch({ type: "dismissToast", id: t.id });
              }}
            >
              {c && <img className="avatar" src={`/characters/${c.id}/avatar.png`} alt="" />}
              <span>{t.text}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
