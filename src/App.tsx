import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { isTauri } from "./api";
import { CharacterSprite } from "./components/CharacterSprite";
import { ChatPanel } from "./components/ChatPanel";
import { SettingsDialog } from "./components/SettingsDialog";
import { useStore } from "./store";

const STAGE_W = 1672;
const STAGE_H = 941;

/** Room width taken by the chat panel (424px wide + 12px margins). */
const PANEL_SPACE = 448;

function useStageScale(ref: React.RefObject<HTMLDivElement | null>) {
  const [size, setSize] = useState({ scale: 1, width: STAGE_W });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      // "cover" the window (the room art has generous margins)
      setSize({ scale: Math.max(r.width / STAGE_W, r.height / STAGE_H), width: r.width });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

/**
 * Horizontal camera pan (screen px) that brings the open character to the middle of the
 * part of the room the chat panel leaves visible. Clamped so the room art still covers
 * that visible part (any bare edge ends up behind the panel); 0 when nothing is open.
 */
function panFor(c: { scene?: unknown } | undefined, scale: number, roomW: number) {
  const visible = roomW - PANEL_SPACE;
  if (!c || visible < 200) return 0;
  const scene = (c.scene ?? {}) as { x?: number; width?: number };
  const stageLeft = roomW / 2 - (STAGE_W * scale) / 2;          // stage is centred in the room
  const charX = stageLeft + ((scene.x ?? 0) + (scene.width ?? 0) / 2) * scale;
  const want = visible / 2 - charX;
  const min = visible - STAGE_W * scale - stageLeft;            // stage's right edge stays >= panel edge
  const max = -stageLeft;                                       // stage's left edge stays <= 0
  return Math.round(Math.min(max, Math.max(min, want)));
}

export default function App() {
  const { state, dispatch } = useStore();
  const wrap = useRef<HTMLDivElement>(null);
  const { scale, width: roomW } = useStageScale(wrap);
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

  // Slide the room so the character being chatted with sits in the middle of the free space.
  const pan = panFor(open, scale, roomW);

  return (
    <div className={`app ${open ? "panel-open" : ""}`}>
      <div className="room" ref={wrap} onClick={(e) => e.target === e.currentTarget && dispatch({ type: "open", characterId: null })}>
        <div
          className="stage"
          style={{ width: STAGE_W, height: STAGE_H, transform: `translate(calc(-50% + ${pan}px), -50%) scale(${scale})` }}
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
