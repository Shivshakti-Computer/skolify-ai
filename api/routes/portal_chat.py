# api/routes/portal_chat.py
# UPDATED: 2025-02-01
# ✅ Anti-hallucination system
# ✅ Advanced Hindi/Hinglish support
# ✅ Tool response caching
# ✅ Better model selection
# ✅ Complete formatters for all 20 tools
# ✅ Backward compatible

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import re
import httpx
from datetime import datetime, timedelta
import json

from ..dependencies import get_llm_manager, get_conv_store, get_context_manager, get_suggestions_engine
from ..config import settings
from ..prompts.system_prompt import (
    PORTAL_SYSTEM_PROMPT,
    ROLE_PROMPTS,
    SUPERADMIN_SYSTEM_PROMPT,
)

from ..utils.command_parser import get_command_parser, CommandType
from ..utils.command_executor import get_command_executor
from ..utils.command_formatter import get_command_formatter

from ..utils.response_cache import get_portal_cache, get_tool_cache
from .chat import search_knowledge_base, build_context_str, detect_language

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
# INTENT DETECTION - IMPROVED
# ════════════════════════════════════════════════

def detect_tool_intent(message: str, role: str) -> Optional[Dict]:
    """
    ✅ ENHANCED: Better Hindi/Hinglish support
    ✅ NEW: 50+ more patterns
    ✅ IMPROVED: Smarter disambiguation
    """
    msg = message.lower().strip()

    if role in ['admin', 'staff']:
        
        # ── School Stats ──────────────────────────────────
        school_stats_patterns = [
            'stats', 'statistics', 'overview', 'summary',
            'school mein kitne', 'total students', 'total teachers',
            'kitne students hain', 'school overview',
            'school data', 'overall stats',
            'kitne students', 'students hain',
            'school ki jankari',  # ✅ NEW
            'school info',        # ✅ NEW
            'school details',     # ✅ NEW
            'mera school',        # ✅ NEW
            'my school',          # ✅ NEW
            'school ka data',     # ✅ NEW
        ]
        
        if any(pattern in msg for pattern in school_stats_patterns):
            # ✅ SMART: Don't trigger if asking about specific things
            if not any(x in msg for x in ['absent', 'present', 'attendance', 'fee', 'fees', 'marks', 'result']):
                return {'tool': 'get_school_stats', 'params': {}}

        # ── Absent Students List ──────────────────────────
        absent_students_patterns = [
            'absent kon kon',
            'kaun absent',
            'kon kon absent',
            'absent students list',
            'absent list',
            'who is absent',
            'absent kaun hain',
            'absent students kaun',
            'absent ke naam',
            'absent students names',
            'kon kon absent hai',
            'absent hai kaun',
            'show absent',
            'dikhao absent',
            'absent students dikhao',
            'absent ka list',          # ✅ NEW
            'absent list dikhao',      # ✅ NEW
            'kaun kaun absent',        # ✅ NEW
            'absent students batao',   # ✅ NEW
            'absent wale students',    # ✅ NEW
        ]

        if any(pattern in msg for pattern in absent_students_patterns):
            return {'tool': 'get_attendance_today', 'params': {}}

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
            'aaj kitne absent',
            'kitne absent hain',
            'absent students today',
            'total absent',
            'absent kitne',
            'how many absent',
            'absent count',
            'today absent count',
            'aaj absent kitne hain',
            'aaj ka status',         # ✅ NEW
            'today status',          # ✅ NEW
            'attendance batao',      # ✅ NEW
            'attendance dikhao',     # ✅ NEW
            'aaj ki report',         # ✅ NEW
        ]
        
        if any(pattern in msg for pattern in attendance_today_patterns):
            return {'tool': 'get_attendance_today', 'params': {}}

        # ── Attendance Summary ────────────────────────────
        attendance_summary_patterns = [
            'attendance summary',
            'monthly attendance',
            'is month attendance',
            'attendance report',
            'average attendance',
            'overall attendance',
            'attendance stats',
            'attendance data',
            'attendance ka report',    # ✅ NEW
            'monthly report',          # ✅ NEW
        ]
        
        if any(w in msg for w in attendance_summary_patterns):
            return {'tool': 'get_attendance_summary', 'params': {}}

        # ── Fee Summary ───────────────────────────────────
        fee_summary_patterns = [
            'fee collection',
            'kitni fees aayi',
            'fee summary',
            'fees collected',
            'pending fees total',
            'fee status',
            'collection kitni',
            'fees ka status',
            'total fees',
            'fees overview',
            'total pending fee',
            'pending fee total',
            'kitni fee pending',
            'fee pending kitni',
            'pending fees kitne',
            'total fee pending',
            'how much fee pending',
            'fee baaki kitni',
            'total fee batao',        # ✅ NEW
            'total collected fee',    # ✅ NEW
            'total due amount',       # ✅ NEW
            'collected fee',          # ✅ NEW
            'fee batao',              # ✅ NEW
            'kitni fee hai',          # ✅ NEW
            'fee kitni hai',          # ✅ NEW
            'due amount',             # ✅ NEW
            'pending amount',         # ✅ NEW
            'total collection',       # ✅ NEW
            'collection status',      # ✅ NEW
            'fee ka total',           # ✅ NEW
            'total fee',              # ✅ NEW
            'fees total',             # ✅ NEW
            'collected total',        # ✅ NEW
            'pending total',          # ✅ NEW
            'kitna collect hua',      # ✅ NEW
            'kitna fee collect',      # ✅ NEW
            'collection kitna hua',   # ✅ NEW
            'fee collection kitni',   # ✅ NEW
            'kitna fees aayi',        # ✅ NEW
            'fees kitni aayi',        # ✅ NEW
            'collected amount',       # ✅ NEW
            'pending kitna hai',      # ✅ NEW
            'due kitna hai',          # ✅ NEW
            'fee report',             # ✅ NEW
            'fees ka report',         # ✅ NEW
            'collection report',      # ✅ NEW
        ]
        
        if any(pattern in msg for pattern in fee_summary_patterns):
            return {'tool': 'get_fee_summary', 'params': {}}

        # ── Pending Fees List ─────────────────────────────
        pending_fees_patterns = [
            'pending fees list',
            'fee defaulter',
            'who has pending',
            'defaulters',
            'pending fee students',
            'kaun pending',
            'defaulter list',
            'pending wale students',   # ✅ NEW
            'fee pending kaun',        # ✅ NEW
        ]
        
        if any(w in msg for w in pending_fees_patterns):
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
            'kitne students',         # ✅ NEW
            'students batao',         # ✅ NEW
            'students dikhao',        # ✅ NEW
            'class ka count',         # ✅ NEW
            'students ki sankhya',    # ✅ NEW
            'baccho ki sankhya',      # ✅ NEW
        ]
        
        if any(pattern in msg for pattern in student_count_patterns):
            # ✅ SMART: Only trigger if asking about count/class
            if any(kw in msg for kw in ['class', 'how many', 'count', 'kitne', 'sankhya']):
                return {'tool': 'get_student_count', 'params': {}}

        # ── Staff/Teacher Count ───────────────────────────
        staff_count_patterns = [
            'kitne staff',
            'staff count',
            'teachers count',
            'kitne teachers',
            'total staff',
            'how many teachers',
            'how many staff',
            'active teacher',
            'teacher batao',
            'kitne teacher hain',
            'total teacher',
            'teacher count',
            'active teachers',
            'staff batao',            # ✅ NEW
            'staff dikhao',           # ✅ NEW
            'teachers batao',         # ✅ NEW
            'staff ki sankhya',       # ✅ NEW
            'teacher ki sankhya',     # ✅ NEW
        ]
        
        if any(pattern in msg for pattern in staff_count_patterns):
            return {'tool': 'get_staff_count', 'params': {}}

        # ── Recent Notices ────────────────────────────────
        notices_patterns = [
            'recent notices',
            'last notices',
            'notices kya hain',
            'latest notices',
            'notice board',
            'notices dikhao',
            'koi notice',
            'notice batao',           # ✅ NEW
            'notice hai kya',         # ✅ NEW
            'latest notice',          # ✅ NEW
        ]
        
        if any(w in msg for w in notices_patterns):
            return {'tool': 'get_recent_notices', 'params': {}}

    # ══════════════════════════════════════════════════════
    # TEACHER TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'teacher':
        
        # ── My Students ───────────────────────────────────
        my_students_patterns = [
            'mere students',
            'my students',
            'meri class',
            'class list',
            'students list',
            'roll list',
            'my class students',
            'mere bacche',            # ✅ NEW
            'meri class ke students', # ✅ NEW
        ]
        
        if any(w in msg for w in my_students_patterns):
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
            'meri class ka attendance',  # ✅ NEW
            'class mein kitne aaye',     # ✅ NEW
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
        homework_patterns = [
            'homework',
            'assignment',
            'pending assignment',
            'homework list',
            'kya homework diya',
            'pending homework',
            'homework status',
            'homework batao',         # ✅ NEW
            'assignment batao',       # ✅ NEW
        ]
        
        if any(w in msg for w in homework_patterns):
            return {'tool': 'get_pending_homework', 'params': {}}

    # ══════════════════════════════════════════════════════
    # STUDENT TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'student':
        
        my_attendance_patterns = [
            'meri attendance',
            'my attendance',
            'attendance kitni',
            'attendance check',
            'kitne din present',
            'attendance percentage',
            'aaj present tha',
            'attendance status',
            'my attendance record',
            'meri attendance kitni',  # ✅ NEW
            'attendance batao',       # ✅ NEW
        ]
        
        if any(w in msg for w in my_attendance_patterns):
            return {'tool': 'get_my_attendance', 'params': {}}

        my_fees_patterns = [
            'meri fees',
            'my fees',
            'fees kitni hai',
            'fee status',
            'pending fee',
            'kitna pay karna hai',
            'fee due',
            'fees pay',
            'fee baaki',
            'my fee status',
            'meri fee kitni',         # ✅ NEW
            'fee batao',              # ✅ NEW
        ]
        
        if any(w in msg for w in my_fees_patterns):
            return {'tool': 'get_my_fees', 'params': {}}

        my_notices_patterns = [
            'notices',
            'notice',
            'announcement',
            'school ne kya bataya',
            'koi notice',
            'school notices',
            'announcements',
            'notice batao',           # ✅ NEW
            'notices dikhao',         # ✅ NEW
        ]
        
        if any(w in msg for w in my_notices_patterns):
            return {'tool': 'get_my_notices', 'params': {}}

        my_homework_patterns = [
            'homework',
            'assignment',
            'pending homework',
            'aaj ka homework',
            'my homework',
            'homework status',
            'homework batao',         # ✅ NEW
            'kya homework hai',       # ✅ NEW
        ]
        
        if any(w in msg for w in my_homework_patterns):
            return {'tool': 'get_my_homework', 'params': {}}

        my_profile_patterns = [
            'mera profile',
            'my profile',
            'mera roll number',
            'admission number',
            'my details',
            'profile check',
            'profile batao',          # ✅ NEW
            'meri details',           # ✅ NEW
        ]
        
        if any(w in msg for w in my_profile_patterns):
            return {'tool': 'get_my_profile', 'params': {}}

    # ══════════════════════════════════════════════════════
    # PARENT TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'parent':
        
        child_attendance_patterns = [
            'beta aaya',
            'child attendance',
            'bacche ki attendance',
            'aaj school aaya',
            'baccha aaya',
            'attendance kitni hai',
            'child present',
            'baccha present',
            'baccha aaya kya',        # ✅ NEW
            'beta school gaya',       # ✅ NEW
        ]
        
        if any(w in msg for w in child_attendance_patterns):
            return {'tool': 'get_child_attendance', 'params': {}}

        child_fees_patterns = [
            'fees kitni',
            'fee status',
            'fee pending',
            'kitna pay karna',
            'fee due',
            'fee baaki',
            'fee pay',
            'child fee',
            'bacche ki fees',
            'bacche ki fee kitni',    # ✅ NEW
            'fee batao',              # ✅ NEW
        ]
        
        if any(w in msg for w in child_fees_patterns):
            return {'tool': 'get_child_fees', 'params': {}}

        child_notices_patterns = [
            'notice',
            'announcement',
            'school ne kya kaha',
            'school notice',
            'school updates',
            'notice batao',           # ✅ NEW
            'koi notice hai',         # ✅ NEW
        ]
        
        if any(w in msg for w in child_notices_patterns):
            return {'tool': 'get_child_notices', 'params': {}}

        child_profile_patterns = [
            'bacche ka profile',
            'child profile',
            'roll number',
            'admission number',
            'child details',
            'bacche ki details',      # ✅ NEW
            'profile batao',          # ✅ NEW
        ]
        
        if any(w in msg for w in child_profile_patterns):
            return {'tool': 'get_child_profile', 'params': {}}

    # ══════════════════════════════════════════════════════
    # SUPERADMIN TOOLS
    # ══════════════════════════════════════════════════════
    
    elif role == 'superadmin':
        
        platform_stats_patterns = [
            'platform stats',
            'overview',
            'total schools',
            'kitne schools',
            'platform overview',
            'sab schools',
            'platform data',
            'dashboard',
            'platform batao',         # ✅ NEW
        ]
        
        if any(w in msg for w in platform_stats_patterns):
            return {'tool': 'get_platform_stats', 'params': {}}

        schools_list_patterns = [
            'schools list',
            'all schools',
            'schools dikhao',
            'registered schools',
            'school list',
            'schools batao',          # ✅ NEW
        ]
        
        if any(w in msg for w in schools_list_patterns):
            return {'tool': 'get_schools_list', 'params': {}}

        revenue_patterns = [
            'revenue',
            'income',
            'earnings',
            'kitna revenue',
            'monthly revenue',
            'revenue kya hai',
            'revenue summary',
            'revenue batao',          # ✅ NEW
        ]
        
        if any(w in msg for w in revenue_patterns):
            return {'tool': 'get_revenue_summary', 'params': {}}

        subscription_patterns = [
            'subscription',
            'plans',
            'plan breakdown',
            'plan distribution',
            'subscription breakdown',
            'plans batao',            # ✅ NEW
        ]
        
        if any(w in msg for w in subscription_patterns):
            return {'tool': 'get_subscription_breakdown', 'params': {}}

        expiring_patterns = [
            'expiring',
            'trial expire',
            'trial khatam',
            'expiring trials',
            'trial end',
            'trials ending',
            'expire hone wale',       # ✅ NEW
        ]
        
        if any(w in msg for w in expiring_patterns):
            return {'tool': 'get_expiring_trials', 'params': {}}

        recent_reg_patterns = [
            'new schools',
            'recent registration',
            'naye schools',
            'recently joined',
            'latest registrations',
            'new schools batao',      # ✅ NEW
        ]
        
        if any(w in msg for w in recent_reg_patterns):
            return {'tool': 'get_recent_registrations', 'params': {}}

    return None


# ════════════════════════════════════════════════
# TOOL CALLER - ALREADY FIXED (follow_redirects=True)
# ════════════════════════════════════════════════

async def call_tool(
    role: str,
    tool: str,
    params: Dict,
    session_cookie: str,
    tenant_id: str,
) -> Optional[Dict]:
    """✅ FIXED: follow_redirects=True"""
    endpoint = TOOL_ENDPOINTS.get(role)
    if not endpoint:
        print(f"❌ No endpoint for role: {role}")
        return None

    request_body = {
        'tool':      tool,
        'params':    params,
        'tenant_id': tenant_id,
    }

    headers = {
        'Content-Type':  'application/json',
        'X-Internal-AI': 'true',
    }

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
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,  # ✅ FIX
        ) as client:
            response = await client.post(
                endpoint,
                json=request_body,
                headers=headers,
            )

            print(f"\n{'='*60}")
            print(f"📥 TOOL API RESPONSE")
            print(f"{'='*60}")
            print(f"Status:    {response.status_code}")
            print(f"Final URL: {response.url}")
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
                except Exception as e:
                    print(f"❌ JSON decode error: {e}")
                    print(f"   Response text: {response.text[:200]}")
                    return None

            elif response.status_code == 401:
                print(f"🔐 401 Unauthorized")
                return None

            elif response.status_code == 403:
                print(f"🚫 403 Forbidden")
                return None

            else:
                print(f"⚠️  HTTP {response.status_code}")
                return None

    except httpx.ConnectError as e:
        print(f"🔌 Connection Error: {endpoint}")
        return None

    except httpx.TimeoutException:
        print(f"⏰ Timeout after 15s")
        return None

    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        return None


# ════════════════════════════════════════════════
# ✅ LOCAL FORMATTER - COMPLETE (all 20 tools)
# ════════════════════════════════════════════════

def format_tool_response_locally(tool: str, data: Dict) -> str:
    """
    ✅ PRIVACY: Data LLM ke through NAHI jaata
    ✅ COMPLETE: All 20 tools formatted
    """
    if not data:
        return "⚠️  No data available at the moment. Please try again."

    # ADMIN TOOLS
    if tool == 'get_school_stats':
        total_students = data.get('total_students', 0)
        active_students = data.get('active_students', 0)
        total_teachers = data.get('total_teachers', 0)
        active_teachers = data.get('active_teachers', 0)
        total_staff = data.get('total_staff', 0)
        
        return f"""📊 **School Overview**

👨‍🎓 **Students:**
  • Total: {total_students:,}
  • Active: {active_students:,}

👨‍🏫 **Teachers:**
  • Total: {total_teachers}
  • Active: {active_teachers}

👔 **Other Staff:** {total_staff}

📍 Check dashboard for detailed analytics."""

    if tool == 'get_attendance_today':
        present = data.get('present', 0)
        absent = data.get('absent', 0)
        late = data.get('late', 0)
        percentage = data.get('percentage', 0)
        date_display = data.get('date', 'Today')
        absent_students = data.get('absent_students', [])  # ✅ NEW
        
        response = f"""📅 **Today's Attendance** ({date_display})

✅ **Present:** {present} students
❌ **Absent:** {absent} students
⏰ **Late:** {late} students

📊 **Attendance Rate:** {percentage}%
"""
        
        # ✅ SHOW ABSENT LIST
        if absent_students and len(absent_students) <= 10:
            response += "\n**📋 Absent Students:**\n"
            for student in absent_students:
                name = student.get('name', 'Unknown')
                cls = student.get('class', '')
                response += f"  • {name} ({cls})\n"
        elif absent > 10:
            response += f"\n_View full absent list ({absent} students) in Attendance section_"
        
        if percentage >= 90:
            response += "\n\n✅ **Excellent attendance today!**"
        elif percentage >= 75:
            response += "\n\n👍 **Good attendance.**"
        else:
            response += "\n\n⚠️ **Attendance below 75% - follow up needed.**"
        
        return response

    if tool == 'get_attendance_summary':
        period = data.get('period', 'Last 30 days')
        present = data.get('present', 0)
        absent = data.get('absent', 0)
        late = data.get('late', 0)
        avg = data.get('average_attendance', '0%')
        
        return f"""📊 **Attendance Summary** ({period})

✅ **Present:** {present:,} entries
❌ **Absent:** {absent:,} entries
⏰ **Late:** {late:,} entries

📈 **Average Attendance:** {avg}

_Go to Attendance → Reports for detailed analysis_"""

    if tool == 'get_fee_summary':
        collected = data.get('total_collected', 0)
        pending = data.get('total_pending', 0)
        this_month = data.get('collected_this_month', 0)
        overdue = data.get('overdue_count', 0)
        partial = data.get('partial_count', 0)
        currency = data.get('currency', '₹')
        
        total = collected + pending
        collection_rate = round((collected / total * 100)) if total > 0 else 0
        
        return f"""💰 **Fee Collection Summary**

✅ **Total Collected:** {currency}{collected:,}
⏳ **Total Pending:** {currency}{pending:,}
📅 **This Month:** {currency}{this_month:,}

📊 **Collection Rate:** {collection_rate}%

⚠️ **Overdue Fees:** {overdue} students
📋 **Partial Payments:** {partial} students

_Go to Fees section for detailed reports_"""

    if tool == 'get_pending_fees':
        count = data.get('count', 0)
        fees = data.get('fees', [])
        
        if count == 0:
            return "✅ **Great news!**\n\nNo pending fees at the moment. All students are up to date!"
        
        response = f"💰 **Pending Fees** ({count} students)\n\n"
        
        for fee in fees[:10]:
            student = fee.get('student', 'Unknown')
            cls = fee.get('class', '')
            amount = fee.get('amount', 0)
            due = fee.get('due_date', 'N/A')
            status = fee.get('status', 'pending')
            
            status_icon = '⚠️' if status == 'pending' else '📋'
            response += f"{status_icon} **{student}** ({cls})\n"
            response += f"    ₹{amount:,} | Due: {due}\n\n"
        
        if count > 10:
            response += f"_...and {count - 10} more. View all in Fees → Pending section_"
        
        return response

    if tool == 'get_student_count':
        total = data.get('total_active', 0)
        by_class = data.get('by_class', [])
        
        response = f"👨‍🎓 **Student Count**\n\n"
        
        if by_class:
            response += "**Class-wise Breakdown:**\n"
            for cls in by_class:
                class_name = cls.get('class', 'Unknown')
                count = cls.get('count', 0)
                response += f"  • Class {class_name}: {count} students\n"
        
        response += f"\n**Total Active Students:** {total:,}"
        
        return response

    if tool == 'get_staff_count':
        total = data.get('total', 0)
        by_category = data.get('by_category', [])
        by_dept = data.get('by_department', [])
        
        response = f"👨‍🏫 **Staff Overview**\n\n"
        response += f"**Total Active Staff:** {total}\n\n"
        
        if by_category:
            response += "**By Category:**\n"
            for cat in by_category:
                category = cat.get('category', 'unknown').replace('_', ' ').title()
                count = cat.get('count', 0)
                response += f"  • {category}: {count}\n"
        
        if by_dept:
            response += "\n**Top Departments:**\n"
            for dept in by_dept[:5]:
                dept_name = dept.get('department', 'N/A')
                count = dept.get('count', 0)
                response += f"  • {dept_name}: {count}\n"
        
        return response

    if tool == 'get_recent_notices':
        count = data.get('count', 0)
        notices = data.get('notices', [])
        
        if count == 0:
            return "📢 **No recent notices**\n\nCheck back later for updates!"
        
        response = f"📢 **Recent Notices** ({count})\n\n"
        
        for notice in notices:
            title = notice.get('title', 'Untitled')
            date = notice.get('date', '')
            audience = notice.get('audience', 'All')
            response += f"📌 **{title}**\n"
            response += f"    {date} | {audience}\n\n"
        
        response += "_View all in Notices section_"
        return response

    # TEACHER TOOLS
    if tool == 'get_my_students':
        total = data.get('total', 0)
        cls = data.get('class', 'All')
        section = data.get('section', '')
        students = data.get('students', [])
        
        if total == 0:
            return "👥 **No students found**\n\nCheck your class/section assignment."
        
        class_display = f"{cls} {section}".strip()
        response = f"👥 **My Students** (Class {class_display})\n\n"
        response += f"**Total:** {total} students\n\n"
        
        if students and len(students) <= 20:
            response += "**Student List:**\n"
            for s in students[:20]:
                name = s.get('name', 'Unknown')
                roll = s.get('roll', '-')
                status = s.get('status', 'active')
                status_icon = '✅' if status == 'active' else '⚠️'
                response += f"{status_icon} {name} (Roll: {roll})\n"
        else:
            response += "_View full list in Students section_"
        
        return response

    if tool == 'get_my_class_attendance_today':
        date_display = data.get('date', 'Today')
        cls = data.get('class', 'Your class')
        present = data.get('present', 0)
        absent = data.get('absent', 0)
        late = data.get('late', 0)
        percentage = data.get('percentage', '0%')
        is_marked = data.get('is_marked', False)
        
        if not is_marked:
            return f"""📅 **Attendance - {cls}** ({date_display})

⚠️ **Not marked yet**

Total students: {data.get('total_students', 0)}

_Go to Attendance → Mark Attendance_"""
        
        return f"""📅 **Attendance - {cls}** ({date_display})

✅ Present: {present}
❌ Absent: {absent}
⏰ Late: {late}

📊 **Attendance:** {percentage}"""

    if tool == 'get_student_attendance':
        name = data.get('student_name', 'Student')
        cls = data.get('class', '')
        period = data.get('period', 'Last 30 days')
        present = data.get('present', 0)
        absent = data.get('absent', 0)
        late = data.get('late', 0)
        percentage = data.get('attendance_percentage', '0%')
        status = data.get('status', '')
        
        return f"""📊 **{name}'s Attendance** ({cls})

**Period:** {period}

✅ Present: {present} days
❌ Absent: {absent} days
⏰ Late: {late} days

📈 **Attendance:** {percentage}

**Status:** {status}"""

    if tool == 'get_pending_homework':
        count = data.get('count', 0)
        homework = data.get('homework', [])
        
        if count == 0:
            return "📚 **No pending homework**\n\nAll assignments are up to date!"
        
        response = f"📚 **Pending Homework** ({count} assignments)\n\n"
        
        for hw in homework:
            title = hw.get('title', 'Untitled')
            cls = hw.get('class', '')
            subject = hw.get('subject', '')
            due = hw.get('due', 'N/A')
            
            response += f"📝 **{title}**\n"
            response += f"    {subject} | {cls} | Due: {due}\n\n"
        
        return response

    # STUDENT TOOLS
    if tool == 'get_my_attendance':
        period = data.get('period', 'Last 30 days')
        present = data.get('present', 0)
        absent = data.get('absent', 0)
        late = data.get('late', 0)
        percentage = data.get('attendance_percentage', '0%')
        today_status = data.get('today_status', 'Not marked')
        remark = data.get('remark', '')
        
        return f"""📊 **My Attendance** ({period})

✅ Present: {present} days
❌ Absent: {absent} days
⏰ Late: {late} days

📈 **Attendance:** {percentage}

**Today:** {today_status}

{remark}"""

    if tool == 'get_my_fees':
        pending_count = data.get('pending_count', 0)
        total_pending = data.get('total_pending', '₹0')
        pending_fees = data.get('pending_fees', [])
        recent_paid = data.get('recent_paid', [])
        
        response = f"💰 **My Fees**\n\n"
        
        if pending_count > 0:
            response += f"⚠️ **Pending:** {total_pending}\n\n"
            response += "**Due Fees:**\n"
            for fee in pending_fees:
                amount = fee.get('amount', '₹0')
                due = fee.get('due_date', 'N/A')
                status = fee.get('status', 'pending')
                response += f"  • {amount} (Due: {due}) [{status}]\n"
        else:
            response += "✅ **All fees paid!**\n\n"
        
        if recent_paid:
            response += "\n**Recent Payments:**\n"
            for payment in recent_paid[:3]:
                amount = payment.get('amount', '₹0')
                paid = payment.get('paid_on', 'N/A')
                response += f"  • {amount} (Paid: {paid})\n"
        
        return response

    if tool == 'get_my_notices':
        count = data.get('count', 0)
        notices = data.get('notices', [])
        
        if count == 0:
            return "📢 **No new notices**\n\nCheck back later!"
        
        response = f"📢 **My Notices** ({count})\n\n"
        
        for notice in notices:
            title = notice.get('title', 'Untitled')
            preview = notice.get('preview', '')
            date = notice.get('date', '')
            
            response += f"📌 **{title}**\n"
            if preview:
                response += f"    {preview}\n"
            response += f"    {date}\n\n"
        
        return response

    if tool == 'get_my_homework':
        cls = data.get('class', 'Your class')
        pending_count = data.get('pending_count', 0)
        homework = data.get('homework', [])
        
        if pending_count == 0:
            return f"📚 **My Homework** ({cls})\n\n✅ No pending assignments!"
        
        response = f"📚 **My Homework** ({cls})\n\n"
        response += f"**Pending:** {pending_count} assignments\n\n"
        
        for hw in homework:
            title = hw.get('title', 'Untitled')
            subject = hw.get('subject', '')
            due = hw.get('due', 'N/A')
            
            response += f"📝 **{title}**\n"
            response += f"    {subject} | Due: {due}\n\n"
        
        return response

    if tool == 'get_my_profile':
        cls = data.get('class', 'N/A')
        roll = data.get('roll_number', 'N/A')
        admission = data.get('admission_number', 'N/A')
        academic_year = data.get('academic_year', 'N/A')
        status = data.get('status', 'active')
        
        return f"""👤 **My Profile**

**Class:** {cls}
**Roll Number:** {roll}
**Admission Number:** {admission}
**Academic Year:** {academic_year}
**Status:** {status}

_Contact admin to update details_"""

    # PARENT TOOLS
    if tool == 'get_child_attendance':
        child_name = data.get('child_name', 'Your child')
        cls = data.get('class', '')
        today = data.get('today', 'Not marked')
        period = data.get('period', 'Last 30 days')
        present = data.get('present', 0)
        absent = data.get('absent', 0)
        late = data.get('late', 0)
        percentage = data.get('percentage', '0%')
        message = data.get('message', '')
        
        return f"""📊 **{child_name}'s Attendance** ({cls})

**Today:** {today}

**{period}:**
✅ Present: {present} days
❌ Absent: {absent} days
⏰ Late: {late} days

📈 **Attendance:** {percentage}

{message}"""

    if tool == 'get_child_fees':
        child_name = data.get('child_name', 'Your child')
        pending_amount = data.get('pending_amount', '₹0')
        pending_count = data.get('pending_count', 0)
        pending_fees = data.get('pending_fees', [])
        recent_payments = data.get('recent_payments', [])
        action = data.get('action', '')
        
        response = f"💰 **{child_name}'s Fees**\n\n"
        
        if pending_count > 0:
            response += f"⚠️ **Pending:** {pending_amount}\n\n"
            response += "**Due Payments:**\n"
            for fee in pending_fees:
                amount = fee.get('amount', '₹0')
                due = fee.get('due', 'N/A')
                status = fee.get('status', 'pending')
                response += f"  • {amount} (Due: {due}) [{status}]\n"
            response += f"\n{action}"
        else:
            response += "✅ All fees paid!\n\n"
        
        if recent_payments:
            response += "\n**Recent Payments:**\n"
            for payment in recent_payments:
                amount = payment.get('amount', '₹0')
                paid = payment.get('paid', 'N/A')
                response += f"  • {amount} (Paid: {paid})\n"
        
        return response

    if tool == 'get_child_notices':
        count = data.get('count', 0)
        notices = data.get('notices', [])
        
        if count == 0:
            return "📢 **No new notices**\n\nCheck back later for updates!"
        
        response = f"📢 **School Notices** ({count})\n\n"
        
        for notice in notices:
            title = notice.get('title', 'Untitled')
            preview = notice.get('preview', '')
            date = notice.get('date', '')
            
            response += f"📌 **{title}**\n"
            if preview:
                response += f"    {preview}\n"
            response += f"    {date}\n\n"
        
        return response

    if tool == 'get_child_profile':
        name = data.get('name', 'Student')
        cls = data.get('class', 'N/A')
        roll = data.get('roll_number', 'N/A')
        admission = data.get('admission_number', 'N/A')
        academic_year = data.get('academic_year', 'N/A')
        
        return f"""👤 **Child Profile**

**Name:** {name}
**Class:** {cls}
**Roll Number:** {roll}
**Admission Number:** {admission}
**Academic Year:** {academic_year}

_Contact school for any updates_"""

    # SUPERADMIN TOOLS
    if tool == 'get_platform_stats':
        total_schools = data.get('total_schools', 0)
        active_schools = data.get('active_schools', 0)
        trial_schools = data.get('trial_schools', 0)
        expired_schools = data.get('expired_schools', 0)
        total_users = data.get('total_users', 0)
        health = data.get('health', '🟢 Good')
        
        return f"""📊 **Platform Overview**

🏫 **Schools:**
  • Total: {total_schools}
  • Active: {active_schools}
  • Trial: {trial_schools}
  • Expired: {expired_schools}

👥 **Total Users:** {total_users:,}

**Platform Health:** {health}"""

    if tool == 'get_schools_list':
        total = data.get('total', 0)
        schools = data.get('schools', [])
        
        response = f"🏫 **Schools List** (Latest {total})\n\n"
        
        for school in schools:
            name = school.get('name', 'Unknown')
            status = school.get('status', 'unknown')
            plan = school.get('plan', 'starter')
            city = school.get('city', 'N/A')
            joined = school.get('joined', '')
            
            status_icon = '✅' if status == 'active' else '⚠️' if status == 'trial' else '❌'
            response += f"{status_icon} **{name}**\n"
            response += f"    {plan.title()} | {city} | Joined: {joined}\n\n"
        
        return response

    if tool == 'get_revenue_summary':
        this_month = data.get('this_month', '₹0')
        last_month = data.get('last_month', '₹0')
        growth = data.get('growth', '0%')
        active_subs = data.get('active_subscriptions', 0)
        trend = data.get('trend', '➡️ Stable')
        
        return f"""💰 **Revenue Summary**

**This Month:** {this_month}
**Last Month:** {last_month}
**Growth:** {growth}

**Active Subscriptions:** {active_subs}

**Trend:** {trend}"""

    if tool == 'get_subscription_breakdown':
        breakdown = data.get('breakdown', [])
        
        response = "📊 **Subscription Breakdown**\n\n"
        
        for item in breakdown:
            plan = item.get('plan', 'unknown').title()
            status = item.get('status', 'unknown')
            count = item.get('count', 0)
            
            response += f"  • {plan} ({status}): {count} schools\n"
        
        return response

    if tool == 'get_expiring_trials':
        count = data.get('count', 0)
        schools = data.get('schools', [])
        
        if count == 0:
            return "✅ **No trials expiring soon**\n\nAll good for next 7 days!"
        
        response = f"⏰ **Expiring Trials** ({count} schools)\n\n"
        
        for school in schools:
            name = school.get('name', 'Unknown')
            expires = school.get('expires', 'N/A')
            days_left = school.get('days_left', 0)
            
            urgency = '🔴' if days_left <= 2 else '🟡' if days_left <= 5 else '🟢'
            response += f"{urgency} **{name}**\n"
            response += f"    Expires: {expires} ({days_left} days left)\n\n"
        
        return response

    if tool == 'get_recent_registrations':
        count = data.get('count', 0)
        schools = data.get('schools', [])
        
        response = f"🆕 **Recent Registrations** ({count})\n\n"
        
        for school in schools:
            name = school.get('name', 'Unknown')
            plan = school.get('plan', 'starter')
            city = school.get('city', 'N/A')
            joined = school.get('joined', '')
            
            response += f"🏫 **{name}**\n"
            response += f"    {plan.title()} | {city} | {joined}\n\n"
        
        return response

    # FALLBACK
    try:
        if isinstance(data, dict) and len(data) < 10:
            lines = ["📋 **Data:**\n"]
            for key, value in data.items():
                key_formatted = key.replace('_', ' ').title()
                lines.append(f"• **{key_formatted}:** {value}")
            return "\n".join(lines)
        
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
    """Smart fallback when all LLMs fail"""
    msg = message.lower()
    
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
    
    return (
        "Abhi connect nahi ho pa raha. 😅\n\n"
        "Portal section mein directly check karo ya "
        "**support@skolify.in** pe contact karo."
    )


async def _generate_message_template(params: Dict, llm_manager) -> str:
    """Generate message template using AI"""
    msg_type = params.get('message_type', 'general')
    channel  = params.get('channel', 'sms').upper()
    topic    = params.get('topic', '')

    template_prompt = f"""You are a school communication expert.
Generate a professional {channel} template for Indian schools.
Type: {msg_type}
Topic: {topic}

Rules:
- Keep SMS under 160 characters
- WhatsApp can be longer (300-400 chars)
- Email should be formal
- End with school name placeholder: -[School Name]
- Include: Student Name, relevant details
- Use placeholders like [Student Name], [Date], [Amount]
- Be respectful and professional
- Include Hindi/English mix if appropriate

Return ONLY the message template, nothing else."""

    response, provider = await llm_manager.chat(
        system_prompt=template_prompt,
        messages=[
            {"role": "user", "content": f"Generate {msg_type} {channel} template for: {topic}"}
        ],
        temperature=0.7,
        max_tokens=300,
    )

    if response:
        return f"""✨ **{channel} Template Generated:**

---
{response}
---

**How to use:**
• Replace `[Student Name]` with actual name
• Replace `[Date]` with actual date
• Replace `[Amount]` with fee amount

**Send this?**
Type **"send this to all parents"** or **"send to class 10"**
Or **"modify"** to change the template."""

    fallback = _get_fallback_template(msg_type, channel)
    return f"""✨ **{channel} Template:**

---
{fallback}
---

Type **"send this"** to send or **"modify"** to change."""


def _get_fallback_template(msg_type: str, channel: str) -> str:
    """Fallback templates when LLM unavailable"""
    templates = {
        'holiday': (
            "Dear Parent, School will remain CLOSED on [Date] "
            "due to [Reason]. Classes will resume on [Next Date]. "
            "-[School Name]"
        ),
        'exam': (
            "Dear Parent, [Exam Name] will be held on [Date] "
            "from [Time]. Please ensure [Student Name] brings "
            "admit card and stationery. -[School Name]"
        ),
        'fee_reminder': (
            "Dear Parent, fee of Rs.[Amount] for [Student Name] "
            "is due on [Date]. Please pay to avoid late fine. "
            "Pay online at portal. -[School Name]"
        ),
        'event': (
            "Dear Parent, [Event Name] will be held on [Date] "
            "at [Time]. Your presence is requested. "
            "-[School Name]"
        ),
        'result': (
            "Dear Parent, [Student Name]'s [Exam Name] result "
            "is available. Please login to portal to view marks "
            "and grade card. -[School Name]"
        ),
        'general': (
            "Dear Parent, [Message]. Please contact school "
            "for more details. -[School Name]"
        ),
    }
    return templates.get(msg_type, templates['general'])


# ══════════════════════════════════════════════════════════
# ✅ PORTAL CHAT ENDPOINT - ENHANCED
# ══════════════════════════════════════════════════════════

@router.post("/portal-chat", response_model=PortalChatResponse)
async def portal_chat(request: PortalChatRequest):
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

        store = get_conv_store()
        store.get_or_create(
            conv_id=conv_id,
            mode="portal",
            tenant_id=request.tenant_id,
            user_role=role,
            user_id=request.user_id,
        )

        context_mgr = get_context_manager()

        # ✅ CONTEXT RESOLUTION
        resolved_message, was_resolved = context_mgr.resolve_message(
            message,
            conv_id,
            role
        )

        if was_resolved:
            print(f"💡 Context resolved: {message} → {resolved_message}")
            message = resolved_message

        msg_lower = message.lower().strip()

        # ══════════════════════════════════════════════════
        # ADMIN COMMAND DETECTION
        # ══════════════════════════════════════════════════

        if role in ['admin', 'staff']:
            cmd_parser    = get_command_parser()
            cmd_executor  = get_command_executor()
            cmd_formatter = get_command_formatter()

            ctx = context_mgr.get_context(conv_id)

            pending_cmd = None
            if ctx:
                topic = ctx.get('topic', '')
                data  = ctx.get('data', {})

                if topic == 'pending_command' and isinstance(data, dict):
                    pending_cmd = data.get('pending_command')

                if not pending_cmd and isinstance(data, dict):
                    if 'command_type' in data:
                        pending_cmd = data

            CONFIRM_WORDS = [
                'confirm', 'yes', 'haan', 'ok', 'okay',
                'bilkul', 'ha', 'proceed', 'karo', 'han',
                'haa', 'theek hai', 'theek', 'sahi hai',
                'kar do', 'kardo', 'done', 'go ahead',
            ]

            CANCEL_WORDS = [
                'cancel', 'nahi', 'no', 'mat karo',
                'band karo', 'ruko', 'stop', 'nai',
                'nahi chahiye', 'rehne do', 'chodo',
            ]

            is_confirm = pending_cmd and any(
                w in msg_lower for w in CONFIRM_WORDS
            )
            is_cancel = pending_cmd and any(
                w in msg_lower for w in CANCEL_WORDS
            )

            if is_confirm:
                print(f"✅ Executing confirmed: {pending_cmd['command_type']}")

                from ..utils.command_parser import ParsedCommand
                cmd = ParsedCommand(
                    command_type=pending_cmd['command_type'],
                    params=pending_cmd['params'],
                    raw_message=pending_cmd['raw_message'],
                )

                result = await cmd_executor.execute(
                    command=cmd,
                    tenant_id=request.tenant_id,
                    session_cookie=request.session_cookie or '',
                )

                ai_response = cmd_formatter.format_result(
                    command_type=pending_cmd['command_type'],
                    result=result,
                    params=pending_cmd['params'],
                )

                context_mgr.clear_context(conv_id)

                store.add_messages(
                    conv_id=conv_id,
                    user_msg=request.message,
                    ai_msg=ai_response,
                )

                return PortalChatResponse(
                    success=True,
                    answer=ai_response,
                    conversation_id=conv_id,
                    sources=[],
                    quickReplies=get_portal_quick_replies(role),
                    canForward=True,
                    metadata={
                        'command_executed': pending_cmd['command_type'],
                        'portal_mode':      True,
                        'data_sent_to_llm': False,
                    },
                )

            elif is_cancel:
                print(f"❌ Command cancelled by user")

                context_mgr.clear_context(conv_id)

                ai_response = (
                    "❌ **Command cancelled.**\n\n"
                    "Koi aur kaam kar sakta hoon? 😊"
                )

                store.add_messages(
                    conv_id=conv_id,
                    user_msg=request.message,
                    ai_msg=ai_response,
                )

                return PortalChatResponse(
                    success=True,
                    answer=ai_response,
                    conversation_id=conv_id,
                    sources=[],
                    quickReplies=get_portal_quick_replies(role),
                    canForward=True,
                    metadata={
                        'command_cancelled': True,
                        'data_sent_to_llm':  False,
                    },
                )

            elif not pending_cmd and request.session_cookie:
                parsed_cmd = cmd_parser.parse(message, role)

                if parsed_cmd:
                    print(f"🎯 Admin command: {parsed_cmd.command_type}")

                    if parsed_cmd.command_type == CommandType.GENERATE_MESSAGE:
                        ai_response = await _generate_message_template(
                            params=parsed_cmd.params,
                            llm_manager=get_llm_manager(),
                        )

                        store.add_messages(
                            conv_id=conv_id,
                            user_msg=request.message,
                            ai_msg=ai_response,
                        )

                        return PortalChatResponse(
                            success=True,
                            answer=ai_response,
                            conversation_id=conv_id,
                            sources=[],
                            quickReplies=[
                                {'text': '📨 Send this SMS', 'payload': 'send this message'},
                                {'text': '✏️ Edit message',  'payload': 'modify the message'},
                                {'text': '❌ Cancel',         'payload': 'cancel'},
                            ],
                            canForward=True,
                            metadata={
                                'command_type':     'generate_message',
                                'data_sent_to_llm': False,
                            },
                        )

                    preview_data = await cmd_executor.preview(
                        command=parsed_cmd,
                        tenant_id=request.tenant_id,
                        session_cookie=request.session_cookie,
                    )

                    if preview_data.get('needs_content') or preview_data.get('needs_title'):
                        ai_response = cmd_formatter.format_preview(
                            command_type=parsed_cmd.command_type,
                            preview_data=preview_data,
                            params=parsed_cmd.params,
                        )

                        context_mgr.set_context(
                            conv_id=conv_id,
                            topic='pending_command',
                            data={
                                'pending_command': {
                                    'command_type':  parsed_cmd.command_type,
                                    'params':        parsed_cmd.params,
                                    'raw_message':   parsed_cmd.raw_message,
                                    'needs_content': True,
                                }
                            }
                        )

                    elif preview_data.get('ready_to_execute', True):
                        ai_response = cmd_formatter.format_preview(
                            command_type=parsed_cmd.command_type,
                            preview_data=preview_data,
                            params=parsed_cmd.params,
                        )

                        context_mgr.set_context(
                            conv_id=conv_id,
                            topic='pending_command',
                            data={
                                'pending_command': {
                                    'command_type': parsed_cmd.command_type,
                                    'params':       {**parsed_cmd.params, **preview_data},
                                    'raw_message':  parsed_cmd.raw_message,
                                }
                            }
                        )

                    else:
                        students_count = preview_data.get('students_count', 0)
                        error_msg      = preview_data.get('error', '')

                        if students_count == 0:
                            from_class = parsed_cmd.params.get('from_class', '?')
                            
                            ai_response = (
                                f"⚠️ **No students found in Class {from_class}**\n\n"
                                f"Current academic year mein Class {from_class} mein "
                                f"koi active student nahi hai.\n\n"
                                f"**Possible reasons:**\n"
                                f"• Students already promoted\n"
                                f"• Students in different academic year\n"
                                f"• Class {from_class} mein koi enrolled nahi\n\n"
                                f"📍 Check **Students → Class {from_class}** section."
                            )
                        elif error_msg:
                            ai_response = (
                                f"⚠️ **Preview failed**\n\n"
                                f"Error: {error_msg}\n\n"
                                f"Please try again."
                            )
                        else:
                            ai_response = (
                                "⚠️ **Command cannot be executed.**\n\n"
                                "Please check the details and try again."
                            )

                    store.add_messages(
                        conv_id=conv_id,
                        user_msg=request.message,
                        ai_msg=ai_response,
                    )

                    return PortalChatResponse(
                        success=True,
                        answer=ai_response,
                        conversation_id=conv_id,
                        sources=[],
                        quickReplies=[
                            {'text': '✅ Confirm', 'payload': 'confirm'},
                            {'text': '❌ Cancel',  'payload': 'cancel'},
                        ],
                        canForward=True,
                        metadata={
                            'command_type':          parsed_cmd.command_type,
                            'portal_mode':           True,
                            'data_sent_to_llm':      False,
                            'awaiting_confirmation': True,
                        },
                    )

            elif pending_cmd:
                print(f"⚠️ Pending command exists, waiting for confirm/cancel")
                cmd_type = pending_cmd.get('command_type', 'command')

                ai_response = (
                    f"⏳ **Waiting for confirmation**\n\n"
                    f"Ek command pending hai: `{cmd_type}`\n\n"
                    f"Type **\"confirm\"** to proceed or **\"cancel\"** to abort."
                )

                store.add_messages(
                    conv_id=conv_id,
                    user_msg=request.message,
                    ai_msg=ai_response,
                )

                return PortalChatResponse(
                    success=True,
                    answer=ai_response,
                    conversation_id=conv_id,
                    sources=[],
                    quickReplies=[
                        {'text': '✅ Confirm', 'payload': 'confirm'},
                        {'text': '❌ Cancel',  'payload': 'cancel'},
                    ],
                    canForward=True,
                    metadata={
                        'awaiting_confirmation': True,
                        'data_sent_to_llm':      False,
                    },
                )

        # ── Tool Intent Detection ──────────────────────────
        tool_intent   = detect_tool_intent(message, role)
        tool_data     = None
        tool_used     = False
        provider_used = "none"

        if tool_intent and request.session_cookie:
            print(f"🔧 Tool: {tool_intent['tool']}")
            
            # ✅ CHECK TOOL CACHE FIRST
            tool_cache = get_tool_cache()
            cache_key = f"{tool_intent['tool']}:{request.tenant_id}"
            
            cached_tool_data = tool_cache.get(
                query=cache_key,
                context="",
                role=role,
                mode="tool"
            )
            
            if cached_tool_data:
                print(f"💾 Tool cache HIT: {tool_intent['tool']}")
                tool_data = json.loads(cached_tool_data)
            else:
                tool_data = await call_tool(
                    role=role,
                    tool=tool_intent['tool'],
                    params=tool_intent.get('params', {}),
                    session_cookie=request.session_cookie,
                    tenant_id=request.tenant_id,
                )
                
                # ✅ CACHE TOOL RESPONSE
                if tool_data:
                    tool_cache.set(
                        query=cache_key,
                        response=json.dumps(tool_data),
                        context="",
                        role=role,
                        mode="tool"
                    )

        if tool_data:
            tool_used     = True
            provider_used = "local_formatter"
            ai_response   = format_tool_response_locally(
                tool_intent['tool'], tool_data
            )
            print(f"✅ Formatted locally (zero data to LLM) 🔒")

            CONTEXT_WORTHY_TOOLS = {
                'get_fee_summary',
                'get_attendance_today',
                'get_student_count',
                'get_school_stats',
                'get_pending_fees',
            }

            if tool_intent['tool'] in CONTEXT_WORTHY_TOOLS:
                entities = context_mgr.extract_entities(message, tool_data)
                context_mgr.set_context(
                    conv_id=conv_id,
                    topic=tool_intent['tool'],
                    data=tool_data,
                    entities=entities
                )
                print(f"📝 Context saved for follow-ups: {tool_intent['tool']}")
            else:
                context_mgr.clear_context(conv_id)
                print(f"🗑️  Context cleared (not context-worthy tool)")

        else:
            # ════════════════════════════════════════════════
            # ✅ PUBLIC KB SEARCH - Portal users ko bhi
            # pricing/features data milna chahiye
            # ════════════════════════════════════════════════
            
            # Public knowledge base search karo
            # Tool nahi mila matlab general question hai
            # (pricing, features, trial, etc.)
            public_chunks = search_knowledge_base(message, n=4)
            public_context_str = build_context_str(public_chunks)
            
            if public_chunks:
                print(f"📚 Public KB: {len(public_chunks)} chunks found for portal user")
            else:
                print(f"📚 Public KB: No chunks found")

            # ── System Prompt ──────────────────────────────
            system_prompt = PORTAL_SYSTEM_PROMPT.format(
                school_name=school,
                user_role=role,
                user_name=request.user_name or "User",
                school_context="Guide user to correct portal section.",
            )
            system_prompt += ROLE_PROMPTS.get(role, "")

            # ── Message with public context ────────────────
            if public_context_str:
                # ✅ Language detect karo
                language = detect_language(message)
                
                if language == 'english':
                    lang_hint = "\n⚠️ RESPOND IN ENGLISH ONLY."
                elif language == 'hindi':
                    lang_hint = "\n⚠️ RESPOND IN HINDI/HINGLISH."
                else:
                    lang_hint = "\n⚠️ RESPOND IN HINGLISH."

                # ✅ Public KB data LLM ko do
                # School data NAHI - sirf Skolify product info
                augmented_message = (
                    f"{message}{lang_hint}\n\n"
                    f"[Skolify product information - use this to answer:\n"
                    f"{public_context_str}]"
                )
                print(f"📚 Augmented with public KB context")
            else:
                augmented_message = message

            # ── LLM History ────────────────────────────────
            history          = store.get_llm_messages(conv_id)
            messages_for_llm = history + [
                {"role": "user", "content": augmented_message}
            ]

            llm = get_llm_manager()
            
            ai_response, provider_used = await llm.chat(
                system_prompt=system_prompt,
                messages=messages_for_llm,
                temperature=0.3,
                max_tokens=400,
                use_case="portal",
            )

            if not ai_response:
                ai_response   = get_portal_fallback(role, message)
                provider_used = "local_fallback"
                print("📋 All LLMs unavailable → smart fallback")
            else:
                # ✅ ANTI-HALLUCINATION CHECK
                data_request_keywords = [
                    'list', 'dikhao', 'show', 'batao', 'names',
                    'kaun kaun', 'kon kon', 'who all', 'kitne',
                    'absent', 'present', 'students', 'fees'
                ]
                
                is_data_request = any(kw in msg_lower for kw in data_request_keywords)
                
                fake_data_patterns = [
                    r'\d+\.\s+[A-Z][a-z]+',
                    r'\d+\s+[A-Z][a-z]+\s+\(Class',
                    r'Here.*list.*students:',
                    r'Student List:',
                ]
                
                has_fake_data = any(
                    re.search(pattern, ai_response) 
                    for pattern in fake_data_patterns
                )
                
                if is_data_request and not tool_used and has_fake_data:
                    print("⚠️ HALLUCINATION DETECTED! Blocking fake data.")
                    
                    ai_response = (
                        "I don't have that real-time data. 🤔\n\n"
                        "**Try these for actual data:**\n"
                        "• `aaj ki attendance` → Today's attendance\n"
                        "• `school stats dikhao` → School overview\n"
                        "• `fee collection` → Fee summary\n\n"
                        "Or check the portal section directly! 📍"
                    )
                    provider_used = "hallucination_blocker"

        store.add_messages(
            conv_id=conv_id,
            user_msg=request.message,
            ai_msg=ai_response,
        )

        smart_suggestions = []
        if tool_used and tool_intent:
            suggestions_engine = get_suggestions_engine()
            smart_suggestions  = suggestions_engine.get_suggestions(
                tool=tool_intent['tool'],
                data=tool_data,
                role=role,
                max_suggestions=4,
            )

        final_quick_replies = smart_suggestions if smart_suggestions else get_portal_quick_replies(role)

        return PortalChatResponse(
            success=True,
            answer=ai_response,
            conversation_id=conv_id,
            sources=[],
            quickReplies=final_quick_replies,
            canForward=True,
            metadata={
                "llm_used":              not tool_used,
                "llm_provider":          provider_used,
                "model":                 _get_model_name(provider_used),
                "source":                "local_tool" if tool_used else f"ai_{provider_used}",
                "portal_mode":           True,
                "tenant_id":             request.tenant_id,
                "role":                  role,
                "tool_used":             tool_used,
                "tool_name":             tool_intent['tool'] if tool_intent else None,
                "data_sent_to_llm":      False,
                "data_privacy":          "guaranteed",
                "has_smart_suggestions": len(smart_suggestions) > 0,
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
    """Superadmin console assistant"""
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
                tenant_id='',
            )

        if tool_data:
            tool_used     = True
            provider_used = "local_formatter"
            ai_response   = format_tool_response_locally(
                tool_intent['tool'], tool_data
            )
            print("✅ SA data formatted locally 🔒")

        else:
            history          = store.get_llm_messages(conv_id)
            messages_for_llm = history + [
                {"role": "user", "content": message}
            ]

            llm                        = get_llm_manager()
            ai_response, provider_used = await llm.chat(
                system_prompt=SUPERADMIN_SYSTEM_PROMPT,
                messages=messages_for_llm,
                temperature=0.2,
                max_tokens=600,
            )

            if not ai_response:
                ai_response   = "Console error. Check backend logs."
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
# HELPER
# ════════════════════════════════════════════════

def _get_model_name(provider: str) -> str:
    """Get model name for metadata tracking"""
    model_map = {
        "groq_public":     settings.GROQ_PUBLIC_MODEL,
        "groq_portal":     settings.GROQ_PORTAL_MODEL,
        "groq_admin":      settings.GROQ_ADMIN_MODEL,
        "gemini":          settings.GEMINI_MODEL,
        "openrouter":      settings.OPENROUTER_MODEL,
        "deepseek":        settings.DEEPSEEK_MODEL,
        "huggingface":     settings.HF_MODEL,
        "local_formatter": "local_python",
        "local_fallback":  "template",
        "hallucination_blocker": "anti_hallucination",  # ✅ NEW
        "none":            "template",
    }
    return model_map.get(provider, "unknown")


# ════════════════════════════════════════════════
# CONTEXT MANAGER STATS (DEBUG)
# ════════════════════════════════════════════════

@router.get("/context-stats")
async def get_context_stats():
    """Get conversation context statistics"""
    context_mgr = get_context_manager()
    stats = context_mgr.get_stats()
    
    return {
        "success": True,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }