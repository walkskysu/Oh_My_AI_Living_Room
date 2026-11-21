//! Character definitions (persona, specialties, skills, scene placement, sprites).
//!
//! Each character lives in `characters/<id>/character.json`, optionally with
//! Claude Code skills under `characters/<id>/skills/<skill>/SKILL.md`.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentConfig {
    /// "claude" | "codex" | "deepseek"
    #[serde(default = "default_provider")]
    pub provider: String,
    #[serde(default)]
    pub model: Option<String>,
    /// Claude Code permission mode (default/acceptEdits/bypassPermissions/plan)
    #[serde(default = "default_permission")]
    pub permission_mode: String,
}

fn default_provider() -> String {
    "claude".into()
}
fn default_permission() -> String {
    "acceptEdits".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Character {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub name_zh: Option<String>,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub bio: String,
    #[serde(default)]
    pub specialties: Vec<String>,
    #[serde(default)]
    pub greeting: String,
    /// System prompt describing the persona; appended to the agent's system prompt.
    pub persona: String,
    pub agent: AgentConfig,
    /// Frontend-only data (scene placement, sprites, theme colour…), passed through untouched.
    #[serde(default)]
    pub scene: serde_json::Value,
    #[serde(default)]
    pub sprites: serde_json::Value,
    #[serde(default)]
    pub theme: serde_json::Value,
    /// Idle chatter shown in speech bubbles per activity.
    #[serde(default)]
    pub lines: serde_json::Value,
    /// Per-character status pill wording, e.g. { "reading": "画画中" }.
    #[serde(default)]
    pub activity_labels: serde_json::Value,
    #[serde(default)]
    pub bored_after_sec: Option<u64>,
    /// Extra persona text per harness ("claude" / "codex" / "deepseek"), e.g.
    /// which image tool to use. Claude's goes into persona.md, Codex's into
    /// AGENTS.md, DeepSeek's into the `dsh` patch overlay.
    #[serde(default)]
    pub harness_notes: HashMap<String, String>,
    /// Claude Code permission rules the character may always use, e.g. the
    /// scripts her skills run (`Bash(python3 .claude/skills/x/run.py:*)`).
    /// Headless runs can't ask for approval, so these are passed as
    /// `--allowedTools` (a project `.claude/settings.json` would be ignored
    /// until the workspace is trusted interactively).
    #[serde(default)]
    pub allowed_tools: Vec<String>,
    /// Names of skills bundled with the character (filled in at load time).
    #[serde(default)]
    pub skills: Vec<SkillInfo>,
    #[serde(skip)]
    pub dir: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SkillInfo {
    pub name: String,
    pub description: String,
}

pub fn load_all(root: &Path) -> Vec<Character> {
    let mut out = Vec::new();
    let Ok(entries) = std::fs::read_dir(root) else {
        return out;
    };
    for e in entries.flatten() {
        let dir = e.path();
        let file = dir.join("character.json");
        let Ok(text) = std::fs::read_to_string(&file) else {
            continue;
        };
        match serde_json::from_str::<Character>(&text) {
            Ok(mut c) => {
                c.dir = dir.clone();
                c.skills = scan_skills(&dir.join("skills"));
                out.push(c);
            }
            Err(err) => eprintln!("[characters] failed to parse {}: {err}", file.display()),
        }
    }
    out.sort_by(|a, b| a.id.cmp(&b.id));
    out
}

fn scan_skills(dir: &Path) -> Vec<SkillInfo> {
    let mut skills = Vec::new();
    let Ok(entries) = std::fs::read_dir(dir) else {
        return skills;
    };
    for e in entries.flatten() {
        let md = e.path().join("SKILL.md");
        let Ok(text) = std::fs::read_to_string(&md) else {
            continue;
        };
        let (name, description) = parse_frontmatter(&text);
        skills.push(SkillInfo {
            name: name.unwrap_or_else(|| e.file_name().to_string_lossy().into_owned()),
            description: description.unwrap_or_default(),
        });
    }
    skills.sort_by(|a, b| a.name.cmp(&b.name));
    skills
}

fn parse_frontmatter(text: &str) -> (Option<String>, Option<String>) {
    let mut name = None;
    let mut desc = None;
    let mut lines = text.lines();
    if lines.next().map(str::trim) != Some("---") {
        return (None, None);
    }
    for line in lines {
        if line.trim() == "---" {
            break;
        }
        if let Some(v) = line.strip_prefix("name:") {
            name = Some(v.trim().trim_matches('"').to_string());
        } else if let Some(v) = line.strip_prefix("description:") {
            desc = Some(v.trim().trim_matches('"').to_string());
        }
    }
    (name, desc)
}

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for e in std::fs::read_dir(src)? {
        let e = e?;
        let to = dst.join(e.file_name());
        if e.file_type()?.is_dir() {
            copy_dir(&e.path(), &to)?;
        } else {
            std::fs::copy(e.path(), to)?;
        }
    }
    Ok(())
}

/// Prepare the character's private working directory:
/// * Claude Code project skills in `.claude/skills/`
/// * `AGENTS.md` with the persona + skills (read by Codex)
/// * `outputs/` for task deliverables
pub fn prepare_workspace(c: &Character, ws: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(ws.join("outputs"))?;
    let skills_src = c.dir.join("skills");
    if skills_src.is_dir() {
        copy_dir(&skills_src, &ws.join(".claude").join("skills"))?;
    }
    let mut agents_md = format!("# {}\n\n{}\n", c.name, with_notes(c, "codex"));
    if !c.skills.is_empty() {
        agents_md.push_str("\n## Skills\n\nDetailed instructions for each skill are in `.claude/skills/<name>/SKILL.md`; read the file before using the skill.\n\n");
        for s in &c.skills {
            agents_md.push_str(&format!("- **{}**: {}\n", s.name, s.description));
        }
    }
    std::fs::write(ws.join("AGENTS.md"), agents_md)?;
    std::fs::create_dir_all(ws.join(".living-room"))?;
    std::fs::write(persona_file(ws), with_notes(c, "claude"))?;
    Ok(())
}

/// The persona plus the harness-specific notes for `provider`, if any.
fn with_notes(c: &Character, provider: &str) -> String {
    match c.harness_notes.get(provider).map(|n| n.trim()).filter(|n| !n.is_empty()) {
        Some(n) => format!("{}\n\n{}", c.persona.trim_end(), n),
        None => c.persona.clone(),
    }
}

/// `allowed_tools`, plus a variant with the absolute workspace path for every rule
/// that names a workspace-relative `.claude/` path (agents sometimes call scripts
/// by their full path).
pub fn allowed_tools(c: &Character, ws: &Path) -> Vec<String> {
    let mut out = Vec::new();
    for rule in &c.allowed_tools {
        out.push(rule.clone());
        if rule.contains(" .claude/") {
            let abs = format!("{}/.claude/", ws.to_string_lossy().replace('\\', "/"));
            out.push(rule.replacen(" .claude/", &format!(" {abs}"), 1));
        }
    }
    out
}

/// Tells the DeepSeek agent how the Claude Code tool names used in skills map
/// onto its own tools.
const DSH_TOOL_NOTE: &str = "## 工具名称对照（你现在运行在 DeepSeek Harness 上）\n技能说明里提到的 Claude Code 工具对应你自己的工具：Read → read，Write → write，Edit → edit，Bash → bash，WebSearch → web_search，WebFetch → web_fetch，Skill → skill。技能目录在 `.claude/skills/<name>/`，脚本用相对路径运行（例如 `python3 .claude/skills/<name>/xxx.py`）。运行耗时较长的脚本（画图、生成 PDF 等）时，把 bash 的 timeoutMs 设到 600000；如果命令被转为后台任务，用 job_output（wait: true）取结果。";

/// Write the `dsh --patch` overlay for this run and return its path:
/// * the persona (plus DeepSeek notes) as the system-prompt persona prefix
/// * `.claude/skills` as an extra skill root (so skills keep their paths)
/// * `AGENTS.md` loading off (it carries the Codex-specific notes)
/// * the model, when one is configured
///
/// The file is JSON, which is valid YAML, so no escaping rules beyond JSON apply.
pub fn write_dsh_patch(c: &Character, ws: &Path, model: Option<&str>) -> std::io::Result<PathBuf> {
    // `{{name}}` is template syntax in dsh prompts; an unknown name fails the run.
    let persona = format!("{}\n\n{}", with_notes(c, "deepseek").trim_end(), DSH_TOOL_NOTE).replace("{{", "{ {");
    let skills = ws.join(".claude").join("skills");
    let mut patch = vec![
        serde_json::json!({ "id": "system-prompt", "config": { "personaPrefix": persona } }),
        serde_json::json!({ "id": "skill-filesystem", "config": { "customSkillDirs": [skills.to_string_lossy()] } }),
        serde_json::json!({ "id": "agent-instructions", "disabled": true }),
    ];
    if let Some(m) = model.map(str::trim).filter(|m| !m.is_empty()) {
        patch.push(serde_json::json!({
            "id": "agent-default-model",
            "config": { "provider": "deepseek-official", "model": m }
        }));
    }
    let path = ws.join(".living-room").join("dsh.patch.yml");
    std::fs::create_dir_all(path.parent().unwrap())?;
    std::fs::write(&path, serde_json::to_string_pretty(&patch).map_err(std::io::Error::other)?)?;
    Ok(path)
}

/// Where the persona text for `--append-system-prompt-file` is written.
pub fn persona_file(ws: &Path) -> PathBuf {
    ws.join(".living-room").join("persona.md")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_characters_parse_with_skills() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../characters");
        let entries = std::fs::read_dir(&root).unwrap().flatten().filter(|e| e.path().join("character.json").is_file()).count();
        let all = load_all(&root);
        assert_eq!(all.len(), entries, "every characters/<id>/character.json must parse");
        let claire = all.iter().find(|c| c.id == "claire").expect("claire");
        let names: Vec<_> = claire.skills.iter().map(|s| s.name.as_str()).collect();
        assert_eq!(names, ["financial-analysis", "stock-analysis"]);
        assert!(claire.allowed_tools.iter().any(|t| t.contains("stock-analysis/stock.py")));
    }

    #[test]
    fn dsh_patch_carries_persona_skills_and_model() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../characters");
        let poppy = load_all(&root).into_iter().find(|c| c.id == "poppy").expect("poppy");
        let ws = std::env::temp_dir().join(format!("lr-dsh-{}", std::process::id()));
        let path = write_dsh_patch(&poppy, &ws, Some("deepseek-v4-pro")).unwrap();
        let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        let rows = v.as_array().unwrap();
        let persona = rows[0]["config"]["personaPrefix"].as_str().unwrap();
        assert!(persona.contains("Poppy") && persona.contains("DeepSeek"));
        assert!(!persona.contains("{{"));
        assert!(rows[1]["config"]["customSkillDirs"][0].as_str().unwrap().ends_with("skills"));
        assert_eq!(rows[2]["disabled"], true);
        assert_eq!(rows[3]["config"]["model"], "deepseek-v4-pro");
        let _ = std::fs::remove_dir_all(&ws);
    }
}
