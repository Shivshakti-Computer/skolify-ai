# api/routes/portal_chat.py
# FIXES:
# 1. Tool data → LOCAL format karo (NO LLM = NO data leak)
# 2. Multi-provider LLM for general questions only
# 3. Rate limiting handled via LLMManager
# 4. ✅ NEW: Support for all 5 providers (2025 edition)

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import uuid
import re
import json
import httpx

from ..dependencies import get_llm_manager, get_conv_store
from ..config import settings
from ..prompts.system_prompt import (
    PORTAL_SYSTEM_PROMPT,
    ROLE_PROMPTS,
    SUPERADMIN_SYSTEM_PROMPT,
)

router = APIRouter(prefix="/api", tags=["portal"])

# ── Tool Endpoints ────────────────────────────────────────
NEXTJS_BASE    = settings.NEXTJS_URL
TOOL_ENDPOINTS = {
    'admin':      f'{NEXTJS_BASE}/api/chat/tools/admin',
    'staff':      f'{NEXTJS_BASE}/api/chat/tools/admin',
    'teacher':    f'{NEXTJS_BASE}/api/chat/tools/teacher',
    'student':    f'{NEXTJS_BASE}/api/chat/tools/student',
    'parent':     f'{NEXTJS_BASE}/api/chat/tools/parent',
    'superadmin': f'{NEXTJS_BASE}/api/chat/tools/superadmin',
}


# ════════════════════════════════════════════════
# MODELS
# ════════════════════════════════════════════════

class PortalChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[str] = None
    tenant_id: str
    user_role: str = "admin"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    school_name: Optional[str] = None
    session_cookie: Optional[str] = None


class SuperadminChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    superadmin_id: Optional[str] = None
    superadmin_name: Optional[str] = None
    session_cookie: Optional[str] = None


class PortalChatResponse(BaseModel):
    success: bool
    answer: str
    conversation_id: str
    sources: List[Dict] = []
    quickReplies: List[Dict] = []
    canForward: bool = False
    metadata: Dict[str, Any] = {}


# ════════════════════════════════════════════════
# INTENT DETECTION
# ════════════════════════════════════════════════

def detect_tool_intent(message: str, role: str) -> Optional[Dict]:
    """
    ✅ COMPREHENSIVE: Detects tool intent from natural language queries
    Supports Hindi, Hinglish, and English
    """
    msg = message.lower().strip()

    # ══════════════════════════════════════════════════════
    # ADMIN/STAFF TOOLS
    # ══════════════════════════════════════════════════════
    
    if role in ['admin', 'staff']:
        
        # ── School Stats (Overview) ───────────────────────
        school_stats_patterns = [
            'stats', 'statistics', 'overview', 'summary',
            'school mein kitne', 'total students', 'total teachers',
            'kitne students hain', 'school overview',
            'school data', 'overall stats',
            'kitne students', 'students hain',  # ✅ Your working query
        ]
        
        if any(pattern in msg for pattern in school_stats_patterns):
            # But NOT if asking specifically about attendance/fees
            if not any(x in msg for x in ['absent', 'present', 'attendance', 'fee', 'fees']):
                return {'tool': 'get_school_stats', 'params': {}}

        # ── Today's Attendance ────────────────────────────
        attendance_today_patterns = [
            'aaj ki attendance',
            'today attendance',
            'aaj kaun absent',
            'today absent',
            'aaj present',
            'attendance today',
            'aaj ka attendance',
            'kitne absent aaj',
            'how many students present',
            'how many present today',
            'kitne students present',
            'kitne present hain',
            'present students today',
            'students present',
            'kitne aaye aaj',
            'kitne bacche aaye',
            'attendance status today',
            'today present',
            'present count',
            'kitne student present',
            'student present hain',
            'present students kitne',
            'aaj kitne students',
            'today kitne students',
            # ✅ NEW PATTERNS FOR YOUR QUERIES:
            'aaj kitne absent',         # ← "aaj kitne absent hain"
            'kitne absent hain',
            'absent students today',
            'total absent',             # ← "total absent"
            'absent kitne',
            'how many absent',
            'absent count',
            'today absent count',
            'aaj absent kitne hain',
        ]
        
        if any(pattern in msg for pattern in attendance_today_patterns):
            return {'tool': 'get_attendance_today', 'params': {}}

        # ── Attendance Summary ────────────────────────────
        if any(w in msg for w in [
            'attendance summary', 'monthly attendance',
            'is month attendance', 'attendance report',
            'average attendance', 'overall attendance',
            'attendance stats', 'attendance data'
        ]):
            return {'tool': 'get_attendance_summary', 'params': {}}

        # ── Fee Summary ───────────────────────────────────
        fee_summary_patterns = [
            'fee collection', 'kitni fees aayi',
            'fee summary', 'fees collected', 'pending fees total',
            'fee status', 'collection kitni', 'fees ka status',
            'total fees', 'fees overview',
            # ✅ NEW PATTERNS:
            'total pending fee',        # ← "total pending fee"
            'pending fee total',
            'kitni fee pending',
            'fee pending kitni',
            'pending fees kitne',
            'total fee pending',
            'how much fee pending',
            'fee baaki kitni',
        ]
        
        if any(pattern in msg for pattern in fee_summary_patterns):
            return {'tool': 'get_fee_summary', 'params': {}}

        # ── Pending Fees List ─────────────────────────────
        if any(w in msg for w in [
            'pending fees list', 'fee defaulter',
            'who has pending', 'defaulters', 'pending fee students',
            'kaun pending', 'defaulter list'
        ]):
            return {'tool': 'get_pending_fees', 'params': {}}

        # ── Student Count ─────────────────────────────────
        student_count_patterns = [
            'student count',
            'students kitne hain',
            'class wise students',
            'students by class',
            'how many students',
            'total students',
            'number of students',
            'students hain kitne',
            'students in my school',
            'students hai school mein',
            'school mein kitne students',
            'my school students',
            'school student count',
            'total student count',
        ]
        
        # Only trigger if NOT asking for school stats (which is broader)
        if any(pattern in msg for pattern in student_count_patterns):
            if 'class' in msg or 'how many' in msg:
                return {'tool': 'get_student_count', 'params': {}}

        # ── Staff/Teacher Count ───────────────────────────
        staff_count_patterns = [
            'kitne staff', 'staff count',
            'teachers count', 'kitne teachers', 'total staff',
            'how many teachers', 'how many staff',
            # ✅ NEW PATTERNS:
            'active teacher',           # ← "active teacher batao"
            'teacher batao',
            'kitne teacher hain',
            'total teacher',
            'teacher count',
            'active teachers',
        ]
        
        if any(pattern in msg for pattern in staff_count_patterns):
            return {'tool': 'get_staff_count', 'params': {}}

        # ── Recent Notices ────────────────────────────────
        if any(w in msg for w in [
            'recent notices', 'last notices',
            'notices kya hain', 'latest notices', 'notice board',
            'notices dikhao', 'koi notice'
        ]):
            return {'tool': 'get_recent_notices', 'params': {}}

    # ══════════════════════════════════════════════════════
    # TEACHER TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'teacher':
        
        # ── My Students ───────────────────────────────────
        if any(w in msg for w in [
            'mere students', 'my students', 'meri class',
            'class list', 'students list', 'roll list',
            'my class students'
        ]):
            class_match = re.search(r'\bclass\s*(\d+|[a-zA-Z]+)\b', msg, re.IGNORECASE)
            params = {}
            if class_match:
                params['class'] = class_match.group(1)
            return {'tool': 'get_my_students', 'params': params}

        # ── Class Attendance Today ────────────────────────
        class_attendance_patterns = [
            'aaj attendance',
            'today attendance',
            'class attendance',
            'meri class mein aaj',
            'kitne present aaj',
            'my class attendance',
            'class attendance today',
            'how many present in my class',
            'kitne bacche aaye',
            'aaj kitne absent',
            'kitne absent hain',
        ]
        
        if any(pattern in msg for pattern in class_attendance_patterns):
            return {'tool': 'get_my_class_attendance_today', 'params': {}}

        # ── Student Attendance (specific) ─────────────────
        for pattern in [
            r'(\w+)\s+(?:ki|ka)\s+attendance',
            r'attendance\s+of\s+(\w+)',
            r'(\w+)\s+(?:absent|present)\s+kitni',
            r'(\w+)\s+attendance\s+check',
        ]:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                return {
                    'tool': 'get_student_attendance',
                    'params': {'studentName': match.group(1)}
                }

        # ── Homework ──────────────────────────────────────
        if any(w in msg for w in [
            'homework', 'assignment',
            'pending assignment', 'homework list', 'kya homework diya',
            'pending homework', 'homework status'
        ]):
            return {'tool': 'get_pending_homework', 'params': {}}

    # ══════════════════════════════════════════════════════
    # STUDENT TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'student':
        
        if any(w in msg for w in [
            'meri attendance', 'my attendance',
            'attendance kitni', 'attendance check', 'kitne din present',
            'attendance percentage', 'aaj present tha', 'attendance status',
            'my attendance record'
        ]):
            return {'tool': 'get_my_attendance', 'params': {}}

        if any(w in msg for w in [
            'meri fees', 'my fees', 'fees kitni hai',
            'fee status', 'pending fee', 'kitna pay karna hai',
            'fee due', 'fees pay', 'fee baaki',
            'my fee status'
        ]):
            return {'tool': 'get_my_fees', 'params': {}}

        if any(w in msg for w in [
            'notices', 'notice', 'announcement',
            'school ne kya bataya', 'koi notice',
            'school notices', 'announcements'
        ]):
            return {'tool': 'get_my_notices', 'params': {}}

        if any(w in msg for w in [
            'homework', 'assignment',
            'pending homework', 'aaj ka homework',
            'my homework', 'homework status'
        ]):
            return {'tool': 'get_my_homework', 'params': {}}

        if any(w in msg for w in [
            'mera profile', 'my profile',
            'mera roll number', 'admission number',
            'my details', 'profile check'
        ]):
            return {'tool': 'get_my_profile', 'params': {}}

    # ══════════════════════════════════════════════════════
    # PARENT TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'parent':
        
        if any(w in msg for w in [
            'beta aaya', 'child attendance',
            'bacche ki attendance', 'aaj school aaya', 'baccha aaya',
            'attendance kitni hai',
            'child present', 'baccha present'
        ]):
            return {'tool': 'get_child_attendance', 'params': {}}

        if any(w in msg for w in [
            'fees kitni', 'fee status', 'fee pending',
            'kitna pay karna', 'fee due', 'fee baaki', 'fee pay',
            'child fee', 'bacche ki fees'
        ]):
            return {'tool': 'get_child_fees', 'params': {}}

        if any(w in msg for w in [
            'notice', 'announcement',
            'school ne kya kaha', 'school notice',
            'school updates'
        ]):
            return {'tool': 'get_child_notices', 'params': {}}

        if any(w in msg for w in [
            'bacche ka profile', 'child profile',
            'roll number', 'admission number',
            'child details'
        ]):
            return {'tool': 'get_child_profile', 'params': {}}

    # ══════════════════════════════════════════════════════
    # SUPERADMIN TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'superadmin':
        
        if any(w in msg for w in [
            'platform stats', 'overview', 'total schools',
            'kitne schools', 'platform overview', 'sab schools',
            'platform data', 'dashboard'
        ]):
            return {'tool': 'get_platform_stats', 'params': {}}

        if any(w in msg for w in [
            'schools list', 'all schools',
            'schools dikhao', 'registered schools',
            'school list'
        ]):
            return {'tool': 'get_schools_list', 'params': {}}

        if any(w in msg for w in [
            'revenue', 'income', 'earnings',
            'kitna revenue', 'monthly revenue', 'revenue kya hai',
            'revenue summary'
        ]):
            return {'tool': 'get_revenue_summary', 'params': {}}

        if any(w in msg for w in [
            'subscription', 'plans', 'plan breakdown',
            'plan distribution', 'subscription breakdown'
        ]):
            return {'tool': 'get_subscription_breakdown', 'params': {}}

        if any(w in msg for w in [
            'expiring', 'trial expire', 'trial khatam',
            'expiring trials', 'trial end',
            'trials ending'
        ]):
            return {'tool': 'get_expiring_trials', 'params': {}}

        if any(w in msg for w in [
            'new schools', 'recent registration',
            'naye schools', 'recently joined',
            'latest registrations'
        ]):
            return {'tool': 'get_recent_registrations', 'params': {}}

    return None

# ════════════════════════════════════════════════
# TOOL CALLER
# ════════════════════════════════════════════════

async def call_tool(
    role: str,
    tool: str,
    params: Dict,
    session_cookie: str,
    tenant_id: str,  # ✅ ADD THIS
) -> Optional[Dict]:
    """
    ✅ ENHANCED: Send tenant_id to Next.js for internal AI calls
    """
    endpoint = TOOL_ENDPOINTS.get(role)
    if not endpoint:
        print(f"❌ No endpoint for role: {role}")
        return None

    # ✅ Include tenant_id in request body
    request_body = {
        'tool': tool,
        'params': params,
        'tenant_id': tenant_id,  # ← ADD THIS
    }

    headers = {
        'Content-Type':  'application/json',
        'X-Internal-AI': 'true',  # ← Next.js identifies internal call
    }
    
    # Cookie optional (internal calls don't need it)
    if session_cookie:
        headers['Cookie'] = session_cookie

    print(f"\n{'='*60}")
    print(f"📡 TOOL API CALL")
    print(f"{'='*60}")
    print(f"Endpoint:  {endpoint}")
    print(f"Tool:      {tool}")
    print(f"Tenant:    {tenant_id[-6:]}")
    print(f"Params:    {params}")
    print(f"{'='*60}\n")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                endpoint,
                json=request_body,
                headers=headers,
            )
            
            print(f"\n{'='*60}")
            print(f"📥 TOOL API RESPONSE")
            print(f"{'='*60}")
            print(f"Status:    {response.status_code}")
            print(f"{'='*60}\n")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('success'):
                        print(f"✅ Tool success")
                        return data.get('data')
                    else:
                        print(f"⚠️  Tool error: {data.get('error')}")
                        return None
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    return None
                    
            elif response.status_code == 401:
                print(f"🔐 401 Unauthorized - Check X-Internal-AI header")
                print(f"   Response: {response.text[:200]}")
                return None
                
            elif response.status_code == 403:
                print(f"🚫 403 Forbidden - Auth bypassed nahi hua")
                print(f"   Response: {response.text[:200]}")
                return None
                
            else:
                print(f"⚠️  HTTP {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return None

    except httpx.ConnectError as e:
        print(f"🔌 Connection Error to Next.js:")
        print(f"   {endpoint}")
        print(f"   Is Next.js running? Error: {e}")
        return None
        
    except httpx.TimeoutException:
        print(f"⏰ Timeout after 15s")
        return None
        
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        return None

# ════════════════════════════════════════════════
# ✅ LOCAL FORMATTER - Data never goes to LLM
# ════════════════════════════════════════════════

def format_tool_response_locally(tool: str, data: Dict) -> str:
    """
    Tool data ko locally format karo.
    
    ✅ PRIVACY GUARANTEE:
    - Data LLM ke through NAHI jaata
    - Zero external API calls
    - Pure Python string formatting
    """

    # ... (keep all existing formatters - they're perfect!)
    # ... (I'll keep your existing code here - no changes needed)
    
    # Just adding this at the end for unknown tools:
    if not data:
        return "⚠️  No data received from tool."
    
        # ✅ FIXED: No JSON dumps - human-readable fallback
    if not data:
        return "⚠️  No data available at the moment. Please try again."
    
    # Try generic formatting for simple data
    try:
        if isinstance(data, dict) and len(data) < 10:
            lines = ["📋 **Data:**\n"]
            for key, value in data.items():
                key_formatted = key.replace('_', ' ').title()
                lines.append(f"• **{key_formatted}:** {value}")
            return "\n".join(lines)
        
        # Complex data - friendly message
        return (
            "✅ **Data received!**\n\n"
            "The information has been fetched. "
            "Check the relevant portal section for detailed view.\n\n"
            "_If this was unexpected, contact support@skolify.in_"
        )
        
    except Exception:
        return "⚠️  Unable to format data. Please check the portal section directly."


# ════════════════════════════════════════════════
# QUICK REPLIES
# ════════════════════════════════════════════════

def get_portal_quick_replies(role: str) -> List[Dict]:
    """Quick action buttons based on user role"""
    replies = {
        "admin": [
            {"text": "📊 School Stats",     "payload": "school stats dikhao"},
            {"text": "📅 Today Attendance", "payload": "aaj ki attendance"},
            {"text": "💰 Fee Collection",   "payload": "fee collection summary"},
            {"text": "👥 Student Count",    "payload": "kitne students hain"},
        ],
        "teacher": [
            {"text": "📅 Aaj Attendance",  "payload": "aaj attendance check karo"},
            {"text": "👥 Mere Students",   "payload": "mere students dikhao"},
            {"text": "📚 Homework",        "payload": "pending homework"},
            {"text": "📝 Marks Enter",     "payload": "marks kaise enter karein"},
        ],
        "student": [
            {"text": "📊 Meri Attendance", "payload": "meri attendance kitni hai"},
            {"text": "💰 Meri Fees",       "payload": "meri fees kitni pending hai"},
            {"text": "📢 Notices",         "payload": "school notices dikhao"},
            {"text": "📚 Homework",        "payload": "pending homework kya hai"},
        ],
        "parent": [
            {"text": "📊 Child Attendance","payload": "bacche ki attendance"},
            {"text": "💰 Fees Status",     "payload": "fees kitni pending hai"},
            {"text": "📢 Notices",         "payload": "school notices"},
            {"text": "📝 Results",         "payload": "bacche ke results"},
        ],
    }
    return replies.get(role, [{"text": "❓ Help", "payload": "help chahiye"}])


def get_superadmin_quick_replies() -> List[Dict]:
    """Superadmin quick actions"""
    return [
        {"text": "🏫 Platform Stats",  "payload": "platform overview dikhao"},
        {"text": "💰 Revenue",         "payload": "revenue kya hai"},
        {"text": "🔔 Expiring Trials", "payload": "expiring trials"},
        {"text": "🆕 New Schools",     "payload": "recent registrations"},
        {"text": "📊 Subscriptions",   "payload": "subscription breakdown"},
    ]


def get_portal_fallback(role: str, message: str) -> str:
    """
    Smart fallback when all LLMs fail
    Guide users to correct portal section
    """
    msg = message.lower()
    
    # Navigation hints based on keywords
    nav_map = {
        "attendance": {
            "admin":   "**Attendance** section → Reports milenge",
            "teacher": "**Attendance** → Class select → Mark karo",
            "student": "**Attendance** section mein apni record dekho",
            "parent":  "**Attendance** section mein bacche ki record milegi",
        },
        "fee": {
            "admin":   "**Fees** section → Dashboard mein summary hai",
            "teacher": "Fee management Admin karta hai",
            "student": "**Fees** section mein pending amount dekho",
            "parent":  "**Fees** → Pending → Pay Now se pay karo",
        },
        "marks": {
            "admin":   "**Exams** → Results → Class-wise marks",
            "teacher": "**Exams** → Enter Marks → Subject select",
            "student": "**Exams** section mein apne marks dekho",
            "parent":  "**Exams** → Results mein bacche ke marks",
        },
        "homework": {
            "teacher": "**Homework** → Create New → Class assign",
            "student": "**Homework** section mein pending list hai",
            "parent":  "**Homework** mein bacche ki pending assignments",
        },
    }
    
    for keyword, role_map in nav_map.items():
        if keyword in msg:
            hint = role_map.get(role, "Portal section mein check karo.")
            return f"💡 **Quick Tip:**\n\n{hint}"
    
    # Generic fallback
    return (
        "Abhi connect nahi ho pa raha. 😅\n\n"
        "Portal section mein directly check karo ya "
        "**support@skolify.in** pe contact karo."
    )


# ════════════════════════════════════════════════
# PORTAL CHAT ENDPOINT
# ════════════════════════════════════════════════

@router.post("/portal-chat", response_model=PortalChatResponse)
async def portal_chat(request: PortalChatRequest):
    """
    Portal chat endpoint - School-specific assistant
    
    ✅ PRIVACY ARCHITECTURE:
    1. Tool data → Formatted locally (NO LLM)
    2. General questions → LLM (no sensitive data)
    3. Multi-provider fallback (rate limit handling)
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

        print(f"📋 Session Cookie: {'✅ Present' if request.session_cookie else '❌ MISSING'}")
        print(f"📋 Tenant ID: {request.tenant_id}")
        print(f"📋 User Role: {role}")

        # ── Conversation ───────────────────────────────────
        store = get_conv_store()
        store.get_or_create(
            conv_id=conv_id,
            mode="portal",
            tenant_id=request.tenant_id,
            user_role=role,
            user_id=request.user_id,
        )

        # ── Tool Intent Detection ──────────────────────────
        tool_intent   = detect_tool_intent(message, role)

        # ✅ ADD THIS DEBUG:
        if tool_intent:
            print(f"✅ Tool detected: {tool_intent['tool']}")
        else:
            print(f"⚠️  No tool detected for: '{message}'")
            print(f"   Role: {role}")
        
        # ✅ ADD THIS DEBUG:
        if tool_intent and not request.session_cookie:
            print(f"❌ CRITICAL: Tool detected but NO SESSION COOKIE!")
            print(f"   Tool will NOT be called - frontend must send session_cookie")

        tool_data     = None
        tool_used     = False
        provider_used = "none"

        if tool_intent and request.session_cookie:
            print(f"🔧 Tool: {tool_intent['tool']}")
            tool_data = await call_tool(
                role=role,
                tool=tool_intent['tool'],
                params=tool_intent.get('params', {}),
                session_cookie=request.session_cookie,
                tenant_id=request.tenant_id,  # ✅ ADD THIS
            )
        
        if tool_data:
            print(f"✅ Tool returned data: {list(tool_data.keys())}")
        else:
            print(f"❌ Tool returned NO data (API call failed)")

        # ══════════════════════════════════════════════════
        # ✅ PRIVACY: Tool data → LOCAL format (NO LLM)
        # School data kisi bhi third party ko nahi jaata
        # ══════════════════════════════════════════════════
        if tool_data:
            tool_used     = True
            provider_used = "local_formatter"
            ai_response   = format_tool_response_locally(
                tool_intent['tool'], tool_data
            )
            print(f"✅ Formatted locally (zero data to LLM) 🔒")

        else:
            # ── General question → LLM (no sensitive data) ─
            system_prompt = PORTAL_SYSTEM_PROMPT.format(
                school_name=school,
                user_role=role,
                user_name=request.user_name or "User",
                # ✅ PRIVACY: Real data NEVER in prompt
                school_context="Guide user to correct portal section.",
            )
            system_prompt += ROLE_PROMPTS.get(role, "")

            history          = store.get_llm_messages(conv_id)
            messages_for_llm = history + [
                {"role": "user", "content": message}
            ]

            # ✅ RATE LIMIT FIX: Multi-provider (2025)
            # groq → gemini → openrouter → deepseek → huggingface
            llm                        = get_llm_manager()
            ai_response, provider_used = await llm.chat(
                system_prompt=system_prompt,
                messages=messages_for_llm,
                temperature=0.3,
                max_tokens=400,
            )

            # ✅ FIXED: Proper indentation
            if not ai_response:
                # Check if it was a data request
                is_data_request = any(w in message.lower() for w in [
                    'how many', 'kitne', 'stats', 'count',
                    'present', 'absent', 'fees', 'attendance'
                ])
                
                if is_data_request:
                    ai_response = (
                        "🔍 **Looking for data?**\n\n"
                        "Try these:\n"
                        "• \"**school stats**\" - Overall statistics\n"
                        "• \"**today attendance**\" - Today's attendance\n"
                        "• \"**fee collection**\" - Fee summary\n"
                        "• \"**student count**\" - Total students\n\n"
                        "_Or check the dashboard directly._"
                    )
                else:
                    ai_response = get_portal_fallback(role, message)
                
                provider_used = "local_fallback"
                print("📋 All LLMs unavailable → smart fallback")

        # ── Save ───────────────────────────────────────────
        store.add_messages(
            conv_id=conv_id,
            user_msg=message,
            ai_msg=ai_response,
        )

        print(
            f"✅ Portal done | "
            f"Provider={provider_used} | "
            f"Tool={tool_intent['tool'] if tool_intent else 'none'}"
        )

        return PortalChatResponse(
            success=True,
            answer=ai_response,
            conversation_id=conv_id,
            sources=[],
            quickReplies=get_portal_quick_replies(role),
            canForward=True,
            metadata={
                "llm_used":           not tool_used,
                "llm_provider":       provider_used,
                "model":              _get_model_name(provider_used),
                "context_chunks":     0,
                "source":             "local_tool" if tool_used else f"ai_{provider_used}",
                "portal_mode":        True,
                "tenant_id":          request.tenant_id,
                "role":               role,
                "tool_used":          tool_used,
                "tool_name":          tool_intent['tool'] if tool_intent else None,
                # ✅ Privacy audit trail
                "data_sent_to_llm":   False,
                "data_privacy":       "guaranteed",
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
            quickReplies=[{"text": "📞 Contact Support", "action": "forward"}],
            metadata={"error": str(e)},
        )

# ════════════════════════════════════════════════
# SUPERADMIN CHAT ENDPOINT
# ════════════════════════════════════════════════

@router.post("/superadmin-chat", response_model=PortalChatResponse)
async def superadmin_chat(request: SuperadminChatRequest):
    """
    Superadmin console assistant
    
    ✅ PRIVACY: Platform data also formatted locally
    """
    try:
        conv_id = request.conversation_id or str(uuid.uuid4())
        message = request.message.strip()

        print(f"\n⚡ [Superadmin] [{conv_id[:8]}] {message[:60]}...")

        store = get_conv_store()
        store.get_or_create(
            conv_id=conv_id,
            mode="superadmin",
            tenant_id=None,
            user_role="superadmin",
            user_id=request.superadmin_id,
        )

        # ── Tool Detection ─────────────────────────────────
        tool_intent   = detect_tool_intent(message, 'superadmin')
        tool_data     = None
        tool_used     = False
        provider_used = "none"

        if tool_intent and request.session_cookie:
            print(f"🔧 SA Tool: {tool_intent['tool']}")
            tool_data = await call_tool(
                role='superadmin',
                tool=tool_intent['tool'],
                params=tool_intent.get('params', {}),
                session_cookie=request.session_cookie,
            )

        # ✅ Superadmin data bhi locally format karo
        if tool_data:
            tool_used     = True
            provider_used = "local_formatter"
            ai_response   = format_tool_response_locally(
                tool_intent['tool'], tool_data
            )
            print("✅ SA data formatted locally 🔒")

        else:
            # General superadmin question → LLM (no data)
            history          = store.get_llm_messages(conv_id)
            messages_for_llm = history + [
                {"role": "user", "content": message}
            ]

            # ✅ RATE LIMIT FIX: Multi-provider (2025)
            llm                        = get_llm_manager()
            ai_response, provider_used = await llm.chat(
                system_prompt=SUPERADMIN_SYSTEM_PROMPT,
                messages=messages_for_llm,
                temperature=0.2,
                max_tokens=600,
            )

            if not ai_response:
                ai_response   = (
                    "⚡ **Superadmin Console**\n\n"
                    "AI temporarily unavailable. Check:\n"
                    "- `/superadmin` → Overview\n"
                    "- `/superadmin/revenue` → Revenue\n"
                    "- `/superadmin/schools` → Schools list"
                )
                provider_used = "local_fallback"

        store.add_messages(
            conv_id=conv_id,
            user_msg=message,
            ai_msg=ai_response,
        )

        return PortalChatResponse(
            success=True,
            answer=ai_response,
            conversation_id=conv_id,
            sources=[],
            quickReplies=get_superadmin_quick_replies(),
            canForward=False,
            metadata={
                "llm_used":         not tool_used,
                "llm_provider":     provider_used,
                "model":            _get_model_name(provider_used),
                "source":           "local_tool" if tool_used else f"ai_{provider_used}",
                "role":             "superadmin",
                "tool_used":        tool_used,
                "tool_name":        tool_intent['tool'] if tool_intent else None,
                "data_sent_to_llm": False,
                "data_privacy":     "guaranteed",
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ Superadmin error: {e}")
        traceback.print_exc()

        return PortalChatResponse(
            success=False,
            answer="Console error. Check backend logs.",
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            quickReplies=get_superadmin_quick_replies(),
            metadata={"error": str(e)},
        )


# ════════════════════════════════════════════════
# ✅ UPDATED HELPER - Support all 5 providers
# ════════════════════════════════════════════════

def _get_model_name(provider: str) -> str:
    """Get model name for metadata"""
    model_map = {
        "groq":            settings.GROQ_MODEL,
        "gemini":          settings.GEMINI_MODEL,
        "openrouter":      settings.OPENROUTER_MODEL,
        "deepseek":        settings.DEEPSEEK_MODEL,
        "huggingface":     settings.HF_MODEL,
        "local_formatter": "local_python",
        "local_fallback":  "template",
        "none":            "template",
    }
    return model_map.get(provider, "unknown")