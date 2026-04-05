# api/routes/chat.py
# FIXES:
# 1. Multi-provider LLM (Groq → Gemini fallback)
# 2. Public chat only - no sensitive data ever sent to LLM

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import re

from ..dependencies import (
    get_embedding_model,
    get_collection,
    get_llm_manager,      # ✅ Multi-provider manager
    get_conv_store,
)
from ..config import settings
from ..prompts.system_prompt import (
    PUBLIC_SYSTEM_PROMPT,
    PORTAL_SYSTEM_PROMPT,
    ROLE_PROMPTS,
)

router = APIRouter(prefix="/api", tags=["chat"])


# ════════════════════════════════════════════════
# MODELS
# ════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[str] = None
    role: Optional[str] = "guest"
    mode: Optional[str] = "public"
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None


class Source(BaseModel):
    url: str
    page_type: str
    score: float


class ChatResponse(BaseModel):
    success: bool
    answer: str
    conversation_id: str
    sources: List[Source] = []
    quickReplies: List[Dict] = []
    canForward: bool = False
    metadata: Dict[str, Any] = {}


# ════════════════════════════════════════════════
# VECTOR SEARCH - Same as before
# ════════════════════════════════════════════════

def search_knowledge_base(query: str, n: int = 5) -> List[Dict]:
    try:
        model      = get_embedding_model()
        collection = get_collection()

        if collection is None:
            print("⚠️  ChromaDB unavailable")
            return []

        embedding = model.encode([query])[0]
        results   = collection.query(
            query_embeddings=[embedding.tolist()],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"][0]:
            return []

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = max(0.0, 1.0 - (dist / 2.0))
            if score >= 0.05:
                chunks.append({
                    "text":      doc,
                    "url":       meta.get("url", ""),
                    "page_type": meta.get("page_type", "general"),
                    "score":     round(score, 3),
                })

        print(f"   Scores: {[c['score'] for c in chunks]}")
        return sorted(chunks, key=lambda x: x["score"], reverse=True)

    except Exception as e:
        print(f"⚠️  Search error: {e}")
        return []


def build_context_str(chunks: List[Dict]) -> str:
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks[:4], 1):
        parts.append(f"[Source {i}: {c['url']}]\n{c['text']}")
    return "\n\n---\n\n".join(parts)


# ════════════════════════════════════════════════
# CONTEXT EXTRACTOR
# ════════════════════════════════════════════════

def extract_context(message: str) -> Dict:
    updates   = {}
    msg_lower = message.lower()

    numbers = re.findall(r'\b(\d{2,5})\b', message)
    for n_str in numbers:
        n = int(n_str)
        if 10 <= n <= 50000:
            updates["student_count"] = n
            break

    topics = {
        "pricing":  ["price", "cost", "plan", "kitna", "₹", "rupee", "monthly", "yearly", "fee", "cheap"],
        "features": ["feature", "module", "offer", "include", "kya kya", "what can", "kya hota"],
        "trial":    ["trial", "free", "demo", "try", "bina paise"],
        "support":  ["support", "help", "contact", "call", "email"],
        "setup":    ["setup", "start", "register", "kaise", "begin"],
        "security": ["security", "safe", "privacy", "data"],
        "credits":  ["credit", "sms", "whatsapp", "message"],
    }

    for topic, keywords in topics.items():
        if any(kw in msg_lower for kw in keywords):
            updates["last_topic"] = topic
            break

    return updates


# ════════════════════════════════════════════════
# QUICK REPLIES
# ════════════════════════════════════════════════

def get_quick_replies(topic: str, role: str = "guest") -> List[Dict]:
    defaults = [
        {"text": "💰 Plans",        "payload": "admin_plans_overview"},
        {"text": "🎁 Free Trial",   "payload": "trial_info"},
        {"text": "📦 Features",     "payload": "features_overview"},
        {"text": "📞 Talk to Us",   "action": "forward"},
    ]

    topic_replies = {
        "pricing": [
            {"text": "🎁 Start Free Trial", "payload": "trial_info"},
            {"text": "⭐ Growth Plan",      "payload": "growth_plan_detail"},
            {"text": "📦 All Features",     "payload": "features_overview"},
            {"text": "📞 Get Demo",         "action": "forward"},
        ],
        "features": [
            {"text": "💰 See Pricing",  "payload": "admin_plans_overview"},
            {"text": "🎁 Free Trial",   "payload": "trial_info"},
            {"text": "📱 Mobile App?",  "payload": "mobile_features"},
            {"text": "📞 Talk to Us",   "action": "forward"},
        ],
        "trial": [
            {"text": "🚀 Start Now",        "payload": "start_trial"},
            {"text": "💰 After Trial?",     "payload": "admin_plans_overview"},
            {"text": "📦 What's Included?", "payload": "trial_features"},
            {"text": "📞 Get Help",         "action": "forward"},
        ],
        "support": [
            {"text": "💰 Pricing",        "payload": "admin_plans_overview"},
            {"text": "🎁 Free Trial",     "payload": "trial_info"},
            {"text": "📞 Contact Team",   "action": "forward"},
        ],
        "setup": [
            {"text": "🎁 Start Trial",      "payload": "trial_info"},
            {"text": "📹 Video Guide",      "payload": "setup_guide"},
            {"text": "📞 Free Setup Call",  "action": "forward"},
        ],
    }

    return topic_replies.get(topic, defaults)


# ════════════════════════════════════════════════
# SMART FALLBACK
# ════════════════════════════════════════════════

FALLBACK_RESPONSES = {
    "greeting": (
        "Hey! 👋 I'm **Anvi**, Skolify's AI assistant!\n\n"
        "I can help you with pricing, features, free trial, "
        "and getting started.\n\nWhat would you like to know?"
    ),
    "pricing": (
        "Here are Skolify's plans:\n\n"
        "• **Starter** — ₹499/mo (500 students)\n"
        "• **Growth** — ₹999/mo (1,500 students) ⭐\n"
        "• **Pro** — ₹1,999/mo (3,000 students)\n"
        "• **Enterprise** — ₹3,999/mo (Unlimited)\n\n"
        "✅ Annual = 2 months FREE\n"
        "✅ All plans: **60-day free trial**\n\n"
        "How many students does your school have?"
    ),
    "features": (
        "Skolify has **22+ modules**!\n\n"
        "**All Plans:** Attendance, Student management, "
        "School website, Notice board\n\n"
        "**Growth+:** Online fees, Exams, Homework, Timetable\n\n"
        "**Pro+:** Library, Online classes, Certificates\n\n"
        "**Enterprise:** HR/Payroll, Transport, Hostel\n\n"
        "Want details on any specific feature?"
    ),
    "trial": (
        "**60-Day Free Trial** 🎁\n\n"
        "✅ Full access — no credit card\n"
        "✅ 500 free SMS/WhatsApp credits\n"
        "✅ Free setup support\n\n"
        "Start at **skolify.in/register** — takes just 2 minutes!"
    ),
    "default": (
        "I can help you with Skolify's plans, features, "
        "free trial, or getting started!\n\n"
        "What would you like to know?"
    ),
}


def smart_fallback(message: str, context: Dict) -> str:
    msg = message.lower()

    greetings = ["hi", "hello", "hey", "namaste", "hlo", "hii"]
    if any(msg.startswith(g) for g in greetings) or msg in greetings:
        return FALLBACK_RESPONSES["greeting"]

    topic = context.get("last_topic", "")
    if topic in FALLBACK_RESPONSES:
        return FALLBACK_RESPONSES[topic]

    if any(w in msg for w in ["price", "plan", "cost", "kitna"]):
        return FALLBACK_RESPONSES["pricing"]
    if any(w in msg for w in ["feature", "module", "offer"]):
        return FALLBACK_RESPONSES["features"]
    if any(w in msg for w in ["trial", "free", "demo"]):
        return FALLBACK_RESPONSES["trial"]

    return FALLBACK_RESPONSES["default"]


# ════════════════════════════════════════════════
# MAIN CHAT ENDPOINT
# ════════════════════════════════════════════════

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        conv_id = request.conversation_id or str(uuid.uuid4())
        message = request.message.strip()
        role    = request.role or "guest"

        is_portal_mode = bool(request.tenant_id and settings.ENABLE_PORTAL_MODE)
        mode           = "portal" if is_portal_mode else "public"

        print(f"\n💬 [{conv_id[:8]}] [{role}] {message[:60]}...")

        # ── Conversation ───────────────────────────────────
        store        = get_conv_store()
        conversation = store.get_or_create(
            conv_id=conv_id,
            mode=mode,
            tenant_id=request.tenant_id,
            user_role=role,
            user_id=request.user_id,
        )

        # ── Knowledge Base Search ──────────────────────────
        # ✅ PRIVACY: Only public website info search hota hai
        # School data kabhi search nahi hota
        chunks      = search_knowledge_base(message)
        context_str = build_context_str(chunks)
        ctx_update  = extract_context(message)
        print(f"🔍 {len(chunks)} chunks found")

        # ── System Prompt ──────────────────────────────────
        if is_portal_mode:
            # Portal mode: guide only, no real data in prompt
            system_prompt = PORTAL_SYSTEM_PROMPT.format(
                school_name=request.user_name or "Your School",
                user_role=role,
                user_name=request.user_name or "User",
                # ✅ PRIVACY: Real school data NEVER in prompt
                school_context="Guide user to correct portal section.",
            )
            system_prompt += ROLE_PROMPTS.get(role, "")
        else:
            system_prompt = PUBLIC_SYSTEM_PROMPT

        # ── Augmented Message ──────────────────────────────
        # ✅ PRIVACY: Only public KB context added
        if context_str:
            augmented_message = (
                f"{message}\n\n"
                f"[Relevant Skolify info:\n{context_str}]"
            )
        else:
            augmented_message = message

        # ── LLM History ───────────────────────────────────
        history          = store.get_llm_messages(conv_id)
        messages_for_llm = history + [
            {"role": "user", "content": augmented_message}
        ]

        # ── Multi-Provider LLM Call ────────────────────────
        # ✅ RATE LIMIT FIX: Groq → Gemini → Together → Fallback
        llm                        = get_llm_manager()
        ai_response, provider_used = await llm.chat(
            system_prompt=system_prompt,
            messages=messages_for_llm,
        )
        used_llm = ai_response is not None

        if used_llm:
            print(f"✅ LLM: {provider_used} | {len(ai_response)} chars")

        # ── Smart Fallback ─────────────────────────────────
        if not ai_response:
            print("📋 All LLMs unavailable → smart fallback")
            ai_response   = smart_fallback(message, ctx_update)
            provider_used = "local_fallback"

        # ── Save ───────────────────────────────────────────
        store.add_messages(
            conv_id=conv_id,
            user_msg=message,
            ai_msg=ai_response,
            context_update=ctx_update,
        )

        # ── Quick Replies + Sources ────────────────────────
        topic        = ctx_update.get("last_topic", "")
        quick_replies = get_quick_replies(topic, role)
        sources       = [
            Source(url=c["url"], page_type=c["page_type"], score=c["score"])
            for c in chunks[:3]
        ]

        print(f"✅ Done | Provider={provider_used} | Sources={len(sources)}")

        return ChatResponse(
            success=True,
            answer=ai_response,
            conversation_id=conv_id,
            sources=sources,
            quickReplies=quick_replies,
            canForward=False,
            metadata={
                "llm_used":           used_llm,
                "llm_provider":       provider_used,
                "model":              _get_model_name(provider_used),
                "context_chunks":     len(chunks),
                "source":             f"ai_{provider_used}" if used_llm else "local_fallback",
                "portal_mode":        is_portal_mode,
                "tenant_id":          request.tenant_id,
                # ✅ Privacy flag
                "data_sent_to_llm":   False,
                "conversation_turns": len(conversation["messages"]) // 2 + 1,
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        traceback.print_exc()

        return ChatResponse(
            success=False,
            answer=(
                "Oops! Something went wrong. 😅\n\n"
                "Please try again, or reach out at **support@skolify.in**"
            ),
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            quickReplies=[{"text": "📞 Contact Support", "action": "forward"}],
            metadata={"error": str(e)},
        )


# ════════════════════════════════════════════════
# HEALTH CHECK
# ════════════════════════════════════════════════

@router.get("/health")
async def health():
    status = {
        "api":      "healthy",
        "vector_db": "unknown",
        "llm":      "unknown",
        "documents": 0,
    }

    try:
        col = get_collection()
        if col:
            status["vector_db"] = "healthy"
            status["documents"] = col.count()
        else:
            status["vector_db"] = "unavailable"
    except Exception as e:
        status["vector_db"] = f"error: {str(e)}"

    # ✅ Multi-provider status
    try:
        llm    = get_llm_manager()
        status["llm"] = "multi_provider"
        status["providers"] = {
            name: client.is_configured()
            for name, client in llm.providers.items()
        }
        status["provider_order"] = llm.provider_order
    except Exception:
        status["llm"] = "unknown"

    try:
        stats = get_conv_store().get_stats()
        status["conversations"] = stats
    except Exception:
        pass

    return status


# ── Helper ────────────────────────────────────────────────
def _get_model_name(provider: str) -> str:
    models = {
        "groq":           settings.GROQ_MODEL,
        "gemini":         settings.GEMINI_MODEL,
        "together":       settings.TOGETHER_MODEL,
        "local_fallback": "template",
        "none":           "template",
    }
    return models.get(provider, "unknown")