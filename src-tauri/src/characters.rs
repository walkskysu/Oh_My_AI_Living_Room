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
    /// "claude" | "codex"
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
    /// Extra persona text per harness ("claude" / "codex"), e.g. which image
    /// tool to use. Claude's goes into persona.md, Codex's into AGENTS.md.
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
}
