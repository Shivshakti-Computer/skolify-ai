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
        # Production mein ChromaDB optional hai
        client = get_chroma_client()
        try:
            _collection = client.get_collection(
                settings.VECTOR_COLLECTION_NAME
            )
            print(f"✅ KB loaded: {_collection.count()} docs")
        except Exception as e:
            print(f"⚠️  ChromaDB not available: {e}")
            print("   Groq will use its own knowledge")
            # None return karo - crash mat karo
            return None
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



# ════════════════════════════════════════════════
# GEMINI CLIENT
# aistudio.google.com/apikey se free key lo
# Free: 15 req/min, 1500 req/day, 1M tokens/day
# ════════════════════════════════════════════════

class GeminiClient:

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model   = settings.GEMINI_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> Optional[str]:
        if not self.is_configured():
            return None

        temperature = min(temperature or settings.TEMPERATURE, 1.0)
        max_tokens  = max_tokens or settings.MAX_TOKENS

        # ── OpenAI format → Gemini format convert ─────────
        gemini_contents = []

        # System prompt inject
        gemini_contents.append({
            "role":  "user",
            "parts": [{"text": f"[Instructions]\n{system_prompt}"}]
        })
        gemini_contents.append({
            "role":  "model",
            "parts": [{"text": "Understood. I'll follow these instructions carefully."}]
        })

        # Conversation history
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            gemini_contents.append({
                "role":  role,
                "parts": [{"text": msg["content"]}]
            })

        payload = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature":     temperature,
                "maxOutputTokens": max_tokens,
                "topP":            0.95,
            },
            # Safety settings - school app ke liye relaxed
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT",
                 "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH",
                 "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                 "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                 "threshold": "BLOCK_ONLY_HIGH"},
            ]
        }

        try:
            url = (
                f"{self.BASE_URL}/models/{self.model}"
                f":generateContent?key={self.api_key}"
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )

                if response.status_code != 200:
                    print(f"❌ Gemini {response.status_code}")
                    print(f"   Response: {response.text[:300]}")
                    return None

                if response.status_code == 200:
                    data       = response.json()
                    candidates = data.get("candidates", [])

                    if not candidates:
                        print("⚠️  Gemini: No candidates returned")
                        return None

                    # Content extract
                    content = (
                        candidates[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                        .strip()
                    )

                    if content:
                        tokens = data.get("usageMetadata", {})
                        print(
                            f"   ✅ Gemini: "
                            f"{tokens.get('totalTokenCount', '?')} tokens"
                        )
                        return content

                    # Safety block check
                    finish_reason = (
                        candidates[0].get("finishReason", "")
                    )
                    if finish_reason == "SAFETY":
                        print("⚠️  Gemini: Safety filter triggered")
                    else:
                        print(f"⚠️  Gemini: Empty content ({finish_reason})")
                    return None

                elif response.status_code == 429:
                    print("⚠️  Gemini rate limited → next provider")
                    return None

                elif response.status_code == 400:
                    err = response.json().get("error", {})
                    print(f"❌ Gemini 400: {err.get('message','')[:100]}")
                    return None

                else:
                    print(f"❌ Gemini {response.status_code}: {response.text[:100]}")
                    return None

        except httpx.TimeoutException:
            print("⏰ Gemini timeout → next provider")
            return None
        except Exception as e:
            print(f"❌ Gemini error: {e}")
            return None



# ════════════════════════════════════════════════
# HUGGING FACE CLIENT (Free unlimited)
# ════════════════════════════════════════════════

class HuggingFaceClient:
    """
    Hugging Face Inference API
    
    ✅ FREE - Unlimited requests!
    ⚠️  Slower cold start (20-30s first time)
    ✅ No rate limits
    
    Best models (2025):
    - Qwen/Qwen2.5-7B-Instruct (Multilingual, Hindi support)
    - meta-llama/Llama-3.2-3B-Instruct (Fast, efficient)
    - mistralai/Mistral-7B-Instruct-v0.3 (Good reasoning)
    
    Get token: https://huggingface.co/settings/tokens
    """

    BASE_URL = "https://api-inference.huggingface.co/models"

    def __init__(self):
        self.api_key = settings.HF_API_KEY
        self.model   = settings.HF_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

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
        max_tokens  = max_tokens or settings.MAX_TOKENS

        # ── Format for instruction models ─────────────────
        # Most HF models expect specific prompt format
        prompt_parts = [f"<|system|>\n{system_prompt}\n"]
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "user":
                prompt_parts.append(f"<|user|>\n{content}\n")
            elif role == "assistant":
                prompt_parts.append(f"<|assistant|>\n{content}\n")
        
        prompt_parts.append("<|assistant|>\n")
        prompt = "".join(prompt_parts)

        # ── Alternative format for Qwen/Llama ─────────────
        # If above doesn't work, try this simpler format:
        simple_prompt = f"System: {system_prompt}\n\n"
        for msg in messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            simple_prompt += f"{role}: {msg['content']}\n"
        simple_prompt += "Assistant:"

        # Try complex format first, fallback to simple
        prompts_to_try = [prompt, simple_prompt]

        for attempt, prompt_text in enumerate(prompts_to_try, 1):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(
                        f"{self.BASE_URL}/{self.model}",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type":  "application/json",
                        },
                        json={
                            "inputs": prompt_text,
                            "parameters": {
                                "max_new_tokens": max_tokens,
                                "temperature": temperature,
                                "top_p": 0.9,
                                "return_full_text": False,
                                "do_sample": True,
                            },
                            "options": {
                                "wait_for_model": True,
                                "use_cache": False,
                            }
                        },
                    )

                    # ── Success ───────────────────────────────
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Handle different response formats
                        if isinstance(data, list) and len(data) > 0:
                            if isinstance(data[0], dict):
                                text = data[0].get("generated_text", "").strip()
                            else:
                                text = str(data[0]).strip()
                        elif isinstance(data, dict):
                            text = data.get("generated_text", "").strip()
                        else:
                            text = str(data).strip()

                        if text:
                            # Clean up common artifacts
                            text = text.replace("<|assistant|>", "").strip()
                            text = text.replace("Assistant:", "").strip()
                            
                            print(f"   ✅ HuggingFace: {len(text)} chars (attempt {attempt})")
                            return text

                    # ── Model loading ─────────────────────────
                    elif response.status_code == 503:
                        error_data = response.json()
                        if "loading" in str(error_data).lower():
                            wait_time = error_data.get("estimated_time", 20)
                            print(f"⏳ HF model loading... (~{wait_time}s)")
                            
                            # Wait and retry once
                            import asyncio
                            await asyncio.sleep(min(wait_time + 5, 30))
                            
                            # Retry the request
                            response = await client.post(
                                f"{self.BASE_URL}/{self.model}",
                                headers={
                                    "Authorization": f"Bearer {self.api_key}",
                                    "Content-Type": "application/json",
                                },
                                json={
                                    "inputs": prompt_text,
                                    "parameters": {
                                        "max_new_tokens": max_tokens,
                                        "temperature": temperature,
                                        "return_full_text": False,
                                    },
                                    "options": {"wait_for_model": True}
                                },
                            )
                            
                            if response.status_code == 200:
                                data = response.json()
                                if isinstance(data, list) and data:
                                    text = data[0].get("generated_text", "").strip()
                                    if text:
                                        print(f"   ✅ HF (after loading): {len(text)} chars")
                                        return text
                        
                        print("⚠️  HF model still loading → next provider")
                        return None

                    # ── Rate limit (shouldn't happen on free tier) ─
                    elif response.status_code == 429:
                        print("⚠️  HF rate limit (unusual) → next")
                        return None

                    # ── Other errors ──────────────────────────
                    else:
                        if attempt == 1:
                            print(f"⚠️  HF attempt {attempt} failed, trying simple format...")
                            continue  # Try next format
                        else:
                            print(f"❌ HF {response.status_code}: {response.text[:150]}")
                            return None

            except httpx.TimeoutException:
                if attempt == 1:
                    print(f"⏰ HF timeout (attempt {attempt}), retrying...")
                    continue
                else:
                    print("⏰ HF timeout → next provider")
                    return None
                    
            except Exception as e:
                print(f"❌ HF error (attempt {attempt}): {e}")
                if attempt == len(prompts_to_try):
                    return None

        return None


# ════════════════════════════════════════════════
# OPENROUTER CLIENT
# ════════════════════════════════════════════════

class OpenRouterClient:
    """
    OpenRouter API - Access to 100+ LLMs via one API
    
    Free models (2025):
    - google/gemini-2.0-flash-exp:free (Best free option)
    - meta-llama/llama-3.1-8b-instruct:free
    - mistralai/mistral-7b-instruct:free
    - qwen/qwen-2-7b-instruct:free
    
    Sign up: https://openrouter.ai
    Docs: https://openrouter.ai/docs
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model   = settings.OPENROUTER_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

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
        max_tokens  = max_tokens or settings.MAX_TOKENS

        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type":  "application/json",
                        "HTTP-Referer":  "https://skolify.in",
                        "X-Title":       "Skolify AI Assistant",
                    },
                    json={
                        "model":       self.model,
                        "messages":    full_messages,
                        "temperature": temperature,
                        "max_tokens":  max_tokens,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    usage = data.get("usage", {})
                    print(f"   ✅ OpenRouter: {usage.get('total_tokens', '?')} tokens")
                    return content

                elif response.status_code == 429:
                    print("⚠️  OpenRouter rate limit → next")
                    return None

                elif response.status_code == 402:
                    print("⚠️  OpenRouter: Credits exhausted → next")
                    return None

                else:
                    print(f"❌ OpenRouter {response.status_code}: {response.text[:100]}")
                    return None

        except httpx.TimeoutException:
            print("⏰ OpenRouter timeout → next")
            return None
        except Exception as e:
            print(f"❌ OpenRouter error: {e}")
            return None


# ════════════════════════════════════════════════
# DEEPSEEK CLIENT
# ════════════════════════════════════════════════

class DeepSeekClient:
    """
    DeepSeek API - Best value LLM in 2025
    
    Model: deepseek-chat (Jan 2025)
    - Better than GPT-4 on many benchmarks
    - 64K context window
    - Pricing: $0.14 per 1M input tokens, $0.28 per 1M output
    - Rate: 60 requests/minute
    
    $1 = ~7 million tokens (99% cheaper than GPT-4)
    
    Sign up: https://platform.deepseek.com
    """

    BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model   = settings.DEEPSEEK_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

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
        max_tokens  = max_tokens or settings.MAX_TOKENS

        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type":  "application/json",
                    },
                    json={
                        "model":       self.model,
                        "messages":    full_messages,
                        "temperature": temperature,
                        "max_tokens":  max_tokens,
                        "stream":      False,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    usage = data.get("usage", {})
                    total_tokens = usage.get("total_tokens", 0)
                    cost = (total_tokens / 1_000_000) * 0.14  # Rough estimate
                    print(f"   ✅ DeepSeek: {total_tokens} tokens (~${cost:.4f})")
                    return content

                elif response.status_code == 429:
                    print("⚠️  DeepSeek rate limit → next")
                    return None

                elif response.status_code == 401:
                    print("❌ DeepSeek: Invalid API key")
                    return None

                elif response.status_code == 402:
                    print("❌ DeepSeek: Insufficient credits")
                    return None

                else:
                    print(f"❌ DeepSeek {response.status_code}: {response.text[:100]}")
                    return None

        except httpx.TimeoutException:
            print("⏰ DeepSeek timeout → next")
            return None
        except Exception as e:
            print(f"❌ DeepSeek error: {e}")
            return None


# ════════════════════════════════════════════════
# UPDATED LLM MANAGER (2025 Edition)
# ════════════════════════════════════════════════

class LLMManager:
    """
    Multi-provider LLM orchestrator with intelligent fallback
    
    🎯 2025 Provider Chain:
    1. Groq        → Fastest (30 RPM, 14K RPD free)
    2. Gemini 2.0  → Latest (Unlimited experimental)
    3. OpenRouter  → Multi-model (100+ options)
    4. DeepSeek    → Best value ($0.14/1M tokens)
    5. HuggingFace → Unlimited free (slower cold start)
    
    ✅ PRIVACY GUARANTEED:
    - Portal data → NEVER sent to ANY provider
    - Only public website info sent to LLMs
    """

    def __init__(self):
        self.providers: Dict[str, any] = {
            "groq":        GroqClient(),
            "gemini":      GeminiClient(),
            "openrouter":  OpenRouterClient(),
            "deepseek":    DeepSeekClient(),
            "huggingface": HuggingFaceClient(),
        }

        self.provider_order = [
            p.strip()
            for p in settings.LLM_PROVIDER_ORDER.split(",")
            if p.strip() in self.providers
        ]

        self._log_status()

    def _log_status(self):
        print("\n🤖 LLM Provider Chain (2025):")
        
        rate_info = {
            "groq":        "⚡ 30 RPM, 14K RPD",
            "gemini":      "🆕 Unlimited (exp)",
            "openrouter":  "🎯 100+ models",
            "deepseek":    "💎 60 RPM, $0.14/1M",
            "huggingface": "♾️  Unlimited free",
        }
        
        for i, name in enumerate(self.provider_order, 1):
            client = self.providers[name]
            configured = client.is_configured()
            
            status_icon = "✅" if configured else "❌"
            status_text = "ready" if configured else "no key"
            
            print(
                f"   {i}. {name:12} "
                f"{status_icon} {status_text:8} "
                f"{rate_info.get(name, '')}"
            )
        
        if not self.is_any_configured():
            print("   ⚠️  No LLM configured → local fallback only")
        
        if settings.ENABLE_RESPONSE_CACHE:
            print(f"\n   💾 Response cache enabled ({settings.CACHE_TTL_SECONDS}s TTL)")
        
        print()

    def is_any_configured(self) -> bool:
        """Check if at least one provider is configured"""
        return any(
            self.providers[name].is_configured()
            for name in self.provider_order
        )

    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> tuple[Optional[str], str]:
        """
        Try providers in order until one succeeds
        
        Args:
            system_prompt: System instructions
            messages: Chat history
            temperature: Sampling temperature (0-1)
            max_tokens: Max response length
            
        Returns:
            (response_text, provider_used)
            provider_used: "groq"|"gemini"|"openrouter"|"deepseek"|"huggingface"|"none"
        """

        for provider_name in self.provider_order:
            client = self.providers.get(provider_name)

            # Skip if not configured
            if not client or not client.is_configured():
                continue

            print(f"🔄 Trying {provider_name}...")

            try:
                result = await client.chat(
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                if result:
                    # Success!
                    return result, provider_name

                # Failed → try next provider
                print(f"   ↳ {provider_name} failed, trying next...")

            except Exception as e:
                print(f"   ↳ {provider_name} exception: {e}")
                continue

        # All providers failed
        print("❌ All LLM providers failed → local fallback")
        return None, "none"


# ════════════════════════════════════════════════
# SINGLETONS
# ════════════════════════════════════════════════

_hf_client: Optional[HuggingFaceClient] = None
_openrouter_client: Optional[OpenRouterClient] = None
_deepseek_client: Optional[DeepSeekClient] = None
_llm_manager: Optional[LLMManager] = None


def get_hf_client() -> HuggingFaceClient:
    """Get HuggingFace client singleton"""
    global _hf_client
    if _hf_client is None:
        _hf_client = HuggingFaceClient()
        status = "✅ ready" if _hf_client.is_configured() else "❌ no token"
        print(f"HuggingFace: {status}")
    return _hf_client


def get_openrouter_client() -> OpenRouterClient:
    """Get OpenRouter client singleton"""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
        status = "✅ ready" if _openrouter_client.is_configured() else "❌ no key"
        print(f"OpenRouter: {status}")
    return _openrouter_client


def get_deepseek_client() -> DeepSeekClient:
    """Get DeepSeek client singleton"""
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient()
        status = "✅ ready" if _deepseek_client.is_configured() else "❌ no key"
        print(f"DeepSeek: {status}")
    return _deepseek_client


def get_llm_manager() -> LLMManager:
    """
    Get LLM Manager singleton
    
    ⭐ USE THIS in chat.py and portal_chat.py
    
    Automatically handles:
    - Multi-provider fallback
    - Rate limiting
    - Error handling
    - Response caching
    """
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager