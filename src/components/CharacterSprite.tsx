import { useEffect, useMemo, useRef, useState } from "react";
import { baseActivity, labelFor, useStore } from "../store";
import type { Activity, Character } from "../types";
import { preloadSheet, SpritePlayer } from "./SpritePlayer";

type Pose = "reading" | "bored" | "working" | "done";

const poseFor: Record<Activity, Pose> = {
  reading: "reading",
  chatting: "reading",
  bored: "bored",
  working: "working",
  done: "done",
  error: "bored",
};

function pick<T>(arr: T[] | undefined): T | undefined {
  if (!arr || arr.length === 0) return undefined;
  return arr[Math.floor(Math.random() * arr.length)];
}

/** Alpha mask of the current pose, for pixel-accurate hover/click. */
function useAlphaMask(src: string | undefined) {
  const mask = useRef<{ data: Uint8ClampedArray; w: number; h: number } | null>(null);
  useEffect(() => {
    mask.current = null;
    if (!src) return;
    const img = new Image();
    img.src = src;
    img.decode().then(() => {
      const w = Math.max(1, Math.round(img.naturalWidth / 4));
      const h = Math.max(1, Math.round(img.naturalHeight / 4));
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(img, 0, 0, w, h);
      mask.current = { data: ctx.getImageData(0, 0, w, h).data, w, h };
    }).catch(() => {});
  }, [src]);
  return (fx: number, fy: number) => {
    const m = mask.current;
    if (!m) return true;
    const x = Math.floor(fx * m.w);
    const y = Math.floor(fy * m.h);
    if (x < 0 || y < 0 || x >= m.w || y >= m.h) return false;
    return m.data[(y * m.w + x) * 4 + 3] > 40;
  };
}

export function CharacterSprite({ character }: { character: Character }) {
  const { state, dispatch } = useStore();
  const base = baseActivity(state, character.id);
  const [bored, setBored] = useState(false);
  const [hover, setHover] = useState(false);
  const [line, setLine] = useState<string | null>(null);
  const lastPoke = useRef(Date.now());
  const isOpen = state.openCharacterId === character.id;

  // Idle → bored after a while; bored → back to reading after a stretch/yawn.
  useEffect(() => {
    if (base !== "reading" || isOpen) {
      setBored(false);
      lastPoke.current = Date.now();
      return;
    }
    const after = (character.boredAfterSec ?? 45) * 1000;
    const t = setInterval(() => {
      const idle = Date.now() - lastPoke.current;
      if (!bored && idle > after) setBored(true);
      if (bored && idle > after + 18000) {
        setBored(false);
        lastPoke.current = Date.now();
      }
    }, 1000);
    return () => clearInterval(t);
  }, [base, bored, isOpen, character.boredAfterSec]);

  const activity: Activity = base === "reading" && bored && !hover ? "bored" : base;
  const pose = poseFor[activity];

  // Speech bubble lines.
  useEffect(() => {
    const lines = character.lines?.[activity];
    if (activity === "done" || activity === "error") {
      setLine(pick(lines) ?? (activity === "done" ? "完成啦！" : "出了点问题…"));
      return;
    }
    if (activity === "working" || activity === "chatting") {
      setLine(activity === "chatting" ? "…" : pick(lines) ?? "工作中…");
      if (activity === "chatting") return;
      const t = setInterval(() => setLine(pick(lines) ?? "工作中…"), 6000);
      return () => clearInterval(t);
    }
    // reading / bored: occasional mumbles
    setLine(activity === "bored" ? pick(lines) ?? null : null);
    let hide: ReturnType<typeof setTimeout>;
    const t = setInterval(() => {
      setLine(pick(lines) ?? null);
      hide = setTimeout(() => setLine(null), 4500);
    }, activity === "bored" ? 9000 : 22000);
    return () => {
      clearInterval(t);
      clearTimeout(hide);
    };
  }, [activity, character.lines]);

  const sprites = character.sprites;
  const poses = useMemo(() => (["reading", "bored", "working", "done"] as Pose[]).filter((p) => sprites[p]), [sprites]);
  const currentImage = sprites[pose]?.image ?? sprites.reading?.image;
  const animated = !!sprites[pose]?.sheet;
  useEffect(() => {
    // decode the other poses' sheets in the background so switching is instant
    const t = setTimeout(() => poses.forEach((p) => sprites[p]?.sheet && preloadSheet(sprites[p]!.sheet!)), 1500);
    return () => clearTimeout(t);
  }, [poses, sprites]);
  const hit = useAlphaMask(currentImage);

  const { x, y, width, z, bubbleAnchor } = character.scene;
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const inside = hit((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    if (inside !== hover) setHover(inside);
    if (inside) lastPoke.current = Date.now();
  };
  const onClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (!hit((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height)) return;
    lastPoke.current = Date.now();
    setBored(false);
    dispatch({ type: "open", characterId: character.id });
  };

  const showBubble = line && !(isOpen && (activity === "reading" || activity === "bored"));
  return (
    <div
      className={`character act-${activity} ${animated ? "animated" : ""} ${hover ? "is-hover" : ""} ${isOpen ? "is-open" : ""}`}
      style={{ left: x, top: y, width, zIndex: z ?? 10, ["--theme" as any]: character.theme.color ?? "#c46a8c" }}
      onPointerMove={onMove}
      onPointerLeave={() => setHover(false)}
      onClick={onClick}
    >
      <div className="character-body">
        {poses.map((p) => {
          const def = sprites[p]!;
          return (
            <div key={p} className={`pose ${p === pose ? "active" : ""}`}>
              {def.sheet && p === pose ? (
                <SpritePlayer src={def.sheet} still={def.image} fps={def.fps} className="pose-img" />
              ) : (
                <img src={def.image} className="pose-img" draggable={false} alt="" />
              )}
            </div>
          );
        })}
      </div>

      {activity === "bored" && <div className="zzz"><span>z</span><span>z</span><span>z</span></div>}
      {activity === "working" && <div className="work-sparks"><span>✎</span><span>✦</span><span>✧</span></div>}
      {activity === "done" && <div className="done-sparks"><span>✦</span><span>★</span><span>✧</span><span>✦</span></div>}

      {showBubble && (
        <div
          className={`bubble bubble-${activity}`}
          style={{ left: `${(bubbleAnchor?.x ?? 0.5) * 100}%`, top: `${(bubbleAnchor?.y ?? 0) * 100}%` }}
        >
          {activity === "chatting" ? <span className="typing"><i /><i /><i /></span> : line}
          {activity === "working" && <span className="typing small"><i /><i /><i /></span>}
        </div>
      )}

      <div className="nametag">
        <b>{character.name}</b>
        <span className={`status-dot s-${activity}`} />
        <span>{labelFor(character, activity)}</span>
      </div>
    </div>
  );
}
