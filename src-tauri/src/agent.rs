//! Agent harness adapters. Each character is backed by a CLI coding agent
//! (Claude Code or Codex) running headless in the character's workspace.
//! Output is parsed line-by-line (JSONL) into a small normalized event set.

use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Provider {
    Claude,
    Codex,
}

impl Provider {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "claude" => Some(Self::Claude),
            "codex" => Some(Self::Codex),
            _ => None,
        }
    }
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Claude => "claude",
            Self::Codex => "codex",
        }
    }
    pub fn binary(&self) -> &'static str {
        self.as_str()
    }
}

/// Normalized events emitted to the frontend (and partially persisted).
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum AgentEvent {
    /// The harness reported its session/thread id (used to resume later).
    Session { session_id: String },
    /// Streaming text chunk (not persisted).
    Delta { text: String },
    /// A complete assistant text block (persisted).
    Message { text: String },
    /// The agent invoked a tool (persisted).
    Tool { name: String, summary: String },
    /// Result of a tool call (persisted into the tool row's meta by the runner).
    ToolResult { ok: bool, output: String },
    /// The turn finished.
    Done {
        ok: bool,
        error: Option<String>,
        cost_usd: Option<f64>,
        duration_ms: Option<u64>,
    },
}

pub struct RunSpec<'a> {
    pub provider: Provider,
    pub binary: PathBuf,
    pub workspace: &'a Path,
    /// File holding the persona (system prompt addition). A file instead of an
    /// argument keeps multi-line text off the command line (Windows .cmd shims reject it).
    pub persona_file: &'a Path,
    pub model: Option<&'a str>,
    pub permission_mode: &'a str,
    pub resume: Option<&'a str>,
}

/// Build the command line. The prompt itself is written to stdin.
pub fn build_command(spec: &RunSpec) -> tokio::process::Command {
    let mut cmd = tokio::process::Command::new(&spec.binary);
    cmd.current_dir(spec.workspace);
    match spec.provider {
        Provider::Claude => {
            cmd.args([
                "-p",
                "--output-format",
                "stream-json",
                "--verbose",
                "--include-partial-messages",
                "--permission-mode",
                spec.permission_mode,
            ]);
            cmd.arg("--append-system-prompt-file").arg(spec.persona_file);
            if let Some(m) = spec.model.filter(|m| !m.is_empty()) {
                cmd.args(["--model", m]);
            }
            if let Some(r) = spec.resume {
                cmd.args(["--resume", r]);
            }
        }
        Provider::Codex => {
            // Persona is provided through AGENTS.md in the workspace.
            cmd.args(["exec", "--json", "--skip-git-repo-check"]);
            let sandbox = if spec.permission_mode == "bypassPermissions" {
                "danger-full-access"
            } else {
                "workspace-write"
            };
            cmd.args(["--sandbox", sandbox]);
            if let Some(m) = spec.model.filter(|m| !m.is_empty()) {
                cmd.args(["--model", m]);
            }
            if let Some(r) = spec.resume {
                cmd.args(["resume", r]);
            }
            cmd.arg("-"); // read prompt from stdin
        }
    }
    cmd.env("PATH", augmented_path());
    #[cfg(windows)]
    {
        // Don't flash a console window for every agent run.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let t: String = s.chars().take(max).collect();
        format!("{t}…")
    }
}

/// Short human-readable description of a tool call.
fn summarize_tool_input(name: &str, input: &Value) -> String {
    let pick = |k: &str| input.get(k).and_then(Value::as_str).map(str::to_string);
    let s = match name {
        "Bash" => pick("command"),
        "Read" | "Write" | "Edit" | "NotebookEdit" => pick("file_path"),
        "Glob" | "Grep" => pick("pattern"),
        "WebFetch" => pick("url"),
        "WebSearch" => pick("query"),
        "Skill" => pick("skill"),
        "Task" | "Agent" => pick("description"),
        "TodoWrite" => Some("更新待办清单".into()),
        _ => None,
    };
    truncate(&s.unwrap_or_else(|| input.to_string()), 200)
}

fn tool_result_text(content: &Value) -> String {
    match content {
        Value::String(s) => s.clone(),
        Value::Array(parts) => parts
            .iter()
            .filter_map(|p| p.get("text").and_then(Value::as_str))
            .collect::<Vec<_>>()
            .join("\n"),
        other => other.to_string(),
    }
}

/// Parse one JSONL line from the harness into zero or more events.
pub fn parse_line(provider: Provider, line: &str) -> Vec<AgentEvent> {
    let Ok(v) = serde_json::from_str::<Value>(line) else {
        return vec![];
    };
    match provider {
        Provider::Claude => parse_claude(&v),
        Provider::Codex => parse_codex(&v),
    }
}

fn parse_claude(v: &Value) -> Vec<AgentEvent> {
    let mut out = vec![];
    let ty = v.get("type").and_then(Value::as_str).unwrap_or("");
    match ty {
        "system" => {
            if v.get("subtype").and_then(Value::as_str) == Some("init") {
                if let Some(sid) = v.get("session_id").and_then(Value::as_str) {
                    out.push(AgentEvent::Session {
                        session_id: sid.into(),
                    });
                }
            }
        }
        "stream_event" => {
            // Only stream top-level text (sub-agents have parent_tool_use_id set).
            if v.get("parent_tool_use_id").map_or(false, |p| !p.is_null()) {
                return out;
            }
            let ev = &v["event"];
            if ev["type"] == "content_block_delta" && ev["delta"]["type"] == "text_delta" {
                if let Some(t) = ev["delta"]["text"].as_str() {
                    out.push(AgentEvent::Delta { text: t.into() });
                }
            }
        }
        "assistant" => {
            if v.get("parent_tool_use_id").map_or(false, |p| !p.is_null()) {
                return out;
            }
            if let Some(blocks) = v["message"]["content"].as_array() {
                for b in blocks {
                    match b["type"].as_str() {
                        Some("text") => {
                            let t = b["text"].as_str().unwrap_or("").trim();
                            if !t.is_empty() {
                                out.push(AgentEvent::Message { text: t.into() });
                            }
                        }
                        Some("tool_use") => {
                            let name = b["name"].as_str().unwrap_or("tool").to_string();
                            let summary = summarize_tool_input(&name, &b["input"]);
                            out.push(AgentEvent::Tool { name, summary });
                        }
                        _ => {}
                    }
                }
            }
        }
        "user" => {
            if v.get("parent_tool_use_id").map_or(false, |p| !p.is_null()) {
                return out;
            }
            if let Some(blocks) = v["message"]["content"].as_array() {
                for b in blocks {
                    if b["type"] == "tool_result" {
                        out.push(AgentEvent::ToolResult {
                            ok: !b["is_error"].as_bool().unwrap_or(false),
                            output: truncate(&tool_result_text(&b["content"]), 1500),
                        });
                    }
                }
            }
        }
        "result" => {
            let is_err = v["is_error"].as_bool().unwrap_or(false);
            let error = if is_err {
                Some(
                    v["result"]
                        .as_str()
                        .map(str::to_string)
                        .unwrap_or_else(|| v["subtype"].as_str().unwrap_or("error").to_string()),
                )
            } else {
                None
            };
            out.push(AgentEvent::Done {
                ok: !is_err,
                error,
                cost_usd: v["total_cost_usd"].as_f64(),
                duration_ms: v["duration_ms"].as_u64(),
            });
        }
        _ => {}
    }
    out
}

fn parse_codex(v: &Value) -> Vec<AgentEvent> {
    let mut out = vec![];
    let ty = v.get("type").and_then(Value::as_str).unwrap_or("");
    match ty {
        "thread.started" => {
            if let Some(id) = v["thread_id"].as_str() {
                out.push(AgentEvent::Session {
                    session_id: id.into(),
                });
            }
        }
        "item.started" => {
            let item = &v["item"];
            if item["type"] == "command_execution" {
                out.push(AgentEvent::Tool {
                    name: "Shell".into(),
                    summary: truncate(item["command"].as_str().unwrap_or(""), 200),
                });
            }
        }
        "item.completed" => {
            let item = &v["item"];
            match item["type"].as_str() {
                Some("agent_message") => {
                    let t = item["text"].as_str().unwrap_or("").trim();
                    if !t.is_empty() {
                        out.push(AgentEvent::Message { text: t.into() });
                    }
                }
                Some("command_execution") => {
                    out.push(AgentEvent::ToolResult {
                        ok: item["exit_code"].as_i64().unwrap_or(0) == 0,
                        output: truncate(item["aggregated_output"].as_str().unwrap_or(""), 1500),
                    });
                }
                Some("file_change") => {
                    let files: Vec<String> = item["changes"]
                        .as_array()
                        .map(|a| {
                            a.iter()
                                .filter_map(|c| {
                                    Some(format!(
                                        "{} {}",
                                        c["kind"].as_str().unwrap_or("edit"),
                                        c["path"].as_str()?
                                    ))
                                })
                                .collect()
                        })
                        .unwrap_or_default();
                    out.push(AgentEvent::Tool {
                        name: "Edit".into(),
                        summary: truncate(&files.join(", "), 200),
                    });
                }
                Some("mcp_tool_call") => out.push(AgentEvent::Tool {
                    name: format!(
                        "{}:{}",
                        item["server"].as_str().unwrap_or("mcp"),
                        item["tool"].as_str().unwrap_or("tool")
                    ),
                    summary: String::new(),
                }),
                Some("web_search") => out.push(AgentEvent::Tool {
                    name: "WebSearch".into(),
                    summary: truncate(item["query"].as_str().unwrap_or(""), 200),
                }),
                _ => {}
            }
        }
        "turn.completed" => out.push(AgentEvent::Done {
            ok: true,
            error: None,
            cost_usd: None,
            duration_ms: None,
        }),
        "turn.failed" => out.push(AgentEvent::Done {
            ok: false,
            error: Some(
                v["error"]["message"]
                    .as_str()
                    .unwrap_or("turn failed")
                    .to_string(),
            ),
            cost_usd: None,
            duration_ms: None,
        }),
        "error" => out.push(AgentEvent::Done {
            ok: false,
            error: Some(v["message"].as_str().unwrap_or("error").to_string()),
            cost_usd: None,
            duration_ms: None,
        }),
        _ => {}
    }
    out
}

/// PATH as seen by a GUI-launched app is often minimal; add the usual
/// per-user install locations so `claude` / `codex` / `node` resolve.
pub fn augmented_path() -> std::ffi::OsString {
    let mut parts: Vec<PathBuf> = std::env::var_os("PATH")
        .map(|p| std::env::split_paths(&p).collect())
        .unwrap_or_default();
    let mut extra: Vec<PathBuf> = vec![];
    let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).map(PathBuf::from);
    if let Some(home) = &home {
        for d in [".local/bin", ".npm-global/bin", ".bun/bin", ".cargo/bin", ".volta/bin", ".claude/local"] {
            extra.push(home.join(d));
        }
    }
    if cfg!(windows) {
        if let Some(appdata) = std::env::var_os("APPDATA") {
            extra.push(PathBuf::from(appdata).join("npm"));
        }
        if let Some(local) = std::env::var_os("LOCALAPPDATA") {
            extra.push(PathBuf::from(&local).join("Programs").join("claude"));
            extra.push(PathBuf::from(local).join("pnpm"));
        }
        if let Some(pf) = std::env::var_os("ProgramFiles") {
            extra.push(PathBuf::from(&pf).join("nodejs"));
            extra.push(PathBuf::from(pf).join("Git").join("cmd"));
        }
    } else {
        for d in ["/usr/local/bin", "/usr/bin", "/bin"] {
            extra.push(PathBuf::from(d));
        }
    }
    for e in extra {
        if !parts.contains(&e) {
            parts.push(e);
        }
    }
    std::env::join_paths(parts).unwrap_or_default()
}

/// Executable names to try for a command (Windows needs an extension; npm installs `.cmd` shims).
fn candidates(name: &str) -> Vec<String> {
    if cfg!(windows) {
        ["exe", "cmd", "bat"].iter().map(|e| format!("{name}.{e}")).collect()
    } else {
        vec![name.to_string()]
    }
}

/// Locate a harness binary: explicit override, else search the augmented PATH.
pub fn resolve_binary(provider: Provider, override_path: Option<&str>) -> Option<PathBuf> {
    if let Some(p) = override_path.filter(|p| !p.trim().is_empty()) {
        let p = PathBuf::from(p.trim().trim_matches('"'));
        return p.is_file().then_some(p);
    }
    for dir in std::env::split_paths(&augmented_path()) {
        for name in candidates(provider.binary()) {
            let cand = dir.join(&name);
            if cand.is_file() {
                return Some(cand);
            }
        }
    }
    None
}
