# api/utils/command_executor.py
"""
Admin Command Executor

✅ BACKWARD COMPATIBLE with manual promotions:
- Sends filterByYear to Next.js (new optional field)
- Manual UI calls don't send filterByYear → work as before
- AI calls send filterByYear → only current year students promoted
"""

import httpx
from typing import Dict, Optional, List
from datetime import datetime

from ..config import settings
from .command_parser import ParsedCommand, CommandType


NEXTJS_BASE = settings.NEXTJS_URL


class CommandExecutor:
    """Execute admin commands via Next.js APIs"""

    async def preview(
        self,
        command:        ParsedCommand,
        tenant_id:      str,
        session_cookie: str,
        llm_manager=None,
    ) -> Dict:
        """Preview command impact before execution"""
        cmd_type = command.command_type
        params   = command.params

        print(f"🔍 Preview: {cmd_type} | Tenant: {tenant_id[-6:]}")

        if cmd_type == CommandType.PROMOTE_STUDENTS:
            return await self._preview_promote(params, tenant_id, session_cookie)

        if cmd_type == CommandType.SEND_ABSENT_SMS:
            return await self._preview_absent_sms(params, tenant_id, session_cookie)

        if cmd_type == CommandType.SEND_FEE_REMINDER:
            return await self._preview_fee_reminder(params, tenant_id, session_cookie)

        if cmd_type == CommandType.MARK_ATTENDANCE:
            return await self._preview_mark_attendance(params, tenant_id, session_cookie)

        if cmd_type in [
            CommandType.SEND_SMS,
            CommandType.SEND_WHATSAPP,
            CommandType.SEND_EMAIL,
        ]:
            return await self._preview_send_message(params, tenant_id, session_cookie)

        if cmd_type == CommandType.SEND_NOTICE:
            return self._preview_notice(params)

        if cmd_type == CommandType.GENERATE_MESSAGE:
            return {'needs_preview': False, 'ready_to_generate': True}

        return {'error': f'Unknown command: {cmd_type}'}

    async def execute(
        self,
        command:        ParsedCommand,
        tenant_id:      str,
        session_cookie: str,
        extra_params:   Optional[Dict] = None,
    ) -> Dict:
        """Execute confirmed command"""
        cmd_type = command.command_type
        params   = {**command.params, **(extra_params or {})}

        print(f"⚡ Execute: {cmd_type} | Tenant: {tenant_id[-6:]}")

        try:
            if cmd_type == CommandType.PROMOTE_STUDENTS:
                return await self._execute_promote(params, tenant_id, session_cookie)

            if cmd_type == CommandType.SEND_ABSENT_SMS:
                return await self._execute_absent_sms(params, tenant_id, session_cookie)

            if cmd_type == CommandType.SEND_FEE_REMINDER:
                return await self._execute_fee_reminder(params, tenant_id, session_cookie)

            if cmd_type == CommandType.MARK_ATTENDANCE:
                return await self._execute_mark_attendance(params, tenant_id, session_cookie)

            if cmd_type in [
                CommandType.SEND_SMS,
                CommandType.SEND_WHATSAPP,
                CommandType.SEND_EMAIL,
            ]:
                return await self._execute_send_message(params, tenant_id, session_cookie)

            if cmd_type == CommandType.SEND_NOTICE:
                return await self._execute_send_notice(params, tenant_id, session_cookie)

            return {'success': False, 'error': f'Unknown command: {cmd_type}'}

        except Exception as e:
            print(f"❌ Execute error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    # ══════════════════════════════════════════════════════
    # PROMOTE STUDENTS
    # ══════════════════════════════════════════════════════

    async def _preview_promote(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """
        Get promotion preview from Next.js GET endpoint

        ✅ Only fetches current academic year students
        """
        try:
            from_class = params.get('from_class', '')
            section    = params.get('section')

            # Build query - Next.js will filter by currentYear automatically
            query_params = f"?class={from_class}"
            if section:
                query_params += f"&section={section}"

            print(f"📡 Preview GET: /api/students/promote{query_params}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{NEXTJS_BASE}/api/students/promote{query_params}",
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                    },
                )

                print(f"📥 Preview status: {response.status_code}")

                if response.status_code != 200:
                    print(f"❌ Preview failed: {response.text[:200]}")
                    return {'error': f'Preview failed: {response.status_code}'}

                data         = response.json()
                students     = data.get('students', [])
                next_year    = data.get('nextYear', '')
                current_year = data.get('currentYear', '')

                print(f"✅ Preview: {len(students)} students found")
                print(f"   currentYear : {current_year}")
                print(f"   nextYear    : {next_year}")

                # ✅ Verify all returned students are current year
                # (defensive check - Next.js should already filter)
                old_year_students = [
                    s for s in students
                    if s.get('academicYear') != current_year
                ]
                if old_year_students:
                    print(
                        f"⚠️  WARNING: {len(old_year_students)} students "
                        f"from old academic years in preview!"
                    )
                    # Filter them out on Python side too
                    students = [
                        s for s in students
                        if s.get('academicYear') == current_year
                    ]
                    print(f"   Filtered to {len(students)} current year students")

                return {
                    'students_count':   len(students),
                    'from_class':       from_class,
                    'to_class':         params.get('to_class'),
                    'section':          section,
                    'current_year':     current_year,
                    'next_year':        next_year,
                    # ✅ Save ALL students for execution (not just [:5])
                    'all_students':     students,
                    # First 5 for display preview only
                    'preview_data':     students[:5],
                    'ready_to_execute': len(students) > 0,
                }

        except Exception as e:
            print(f"❌ Preview promote error: {e}")
            return {'error': str(e)}

    async def _execute_promote(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """
        Execute student promotion via Next.js POST endpoint

        ✅ BACKWARD COMPATIBLE:
        Sends filterByYear so Next.js skips old-year students
        Manual UI promotions don't send filterByYear → unaffected

        Next.js POST expects:
        {
            studentIds:     string[]
            fromClass:      string
            toClass:        string
            toSection:      string
            toAcademicYear: string
            result:         'promoted' | 'detained'
            filterByYear?:  string   ← NEW optional (AI only)
        }
        """
        try:
            from_class   = params.get('from_class')
            to_class     = params.get('to_class')
            section      = params.get('section')
            next_year    = params.get('next_year')
            current_year = params.get('current_year')

            print(f"\n{'='*55}")
            print(f"📋 EXECUTE PROMOTE - PARAMS")
            print(f"{'='*55}")
            print(f"  from_class    : {from_class}")
            print(f"  to_class      : {to_class}")
            print(f"  section       : {section}")
            print(f"  current_year  : {current_year}")
            print(f"  next_year     : {next_year}")
            print(f"  all_students  : {len(params.get('all_students', []))}")
            print(f"{'='*55}\n")

            # ── Validation ──────────────────────────────
            if not from_class:
                return {'success': False, 'error': 'from_class is missing'}

            if not to_class:
                return {'success': False, 'error': 'to_class is missing'}

            if str(from_class) == str(to_class):
                return {
                    'success': False,
                    'error':   (
                        f'Cannot promote: '
                        f'from_class ({from_class}) == to_class ({to_class})'
                    )
                }

            if not next_year:
                return {
                    'success': False,
                    'error':   'next_year (toAcademicYear) is missing'
                }

            print(f"📚 Promoting: Class {from_class} → {to_class} | Year: {next_year}")

            # ── Get student IDs ──────────────────────────
            all_students = params.get('all_students', [])
            preview_data = params.get('preview_data', [])

            if all_students:
                # ✅ Double-filter: only current year students
                # Even if Next.js returned some old year students,
                # we filter here as well (double safety)
                if current_year:
                    filtered = [
                        s for s in all_students
                        if s.get('academicYear') == current_year
                    ]
                    skipped_count = len(all_students) - len(filtered)

                    if skipped_count > 0:
                        print(
                            f"⚠️  Python filter: skipped {skipped_count} "
                            f"students from old academic years"
                        )
                        print(
                            f"   Promoting {len(filtered)} students "
                            f"from {current_year}"
                        )
                    all_students = filtered

                student_ids = [str(s['_id']) for s in all_students]
                print(f"✅ Using all_students: {len(student_ids)} IDs")

            elif preview_data:
                # ⚠️ Fallback: only have preview subset
                if current_year:
                    preview_data = [
                        s for s in preview_data
                        if s.get('academicYear') == current_year
                    ]
                student_ids = [str(s['_id']) for s in preview_data]
                print(f"⚠️  Using preview_data: {len(student_ids)} IDs")

            else:
                # 🔄 Re-fetch fresh from API
                print(f"🔄 Re-fetching students from API...")

                query = f"?class={from_class}"
                if section:
                    query += f"&section={section}"

                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.get(
                        f"{NEXTJS_BASE}/api/students/promote{query}",
                        headers={
                            'Cookie':        session_cookie,
                            'X-Internal-AI': 'true',
                        },
                    )

                    if res.status_code != 200:
                        return {
                            'success': False,
                            'error':   f'Re-fetch failed: {res.status_code}'
                        }

                    fresh        = res.json()
                    students     = fresh.get('students', [])
                    student_ids  = [str(s['_id']) for s in students]
                    current_year = fresh.get('currentYear', current_year)

                    if not next_year:
                        next_year = fresh.get('nextYear', '')

                    print(f"✅ Re-fetched: {len(student_ids)} students")

            if not student_ids:
                return {
                    'success': False,
                    'error':   (
                        f'No students found in class {from_class} '
                        f'for academic year {current_year}'
                    )
                }

            # ✅ toSection
            to_section = str(section) if section else 'A'

            # ── Build payload ────────────────────────────
            payload = {
                'studentIds':     student_ids,
                'fromClass':      str(from_class),
                'toClass':        str(to_class),
                'toSection':      to_section,
                'toAcademicYear': str(next_year),
                'result':         'promoted',
                # ✅ NEW: Tell Next.js to skip old-year students
                # Backward compatible: manual UI doesn't send this
                'filterByYear':   str(current_year) if current_year else None,
            }

            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            print(f"\n{'='*55}")
            print(f"📤 PROMOTE API PAYLOAD:")
            print(f"{'='*55}")
            print(f"  studentIds:     {len(student_ids)} IDs")
            print(f"  fromClass:      {payload['fromClass']}")
            print(f"  toClass:        {payload['toClass']}")
            print(f"  toSection:      {payload['toSection']}")
            print(f"  toAcademicYear: {payload['toAcademicYear']}")
            print(f"  filterByYear:   {payload.get('filterByYear', 'not set')}")
            print(f"  result:         {payload['result']}")
            print(f"{'='*55}\n")

            # ── Execute ──────────────────────────────────
            async with httpx.AsyncClient(timeout=60.0) as client:
                promote_res = await client.post(
                    f"{NEXTJS_BASE}/api/students/promote",
                    json=payload,
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                        'Content-Type':  'application/json',
                    },
                )

            print(f"📥 Promote status : {promote_res.status_code}")
            print(f"📥 Promote body   : {promote_res.text[:500]}")

            if promote_res.status_code == 200:
                result_data = promote_res.json()
                skipped     = result_data.get('skippedOldYear', 0)

                if skipped > 0:
                    print(f"⚠️  Next.js skipped {skipped} old-year students")

                return {
                    'success':          True,
                    'promoted':         result_data.get('promoted', len(student_ids)),
                    'failed':           result_data.get('failed', 0),
                    'skipped_old_year': skipped,
                    'new_year':         result_data.get('newYear', next_year),
                    'log_id':           result_data.get('logId', 'N/A'),
                }

            # ── Error handling ───────────────────────────
            try:
                err_body = promote_res.json()
                err_msg  = (
                    err_body.get('error')
                    or err_body.get('message')
                    or str(err_body)
                )
            except Exception:
                err_msg = promote_res.text[:300]

            print(f"❌ Promote failed: {promote_res.status_code} - {err_msg}")

            return {
                'success': False,
                'error':   f'Promotion failed ({promote_res.status_code}): {err_msg}',
            }

        except Exception as e:
            print(f"❌ Execute promote exception: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    # ══════════════════════════════════════════════════════
    # ABSENT SMS
    # ══════════════════════════════════════════════════════

    async def _preview_absent_sms(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Preview absent SMS"""
        try:
            date = params.get('date', datetime.now().strftime('%Y-%m-%d'))

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{NEXTJS_BASE}/api/chat/tools/admin",
                    json={
                        'tool':      'get_attendance_today',
                        'params':    {},
                        'tenant_id': tenant_id,
                    },
                    headers={
                        'X-Internal-AI': 'true',
                        'Cookie':        session_cookie,
                    },
                )

                if response.status_code == 200:
                    data     = response.json()
                    att_data = data.get('data', {})
                    absent   = att_data.get('absent', 0)

                    return {
                        'absent_count':     absent,
                        'date':             date,
                        'credits_required': absent,
                        'ready_to_execute': absent > 0,
                        'preview_data':     att_data.get('absent_students', []),
                    }

                return {'error': 'Could not fetch attendance data'}

        except Exception as e:
            return {'error': str(e)}

    async def _execute_absent_sms(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Send SMS to absent students"""
        try:
            date = params.get('date', datetime.now().strftime('%Y-%m-%d'))

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{NEXTJS_BASE}/api/ai/admin-commands",
                    json={
                        'command': 'send_absent_sms',
                        'params': {
                            'date':    date,
                            'class':   params.get('class'),
                            'section': params.get('section'),
                        },
                        'tenant_id': tenant_id,
                    },
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                        'Content-Type':  'application/json',
                    },
                )

                if response.status_code == 200:
                    return response.json()

                return {
                    'success': False,
                    'error':   f'SMS send failed: {response.status_code}'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ══════════════════════════════════════════════════════
    # FEE REMINDER
    # ══════════════════════════════════════════════════════

    async def _preview_fee_reminder(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Preview fee reminder"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{NEXTJS_BASE}/api/chat/tools/admin",
                    json={
                        'tool':      'get_fee_summary',
                        'params':    {},
                        'tenant_id': tenant_id,
                    },
                    headers={
                        'X-Internal-AI': 'true',
                        'Cookie':        session_cookie,
                    },
                )

                if response.status_code == 200:
                    data          = response.json()
                    fee_data      = data.get('data', {})
                    pending_count = fee_data.get('overdue_count', 0)
                    channel       = params.get('channel', 'sms')

                    return {
                        'pending_students':  pending_count,
                        'total_pending':     fee_data.get('total_pending', 0),
                        'channel':           channel,
                        'credits_required':  pending_count,
                        'ready_to_execute':  pending_count > 0,
                    }

                return {'error': 'Could not fetch fee data'}

        except Exception as e:
            return {'error': str(e)}

    async def _execute_fee_reminder(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Send fee reminders"""
        try:
            channel = params.get('channel', 'sms')

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{NEXTJS_BASE}/api/ai/admin-commands",
                    json={
                        'command': 'send_fee_reminder',
                        'params': {
                            'channel': channel,
                            'class':   params.get('class'),
                        },
                        'tenant_id': tenant_id,
                    },
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                        'Content-Type':  'application/json',
                    },
                )

                if response.status_code == 200:
                    return response.json()

                return {
                    'success': False,
                    'error':   f'Fee reminder failed: {response.status_code}'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ══════════════════════════════════════════════════════
    # MARK ATTENDANCE
    # ══════════════════════════════════════════════════════

    async def _preview_mark_attendance(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Preview bulk attendance marking"""
        try:
            cls     = params.get('class', '')
            section = params.get('section', '')
            status  = params.get('status', 'present')
            date    = params.get('date', datetime.now().strftime('%Y-%m-%d'))

            query = f"?class={cls}&date={date}"
            if section:
                query += f"&section={section}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{NEXTJS_BASE}/api/attendance{query}",
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                    },
                )

                if response.status_code == 200:
                    data  = response.json()
                    total = data.get('total', 0)

                    return {
                        'students_count':   total,
                        'status_to_mark':   status,
                        'class':            cls,
                        'section':          section,
                        'date':             date,
                        'ready_to_execute': total > 0,
                    }

                return {'error': 'Could not fetch attendance data'}

        except Exception as e:
            return {'error': str(e)}

    async def _execute_mark_attendance(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Bulk mark attendance"""
        try:
            cls     = params.get('class', '')
            section = params.get('section', '')
            status  = params.get('status', 'present')
            date    = params.get('date', datetime.now().strftime('%Y-%m-%d'))

            query = f"?class={cls}&date={date}"
            if section:
                query += f"&section={section}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                students_res = await client.get(
                    f"{NEXTJS_BASE}/api/attendance{query}",
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                    },
                )

                if students_res.status_code != 200:
                    return {'success': False, 'error': 'Could not fetch students'}

                students_data = students_res.json()
                students      = students_data.get('list', [])

                if not students:
                    return {'success': False, 'error': 'No students found'}

                records = [
                    {'studentId': s['studentId'], 'status': status}
                    for s in students
                ]

                att_res = await client.post(
                    f"{NEXTJS_BASE}/api/attendance",
                    json={
                        'date':          date,
                        'records':       records,
                        'sendAbsentSms': status == 'absent',
                    },
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                        'Content-Type':  'application/json',
                    },
                )

                if att_res.status_code == 200:
                    result = att_res.json()
                    return {
                        'success': True,
                        'marked':  result.get('saved', 0),
                        'status':  status,
                        'date':    date,
                        'sms':     result.get('sms', {}),
                    }

                return {
                    'success': False,
                    'error':   f'Attendance failed: {att_res.status_code}'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ══════════════════════════════════════════════════════
    # SEND MESSAGE
    # ══════════════════════════════════════════════════════

    def _preview_send_message(self, params: Dict, *args) -> Dict:
        """Preview bulk message"""
        return {
            'channel':          params.get('channel', 'sms'),
            'target':           params.get('target', 'all'),
            'class':            params.get('class'),
            'needs_content':    params.get('needs_content', True),
            'content_hint':     params.get('content_hint', ''),
            'ready_to_execute': not params.get('needs_content', True),
        }

    async def _execute_send_message(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Send bulk message"""
        try:
            channel = params.get('channel', 'sms')
            content = params.get('content', '')
            cls     = params.get('class')
            section = params.get('section')

            if not content:
                return {'success': False, 'error': 'Message content required'}

            recipients = 'all'
            if cls and section:
                recipients = 'section'
            elif cls:
                recipients = 'class'

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{NEXTJS_BASE}/api/communication",
                    json={
                        'type':          channel,
                        'content':       content,
                        'recipients':    recipients,
                        'targetClass':   cls,
                        'targetSection': section,
                    },
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                        'Content-Type':  'application/json',
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    return {
                        'success': True,
                        'sent':    result.get('sent', 0),
                        'failed':  result.get('failed', 0),
                        'credits': result.get('creditsUsed', 0),
                    }

                try:
                    err_data = response.json()
                    err_msg  = err_data.get('error', 'Send failed')
                except Exception:
                    err_msg = response.text[:200]

                return {'success': False, 'error': err_msg}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ══════════════════════════════════════════════════════
    # NOTICE
    # ══════════════════════════════════════════════════════

    def _preview_notice(self, params: Dict) -> Dict:
        """Preview notice creation"""
        return {
            'target':        params.get('target', 'all'),
            'class':         params.get('class'),
            'notice_hint':   params.get('notice_hint', ''),
            'needs_content': True,
            'needs_title':   True,
        }

    async def _execute_send_notice(
        self,
        params:         Dict,
        tenant_id:      str,
        session_cookie: str,
    ) -> Dict:
        """Create and publish notice"""
        try:
            title   = params.get('title', 'Important Notice')
            content = params.get('content', '')
            target  = params.get('target', 'all')

            if not content:
                return {'success': False, 'error': 'Notice content required'}

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{NEXTJS_BASE}/api/ai/admin-commands",
                    json={
                        'command': 'create_notice',
                        'params': {
                            'title':       title,
                            'content':     content,
                            'targetRole':  target,
                            'targetClass': params.get('class'),
                            'priority':    params.get('priority', 'normal'),
                        },
                        'tenant_id': tenant_id,
                    },
                    headers={
                        'Cookie':        session_cookie,
                        'X-Internal-AI': 'true',
                        'Content-Type':  'application/json',
                    },
                )

                if response.status_code == 200:
                    return response.json()

                return {
                    'success': False,
                    'error':   f'Notice failed: {response.status_code}'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}


# ══════════════════════════════════════════════════════════
# SINGLETON
# ══════════════════════════════════════════════════════════

_executor_instance = None


def get_command_executor() -> CommandExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = CommandExecutor()
    return _executor_instance