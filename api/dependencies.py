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
import abc

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
    """

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "")

    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> Optional[str]:
        if not self.is_configured():
            return None

        temperature = temperature or settings.TEMPERATURE
        max_tokens = max_tokens or settings.MAX_TOKENS

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
                        data["choices"][0]["message"]["content"].strip()
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
# ABSTRACT BASE STORE
# ════════════════════════════════════════════════

class BaseConversationStore(abc.ABC):
    """
    Common interface — dono backends (SQLite + Turso) same methods expose karte hain.
    Future mein koi bhi backend add karo bina chat.py change kiye.
    """

    @abc.abstractmethod
    def get_or_create(
        self,
        conv_id: str,
        mode: str = "public",
        tenant_id: Optional[str] = None,
        user_role: str = "guest",
        user_id: Optional[str] = None,
    ) -> Dict:
        pass

    @abc.abstractmethod
    def add_messages(
        self,
        conv_id: str,
        user_msg: str,
        ai_msg: str,
        context_update: Optional[Dict] = None,
    ):
        pass

    @abc.abstractmethod
    def get_llm_messages(self, conv_id: str) -> List[Dict]:
        pass

    @abc.abstractmethod
    def get_stats(self) -> Dict:
        pass

    @abc.abstractmethod
    def _cleanup_old(self):
        pass


# ════════════════════════════════════════════════
# SQLITE BACKEND (Local Development)
# ════════════════════════════════════════════════

class SQLiteConversationStore(BaseConversationStore):
    """
    Local SQLite storage.
    Development ke liye perfect.
    CONV_STORAGE=sqlite
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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

            # Migration — purane DB ke liye safe
            existing = [
                row[1] for row in
                conn.execute("PRAGMA table_info(conversations)").fetchall()
            ]
            migrations = [
                ("mode",      "ALTER TABLE conversations ADD COLUMN mode TEXT DEFAULT 'public'"),
                ("tenant_id", "ALTER TABLE conversations ADD COLUMN tenant_id TEXT DEFAULT NULL"),
                ("user_role", "ALTER TABLE conversations ADD COLUMN user_role TEXT DEFAULT 'guest'"),
                ("user_id",   "ALTER TABLE conversations ADD COLUMN user_id TEXT DEFAULT NULL"),
            ]
            for col, sql in migrations:
                if col not in existing:
                    conn.execute(sql)
                    print(f"🔧 Migration: added column '{col}'")

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_active
                ON conversations(last_active)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant
                ON conversations(tenant_id)
            """)
            conn.commit()
        print("✅ SQLite ConversationDB ready")

    def get_or_create(
        self,
        conv_id: str,
        mode: str = "public",
        tenant_id: Optional[str] = None,
        user_role: str = "guest",
        user_id: Optional[str] = None,
    ) -> Dict:
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

            max_msgs = settings.MAX_HISTORY_PAIRS * 2
            if len(messages) > max_msgs:
                messages = messages[-max_msgs:]

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
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT messages FROM conversations WHERE id = ?",
                (conv_id,)
            ).fetchone()

        if not row:
            return []

        return [
            {"role": m["role"], "content": m["content"]}
            for m in json.loads(row[0])
        ]

    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0]

            cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
            active = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE last_active > ?",
                (cutoff,)
            ).fetchone()[0]

            by_role = dict(conn.execute(
                "SELECT user_role, COUNT(*) FROM conversations GROUP BY user_role"
            ).fetchall())

            by_tenant = conn.execute(
                "SELECT tenant_id, COUNT(*) as count "
                "FROM conversations "
                "WHERE tenant_id IS NOT NULL "
                "GROUP BY tenant_id "
                "ORDER BY count DESC LIMIT 10"
            ).fetchall()

        return {
            "total": total,
            "active_last_hour": active,
            "by_role": by_role,
            "by_tenant": [
                {"tenant_id": r[0], "conversations": r[1]}
                for r in by_tenant
            ],
            "storage": "sqlite_local",
        }

    def _cleanup_old(self):
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


# ════════════════════════════════════════════════
# TURSO BACKEND (Production - Free Cloud)
# Pure HTTP API — zero extra dependencies
# Render pe perfectly works, no Rust needed
# ════════════════════════════════════════════════

class TursoConversationStore(BaseConversationStore):
    """
    Turso Cloud SQLite via HTTP API.

    Zero extra pip packages — sirf httpx use karta hai
    jo already requirements.txt mein hai.

    Free tier:
    - 500 databases
    - 9 GB storage
    - 1 Billion row reads/month

    Sign up: turso.tech
    CONV_STORAGE=turso
    """

    def __init__(self, url: str, token: str):
        # libsql:// → https:// convert karo HTTP API ke liye
        self.http_url = url.replace("libsql://", "https://")
        self.token = token
        self._init_db()

    # ── Internal HTTP call ────────────────────────────────

    def _execute(self, sql: str, params: list = None) -> dict:
        """
        Turso HTTP Pipeline API call.
        Ek ya multiple SQL statements bhejo.
        Docs: docs.turso.tech/sdk/http/reference
        """
        if params is None:
            params = []

        # Params ko Turso format mein convert karo
        turso_params = []
        for p in params:
            if p is None:
                turso_params.append({"type": "null"})
            elif isinstance(p, int):
                turso_params.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                turso_params.append({"type": "float", "value": str(p)})
            else:
                turso_params.append({"type": "text", "value": str(p)})

        body = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {"sql": sql, "args": turso_params}
                },
                {"type": "close"}
            ]
        }

        try:
            response = httpx.post(
                f"{self.http_url}/v2/pipeline",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=10.0,
            )

            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if results and results[0].get("type") == "ok":
                return results[0].get("response", {}).get("result", {})
            return {}

        except httpx.TimeoutException:
            print("⏰ Turso HTTP timeout")
            return {}
        except httpx.HTTPStatusError as e:
            print(f"❌ Turso HTTP {e.response.status_code}: {e.response.text[:200]}")
            return {}
        except Exception as e:
            print(f"❌ Turso error: {e}")
            return {}

    def _rows(self, result: dict) -> List[dict]:
        """
        Turso result se Python dicts banao.
        Column names automatically map hote hain.
        """
        raw_rows = result.get("rows", [])
        cols = [c["name"] for c in result.get("cols", [])]

        parsed = []
        for row in raw_rows:
            parsed.append({
                cols[i]: (
                    cell.get("value") if cell.get("type") != "null" else None
                )
                for i, cell in enumerate(row)
            })
        return parsed

    # ── Init ─────────────────────────────────────────────

    def _init_db(self):
        """Tables aur indexes banao (idempotent)"""
        sqls = [
            """CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                messages    TEXT NOT NULL DEFAULT '[]',
                context     TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL,
                last_active TEXT NOT NULL,
                mode        TEXT DEFAULT 'public',
                tenant_id   TEXT DEFAULT NULL,
                user_role   TEXT DEFAULT 'guest',
                user_id     TEXT DEFAULT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_last_active
               ON conversations(last_active)""",
            """CREATE INDEX IF NOT EXISTS idx_tenant
               ON conversations(tenant_id)""",
        ]
        for sql in sqls:
            self._execute(sql)
        print("✅ Turso ConversationDB ready")

    # ── Public Methods ────────────────────────────────────

    def get_or_create(
        self,
        conv_id: str,
        mode: str = "public",
        tenant_id: Optional[str] = None,
        user_role: str = "guest",
        user_id: Optional[str] = None,
    ) -> Dict:
        self._cleanup_old()

        result = self._execute(
            "SELECT id, messages, context, mode, tenant_id, user_role "
            "FROM conversations WHERE id = ?",
            [conv_id]
        )
        rows = self._rows(result)
        now = datetime.now().isoformat()

        if rows:
            row = rows[0]
            self._execute(
                "UPDATE conversations SET last_active = ? WHERE id = ?",
                [now, conv_id]
            )
            return {
                "id": row["id"],
                "messages": json.loads(row["messages"] or "[]"),
                "context": json.loads(row["context"] or "{}"),
                "mode": row["mode"] or "public",
                "tenant_id": row["tenant_id"],
                "user_role": row["user_role"] or "guest",
            }
        else:
            self._execute(
                """INSERT INTO conversations
                   (id, messages, context, created_at, last_active,
                    mode, tenant_id, user_role, user_id)
                   VALUES (?, '[]', '{}', ?, ?, ?, ?, ?, ?)""",
                [conv_id, now, now, mode, tenant_id, user_role, user_id]
            )
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
        result = self._execute(
            "SELECT messages, context FROM conversations WHERE id = ?",
            [conv_id]
        )
        rows = self._rows(result)

        if not rows:
            print(f"⚠️  Conv {conv_id[:8]} not found in Turso")
            return

        messages = json.loads(rows[0]["messages"] or "[]")
        context = json.loads(rows[0]["context"] or "{}")

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

        max_msgs = settings.MAX_HISTORY_PAIRS * 2
        if len(messages) > max_msgs:
            messages = messages[-max_msgs:]

        if context_update:
            context.update(context_update)

        self._execute(
            """UPDATE conversations
               SET messages = ?, context = ?, last_active = ?
               WHERE id = ?""",
            [
                json.dumps(messages),
                json.dumps(context),
                datetime.now().isoformat(),
                conv_id,
            ]
        )

    def get_llm_messages(self, conv_id: str) -> List[Dict]:
        result = self._execute(
            "SELECT messages FROM conversations WHERE id = ?",
            [conv_id]
        )
        rows = self._rows(result)

        if not rows:
            return []

        messages = json.loads(rows[0]["messages"] or "[]")
        return [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]

    def get_stats(self) -> Dict:
        total_result = self._execute(
            "SELECT COUNT(*) as cnt FROM conversations"
        )
        total_rows = self._rows(total_result)
        total = int(total_rows[0]["cnt"]) if total_rows else 0

        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        active_result = self._execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE last_active > ?",
            [cutoff]
        )
        active_rows = self._rows(active_result)
        active = int(active_rows[0]["cnt"]) if active_rows else 0

        return {
            "total": total,
            "active_last_hour": active,
            "storage": "turso_http",
        }

    def _cleanup_old(self):
        cutoff = (
            datetime.now()
            - timedelta(hours=settings.CONVERSATION_EXPIRY_HOURS)
        ).isoformat()

        try:
            self._execute(
                "DELETE FROM conversations WHERE last_active < ?",
                [cutoff]
            )
        except Exception as e:
            print(f"⚠️  Turso cleanup error: {e}")


# ════════════════════════════════════════════════
# FACTORY — Auto backend select
# ════════════════════════════════════════════════

_conv_store: Optional[BaseConversationStore] = None


def get_conv_store() -> BaseConversationStore:
    """
    CONV_STORAGE env se backend select karo:

    sqlite → SQLiteConversationStore (local dev)
    turso  → TursoConversationStore  (production)

    Turso credentials missing hone par
    automatically SQLite pe fallback karta hai.
    """
    global _conv_store

    if _conv_store is not None:
        return _conv_store

    storage = settings.CONV_STORAGE.lower().strip()

    # ── Turso (Production) ────────────────────
    if storage == "turso":
        url = settings.TURSO_DATABASE_URL
        token = settings.TURSO_AUTH_TOKEN

        if not url or not token:
            print("⚠️  Turso credentials missing!")
            print("   TURSO_DATABASE_URL aur TURSO_AUTH_TOKEN set karo")
            print("   Falling back to SQLite...")
        else:
            try:
                _conv_store = TursoConversationStore(url=url, token=token)
                print("✅ Using Turso Cloud Storage (production)")
                return _conv_store
            except Exception as e:
                print(f"⚠️  Turso init failed: {e}")
                print("   Falling back to SQLite...")

    # ── SQLite (Development / Fallback) ───────
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _conv_store = SQLiteConversationStore(str(settings.CONVERSATIONS_DB))
    print("✅ Using SQLite Local Storage (development)")
    return _conv_store