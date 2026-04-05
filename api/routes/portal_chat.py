# api/routes/portal_chat.py
# Portal + Superadmin endpoints
# Existing chat.py ka structure follow karta hai

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import uuid

from ..dependencies import get_groq_client, get_conv_store
from ..config import settings
from ..prompts.system_prompt import (
    PORTAL_SYSTEM_PROMPT,
    ROLE_PROMPTS,
    SUPERADMIN_SYSTEM_PROMPT,
)

router = APIRouter(prefix="/api", tags=["portal"])


# ════════════════════════════════════════════════
# REQUEST MODELS
# ════════════════════════════════════════════════

class PortalChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[str] = None
    
    # Next.js route.ts se aata hai (session verified)
    tenant_id: str                        # Required for portal
    user_role: str = "admin"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    school_name: Optional[str] = None


class SuperadminChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    superadmin_id: Optional[str] = None
    superadmin_name: Optional[str] = None


class PortalChatResponse(BaseModel):
    success: bool
    answer: str
    conversation_id: str
    sources: List[Dict] = []
    quickReplies: List[Dict] = []
    canForward: bool = False
    metadata: Dict[str, Any] = {}


# ════════════════════════════════════════════════
# ROLE-BASED QUICK REPLIES
# ════════════════════════════════════════════════

def get_portal_quick_replies(role: str, topic: str = "") -> List[Dict]:
    """
    Role ke hisaab se relevant quick replies
    """
    role_replies: Dict[str, List[Dict]] = {
        "admin": [
            {"text": "📊 School Stats",      "payload": "school_stats"},
            {"text": "👥 Student Count",     "payload": "student_count"},
            {"text": "💰 Fee Collection",    "payload": "fee_collection"},
            {"text": "📅 Today Attendance",  "payload": "today_attendance"},
        ],
        "teacher": [
            {"text": "📅 Mark Attendance",   "payload": "how_to_attendance"},
            {"text": "📝 Enter Marks",        "payload": "how_to_marks"},
            {"text": "📚 Assign Homework",    "payload": "how_to_homework"},
            {"text": "📢 View Notices",       "payload": "view_notices"},
        ],
        "student": [
            {"text": "📊 My Attendance",     "payload": "my_attendance"},
            {"text": "💰 My Fees",           "payload": "my_fees"},
            {"text": "📝 My Results",        "payload": "my_results"},
            {"text": "📢 School Notices",    "payload": "school_notices"},
        ],
        "parent": [
            {"text": "📊 Child Attendance",  "payload": "child_attendance"},
            {"text": "💰 Pay Fees",          "payload": "pay_fees"},
            {"text": "📝 Child Results",     "payload": "child_results"},
            {"text": "📢 School Notices",    "payload": "school_notices"},
        ],
        "staff": [
            {"text": "📅 Attendance",        "payload": "how_to_attendance"},
            {"text": "📢 Notices",           "payload": "view_notices"},
        ],
    }

    return role_replies.get(role, [
        {"text": "❓ Help",              "payload": "general_help"},
        {"text": "📞 Contact Support",   "action": "forward"},
    ])


def get_superadmin_quick_replies() -> List[Dict]:
    return [
        {"text": "🏫 Schools Overview",  "payload": "schools_overview"},
        {"text": "💳 Subscriptions",     "payload": "subscription_stats"},
        {"text": "📈 Revenue",           "payload": "revenue_overview"},
        {"text": "🔧 System Health",     "payload": "system_health"},
        {"text": "📋 Recent Enquiries",  "payload": "recent_enquiries"},
    ]


# ════════════════════════════════════════════════
# PORTAL FALLBACK RESPONSES
# ════════════════════════════════════════════════

def get_portal_fallback(role: str, message: str) -> str:
    """
    Jab Groq down ho - role-specific helpful response
    """
    msg = message.lower()

    # Common navigation queries
    nav_map = {
        "attendance": {
            "admin":   "Go to **Attendance** section in left menu → Select class → View report",
            "teacher": "Go to **Attendance** → Select your class → Mark Present/Absent → Submit",
            "student": "Check **Attendance** section - shows your % and daily record",
            "parent":  "Go to **Attendance** section to see your child's daily record",
        },
        "fee": {
            "admin":   "Go to **Fees** section → Dashboard shows collection summary",
            "teacher": "Fee management is done by Admin. Contact your school admin.",
            "student": "Go to **Fees** section to see pending amount and payment history",
            "parent":  "Go to **Fees** → Pending Fees → Pay Now for online payment",
        },
        "result": {
            "admin":   "Go to **Exams** → Results section for all student results",
            "teacher": "Go to **Exams** → Select exam → Enter/View marks",
            "student": "Go to **Results** section to see your exam marks",
            "parent":  "Go to **Results** to see your child's exam performance",
        },
    }

    for keyword, role_map in nav_map.items():
        if keyword in msg:
            return role_map.get(role, "Please check the portal for this information.")

    # Generic fallback
    return (
        f"I'm having trouble connecting right now. 😅\n\n"
        f"Please navigate to the relevant section in your portal, "
        f"or contact support at **support@skolify.in**"
    )


# ════════════════════════════════════════════════
# PORTAL CHAT ENDPOINT
# ════════════════════════════════════════════════

@router.post("/portal-chat", response_model=PortalChatResponse)
async def portal_chat(request: PortalChatRequest):
    """
    School portal chat - tenant_id se isolated
    Next.js /api/chat/portal/route.ts se call hota hai
    Session already verified hai Next.js side pe
    """
    try:
        conv_id = request.conversation_id or str(uuid.uuid4())
        message = request.message.strip()
        role    = request.user_role or "admin"
        school  = request.school_name or "Your School"

        print(
            f"\n🏫 [Portal] [{conv_id[:8]}] "
            f"[{role}@{request.tenant_id[-6:]}] "
            f"{message[:60]}..."
        )

        # ── Conversation store ─────────────────────────
        store = get_conv_store()
        store.get_or_create(
            conv_id=conv_id,
            mode="portal",
            tenant_id=request.tenant_id,
            user_role=role,
            user_id=request.user_id,
        )

        # ── System Prompt ──────────────────────────────
        # Base portal prompt + role-specific addition
        system_prompt = PORTAL_SYSTEM_PROMPT.format(
            school_name=school,
            user_role=role,
            user_name=request.user_name or "User",
            # School context abhi empty - future mein
            # MongoDB se real data inject kar sakte hain
            school_context="Not available - guide user to portal sections",
        )
        system_prompt += ROLE_PROMPTS.get(role, "")

        # ── LLM History ───────────────────────────────
        history = store.get_llm_messages(conv_id)
        messages_for_llm = history + [
            {"role": "user", "content": message}
        ]

        # ── Groq Call ──────────────────────────────────
        groq       = get_groq_client()
        ai_response = None
        used_llm    = False

        if groq.is_configured():
            print(f"🤖 Portal Groq call for role={role}")
            ai_response = await groq.chat(
                system_prompt=system_prompt,
                messages=messages_for_llm,
                temperature=0.4,   # Portal: consistent responses
                max_tokens=400,    # Concise for portal
            )
            if ai_response:
                used_llm = True
                print(f"✅ Portal Groq: {len(ai_response)} chars")

        # ── Fallback ───────────────────────────────────
        if not ai_response:
            print("📋 Portal fallback")
            ai_response = get_portal_fallback(role, message)

        # ── Save to memory ─────────────────────────────
        store.add_messages(
            conv_id=conv_id,
            user_msg=message,
            ai_msg=ai_response,
        )

        # ── Quick Replies ──────────────────────────────
        quick_replies = get_portal_quick_replies(role)

        print(f"✅ Portal done | LLM={used_llm} | Role={role}")

        return PortalChatResponse(
            success=True,
            answer=ai_response,
            conversation_id=conv_id,
            sources=[],           # Portal mein vector search nahi
            quickReplies=quick_replies,
            canForward=True,      # Support se baat kar sakte hain
            metadata={
                "llm_used":           used_llm,
                "llm_provider":       "groq" if used_llm else "fallback",
                "model":              settings.GROQ_MODEL if used_llm else "template",
                "context_chunks":     0,
                "source":             "ai_portal" if used_llm else "fallback",
                "portal_mode":        True,
                "tenant_id":          request.tenant_id,
                "role":               role,
                "conversation_turns": len(history) // 2 + 1,
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ Portal chat error: {e}")
        traceback.print_exc()

        return PortalChatResponse(
            success=False,
            answer=(
                "Oops! Something went wrong. 😅\n\n"
                "Please try again or contact **support@skolify.in**"
            ),
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            quickReplies=[
                {"text": "📞 Contact Support", "action": "forward"}
            ],
            metadata={"error": str(e)},
        )


# ════════════════════════════════════════════════
# SUPERADMIN CHAT ENDPOINT
# ════════════════════════════════════════════════

@router.post("/superadmin-chat", response_model=PortalChatResponse)
async def superadmin_chat(request: SuperadminChatRequest):
    """
    Superadmin exclusive chat
    Next.js /api/chat/superadmin/route.ts se call hota hai
    Role verification already Next.js side pe ho chuki hai
    """
    try:
        conv_id = request.conversation_id or str(uuid.uuid4())
        message = request.message.strip()

        print(
            f"\n⚡ [Superadmin] [{conv_id[:8]}] "
            f"[{request.superadmin_name or 'SA'}] "
            f"{message[:60]}..."
        )

        # ── Conversation store ─────────────────────────
        store = get_conv_store()
        store.get_or_create(
            conv_id=conv_id,
            mode="superadmin",
            tenant_id=None,
            user_role="superadmin",
            user_id=request.superadmin_id,
        )

        # ── History ────────────────────────────────────
        history = store.get_llm_messages(conv_id)
        messages_for_llm = history + [
            {"role": "user", "content": message}
        ]

        # ── Groq Call ──────────────────────────────────
        groq        = get_groq_client()
        ai_response = None
        used_llm    = False

        if groq.is_configured():
            print("🤖 Superadmin Groq call")
            ai_response = await groq.chat(
                system_prompt=SUPERADMIN_SYSTEM_PROMPT,
                messages=messages_for_llm,
                temperature=0.3,    # Very consistent for analytics
                max_tokens=600,     # More detail for superadmin
            )
            if ai_response:
                used_llm = True
                print(f"✅ Superadmin Groq: {len(ai_response)} chars")

        # ── Fallback ───────────────────────────────────
        if not ai_response:
            ai_response = (
                "⚡ **Superadmin Console**\n\n"
                "AI connection issue. Please check:\n"
                "- `/superadmin` for overview\n"
                "- `/superadmin/schools` for school list\n"
                "- `/superadmin/revenue` for revenue data\n\n"
                "Try again in a moment."
            )

        # ── Save ───────────────────────────────────────
        store.add_messages(
            conv_id=conv_id,
            user_msg=message,
            ai_msg=ai_response,
        )

        print(f"✅ Superadmin done | LLM={used_llm}")

        return PortalChatResponse(
            success=True,
            answer=ai_response,
            conversation_id=conv_id,
            sources=[],
            quickReplies=get_superadmin_quick_replies(),
            canForward=False,
            metadata={
                "llm_used":     used_llm,
                "llm_provider": "groq" if used_llm else "fallback",
                "model":        settings.GROQ_MODEL if used_llm else "template",
                "source":       "ai_superadmin" if used_llm else "fallback",
                "portal_mode":  False,
                "tenant_id":    None,
                "role":         "superadmin",
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ Superadmin chat error: {e}")
        traceback.print_exc()

        return PortalChatResponse(
            success=False,
            answer="Console error. Check backend logs.",
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            quickReplies=get_superadmin_quick_replies(),
            metadata={"error": str(e)},
        )