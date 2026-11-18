//! Character definitions (persona, specialties, skills, scene placement, sprites).
//!
//! Each character lives in `characters/<id>/character.json`, optionally with
//! Claude Code skills under `characters/<id>/skills/<skill>/SKILL.md`.

use serde::{Deserialize, Serialize};
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
    #[serde(default)]
    pub bored_after_sec: Option<u64>,
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
    let mut agents_md = format!("# {}\n\n{}\n", c.name, c.persona);
    if !c.skills.is_empty() {
        agents_md.push_str("\n## Skills\n\nDetailed instructions for each skill are in `.claude/skills/<name>/SKILL.md`; read the file before using the skill.\n\n");
        for s in &c.skills {
            agents_md.push_str(&format!("- **{}**: {}\n", s.name, s.description));
        }
    }
    std::fs::write(ws.join("AGENTS.md"), agents_md)?;
    std::fs::create_dir_all(ws.join(".living-room"))?;
    std::fs::write(persona_file(ws), &c.persona)?;
    Ok(())
}

/// Where the persona text for `--append-system-prompt-file` is written.
pub fn persona_file(ws: &Path) -> PathBuf {
    ws.join(".living-room").join("persona.md")
}
