mod agent;
mod characters;
mod db;

use agent::{AgentEvent, Provider, RunSpec};
use characters::{AgentConfig, Character};
use db::{Conversation, Db, Message};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_window_state::StateFlags;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    #[serde(default)]
    pub claude_path: Option<String>,
    #[serde(default)]
    pub codex_path: Option<String>,
    /// DeepSeek Harness launcher (`dsh`).
    #[serde(default)]
    pub deepseek_path: Option<String>,
    /// ComfyUI server the painting skills talk to (Claude Code harness).
    #[serde(default)]
    pub comfyui_url: Option<String>,
    /// Per-character overrides of the agent config.
    #[serde(default)]
    pub characters: HashMap<String, AgentConfig>,
}

struct RunInfo {
    run_id: String,
    conversation_id: String,
    /// Became real work (used a tool or ran longer than WORK_AFTER).
    working: bool,
    cancel: Option<tokio::sync::oneshot::Sender<()>>,
}

struct AppState {
    db: Mutex<Db>,
    characters: Vec<Character>,
    data_dir: PathBuf,
    settings: Mutex<Settings>,
    runs: Mutex<HashMap<String, RunInfo>>,
}

impl AppState {
    fn character(&self, id: &str) -> Result<&Character, String> {
        self.characters
            .iter()
            .find(|c| c.id == id)
            .ok_or_else(|| format!("unknown character: {id}"))
    }
    fn workspace(&self, id: &str) -> PathBuf {
        self.data_dir.join("workspaces").join(id)
    }
    fn agent_config(&self, c: &Character) -> AgentConfig {
        self.settings
            .lock()
            .unwrap()
            .characters
            .get(&c.id)
            .cloned()
            .unwrap_or_else(|| c.agent.clone())
    }
    fn settings_path(&self) -> PathBuf {
        self.data_dir.join("settings.json")
    }
}

const DEFAULT_COMFYUI_URL: &str = "http://127.0.0.1:8188";

impl Settings {
    fn comfyui_url(&self) -> String {
        self.comfyui_url
            .as_deref()
            .map(|u| u.trim().trim_end_matches('/'))
            .filter(|u| !u.is_empty())
            .unwrap_or(DEFAULT_COMFYUI_URL)
            .to_string()
    }
}

fn err<E: std::fmt::Display>(e: E) -> String {
    e.to_string()
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AgentAvailability {
    provider: String,
    path: Option<String>,
    version: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ActiveRun {
    character_id: String,
    conversation_id: String,
    run_id: String,
    working: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Bootstrap {
    characters: Vec<Character>,
    settings: Settings,
    data_dir: String,
    active_runs: Vec<ActiveRun>,
}

#[tauri::command]
fn bootstrap(state: State<'_, AppState>) -> Bootstrap {
    let runs = state.runs.lock().unwrap();
    Bootstrap {
        characters: state.characters.clone(),
        settings: state.settings.lock().unwrap().clone(),
        data_dir: state.data_dir.to_string_lossy().into_owned(),
        active_runs: runs
            .iter()
            .map(|(cid, r)| ActiveRun {
                character_id: cid.clone(),
                conversation_id: r.conversation_id.clone(),
                run_id: r.run_id.clone(),
                working: r.working,
            })
            .collect(),
    }
}

#[tauri::command]
async fn check_agents(state: State<'_, AppState>) -> Result<Vec<AgentAvailability>, String> {
    let settings = state.settings.lock().unwrap().clone();
    let mut out = vec![];
    for (p, ov) in [
        (Provider::Claude, settings.claude_path.clone()),
        (Provider::Codex, settings.codex_path.clone()),
        (Provider::Deepseek, settings.deepseek_path.clone()),
    ] {
        let path = agent::resolve_binary(p, ov.as_deref());
        let mut version = None;
        if let Some(path) = &path {
            let mut c = tokio::process::Command::new(path);
            c.arg("--version").env("PATH", agent::augmented_path());
            #[cfg(windows)]
            c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
            let fut = c.output();
            if let Ok(Ok(o)) = tokio::time::timeout(std::time::Duration::from_secs(8), fut).await {
                let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
                if !s.is_empty() {
                    version = Some(s);
                }
            }
        }
        out.push(AgentAvailability {
            provider: p.as_str().into(),
            path: path.map(|p| p.to_string_lossy().into_owned()),
            version,
        });
    }
    Ok(out)
}

#[tauri::command]
fn save_settings(state: State<'_, AppState>, settings: Settings) -> Result<(), String> {
    std::fs::write(
        state.settings_path(),
        serde_json::to_string_pretty(&settings).map_err(err)?,
    )
    .map_err(err)?;
    *state.settings.lock().unwrap() = settings;
    Ok(())
}

#[tauri::command]
fn list_conversations(
    state: State<'_, AppState>,
    character_id: String,
) -> Result<Vec<Conversation>, String> {
    state
        .db
        .lock()
        .unwrap()
        .list_conversations(&character_id)
        .map_err(err)
}

#[tauri::command]
fn get_messages(state: State<'_, AppState>, conversation_id: String) -> Result<Vec<Message>, String> {
    state.db.lock().unwrap().messages(&conversation_id).map_err(err)
}

#[tauri::command]
fn delete_conversation(state: State<'_, AppState>, conversation_id: String) -> Result<(), String> {
    if state
        .runs
        .lock()
        .unwrap()
        .values()
        .any(|r| r.conversation_id == conversation_id)
    {
        return Err("这个对话还在进行中，不能删除".into());
    }
    state
        .db
        .lock()
        .unwrap()
        .delete_conversation(&conversation_id)
        .map_err(err)
}

#[tauri::command]
fn rename_conversation(
    state: State<'_, AppState>,
    conversation_id: String,
    title: String,
) -> Result<(), String> {
    state
        .db
        .lock()
        .unwrap()
        .rename_conversation(&conversation_id, title.trim())
        .map_err(err)
}

#[tauri::command]
fn open_workspace(app: AppHandle, state: State<'_, AppState>, character_id: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let ws = state.workspace(&character_id);
    std::fs::create_dir_all(&ws).map_err(err)?;
    app.opener()
        .open_path(ws.to_string_lossy(), None::<&str>)
        .map_err(err)
}

/// Resolve a path the agent mentioned to a real file inside the character's workspace.
fn workspace_file(state: &AppState, character_id: &str, path: &str) -> Result<PathBuf, String> {
    let ws = state
        .workspace(character_id)
        .canonicalize()
        .map_err(|_| "工作目录不存在".to_string())?;
    let p = PathBuf::from(path.trim());
    let p = if p.is_absolute() { p } else { ws.join(p) };
    let p = p
        .canonicalize()
        .map_err(|_| "找不到这个文件，可能已被移动或删除".to_string())?;
    if !p.starts_with(&ws) {
        return Err("只能打开她工作目录里的文件".into());
    }
    Ok(p)
}

/// Which of these mentioned paths are real files in the workspace (for file cards).
#[tauri::command]
fn existing_files(state: State<'_, AppState>, character_id: String, paths: Vec<String>) -> Vec<bool> {
    paths
        .iter()
        .map(|p| workspace_file(&state, &character_id, p).map(|f| f.is_file()).unwrap_or(false))
        .collect()
}

/// Open a file the character produced, with the system's default app.
/// Only files inside that character's workspace; scripts/executables are
/// revealed in the file manager instead of being run.
#[tauri::command]
fn open_file(app: AppHandle, state: State<'_, AppState>, character_id: String, path: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let p = workspace_file(&state, &character_id, &path)?;
    const RISKY: &[&str] = &[
        "exe", "bat", "cmd", "com", "ps1", "psm1", "vbs", "vbe", "js", "jse", "wsf", "msi", "msix", "lnk", "scr",
        "pif", "reg", "jar", "sh", "bash", "zsh", "run", "appimage", "desktop", "py", "pyw", "app", "command",
    ];
    let ext = p.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase();
    if p.is_dir() || RISKY.contains(&ext.as_str()) {
        return app.opener().reveal_item_in_dir(&p).map_err(err);
    }
    app.opener().open_path(p.to_string_lossy(), None::<&str>).map_err(err)
}

const IMAGE_EXTS: &[(&str, &str)] = &[
    ("png", "image/png"),
    ("jpg", "image/jpeg"),
    ("jpeg", "image/jpeg"),
    ("webp", "image/webp"),
    ("gif", "image/gif"),
    ("bmp", "image/bmp"),
];

fn image_mime(p: &std::path::Path) -> Option<&'static str> {
    let ext = p.extension()?.to_str()?.to_ascii_lowercase();
    IMAGE_EXTS.iter().find(|(e, _)| *e == ext).map(|(_, m)| *m)
}

fn base64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for c in data.chunks(3) {
        let n = (c[0] as u32) << 16 | (*c.get(1).unwrap_or(&0) as u32) << 8 | *c.get(2).unwrap_or(&0) as u32;
        for i in 0..4 {
            if i <= c.len() {
                out.push(T[(n >> (18 - 6 * i) & 63) as usize] as char);
            } else {
                out.push('=');
            }
        }
    }
    out
}

/// An image from her workspace as a data: URL, for inline previews in chat.
#[tauri::command]
fn read_image(state: State<'_, AppState>, character_id: String, path: String) -> Result<String, String> {
    let p = workspace_file(&state, &character_id, &path)?;
    let mime = image_mime(&p).ok_or("不是图片文件")?;
    let meta = std::fs::metadata(&p).map_err(err)?;
    if meta.len() > 25 * 1024 * 1024 {
        return Err("图片太大，无法预览".into());
    }
    let data = std::fs::read(&p).map_err(err)?;
    Ok(format!("data:{mime};base64,{}", base64(&data)))
}

/// A file name that is safe to create inside `inputs/`, made unique if it already exists.
fn unique_input_path(ws: &std::path::Path, name: &str) -> PathBuf {
    let clean: String = name
        .chars()
        .map(|c| if c.is_control() || "\\/:*?\"<>|".contains(c) { '_' } else { c })
        .collect();
    let clean = clean.trim().trim_start_matches('.');
    let clean = if clean.is_empty() { "image.png" } else { clean };
    let dir = ws.join("inputs");
    let p = dir.join(clean);
    if !p.exists() {
        return p;
    }
    let (stem, ext) = match clean.rsplit_once('.') {
        Some((s, e)) => (s.to_string(), format!(".{e}")),
        None => (clean.to_string(), String::new()),
    };
    (2..)
        .map(|i| dir.join(format!("{stem}-{i}{ext}")))
        .find(|p| !p.exists())
        .unwrap()
}

/// Copy a file the user dropped on the chat into her workspace (`inputs/`), so
/// the agent can read it. Returns the workspace-relative path.
#[tauri::command]
fn import_file(state: State<'_, AppState>, character_id: String, path: String) -> Result<String, String> {
    state.character(&character_id)?;
    let src = PathBuf::from(&path);
    if !src.is_file() {
        return Err("只能添加文件（不支持文件夹）".into());
    }
    let ws = state.workspace(&character_id);
    std::fs::create_dir_all(ws.join("inputs")).map_err(err)?;
    let name = src.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let dst = unique_input_path(&ws, &name);
    std::fs::copy(&src, &dst).map_err(err)?;
    Ok(format!("inputs/{}", dst.file_name().unwrap().to_string_lossy()))
}

/// Save pasted bytes (e.g. a screenshot from the clipboard) into `inputs/`.
#[tauri::command]
fn save_upload(state: State<'_, AppState>, character_id: String, name: String, data: Vec<u8>) -> Result<String, String> {
    state.character(&character_id)?;
    let ws = state.workspace(&character_id);
    std::fs::create_dir_all(ws.join("inputs")).map_err(err)?;
    let dst = unique_input_path(&ws, &name);
    std::fs::write(&dst, data).map_err(err)?;
    Ok(format!("inputs/{}", dst.file_name().unwrap().to_string_lossy()))
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ComfyStatus {
    url: String,
    ok: bool,
    detail: String,
}

/// Probe ComfyUI's `/system_stats` (plain HTTP/1.0, so no HTTP client dependency).
#[tauri::command]
async fn check_comfyui(state: State<'_, AppState>, url: Option<String>) -> Result<ComfyStatus, String> {
    let url = match url.map(|u| u.trim().trim_end_matches('/').to_string()).filter(|u| !u.is_empty()) {
        Some(u) => u,
        None => state.settings.lock().unwrap().comfyui_url(),
    };
    let probe = url.clone();
    let res = tauri::async_runtime::spawn_blocking(move || -> Result<String, String> {
        use std::io::{Read, Write};
        use std::net::ToSocketAddrs;
        let rest = probe
            .strip_prefix("http://")
            .ok_or("目前只支持 http:// 地址")?;
        let (hostport, base) = match rest.split_once('/') {
            Some((h, b)) => (h, format!("/{b}")),
            None => (rest, String::new()),
        };
        let addr_str = if hostport.contains(':') { hostport.to_string() } else { format!("{hostport}:80") };
        let addr = addr_str
            .to_socket_addrs()
            .map_err(|e| format!("地址无效：{e}"))?
            .next()
            .ok_or("地址无效")?;
        let t = std::time::Duration::from_secs(4);
        let mut s = std::net::TcpStream::connect_timeout(&addr, t).map_err(|e| format!("连不上：{e}"))?;
        s.set_read_timeout(Some(t)).ok();
        write!(s, "GET {base}/system_stats HTTP/1.0\r\nHost: {hostport}\r\n\r\n").map_err(err)?;
        let mut body = String::new();
        s.read_to_string(&mut body).map_err(err)?;
        let (head, json) = body.split_once("\r\n\r\n").unwrap_or((&body, ""));
        if !head.starts_with("HTTP/1.1 200") && !head.starts_with("HTTP/1.0 200") {
            return Err(head.lines().next().unwrap_or("无响应").to_string());
        }
        let v: serde_json::Value = serde_json::from_str(json).map_err(|_| "不像是 ComfyUI".to_string())?;
        let ver = v["system"]["comfyui_version"].as_str().unwrap_or("?");
        let gpu = v["devices"][0]["name"].as_str().unwrap_or("");
        Ok(format!("ComfyUI {ver} {gpu}").trim().to_string())
    })
    .await
    .map_err(err)?;
    Ok(match res {
        Ok(detail) => ComfyStatus { url, ok: true, detail },
        Err(detail) => ComfyStatus { url, ok: false, detail },
    })
}

#[tauri::command]
fn cancel_run(state: State<'_, AppState>, character_id: String) -> Result<(), String> {
    if let Some(r) = state.runs.lock().unwrap().get_mut(&character_id) {
        if let Some(tx) = r.cancel.take() {
            let _ = tx.send(());
        }
    }
    Ok(())
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SendResult {
    conversation: Conversation,
    user_message: Message,
    run_id: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct EventPayload {
    run_id: String,
    character_id: String,
    conversation_id: String,
    event: AgentEvent,
    /// The persisted row, when the event produced/updated one.
    message: Option<Message>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct StatusPayload {
    character_id: String,
    conversation_id: String,
    run_id: String,
    /// "running" (replying) | "working" (doing real work) | "finished"
    status: String,
    /// Whether this run turned into work (drives the "done" celebration).
    worked: bool,
    ok: bool,
}

/// A reply that takes longer than this counts as work even without tool calls.
const WORK_AFTER: std::time::Duration = std::time::Duration::from_secs(10);

fn make_title(text: &str) -> String {
    let one_line = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let t: String = one_line.chars().take(24).collect();
    if one_line.chars().count() > 24 {
        format!("{t}…")
    } else if t.is_empty() {
        "新对话".into()
    } else {
        t
    }
}

#[tauri::command]
async fn send_message(
    app: AppHandle,
    state: State<'_, AppState>,
    character_id: String,
    conversation_id: Option<String>,
    text: String,
) -> Result<SendResult, String> {
    let text = text.trim().to_string();
    if text.is_empty() {
        return Err("消息不能为空".into());
    }
    let character = state.character(&character_id)?.clone();
    if state.runs.lock().unwrap().contains_key(&character_id) {
        return Err(format!("{} 正在忙，请等她完成或先取消当前工作", character.name));
    }
    let cfg = state.agent_config(&character);
    let provider = Provider::parse(&cfg.provider)
        .ok_or_else(|| format!("暂不支持的 agent：{}", cfg.provider))?;
    let settings = state.settings.lock().unwrap().clone();
    let override_path = match provider {
        Provider::Claude => settings.claude_path.clone(),
        Provider::Codex => settings.codex_path.clone(),
        Provider::Deepseek => settings.deepseek_path.clone(),
    };
    let binary = agent::resolve_binary(provider, override_path.as_deref()).ok_or_else(|| {
        format!(
            "找不到 {} 命令，请先安装或在设置里指定路径",
            provider.binary()
        )
    })?;

    // Conversation + user message.
    let (conversation, user_message) = {
        let db = state.db.lock().unwrap();
        let conv = match &conversation_id {
            Some(id) => db
                .get_conversation(id)
                .map_err(err)?
                .ok_or("对话不存在")?,
            None => db
                .create_conversation(&character_id, &make_title(&text), provider.as_str())
                .map_err(err)?,
        };
        let msg = db
            .add_message(&conv.id, "user", &text, &json!({}))
            .map_err(err)?;
        let conv = db.get_conversation(&conv.id).map_err(err)?.unwrap();
        (conv, msg)
    };
    // Only resume a session created by the same harness.
    let resume = if conversation.provider == provider.as_str() {
        conversation.agent_session_id.clone()
    } else {
        None
    };

    let ws = state.workspace(&character_id);
    characters::prepare_workspace(&character, &ws).map_err(err)?;
    let persona_file = characters::persona_file(&ws);
    let dsh_patch = if provider == Provider::Deepseek {
        characters::write_dsh_patch(&character, &ws, cfg.model.as_deref()).map_err(err)?
    } else {
        PathBuf::new()
    };
    let mut cmd = agent::build_command(&RunSpec {
        provider,
        binary,
        workspace: &ws,
        persona_file: &persona_file,
        dsh_patch: &dsh_patch,
        model: cfg.model.as_deref(),
        permission_mode: &cfg.permission_mode,
        resume: resume.as_deref(),
        allowed_tools: characters::allowed_tools(&character, &ws),
        env: vec![("COMFYUI_URL".into(), settings.comfyui_url())],
    });
    cmd.stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);
    let mut child = cmd.spawn().map_err(|e| format!("启动 agent 失败：{e}"))?;

    let run_id = uuid::Uuid::new_v4().to_string();
    let (cancel_tx, cancel_rx) = tokio::sync::oneshot::channel::<()>();
    state.runs.lock().unwrap().insert(
        character_id.clone(),
        RunInfo {
            run_id: run_id.clone(),
            conversation_id: conversation.id.clone(),
            working: false,
            cancel: Some(cancel_tx),
        },
    );
    let _ = app.emit(
        "agent-status",
        StatusPayload {
            character_id: character_id.clone(),
            conversation_id: conversation.id.clone(),
            run_id: run_id.clone(),
            status: "running".into(),
            worked: false,
            ok: true,
        },
    );

    // Feed the prompt through stdin.
    let prompt = text.clone();
    if let Some(mut stdin) = child.stdin.take() {
        tauri::async_runtime::spawn(async move {
            let _ = stdin.write_all(prompt.as_bytes()).await;
            let _ = stdin.shutdown().await;
        });
    }

    tauri::async_runtime::spawn(drive_run(
        app.clone(),
        child,
        cancel_rx,
        provider,
        character_id.clone(),
        conversation.id.clone(),
        run_id.clone(),
    ));

    Ok(SendResult {
        conversation,
        user_message,
        run_id,
    })
}

#[allow(clippy::too_many_arguments)]
async fn drive_run(
    app: AppHandle,
    mut child: tokio::process::Child,
    mut cancel_rx: tokio::sync::oneshot::Receiver<()>,
    provider: Provider,
    character_id: String,
    conversation_id: String,
    run_id: String,
) {
    let state = app.state::<AppState>();
    let stderr_buf = Arc::new(Mutex::new(String::new()));
    if let Some(mut stderr) = child.stderr.take() {
        let buf = stderr_buf.clone();
        tauri::async_runtime::spawn(async move {
            let mut s = String::new();
            let _ = stderr.read_to_string(&mut s).await;
            *buf.lock().unwrap() = s;
        });
    }
    let stdout = child.stdout.take().expect("piped stdout");
    let mut lines = BufReader::new(stdout).lines();
    let mut last_tool: Option<Message> = None;
    let mut finished: Option<(bool, Option<String>)> = None;
    let mut cancelled = false;
    let mut working = false;
    let work_timer = tokio::time::sleep(WORK_AFTER);
    tokio::pin!(work_timer);

    let emit = |event: AgentEvent, message: Option<Message>| {
        let _ = app.emit(
            "agent-event",
            EventPayload {
                run_id: run_id.clone(),
                character_id: character_id.clone(),
                conversation_id: conversation_id.clone(),
                event,
                message,
            },
        );
    };

    // Promote the run from "replying" to "working" (shown as the working pose).
    let promote = |working: &mut bool| {
        if *working {
            return;
        }
        *working = true;
        if let Some(r) = state.runs.lock().unwrap().get_mut(&character_id) {
            r.working = true;
        }
        let _ = app.emit(
            "agent-status",
            StatusPayload {
                character_id: character_id.clone(),
                conversation_id: conversation_id.clone(),
                run_id: run_id.clone(),
                status: "working".into(),
                worked: true,
                ok: true,
            },
        );
    };

    loop {
        tokio::select! {
            _ = &mut work_timer, if !working => promote(&mut working),
            line = lines.next_line() => {
                let line = match line { Ok(Some(l)) => l, _ => break };
                for ev in agent::parse_line(provider, &line) {
                    let mut persisted = None;
                    {
                        let db = state.db.lock().unwrap();
                        match &ev {
                            AgentEvent::Session { session_id } => {
                                let _ = db.set_session(&conversation_id, provider.as_str(), session_id);
                            }
                            AgentEvent::Message { text } => {
                                persisted = db.add_message(&conversation_id, "assistant", text, &json!({ "provider": provider.as_str() })).ok();
                            }
                            AgentEvent::Tool { name, summary } => {
                                persisted = db.add_message(&conversation_id, "tool", summary, &json!({ "name": name })).ok();
                                last_tool = persisted.clone();
                            }
                            AgentEvent::ToolResult { ok, output } => {
                                if let Some(t) = last_tool.as_mut() {
                                    t.meta["ok"] = json!(ok);
                                    t.meta["output"] = json!(output);
                                    let _ = db.update_meta(t.id, &t.meta);
                                    persisted = Some(t.clone());
                                }
                            }
                            AgentEvent::Done { ok, error, cost_usd, duration_ms } => {
                                finished = Some((*ok, error.clone()));
                                if let Some(e) = error {
                                    persisted = db.add_message(&conversation_id, "error", e, &json!({})).ok();
                                }
                                if *ok {
                                    persisted = persisted.or_else(|| db.add_message(&conversation_id, "system", "done", &json!({ "costUsd": cost_usd, "durationMs": duration_ms })).ok());
                                }
                            }
                            AgentEvent::Delta { .. } => {}
                        }
                    }
                    if matches!(ev, AgentEvent::Tool { .. }) {
                        promote(&mut working);
                    }
                    emit(ev, persisted);
                }
            }
            _ = &mut cancel_rx => {
                cancelled = true;
                let _ = child.kill().await;
                break;
            }
        }
    }
    let status = child.wait().await;

    if finished.is_none() {
        let error = if cancelled {
            "已取消".to_string()
        } else {
            // Give the stderr reader a moment to flush.
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
            let se = stderr_buf.lock().unwrap().trim().to_string();
            let code = status.ok().and_then(|s| s.code());
            if se.is_empty() {
                format!("agent 进程意外结束 (exit code {code:?})")
            } else {
                let tail: String = se.chars().rev().take(1500).collect::<Vec<_>>().into_iter().rev().collect();
                tail
            }
        };
        let msg = state
            .db
            .lock()
            .unwrap()
            .add_message(&conversation_id, "error", &error, &json!({ "cancelled": cancelled }))
            .ok();
        emit(
            AgentEvent::Done {
                ok: false,
                error: Some(error.clone()),
                cost_usd: None,
                duration_ms: None,
            },
            msg,
        );
        finished = Some((false, Some(error)));
    }

    state.runs.lock().unwrap().remove(&character_id);
    let _ = app.emit(
        "agent-status",
        StatusPayload {
            character_id: character_id.clone(),
            conversation_id: conversation_id.clone(),
            run_id: run_id.clone(),
            status: "finished".into(),
            worked: working,
            ok: finished.map(|f| f.0).unwrap_or(false),
        },
    );
}

/// Where conversations, settings and workspaces live.
/// Windows: `%APPDATA%\ohmyailivingroom\`; elsewhere the platform app-data dir
/// (Linux: `~/.local/share/com.ohmyai.livingroom/`).
fn data_dir(app: &AppHandle) -> tauri::Result<PathBuf> {
    if cfg!(windows) {
        if let Some(appdata) = std::env::var_os("APPDATA") {
            return Ok(PathBuf::from(appdata).join("ohmyailivingroom"));
        }
    }
    app.path().app_data_dir()
}

fn characters_root(app: &AppHandle) -> PathBuf {
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../characters");
    if cfg!(debug_assertions) && dev.is_dir() {
        return dev;
    }
    if let Ok(res) = app.path().resource_dir() {
        let p = res.join("characters");
        if p.is_dir() {
            return p;
        }
    }
    dev
}

/// Fraction of the monitor the window takes up on first launch.
const FIRST_LAUNCH_SCALE: f64 = 0.8;

/// The main window starts hidden (see tauri.conf.json). On the very first launch, before the
/// window-state plugin has saved anything, size it to a share of the current monitor and center
/// it; later launches keep the size/position the plugin restored. Then show it.
fn init_main_window(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else { return };
    let has_saved_state = app
        .path()
        .app_config_dir()
        .map(|d| d.join(tauri_plugin_window_state::DEFAULT_FILENAME).is_file())
        .unwrap_or(false);
    if !has_saved_state {
        let monitor = win.current_monitor().ok().flatten().or_else(|| win.primary_monitor().ok().flatten());
        if let Some(m) = monitor {
            let scale = m.scale_factor();
            let area = m.work_area().size.to_logical::<f64>(scale);
            // never below the configured minimum, never larger than the screen
            let w = (area.width * FIRST_LAUNCH_SCALE).max(960.0).min(area.width);
            let h = (area.height * FIRST_LAUNCH_SCALE).max(600.0).min(area.height);
            let _ = win.set_size(tauri::LogicalSize::new(w, h));
        }
        let _ = win.center();
    }
    let _ = win.show();
    let _ = win.set_focus();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(
            // remembers size/position/maximized between launches; visibility is ours to manage
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(StateFlags::all() - StateFlags::VISIBLE)
                .build(),
        )
        .setup(|app| {
            init_main_window(app.handle());
            let data_dir = data_dir(app.handle())?;
            std::fs::create_dir_all(&data_dir)?;
            let db = Db::open(&data_dir.join("living_room.db"))?;
            let settings: Settings = std::fs::read_to_string(data_dir.join("settings.json"))
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
                .unwrap_or_default();
            let characters = characters::load_all(&characters_root(app.handle()));
            for c in &characters {
                let ws = data_dir.join("workspaces").join(&c.id);
                if let Err(e) = characters::prepare_workspace(c, &ws) {
                    eprintln!("[workspace] {}: {e}", c.id);
                }
            }
            println!(
                "[living-room] data dir: {} | characters: {:?}",
                data_dir.display(),
                characters.iter().map(|c| &c.id).collect::<Vec<_>>()
            );
            app.manage(AppState {
                db: Mutex::new(db),
                characters,
                data_dir,
                settings: Mutex::new(settings),
                runs: Mutex::new(HashMap::new()),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap,
            check_agents,
            save_settings,
            list_conversations,
            get_messages,
            delete_conversation,
            rename_conversation,
            open_workspace,
            open_file,
            existing_files,
            read_image,
            import_file,
            save_upload,
            check_comfyui,
            cancel_run,
            send_message,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::agent::*;

    #[test]
    fn claude_command_carries_allowed_tools_and_env() {
        let ws = std::path::Path::new("/tmp/ws");
        let cmd = build_command(&RunSpec {
            provider: Provider::Claude,
            binary: "claude".into(),
            workspace: ws,
            persona_file: &ws.join("persona.md"),
            dsh_patch: &ws.join("dsh.patch.yml"),
            model: None,
            permission_mode: "acceptEdits",
            resume: None,
            allowed_tools: vec!["Bash(python3 a.py:*)".into(), "Bash(py a.py:*)".into()],
            env: vec![("COMFYUI_URL".into(), "http://h:1".into())],
        });
        let std = cmd.as_std();
        let args: Vec<_> = std.get_args().map(|a| a.to_string_lossy().into_owned()).collect();
        let i = args.iter().position(|a| a == "--allowedTools").expect("flag");
        assert_eq!(args[i + 1], "Bash(python3 a.py:*),Bash(py a.py:*)");
        let envs: Vec<_> = std.get_envs().map(|(k, v)| (k.to_string_lossy().into_owned(), v.map(|v| v.to_string_lossy().into_owned()))).collect();
        assert!(envs.contains(&("COMFYUI_URL".into(), Some("http://h:1".into()))));
        assert!(envs.contains(&("LIVING_ROOM_HARNESS".into(), Some("claude".into()))));
    }

    #[test]
    fn base64_matches_rfc4648() {
        for (i, o) in [("", ""), ("f", "Zg=="), ("fo", "Zm8="), ("foo", "Zm9v"), ("foob", "Zm9vYg=="), ("fooba", "Zm9vYmE="), ("foobar", "Zm9vYmFy")] {
            assert_eq!(super::base64(i.as_bytes()), o);
        }
    }

    #[test]
    fn parses_claude_stream() {
        let init = r#"{"type":"system","subtype":"init","session_id":"abc"}"#;
        assert!(matches!(&parse_line(Provider::Claude, init)[0], AgentEvent::Session{session_id} if session_id=="abc"));
        let delta = r#"{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"你好"}},"parent_tool_use_id":null}"#;
        assert!(matches!(&parse_line(Provider::Claude, delta)[0], AgentEvent::Delta{text} if text=="你好"));
        let tool = r#"{"type":"assistant","message":{"content":[{"type":"text","text":"ok"},{"type":"tool_use","name":"Bash","input":{"command":"ls"}}]},"parent_tool_use_id":null}"#;
        let evs = parse_line(Provider::Claude, tool);
        assert_eq!(evs.len(), 2);
        let res = r#"{"type":"result","subtype":"success","is_error":false,"total_cost_usd":0.01,"duration_ms":5}"#;
        assert!(matches!(&parse_line(Provider::Claude, res)[0], AgentEvent::Done{ok:true,..}));
    }

    #[test]
    fn parses_codex_stream() {
        let t = r#"{"type":"thread.started","thread_id":"t1"}"#;
        assert!(matches!(&parse_line(Provider::Codex, t)[0], AgentEvent::Session{session_id} if session_id=="t1"));
        let m = r#"{"type":"item.completed","item":{"id":"i","type":"agent_message","text":"hi"}}"#;
        assert!(matches!(&parse_line(Provider::Codex, m)[0], AgentEvent::Message{text} if text=="hi"));
        let c = r#"{"type":"item.started","item":{"id":"i","type":"command_execution","command":"ls","status":"in_progress"}}"#;
        assert!(matches!(&parse_line(Provider::Codex, c)[0], AgentEvent::Tool{..}));
        let d = r#"{"type":"turn.completed","usage":{}}"#;
        assert!(matches!(&parse_line(Provider::Codex, d)[0], AgentEvent::Done{ok:true,..}));
    }

    #[test]
    fn deepseek_command_uses_headless_profile_and_patch() {
        let ws = std::path::Path::new("/tmp/ws");
        let cmd = build_command(&RunSpec {
            provider: Provider::Deepseek,
            binary: "dsh".into(),
            workspace: ws,
            persona_file: &ws.join("persona.md"),
            dsh_patch: &ws.join("dsh.patch.yml"),
            model: Some("deepseek-v4-pro"),
            permission_mode: "acceptEdits",
            resume: Some("session-1"),
            allowed_tools: vec![],
            env: vec![],
        });
        let std = cmd.as_std();
        let args: Vec<_> = std.get_args().map(|a| a.to_string_lossy().into_owned()).collect();
        assert_eq!(
            args,
            ["--profile", "headless", "--patch", "/tmp/ws/dsh.patch.yml", "--json", "--permission-mode", "workspace-write", "--approval-policy", "never", "--session-id", "session-1", "-"]
        );
        let envs: Vec<_> = std.get_envs().map(|(k, v)| (k.to_string_lossy().into_owned(), v.map(|v| v.to_string_lossy().into_owned()))).collect();
        assert!(envs.contains(&("LIVING_ROOM_HARNESS".into(), Some("deepseek".into()))));
    }

    #[test]
    fn parses_dsh_stream() {
        let lines = [
            r#"{"type":"session","sessionId":"session-abc","cwd":"/w"}"#,
            r#"{"type":"status","phase":"turn_start","turn":1}"#,
            r#"{"type":"thinking","text":"hmm"}"#,
            r#"{"type":"text","text":"现在读取 a.txt："}"#,
            r#"{"type":"tool_call","callId":"c1","tool":"read","input":{"file_path":"a.txt"}}"#,
            r#"{"type":"tool_result","callId":"c1","status":"completed","result":"hello"}"#,
            r#"{"type":"tool_call","callId":"c2","tool":"bash","input":{"description":"Run","command":"python3 x.py"}}"#,
            r#"{"type":"tool_result","callId":"c2","status":"failed","error":{"name":"ToolError","code":"DENIED","reason":"approval required"}}"#,
            r#"{"type":"final","sessionId":"session-abc","reason":{"kind":"completed"},"text":"done"}"#,
        ];
        let evs: Vec<_> = lines.iter().flat_map(|l| parse_line(Provider::Deepseek, l)).collect();
        assert!(matches!(&evs[0], AgentEvent::Session{session_id} if session_id=="session-abc"));
        assert!(matches!(&evs[1], AgentEvent::Message{text} if text=="现在读取 a.txt："));
        assert!(matches!(&evs[2], AgentEvent::Tool{name, summary} if name=="Read" && summary=="a.txt"));
        assert!(matches!(&evs[3], AgentEvent::ToolResult{ok:true, output} if output=="hello"));
        assert!(matches!(&evs[4], AgentEvent::Tool{name, summary} if name=="Bash" && summary=="python3 x.py"));
        assert!(matches!(&evs[5], AgentEvent::ToolResult{ok:false, output} if output=="approval required"));
        assert!(matches!(&evs[6], AgentEvent::Done{ok:true, error:None, ..}));
        assert_eq!(evs.len(), 7);

        let failed = r#"{"type":"final","sessionId":"s","reason":{"kind":"error","code":"LLM_ERROR","message":"401"}}"#;
        assert!(matches!(&parse_line(Provider::Deepseek, failed)[0], AgentEvent::Done{ok:false, error:Some(e), ..} if e=="LLM_ERROR: 401"));
        let err = r#"{"type":"error","message":"unknown session"}"#;
        assert!(matches!(&parse_line(Provider::Deepseek, err)[0], AgentEvent::Done{ok:false, error:Some(e), ..} if e=="unknown session"));
    }

    /// Live run against the installed `dsh` (needs DEEPSEEK_API_KEY), through
    /// the same workspace/patch/command/parse path as `send_message`:
    /// `LR_CHAR=claire LR_PROMPT='…' [LR_RESUME=session-…] [LR_MODEL=…] [LR_WS=dir]
    ///  cargo test dsh_live -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn dsh_live() {
        use std::io::{BufRead, Write};
        let id = std::env::var("LR_CHAR").unwrap_or_else(|_| "iris".into());
        let prompt = std::env::var("LR_PROMPT").unwrap_or_else(|_| "用一句话介绍你自己。".into());
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../characters");
        let c = super::characters::load_all(&root).into_iter().find(|c| c.id == id).expect("character");
        let ws = std::env::var("LR_WS").map(std::path::PathBuf::from).unwrap_or_else(|_| std::env::temp_dir().join("lr-dsh-live").join(&id));
        super::characters::prepare_workspace(&c, &ws).unwrap();
        let model = std::env::var("LR_MODEL").ok().filter(|s| !s.is_empty());
        let patch = super::characters::write_dsh_patch(&c, &ws, model.as_deref()).unwrap();
        let resume = std::env::var("LR_RESUME").ok().filter(|s| !s.is_empty());
        let cmd = build_command(&RunSpec {
            provider: Provider::Deepseek,
            binary: resolve_binary(Provider::Deepseek, None).expect("dsh on PATH"),
            workspace: &ws,
            persona_file: &super::characters::persona_file(&ws),
            dsh_patch: &patch,
            model: model.as_deref(),
            permission_mode: &c.agent.permission_mode,
            resume: resume.as_deref(),
            allowed_tools: vec![],
            env: vec![("COMFYUI_URL".into(), std::env::var("COMFYUI_URL").unwrap_or_else(|_| "http://127.0.0.1:8188".into()))],
        });
        let mut std_cmd = cmd.into_std();
        let mut child = std_cmd
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .spawn()
            .expect("spawn dsh");
        child.stdin.take().unwrap().write_all(prompt.as_bytes()).unwrap();
        let mut done = None;
        for line in std::io::BufReader::new(child.stdout.take().unwrap()).lines() {
            for ev in parse_line(Provider::Deepseek, &line.unwrap()) {
                println!("EVENT {}", serde_json::to_string(&ev).unwrap());
                if let AgentEvent::Done { ok, .. } = ev {
                    done = Some(ok);
                }
            }
        }
        let status = child.wait().unwrap();
        println!("WORKSPACE {}", ws.display());
        assert_eq!(done, Some(true), "run should finish ok");
        assert!(status.success());
    }
}

