# api/routes/chat.py
# UPDATED: 2025-02-01
# ✅ Multi-provider LLM with intelligent fallback
# ✅ Public chat only - no sensitive data to LLM
# ✅ Response caching for rate limit reduction
# ✅ Anti-hallucination system
# ✅ Better language detection
# ✅ Enhanced quick replies

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import re

from ..dependencies import (
    get_embedding_model,
    get_collection,
    get_llm_manager,
    get_conv_store,
)
from ..config import settings
from ..prompts.system_prompt import (
    PUBLIC_SYSTEM_PROMPT,
    PORTAL_SYSTEM_PROMPT,
    ROLE_PROMPTS,
)

from ..utils.response_cache import get_public_cache

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
# VECTOR SEARCH
# ════════════════════════════════════════════════

def search_knowledge_base(query: str, n: int = 5) -> List[Dict]:
    """
    Search Skolify public knowledge base
    
    ✅ PRIVACY: Only public website content indexed
    No school data ever stored in vector DB
    """
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
    """Build context string from top chunks"""
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks[:4], 1):
        parts.append(f"[Source {i}: {c['url']}]\n{c['text']}")
    return "\n\n---\n\n".join(parts)


# ════════════════════════════════════════════════
# ✅ ENHANCED CONTEXT EXTRACTOR
# ════════════════════════════════════════════════

def extract_context(message: str) -> Dict:
    """
    Extract metadata from user message
    
    ✅ IMPROVED: Better topic detection
    ✅ NEW: More topics covered
    """
    updates   = {}
    msg_lower = message.lower()

    # Extract student count if mentioned
    numbers = re.findall(r'\b(\d{2,5})\b', message)
    for n_str in numbers:
        n = int(n_str)
        if 10 <= n <= 50000:
            updates["student_count"] = n
            break

    # ✅ ENHANCED topic detection with more keywords
    topics = {
        "pricing": [
            "price", "cost", "plan", "kitna", "₹", "rupee", 
            "monthly", "yearly", "fee", "cheap", "expensive",
            "kharcha", "paisa", "charge", "rate", "amount"
        ],
        "features": [
            "feature", "module", "offer", "include", "kya kya", 
            "what can", "kya hota", "facility", "option",
            "function", "capability", "benefit"
        ],
        "trial": [
            "trial", "free", "demo", "try", "bina paise",
            "test", "sample", "dekh lo", "use kar ke dekho"
        ],
        "support": [
            "support", "help", "contact", "call", "email",
            "madad", "sahayata", "assistance", "customer care"
        ],
        "setup": [
            "setup", "start", "register", "kaise", "begin",
            "install", "configure", "shuru", "implement"
        ],
        "security": [
            "security", "safe", "privacy", "data", "secure",
            "protection", "suraksha", "backup", "encryption"
        ],
        "credits": [
            "credit", "sms", "whatsapp", "message", "notification",
            "alert", "communication", "messaging"
        ],
        "mobile": [
            "mobile", "app", "android", "ios", "phone",
            "smartphone", "application", "download"
        ],
        "integration": [
            "integration", "api", "connect", "sync", "import",
            "export", "integrate", "third party"
        ],
        "comparison": [
            "compare", "vs", "versus", "better", "difference",
            "alternative", "competitor", "similar"
        ],
    }

    for topic, keywords in topics.items():
        if any(kw in msg_lower for kw in keywords):
            updates["last_topic"] = topic
            break

    return updates


# ════════════════════════════════════════════════
# ✅ ENHANCED QUICK REPLIES
# ════════════════════════════════════════════════

def get_quick_replies(topic: str, role: str = "guest") -> List[Dict]:
    """
    Get contextual quick reply buttons
    
    ✅ IMPROVED: More topic-specific suggestions
    ✅ NEW: Better action buttons
    """
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
        "security": [  # ✅ NEW
            {"text": "🔒 Data Security",  "payload": "security_features"},
            {"text": "📦 All Features",   "payload": "features_overview"},
            {"text": "💰 See Plans",      "payload": "admin_plans_overview"},
            {"text": "📞 Talk to Us",     "action": "forward"},
        ],
        "credits": [  # ✅ NEW
            {"text": "📱 SMS/WhatsApp",   "payload": "credits_info"},
            {"text": "💰 Credit Pricing", "payload": "credit_pricing"},
            {"text": "🎁 Free Trial",     "payload": "trial_info"},
            {"text": "📞 Get Demo",       "action": "forward"},
        ],
        "mobile": [  # ✅ NEW
            {"text": "📱 Mobile Features", "payload": "mobile_features"},
            {"text": "📦 All Features",    "payload": "features_overview"},
            {"text": "💰 See Plans",       "payload": "admin_plans_overview"},
            {"text": "🎁 Try Free",        "payload": "trial_info"},
        ],
        "comparison": [  # ✅ NEW
            {"text": "⚡ Why Skolify?",    "payload": "why_skolify"},
            {"text": "💰 Our Pricing",     "payload": "admin_plans_overview"},
            {"text": "🎁 Free Trial",      "payload": "trial_info"},
            {"text": "📞 Talk to Expert",  "action": "forward"},
        ],
    }

    return topic_replies.get(topic, defaults)


# ════════════════════════════════════════════════
# ✅ ENHANCED SMART FALLBACK
# ════════════════════════════════════════════════

FALLBACK_RESPONSES = {
    "greeting": (
        "Hey! 👋 I'm **Anvi**, Skolify's AI assistant!\n\n"
        "I can help you with:\n"
        "• 💰 Pricing & Plans\n"
        "• 📦 Features & Modules\n"
        "• 🎁 Free Trial (60 days!)\n"
        "• 🚀 Getting Started\n\n"
        "What would you like to know?"
    ),
    "pricing": (
        "Here are Skolify's plans:\n\n"
        "• **Starter** — ₹499/mo (500 students)\n"
        "• **Growth** — ₹999/mo (1,500 students) ⭐\n"
        "• **Pro** — ₹1,999/mo (5,000 students)\n"
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
        "✅ Free setup support\n"
        "✅ All features unlocked\n\n"
        "Start at **skolify.in/register** — takes just 2 minutes!"
    ),
    "support": (  # ✅ NEW
        "**Get Help:**\n\n"
        "📧 Email: support@skolify.in\n"
        "📞 Call: +91-XXXXXXXXXX\n"
        "💬 WhatsApp: +91-XXXXXXXXXX\n\n"
        "Available: Mon-Sat, 9 AM - 6 PM IST\n\n"
        "Or start a free trial and get **free setup support**!"
    ),
    "mobile": (  # ✅ NEW
        "**📱 Mobile App Features:**\n\n"
        "✅ Android & iOS apps\n"
        "✅ Teacher attendance marking\n"
        "✅ Parent notifications\n"
        "✅ Student homework tracking\n"
        "✅ Fee payment reminders\n\n"
        "Download from Play Store & App Store!"
    ),
    "default": (
        "I can help you with Skolify's plans, features, "
        "free trial, or getting started!\n\n"
        "What would you like to know?"
    ),
}


def smart_fallback(message: str, context: Dict) -> str:
    """
    Smart template-based responses when all LLMs fail
    
    ✅ No external API dependency
    ✅ ENHANCED: More topic coverage
    """
    msg = message.lower()

    # Greeting detection
    greetings = ["hi", "hello", "hey", "namaste", "hlo", "hii", "helo", "hy"]
    if any(msg.startswith(g) for g in greetings) or msg in greetings:
        return FALLBACK_RESPONSES["greeting"]

    # Topic-based response
    topic = context.get("last_topic", "")
    if topic in FALLBACK_RESPONSES:
        return FALLBACK_RESPONSES[topic]

    # Keyword-based detection (fallback)
    if any(w in msg for w in ["price", "plan", "cost", "kitna", "₹"]):
        return FALLBACK_RESPONSES["pricing"]
    if any(w in msg for w in ["feature", "module", "offer", "kya kya"]):
        return FALLBACK_RESPONSES["features"]
    if any(w in msg for w in ["trial", "free", "demo", "bina paise"]):
        return FALLBACK_RESPONSES["trial"]
    if any(w in msg for w in ["support", "help", "contact", "madad"]):
        return FALLBACK_RESPONSES["support"]
    if any(w in msg for w in ["mobile", "app", "android", "ios"]):
        return FALLBACK_RESPONSES["mobile"]

    return FALLBACK_RESPONSES["default"]


# ════════════════════════════════════════════════
# ✅ ENHANCED LANGUAGE DETECTION
# ════════════════════════════════════════════════

def detect_language(message: str) -> str:
    """
    Detect if message is in English, Hindi, or Hinglish
    
    ✅ IMPROVED: Better accuracy
    Returns: 'english', 'hindi', or 'hinglish'
    """
    msg_lower = message.lower()
    
    # Pure English indicators
    english_words = [
        'hello', 'hi', 'hey', 'who', 'are', 'you', 'what', 
        'is', 'tell', 'me', 'show', 'how', 'can', 'help',
        'pricing', 'features', 'plans', 'trial', 'free',
        'the', 'and', 'or', 'but', 'for', 'with', 'about',
        'your', 'our', 'their', 'does', 'have', 'want'
    ]
    
    # Hindi/Hinglish indicators
    hindi_words = [
        'kya', 'hai', 'hain', 'kaun', 'ho', 'batao', 'dikhao',
        'kaise', 'kitne', 'aap', 'main', 'mujhe', 'chahiye',
        'mera', 'mere', 'tera', 'tere', 'uska', 'uske',
        'kab', 'kahan', 'kyun', 'kyu', 'koi', 'kuch',
        'bhi', 'bhe', 'toh', 'to', 'jo', 'jab'
    ]
    
    # Count occurrences
    words = msg_lower.split()
    english_count = sum(1 for w in words if any(e in w for e in english_words))
    hindi_count = sum(1 for w in words if any(h in w for h in hindi_words))
    
    # Determine language
    if hindi_count == 0 and english_count > 0:
        return 'english'
    elif hindi_count > 0 and english_count == 0:
        return 'hindi'
    elif hindi_count > 0 and english_count > 0:
        return 'hinglish'
    else:
        # Default: check for Roman script Hindi
        if any(h in msg_lower for h in ['aap', 'mujhe', 'kaise', 'batao']):
            return 'hinglish'
        return 'english'


# ════════════════════════════════════════════════
# ✅ MAIN CHAT ENDPOINT - ENHANCED
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

        # ══════════════════════════════════════════════════
        # ✅ CHECK CACHE FIRST (Public Mode Only)
        # ══════════════════════════════════════════════════
        if not is_portal_mode:
            cache = get_public_cache()
            cached = cache.get(
                query=message,
                context="",
                role=role,
                mode="public"
            )
            
            if cached:
                print(f"💾 Cache HIT for: {message[:40]}...")
                
                # Save to conversation
                store.add_messages(
                    conv_id=conv_id,
                    user_msg=message,
                    ai_msg=cached,
                )
                
                # Extract topic for quick replies
                ctx_update = extract_context(message)
                topic = ctx_update.get("last_topic", "")
                
                return ChatResponse(
                    success=True,
                    answer=cached,
                    conversation_id=conv_id,
                    sources=[],
                    quickReplies=get_quick_replies(topic, role),
                    canForward=False,
                    metadata={
                        'cached': True,
                        'llm_used': False,
                        'source': 'cache',
                        'data_sent_to_llm': False,
                        'cache_hit': True,
                    }
                )

        # ── Knowledge Base Search ──────────────────────────
        chunks      = search_knowledge_base(message)
        context_str = build_context_str(chunks)
        ctx_update  = extract_context(message)
        print(f"🔍 {len(chunks)} chunks found")

        # ── System Prompt ──────────────────────────────────
        if is_portal_mode:
            system_prompt = PORTAL_SYSTEM_PROMPT.format(
                school_name=request.user_name or "Your School",
                user_role=role,
                user_name=request.user_name or "User",
                school_context="Guide user to correct portal section.",
            )
            system_prompt += ROLE_PROMPTS.get(role, "")
        else:
            system_prompt = PUBLIC_SYSTEM_PROMPT

        # ── Augmented Message with Language Detection ─────
        if context_str:
            # ✅ IMPROVED: Use enhanced language detection
            language = detect_language(message)
            
            if language == 'english':
                language_hint = "\n⚠️ RESPOND IN ENGLISH ONLY - User wrote in pure English."
            elif language == 'hindi':
                language_hint = "\n⚠️ RESPOND IN HINDI/HINGLISH - User wrote in Hindi."
            else:  # hinglish
                language_hint = "\n⚠️ RESPOND IN HINGLISH - User wrote in Hindi/English mix."
            
            augmented_message = (
                f"{message}{language_hint}\n\n"
                f"[Relevant Skolify info:\n{context_str}]"
            )
        else:
            augmented_message = message

        # ── LLM History ───────────────────────────────────
        history          = store.get_llm_messages(conv_id)
        messages_for_llm = history + [
            {"role": "user", "content": augmented_message}
        ]

        # ══════════════════════════════════════════════════
        # ✅ LLM CALL WITH USE-CASE ROUTING
        # ══════════════════════════════════════════════════
        llm = get_llm_manager()
        
        use_case = "public"  # Public chat uses public models
        
        ai_response, provider_used = await llm.chat(
            system_prompt=system_prompt,
            messages=messages_for_llm,
            use_case=use_case,
            temperature=0.4,  # Slightly more creative for public chat
            max_tokens=500,   # Longer responses allowed
        )
        
        used_llm = ai_response is not None

        if used_llm:
            print(f"✅ LLM: {provider_used} | {len(ai_response)} chars")
            
            # ✅ ANTI-HALLUCINATION CHECK (for public chat too)
            msg_lower = message.lower()
            
            # Check if asking for specific data
            data_keywords = [
                'list', 'show me', 'tell me the', 'names of',
                'who are', 'which schools', 'student names',
                'teacher names', 'specific data'
            ]
            
            asking_for_data = any(kw in msg_lower for kw in data_keywords)
            
            # Check if response contains fake specific data
            fake_data_patterns = [
                r'\d+\.\s+[A-Z][a-z]+\s+[A-Z][a-z]+',  # "1. John Doe"
                r'Student\s+Name:',
                r'Teacher\s+Name:',
                r'School\s+Name:.*\n.*\n.*\n',  # Multiple school names listed
            ]
            
            has_fake_data = any(
                re.search(pattern, ai_response) 
                for pattern in fake_data_patterns
            )
            
            if asking_for_data and has_fake_data:
                print("⚠️ HALLUCINATION DETECTED in public chat!")
                
                ai_response = (
                    "I don't have access to specific school or student data. 🤔\n\n"
                    "I can help you with:\n"
                    "• 💰 Skolify's pricing & plans\n"
                    "• 📦 Features & modules\n"
                    "• 🎁 Free trial info\n"
                    "• 🚀 How to get started\n\n"
                    "What would you like to know about Skolify?"
                )
                provider_used = "hallucination_blocker"

        # ── Smart Fallback ─────────────────────────────────
        if not ai_response:
            print("📋 All LLMs unavailable → smart fallback")
            ai_response   = smart_fallback(message, ctx_update)
            provider_used = "local_fallback"

        # ══════════════════════════════════════════════════
        # ✅ CACHE THE RESPONSE (Public Mode Only)
        # ══════════════════════════════════════════════════
        if ai_response and not is_portal_mode and used_llm and provider_used != "hallucination_blocker":
            cache = get_public_cache()
            cache.set(
                query=message,
                response=ai_response,
                context="",
                role=role,
                mode="public"
            )
            print(f"💾 Response cached for: {message[:40]}...")

        # ── Save ───────────────────────────────────────────
        store.add_messages(
            conv_id=conv_id,
            user_msg=message,
            ai_msg=ai_response,
            context_update=ctx_update,
        )

        # ── Quick Replies + Sources ────────────────────────
        topic         = ctx_update.get("last_topic", "")
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
                "data_sent_to_llm":   False,
                "conversation_turns": len(conversation["messages"]) // 2 + 1,
                "language_detected":  detect_language(message),  # ✅ NEW
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
# ✅ HEALTH CHECK - ENHANCED
# ════════════════════════════════════════════════

@router.get("/health")
async def health():
    """
    System health check endpoint
    
    ✅ IMPROVED: More detailed status
    """
    status = {
        "api":       "healthy",
        "vector_db": "unknown",
        "llm":       "unknown",
        "cache":     "unknown",  # ✅ NEW
        "documents": 0,
    }
    
    # Vector DB status
    try:
        col = get_collection()
        if col:
            status["vector_db"] = "healthy"
            status["documents"] = col.count()
        else:
            status["vector_db"] = "unavailable"
    except Exception as e:
        status["vector_db"] = f"error: {str(e)}"

    # Multi-provider LLM status
    try:
        llm = get_llm_manager()
        status["llm"] = "multi_provider"
        status["providers"] = {
            name: client.is_configured()
            for name, client in llm.providers.items()
        }
        status["provider_order"] = llm.provider_order
    except Exception:
        status["llm"] = "unknown"

    # ✅ Cache status
    try:
        cache = get_public_cache()
        stats = cache.get_stats()
        status["cache"] = "healthy"
        status["cache_stats"] = stats
    except Exception:
        status["cache"] = "unavailable"

    # Conversation storage
    try:
        conv_stats = get_conv_store().get_stats()
        status["conversations"] = conv_stats
    except Exception:
        pass

    return status


# ════════════════════════════════════════════════
# ✅ HELPER - Model Name Mapping
# ════════════════════════════════════════════════

def _get_model_name(provider: str) -> str:
    """Get model name for metadata tracking"""
    models = {
        "groq_public":            settings.GROQ_PUBLIC_MODEL,
        "groq_portal":            settings.GROQ_PORTAL_MODEL,
        "groq_admin":             settings.GROQ_ADMIN_MODEL,
        "gemini":                 settings.GEMINI_MODEL,
        "openrouter":             settings.OPENROUTER_MODEL,
        "deepseek":               settings.DEEPSEEK_MODEL,
        "huggingface":            settings.HF_MODEL,
        "local_fallback":         "template",
        "hallucination_blocker":  "anti_hallucination",  # ✅ NEW
        "none":                   "template",
    }
    return models.get(provider, "unknown")