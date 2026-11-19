import { useEffect, useState } from "react";
import { useStore } from "../store";

export interface FileRef {
  path: string;
  name: string;
}

const CITATION = /:{1,2}codex-file-citation\{([^}]*)\}/g;
// `outputs/foo.md`, `C:\...\workspaces\iris\outputs\foo.pptx`, `/home/.../outputs/foo.md`
const CODE_PATH = /`([^`\n]*?(?:^|[\\/]|\b)(?:outputs|inputs)[\\/][^`\n]*?\.[A-Za-z0-9]{1,8})`/g;

function baseName(p: string) {
  return p.split(/[\\/]/).filter(Boolean).pop() ?? p;
}

/** Pull file references out of an assistant reply; citation directives are removed from the text. */
export function extractFiles(text: string): { text: string; files: FileRef[] } {
  const files: FileRef[] = [];
  const seen = new Set<string>();
  const add = (path: string) => {
    const name = baseName(path);
    // skip placeholders like outputs/读书笔记-<title>.md
    if (!name.includes(".") || /[<>{}*?|]/.test(name) || seen.has(name)) return;
    seen.add(name);
    files.push({ path, name });
  };
  const cleaned = text.replace(CITATION, (_m, attrs: string) => {
    const path = /path="([^"]*)"/.exec(attrs)?.[1];
    if (path) add(path);
    return "";
  });
  for (const m of cleaned.matchAll(CODE_PATH)) add(m[1]);
  return { text: cleaned.replace(/\n{3,}/g, "\n\n").trim(), files };
}

const ICONS: [RegExp, string][] = [
  [/^(pptx?|key|odp)$/, "📊"],
  [/^(docx?|odt|rtf|pages)$/, "📄"],
  [/^pdf$/, "📕"],
  [/^(xlsx?|csv|tsv|ods|numbers)$/, "📈"],
  [/^(md|txt|markdown)$/, "📝"],
  [/^(png|jpe?g|gif|webp|svg|bmp|heic)$/, "🖼️"],
  [/^(mp4|mov|webm|mkv|avi)$/, "🎬"],
  [/^(mp3|wav|flac|m4a|ogg)$/, "🎵"],
  [/^(html?|htm)$/, "🌐"],
  [/^(zip|7z|rar|tar|gz)$/, "🗜️"],
];

function fileIcon(name: string) {
  const ext = name.split(".").pop()!.toLowerCase();
  return ICONS.find(([re]) => re.test(ext))?.[1] ?? "📎";
}

const PREVIEWABLE = /\.(png|jpe?g|webp|gif|bmp)$/i;

/** Small square preview of a workspace image (empty box if not an image). */
export function ImageThumb({ characterId, path }: { characterId: string; path: string }) {
  const { api } = useStore();
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!PREVIEWABLE.test(path)) return;
    let alive = true;
    api?.readImage(characterId, path).then((u) => alive && setSrc(u)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [api, characterId, path]);
  return src ? <img className="thumb" src={src} alt="" /> : <span className="thumb">📎</span>;
}

/** Thumbnail of an image she produced (loaded through the backend, so only workspace files). */
function ImageCard({ file, characterId, onOpen }: { file: FileRef; characterId: string; onOpen: () => void }) {
  const { api } = useStore();
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    api?.readImage(characterId, file.path).then((u) => alive && setSrc(u)).catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [api, characterId, file.path]);
  if (failed) return null;
  return (
    <button className="image-card" title={`${file.name} · 双击用看图软件打开`} onDoubleClick={onOpen} onKeyDown={(e) => e.key === "Enter" && onOpen()}>
      {src ? <img src={src} alt={file.name} /> : <span className="image-loading">🖼️</span>}
      <span className="image-name">{file.name}</span>
    </button>
  );
}

export function FileCards({ files, characterId }: { files: FileRef[]; characterId: string }) {
  const { api } = useStore();
  const [error, setError] = useState<string | null>(null);
  // only show cards for files that really exist in her workspace
  const [exists, setExists] = useState<boolean[] | null>(null);
  const key = files.map((f) => f.path).join("\n");
  useEffect(() => {
    if (!api || files.length === 0) return;
    let alive = true;
    api
      .existingFiles(characterId, files.map((f) => f.path))
      .then((r) => alive && setExists(r))
      .catch(() => alive && setExists(files.map(() => false)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, characterId, key]);
  const shown = exists ? files.filter((_, i) => exists[i]) : [];
  if (shown.length === 0) return null;
  const open = async (f: FileRef) => {
    setError(null);
    try {
      await api?.openFile(characterId, f.path);
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <div className="file-cards">
      {shown.map((f) => {
        if (PREVIEWABLE.test(f.name)) return <ImageCard key={f.path} file={f} characterId={characterId} onOpen={() => open(f)} />;
        const dot = f.name.lastIndexOf(".");
        return (
          <button
            key={f.path}
            className="file-card"
            title="双击打开"
            onDoubleClick={() => open(f)}
            onKeyDown={(e) => e.key === "Enter" && open(f)}
          >
            <span className="file-icon">{fileIcon(f.name)}</span>
            <span className="file-meta">
              <span className="file-title">{f.name.slice(0, dot)}</span>
              <span className="file-ext">{f.name.slice(dot + 1).toUpperCase()} · 双击打开</span>
            </span>
          </button>
        );
      })}
      {error && <div className="file-error">{error}</div>}
    </div>
  );
}
