# api/utils/command_formatter.py
"""
Format command results into human-readable responses

✅ PRIVACY: No data ever sent to LLM
Pure Python formatting
"""

from typing import Dict, Optional
from .command_parser import CommandType


class CommandFormatter:
    """Format command previews and results"""

    # ══════════════════════════════════════════════════════
    # PREVIEW FORMATS
    # ══════════════════════════════════════════════════════

    def format_preview(
        self,
        command_type: str,
        preview_data: Dict,
        params: Dict,
    ) -> str:
        """Format command preview for user confirmation"""

        if 'error' in preview_data:
            return (
                f"⚠️ **Could not preview command**\n\n"
                f"Error: {preview_data['error']}\n\n"
                "Please check the details and try again."
            )

        if command_type == CommandType.PROMOTE_STUDENTS:
            return self._preview_promote(preview_data, params)

        if command_type == CommandType.SEND_ABSENT_SMS:
            return self._preview_absent_sms(preview_data, params)

        if command_type == CommandType.SEND_FEE_REMINDER:
            return self._preview_fee_reminder(preview_data, params)

        if command_type == CommandType.MARK_ATTENDANCE:
            return self._preview_mark_attendance(preview_data, params)

        if command_type in [
            CommandType.SEND_SMS,
            CommandType.SEND_WHATSAPP,
            CommandType.SEND_EMAIL
        ]:
            return self._preview_send_message(preview_data, params)

        if command_type == CommandType.SEND_NOTICE:
            return self._preview_notice(preview_data, params)

        return "✅ Ready to execute. Confirm?"

    def _preview_promote(self, data: Dict, params: Dict) -> str:
        count      = data.get('students_count', 0)
        from_cls   = params.get('from_class', '?')
        to_cls     = params.get('to_class', '?')
        section    = params.get('section', '')
        next_year  = data.get('next_year', 'next year')

        if count == 0:
            return f"⚠️ **No students found** in Class {from_cls}{section}."

        section_str = f" Section {section}" if section else ""

        preview_students = data.get('preview_data', [])
        student_list = ""
        if preview_students:
            names = [
                s.get('userId', {}).get('name', 'Unknown')
                if isinstance(s.get('userId'), dict)
                else 'Unknown'
                for s in preview_students[:3]
            ]
            student_list = f"\n**Sample:** {', '.join(names)}"
            if count > 3:
                student_list += f" + {count - 3} more"

        return f"""📊 **Promotion Preview**

**Action:** Promote Students
**From:** Class {from_cls}{section_str}
**To:** Class {to_cls}{section_str}
**Academic Year:** {next_year}

**Students Affected:** {count}
{student_list}

**This will:**
✅ Update class to {to_cls}
✅ Add session history entry
✅ Reassign roll numbers
✅ Auto-assign new fee structures

⚠️ **This action cannot be undone easily.**

Type **"confirm"** to proceed or **"cancel"** to abort."""

    def _preview_absent_sms(self, data: Dict, params: Dict) -> str:
        count   = data.get('absent_count', 0)
        date    = data.get('date', 'today')
        credits = data.get('credits_required', count)

        if count == 0:
            return f"✅ **No absent students** found for {date}.\n\nNo SMS to send!"

        preview = data.get('preview_data', [])
        student_list = ""
        if preview:
            names = [f"• {s.get('name', 'Unknown')} ({s.get('class', '')})" for s in preview[:5]]
            student_list = "\n**Absent Students:**\n" + "\n".join(names)
            if count > 5:
                student_list += f"\n• ...and {count - 5} more"

        return f"""📨 **Send Absent SMS Preview**

**Date:** {date}
**Absent Students:** {count}
**Credits Required:** {credits}
{student_list}

**SMS Template:**
_"[Student Name] was ABSENT on {date}. Please contact school if needed. -Skolify"_

Type **"confirm"** to send SMS to {count} parents or **"cancel"** to abort."""

    def _preview_fee_reminder(self, data: Dict, params: Dict) -> str:
        count   = data.get('pending_students', 0)
        pending = data.get('total_pending', 0)
        channel = params.get('channel', 'sms').upper()
        credits = data.get('credits_required', count)

        if count == 0:
            return "✅ **No pending fees!** All parents are up to date."

        return f"""💰 **Fee Reminder Preview**

**Channel:** {channel}
**Pending Students:** {count}
**Total Pending Amount:** ₹{pending:,}
**Credits Required:** {credits}

**Message Template:**
_"Dear Parent, fee payment is due for your child. Please pay at the earliest. Login to portal for details. -Skolify"_

Type **"confirm"** to send {channel} to {count} parents or **"cancel"** to abort."""

    def _preview_mark_attendance(self, data: Dict, params: Dict) -> str:
        count   = data.get('students_count', 0)
        status  = params.get('status', 'present').upper()
        cls     = params.get('class', 'All')
        section = params.get('section', '')
        date    = params.get('date', 'today')

        if count == 0:
            return f"⚠️ **No students found** for the specified class/section."

        section_str = f" {section}" if section else ""

        return f"""✅ **Mark Attendance Preview**

**Date:** {date}
**Class:** {cls}{section_str}
**Status:** {status}
**Students:** {count}

This will mark {count} students as **{status}**.
{'📨 Absent SMS will be sent to parents.' if status == 'ABSENT' else ''}

Type **"confirm"** to proceed or **"cancel"** to abort."""

    def _preview_send_message(self, data: Dict, params: Dict) -> str:
        channel      = params.get('channel', 'sms').upper()
        target       = params.get('target', 'all')
        needs_content = data.get('needs_content', True)
        content_hint = params.get('content_hint', '')

        if needs_content:
            hint_str = f"\n\n**Topic detected:** {content_hint}" if content_hint else ""
            return f"""📨 **Bulk {channel} Setup**

**Target:** {target.title()}
**Channel:** {channel}
{hint_str}

**Please provide the message content:**

Type the message you want to send, or say:
• **"generate message"** - Let AI write it for you
• **"cancel"** - Cancel this command"""

        return f"""📨 **Bulk {channel} Preview**

**Target:** {target.title()}
**Channel:** {channel}
**Content:** {content_hint[:100]}...

Type **"confirm"** to send or **"cancel"** to abort."""

    def _preview_notice(self, data: Dict, params: Dict) -> str:
        target       = params.get('target', 'all')
        notice_hint  = params.get('notice_hint', '')

        hint_str = f"\n**Topic:** {notice_hint}" if notice_hint else ""

        return f"""📢 **Create Notice**

**Target Audience:** {target.title()}
{hint_str}

Please provide:
1. **Title** of the notice
2. **Content** of the notice

Or say **"generate notice"** for AI to write it."""

    # ══════════════════════════════════════════════════════
    # RESULT FORMATS
    # ══════════════════════════════════════════════════════

    def format_result(
        self,
        command_type: str,
        result: Dict,
        params: Dict,
    ) -> str:
        """Format command execution result"""

        if not result.get('success'):
            error = result.get('error', 'Unknown error')
            return (
                f"❌ **Command Failed**\n\n"
                f"Error: {error}\n\n"
                f"Please try again or contact support."
            )

        if command_type == CommandType.PROMOTE_STUDENTS:
            return self._result_promote(result, params)

        if command_type == CommandType.SEND_ABSENT_SMS:
            return self._result_absent_sms(result, params)

        if command_type == CommandType.SEND_FEE_REMINDER:
            return self._result_fee_reminder(result, params)

        if command_type == CommandType.MARK_ATTENDANCE:
            return self._result_mark_attendance(result, params)

        if command_type in [
            CommandType.SEND_SMS,
            CommandType.SEND_WHATSAPP,
            CommandType.SEND_EMAIL,
        ]:
            return self._result_send_message(result, params)

        if command_type == CommandType.SEND_NOTICE:
            return self._result_notice(result, params)

        return "✅ **Command executed successfully!**"

    def _result_promote(self, result: Dict, params: Dict) -> str:
        promoted = result.get('promoted', 0)
        failed   = result.get('failed', 0)
        new_year = result.get('new_year', 'next year')
        from_cls = params.get('from_class', '?')
        to_cls   = params.get('to_class', '?')

        fail_str = f"\n❌ **Failed:** {failed} students" if failed > 0 else ""

        return f"""✅ **Promotion Successful!**

👨‍🎓 **Promoted:** {promoted} students
📚 **From Class:** {from_cls} → {to_cls}
📅 **Academic Year:** {new_year}
{fail_str}

**Actions completed:**
✅ Class updated
✅ Session history saved
✅ Roll numbers reassigned
✅ Fee structures assigned

📋 Action logged: #{result.get('log_id', 'N/A')}

**Next Steps:**
💡 Send promotion SMS to parents?
💡 Update timetable for new class?"""

    def _result_absent_sms(self, result: Dict, params: Dict) -> str:
        sent    = result.get('sent', 0)
        failed  = result.get('failed', 0)
        skipped = result.get('skipped', 0)
        credits = result.get('creditsUsed', sent)

        warning = ""
        if skipped > 0:
            warning = f"\n⚠️ **Skipped:** {skipped} (insufficient credits)"

        return f"""📨 **Absent SMS Sent!**

✅ **Sent:** {sent} SMS
❌ **Failed:** {failed}
💳 **Credits Used:** {credits}
{warning}

All absent parents have been notified."""

    def _result_fee_reminder(self, result: Dict, params: Dict) -> str:
        sent    = result.get('sent', 0)
        failed  = result.get('failed', 0)
        credits = result.get('creditsUsed', 0)
        channel = params.get('channel', 'sms').upper()

        return f"""💰 **Fee Reminder Sent!**

✅ **{channel} Sent:** {sent}
❌ **Failed:** {failed}
💳 **Credits Used:** {credits}

All fee defaulters have been reminded."""

    def _result_mark_attendance(self, result: Dict, params: Dict) -> str:
        marked  = result.get('marked', 0)
        status  = params.get('status', 'present').title()
        sms     = result.get('sms', {})
        sms_str = ""

        if sms.get('sent', 0) > 0:
            sms_str = f"\n📨 **Absent SMS:** {sms.get('sent')} sent"
        elif sms.get('skipped', 0) > 0:
            sms_str = f"\n⚠️ **SMS Skipped:** Insufficient credits"

        return f"""✅ **Attendance Marked!**

📊 **Marked:** {marked} students as {status}
📅 **Date:** {params.get('date', 'today')}
{sms_str}"""

    def _result_send_message(self, result: Dict, params: Dict) -> str:
        sent    = result.get('sent', 0)
        failed  = result.get('failed', 0)
        credits = result.get('credits', 0)
        channel = params.get('channel', 'sms').upper()

        return f"""📨 **Messages Sent!**

✅ **{channel} Sent:** {sent}
❌ **Failed:** {failed}
💳 **Credits Used:** {credits}"""

    def _result_notice(self, result: Dict, params: Dict) -> str:
        return f"""📢 **Notice Published!**

✅ Notice created successfully
📢 **Target:** {params.get('target', 'All').title()}
🔔 Push notification sent (if enabled)"""


# ══════════════════════════════════════════════════════════
# SINGLETON
# ══════════════════════════════════════════════════════════

_formatter_instance = None

def get_command_formatter() -> CommandFormatter:
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = CommandFormatter()
    return _formatter_instance