import { useEffect, useRef, useState } from "react";

/**
 * Plays a TexturePacker "JSON hash/array" sprite sheet (exported by Rigby2D and
 * repacked by art/tools/pack_sheets.py) on a canvas. Frames are drawn at their
 * spriteSourceSize offset inside sourceSize, so every pose shares one frame.
 * Until the sheet is decoded the still image is shown instead.
 */
interface Frame {
  frame: { x: number; y: number; w: number; h: number };
  spriteSourceSize: { x: number; y: number; w: number; h: number };
  sourceSize: { w: number; h: number };
  duration?: number;
}

interface Sheet {
  frames: Record<string, Frame> | (Frame & { filename: string })[];
  meta: { image: string };
}

type Loaded = { img: HTMLImageElement; frames: Frame[] };
const cache = new Map<string, Promise<Loaded>>();

function load(url: string): Promise<Loaded> {
  let p = cache.get(url);
  if (!p) {
    p = (async () => {
      const sheet: Sheet = await (await fetch(url)).json();
      const frames = Array.isArray(sheet.frames) ? sheet.frames : Object.values(sheet.frames);
      const img = new Image();
      img.src = new URL(sheet.meta.image, new URL(url, location.href)).href;
      await img.decode();
      return { img, frames };
    })();
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return p;
}

/** Start fetching/decoding a sheet ahead of time. */
export function preloadSheet(url: string) {
  load(url).catch(() => {});
}

export function SpritePlayer({ src, still, fps = 12, className }: { src: string; still?: string; fps?: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let raf = 0;
    let alive = true;
    setReady(false);
    load(src)
      .then(({ img, frames }) => {
        const canvas = ref.current;
        if (!alive || !canvas || frames.length === 0) return;
        const { w, h } = frames[0].sourceSize;
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d")!;
        let i = 0;
        let next = 0;
        const draw = (t: number) => {
          if (!alive) return;
          if (t >= next) {
            const f = frames[i];
            ctx.clearRect(0, 0, w, h);
            ctx.drawImage(img, f.frame.x, f.frame.y, f.frame.w, f.frame.h, f.spriteSourceSize.x, f.spriteSourceSize.y, f.frame.w, f.frame.h);
            if (i === 0 && next === 0) setReady(true);
            next = t + (f.duration ?? 1000 / fps);
            i = (i + 1) % frames.length;
          }
          raf = requestAnimationFrame(draw);
        };
        raf = requestAnimationFrame(draw);
      })
      .catch((e) => console.warn("sprite sheet failed", src, e));
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
    };
  }, [src, fps]);
  return (
    <>
      <canvas ref={ref} className={className} style={{ display: ready ? "block" : "none" }} />
      {!ready && still && <img src={still} className={className} draggable={false} alt="" />}
    </>
  );
}
