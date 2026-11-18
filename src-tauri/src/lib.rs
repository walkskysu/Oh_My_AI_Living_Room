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
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    #[serde(default)]
    pub claude_path: Option<String>,
    #[serde(default)]
    pub codex_path: Option<String>,
    /// Per-character overrides of the agent config.
    #[serde(default)]
    pub characters: HashMap<String, AgentConfig>,
}

struct RunInfo {
    run_id: String,
    conversation_id: String,
    mode: String,
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
    mode: String,
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
                mode: r.mode.clone(),
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
    /// "running" | "finished"
    status: String,
    mode: String,
    ok: bool,
}

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
    mode: String,
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
            .add_message(&conv.id, "user", &text, &json!({ "mode": mode }))
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
    let mut cmd = agent::build_command(&RunSpec {
        provider,
        binary,
        workspace: &ws,
        persona_file: &persona_file,
        model: cfg.model.as_deref(),
        permission_mode: &cfg.permission_mode,
        resume: resume.as_deref(),
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
            mode: mode.clone(),
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
            mode: mode.clone(),
            ok: true,
        },
    );

    // Feed the prompt through stdin.
    let prompt = agent::compose_prompt(&text, &mode);
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
        mode,
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
    mode: String,
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

    loop {
        tokio::select! {
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
            mode,
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
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
}
