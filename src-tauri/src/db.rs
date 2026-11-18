//! SQLite persistence: every conversation and every message is stored.

use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;
use std::path::Path;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Conversation {
    pub id: String,
    pub character_id: String,
    pub title: String,
    pub provider: String,
    pub agent_session_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub message_count: i64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Message {
    pub id: i64,
    pub conversation_id: String,
    /// user | assistant | tool | error | system
    pub role: String,
    pub content: String,
    pub meta: serde_json::Value,
    pub created_at: String,
}

pub struct Db {
    conn: Connection,
}

fn now() -> String {
    chrono::Utc::now().to_rfc3339()
}

impl Db {
    pub fn open(path: &Path) -> rusqlite::Result<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch(
            r#"
            PRAGMA journal_mode = WAL;
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                title TEXT NOT NULL,
                provider TEXT NOT NULL,
                agent_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conv_char ON conversations(character_id, updated_at);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
            "#,
        )?;
        Ok(Self { conn })
    }

    pub fn create_conversation(
        &self,
        character_id: &str,
        title: &str,
        provider: &str,
    ) -> rusqlite::Result<Conversation> {
        let id = uuid::Uuid::new_v4().to_string();
        let ts = now();
        self.conn.execute(
            "INSERT INTO conversations (id, character_id, title, provider, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?5)",
            params![id, character_id, title, provider, ts],
        )?;
        Ok(self.get_conversation(&id)?.expect("just inserted"))
    }

    pub fn get_conversation(&self, id: &str) -> rusqlite::Result<Option<Conversation>> {
        self.conn
            .query_row(
                "SELECT c.id, c.character_id, c.title, c.provider, c.agent_session_id, c.created_at, c.updated_at,
                        (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id)
                 FROM conversations c WHERE c.id = ?1",
                params![id],
                row_to_conversation,
            )
            .optional()
    }

    pub fn list_conversations(&self, character_id: &str) -> rusqlite::Result<Vec<Conversation>> {
        let mut stmt = self.conn.prepare(
            "SELECT c.id, c.character_id, c.title, c.provider, c.agent_session_id, c.created_at, c.updated_at,
                    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id)
             FROM conversations c WHERE c.character_id = ?1 ORDER BY c.updated_at DESC",
        )?;
        let rows = stmt.query_map(params![character_id], row_to_conversation)?;
        rows.collect()
    }

    pub fn delete_conversation(&self, id: &str) -> rusqlite::Result<()> {
        self.conn
            .execute("DELETE FROM messages WHERE conversation_id = ?1", params![id])?;
        self.conn
            .execute("DELETE FROM conversations WHERE id = ?1", params![id])?;
        Ok(())
    }

    pub fn rename_conversation(&self, id: &str, title: &str) -> rusqlite::Result<()> {
        self.conn.execute(
            "UPDATE conversations SET title = ?2 WHERE id = ?1",
            params![id, title],
        )?;
        Ok(())
    }

    pub fn set_session(&self, id: &str, provider: &str, session: &str) -> rusqlite::Result<()> {
        self.conn.execute(
            "UPDATE conversations SET agent_session_id = ?2, provider = ?3 WHERE id = ?1",
            params![id, session, provider],
        )?;
        Ok(())
    }

    pub fn add_message(
        &self,
        conversation_id: &str,
        role: &str,
        content: &str,
        meta: &serde_json::Value,
    ) -> rusqlite::Result<Message> {
        let ts = now();
        self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content, meta, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![conversation_id, role, content, meta.to_string(), ts],
        )?;
        let id = self.conn.last_insert_rowid();
        self.conn.execute(
            "UPDATE conversations SET updated_at = ?2 WHERE id = ?1",
            params![conversation_id, ts],
        )?;
        Ok(Message {
            id,
            conversation_id: conversation_id.to_string(),
            role: role.to_string(),
            content: content.to_string(),
            meta: meta.clone(),
            created_at: ts,
        })
    }

    pub fn update_meta(&self, id: i64, meta: &serde_json::Value) -> rusqlite::Result<()> {
        self.conn.execute(
            "UPDATE messages SET meta = ?2 WHERE id = ?1",
            params![id, meta.to_string()],
        )?;
        Ok(())
    }

    pub fn messages(&self, conversation_id: &str) -> rusqlite::Result<Vec<Message>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, conversation_id, role, content, meta, created_at FROM messages
             WHERE conversation_id = ?1 ORDER BY id",
        )?;
        let rows = stmt.query_map(params![conversation_id], |r| {
            let meta: String = r.get(4)?;
            Ok(Message {
                id: r.get(0)?,
                conversation_id: r.get(1)?,
                role: r.get(2)?,
                content: r.get(3)?,
                meta: serde_json::from_str(&meta).unwrap_or(serde_json::Value::Null),
                created_at: r.get(5)?,
            })
        })?;
        rows.collect()
    }
}

fn row_to_conversation(r: &rusqlite::Row) -> rusqlite::Result<Conversation> {
    Ok(Conversation {
        id: r.get(0)?,
        character_id: r.get(1)?,
        title: r.get(2)?,
        provider: r.get(3)?,
        agent_session_id: r.get(4)?,
        created_at: r.get(5)?,
        updated_at: r.get(6)?,
        message_count: r.get(7)?,
    })
}
