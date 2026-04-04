# api/dependencies.py

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings as ChromaSettings
from functools import lru_cache
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sqlite3
import json
import httpx

from .config import settings


# ════════════════════════════════════════════════
# EMBEDDING MODEL & VECTOR DB
# ════════════════════════════════════════════════

_embedding_model = None
_chroma_client = None
_collection = None


@lru_cache()
def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        print(f"🤖 Loading: {settings.EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        print("✅ Embedding model ready")
    return _embedding_model


@lru_cache()
def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DB_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        print("✅ ChromaDB connected")
    return _chroma_client


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        try:
            _collection = client.get_collection(
                settings.VECTOR_COLLECTION_NAME
            )
            print(f"✅ KB loaded: {_collection.count()} docs")
        except Exception as e:
            print(f"❌ Collection error: {e}")
            raise Exception(
                "Vector DB missing! Run: python -m scripts.build_vector_db"
            )
    return _collection


def reset_collection():
    global _collection
    _collection = None


# ════════════════════════════════════════════════
# GROQ CLIENT (Free LLM - No data training)
# ════════════════════════════════════════════════

class GroqClient:
    """
    Groq API Client.
    FREE tier: ~14,400 requests/day on Llama 3.3 70B
    Privacy: Groq does NOT use your data for training
    Speed: ~500 tokens/second (very fast!)
    Docs: console.groq.com/docs
    """

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self._available = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "")

    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> Optional[str]:
        """
        Send chat request to Groq.
        Uses OpenAI-compatible API format.
        """
        if not self.is_configured():
            return None

        temperature = temperature or settings.TEMPERATURE
        max_tokens = max_tokens or settings.MAX_TOKENS

        # Build full messages array
        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]

        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "stop": None,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data["choices"][0]["message"]["content"]
                        .strip()
                    )
                    usage = data.get("usage", {})
                    print(f"   Groq: {usage.get('total_tokens', '?')} tokens")
                    return content

                elif response.status_code == 429:
                    print("⚠️  Groq rate limit, using fallback")
                    return None

                else:
                    print(f"❌ Groq error: {response.status_code}")
                    print(f"   {response.text[:200]}")
                    return None

        except httpx.TimeoutException:
            print("⏰ Groq timeout")
            return None
        except Exception as e:
            print(f"❌ Groq error: {e}")
            return None


# Singleton
_groq_client: Optional[GroqClient] = None


def get_groq_client() -> GroqClient:
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient()
        if _groq_client.is_configured():
            print(f"✅ Groq ready | Model: {settings.GROQ_MODEL}")
        else:
            print("⚠️  Groq not configured (no GROQ_API_KEY)")
            print("   Get free key: console.groq.com")
    return _groq_client


# ════════════════════════════════════════════════
# CONVERSATION MEMORY (SQLite - Local & Persistent)
# ════════════════════════════════════════════════

class ConversationStore:
    """
    SQLite-based conversation storage.
    - Persists across server restarts
    - All data stays local (no cloud)
    - tenant_id support for future portal mode
    """

    def __init__(self, db_path: str):
        # ✅ Bug 1 Fix: __init__ add kiya
        # db_path set karna zaroori tha
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables and migrate if needed"""
        with sqlite3.connect(self.db_path) as conn:
            
            # ── Step 1: Table create karo (fresh install) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          TEXT PRIMARY KEY,
                    messages    TEXT NOT NULL DEFAULT '[]',
                    context     TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL,
                    last_active TEXT NOT NULL,
                    mode        TEXT DEFAULT 'public',
                    tenant_id   TEXT DEFAULT NULL,
                    user_role   TEXT DEFAULT 'guest',
                    user_id     TEXT DEFAULT NULL
                )
            """)

            # ── Step 2: Migration - purani table mein columns add karo ──
            # SQLite mein ALTER TABLE sirf ADD COLUMN support karta hai
            # Ye safe hai - agar column exist karta hai to error nahi aayega
            
            existing_columns = [
                row[1] for row in 
                conn.execute("PRAGMA table_info(conversations)").fetchall()
            ]

            migrations = [
                ("mode",        "ALTER TABLE conversations ADD COLUMN mode TEXT DEFAULT 'public'"),
                ("tenant_id",   "ALTER TABLE conversations ADD COLUMN tenant_id TEXT DEFAULT NULL"),
                ("user_role",   "ALTER TABLE conversations ADD COLUMN user_role TEXT DEFAULT 'guest'"),
                ("user_id",     "ALTER TABLE conversations ADD COLUMN user_id TEXT DEFAULT NULL"),
            ]

            for col_name, sql in migrations:
                if col_name not in existing_columns:
                    conn.execute(sql)
                    print(f"🔧 Migration: added column '{col_name}'")

            # ── Step 3: Indexes ──
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_active
                ON conversations(last_active)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant
                ON conversations(tenant_id)
            """)

            conn.commit()
        print("✅ ConversationDB ready")

    def get_or_create(
        self,
        conv_id: str,
        mode: str = "public",
        tenant_id: Optional[str] = None,
        user_role: str = "guest",
        user_id: Optional[str] = None,
    ) -> Dict:
        """Get existing or create new conversation"""

        # ✅ Bug 4 Fix: _cleanup_old() method ab exist karta hai
        self._cleanup_old()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conv_id,)
            ).fetchone()

            now = datetime.now().isoformat()

            if row:
                conn.execute(
                    "UPDATE conversations SET last_active = ? WHERE id = ?",
                    (now, conv_id)
                )
                conn.commit()
                return {
                    "id": conv_id,
                    "messages": json.loads(row["messages"]),
                    "context": json.loads(row["context"]),
                    "mode": row["mode"],
                    "tenant_id": row["tenant_id"],
                    "user_role": row["user_role"],
                }
            else:
                conn.execute(
                    """INSERT INTO conversations
                       (id, messages, context, created_at, last_active,
                        mode, tenant_id, user_role, user_id)
                       VALUES (?, '[]', '{}', ?, ?, ?, ?, ?, ?)""",
                    (conv_id, now, now, mode, tenant_id, user_role, user_id)
                )
                conn.commit()
                return {
                    "id": conv_id,
                    "messages": [],
                    "context": {},
                    "mode": mode,
                    "tenant_id": tenant_id,
                    "user_role": user_role,
                }

    def add_messages(
        self,
        conv_id: str,
        user_msg: str,
        ai_msg: str,
        context_update: Optional[Dict] = None,
    ):
        """
        ✅ Bug 2 Fix: add_messages() method add kiya
        chat.py mein store.add_messages() call hota hai
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT messages, context FROM conversations WHERE id = ?",
                (conv_id,)
            ).fetchone()

            if not row:
                print(f"⚠️  Conversation {conv_id[:8]} not found")
                return

            messages = json.loads(row[0])
            context = json.loads(row[1])

            # New messages append karo
            messages.extend([
                {
                    "role": "user",
                    "content": user_msg,
                    "ts": datetime.now().isoformat()
                },
                {
                    "role": "assistant",
                    "content": ai_msg,
                    "ts": datetime.now().isoformat()
                },
            ])

            # Memory management: last N pairs hi rakhna hai
            max_msgs = settings.MAX_HISTORY_PAIRS * 2
            if len(messages) > max_msgs:
                messages = messages[-max_msgs:]

            # Context merge karo
            if context_update:
                context.update(context_update)

            conn.execute(
                """UPDATE conversations
                   SET messages = ?, context = ?, last_active = ?
                   WHERE id = ?""",
                (
                    json.dumps(messages),
                    json.dumps(context),
                    datetime.now().isoformat(),
                    conv_id,
                )
            )
            conn.commit()

    def get_llm_messages(self, conv_id: str) -> List[Dict]:
        """
        ✅ Bug 3 Fix: get_llm_messages() method add kiya
        chat.py mein store.get_llm_messages() call hota hai
        LLM ke liye formatted messages (timestamps remove)
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT messages FROM conversations WHERE id = ?",
                (conv_id,)
            ).fetchone()

        if not row:
            return []

        messages = json.loads(row[0])

        # Timestamps strip karo - LLM ko nahi chahiye
        return [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]

    def get_stats(self) -> Dict:
        """Stats for admin dashboard"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0]

            active_cutoff = (
                datetime.now() - timedelta(hours=1)
            ).isoformat()

            active = conn.execute(
                "SELECT COUNT(*) FROM conversations "
                "WHERE last_active > ?",
                (active_cutoff,)
            ).fetchone()[0]

            by_tenant = conn.execute(
                "SELECT tenant_id, COUNT(*) as count "
                "FROM conversations "
                "WHERE tenant_id IS NOT NULL "
                "GROUP BY tenant_id "
                "ORDER BY count DESC LIMIT 10"
            ).fetchall()

            by_role = conn.execute(
                "SELECT user_role, COUNT(*) FROM conversations "
                "GROUP BY user_role"
            ).fetchall()

        return {
            "total": total,
            "active_last_hour": active,
            "by_role": dict(by_role),
            "by_tenant": [
                {"tenant_id": r[0], "conversations": r[1]}
                for r in by_tenant
            ],
        }

    def _cleanup_old(self):
        """
        ✅ Bug 4 Fix: _cleanup_old() method add kiya
        Expired conversations delete karo
        """
        cutoff = (
            datetime.now()
            - timedelta(hours=settings.CONVERSATION_EXPIRY_HOURS)
        ).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                "DELETE FROM conversations WHERE last_active < ?",
                (cutoff,)
            ).rowcount
            conn.commit()

        if deleted > 0:
            print(f"🧹 Cleaned {deleted} expired conversations")


# Singleton
_conv_store: Optional[ConversationStore] = None


def get_conv_store() -> ConversationStore:
    global _conv_store
    if _conv_store is None:
        # Data directory ensure karo
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conv_store = ConversationStore(str(settings.CONVERSATIONS_DB))
    return _conv_store