# api/utils/command_parser.py
"""
Natural Language Command Parser for Admin Portal

Supported Commands:
1. Student Promotion
2. Bulk Attendance
3. Bulk SMS/WhatsApp/Email
4. Notice Creation
5. Fee Reminders
6. Message Template Generation (AI-powered)
"""

import re
from typing import Dict, Optional, List, Tuple
from datetime import datetime


# ══════════════════════════════════════════════════════════
# COMMAND TYPES
# ══════════════════════════════════════════════════════════

class CommandType:
    # Student Management
    PROMOTE_STUDENTS     = 'promote_students'
    TRANSFER_STUDENT     = 'transfer_student'
    
    # Attendance
    MARK_ATTENDANCE      = 'mark_attendance'
    SEND_ABSENT_SMS      = 'send_absent_sms'
    
    # Communication
    SEND_SMS             = 'send_sms'
    SEND_WHATSAPP        = 'send_whatsapp'
    SEND_EMAIL           = 'send_email'
    SEND_NOTICE          = 'send_notice'
    
    # Fee Management
    SEND_FEE_REMINDER    = 'send_fee_reminder'
    
    # AI Template
    GENERATE_MESSAGE     = 'generate_message'
    
    # Unknown
    UNKNOWN              = 'unknown'


# ══════════════════════════════════════════════════════════
# PARSED COMMAND STRUCTURE
# ══════════════════════════════════════════════════════════

class ParsedCommand:
    def __init__(
        self,
        command_type: str,
        params: Dict,
        raw_message: str,
        confidence: float = 1.0,
        requires_confirmation: bool = True,
        is_destructive: bool = False,
    ):
        self.command_type         = command_type
        self.params               = params
        self.raw_message          = raw_message
        self.confidence           = confidence
        self.requires_confirmation = requires_confirmation
        self.is_destructive       = is_destructive

    def to_dict(self) -> Dict:
        return {
            'command_type':          self.command_type,
            'params':                self.params,
            'raw_message':           self.raw_message,
            'confidence':            self.confidence,
            'requires_confirmation': self.requires_confirmation,
            'is_destructive':        self.is_destructive,
        }


# ══════════════════════════════════════════════════════════
# COMMAND PARSER
# ══════════════════════════════════════════════════════════

class AdminCommandParser:
    """
    Parse natural language admin commands
    Supports Hindi, Hinglish, and English
    """

    def parse(self, message: str, role: str = 'admin') -> Optional[ParsedCommand]:
        """
        Main parse function
        
        Returns ParsedCommand if detected, None if regular chat
        """
        msg = message.lower().strip()

        # ── Parse attempts in priority order ──────────────
        parsers = [
            self._parse_promote_students,
            self._parse_mark_attendance,
            self._parse_send_absent_sms,
            self._parse_send_fee_reminder,
            self._parse_send_notice,
            self._parse_send_message,
            self._parse_generate_message,
            self._parse_transfer_student,
        ]

        for parser in parsers:
            result = parser(msg, message)
            if result:
                print(f"🎯 Command detected: {result.command_type}")
                return result

        return None

    # ══════════════════════════════════════════════════════
    # STUDENT PROMOTION
    # ══════════════════════════════════════════════════════

    def _parse_promote_students(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect promotion commands

        Examples:
        - "promote all class 10 to class 11"
        - "promote all class 10 to 11"          ← NOW WORKS
        - "class 10 ke students ko 11 mein promote karo"
        - "promote all student of class 10 to 11"  ← NOW WORKS
        - "class 10A to 11A promote"
        """
        promote_keywords = [
            'promote', 'promotion', 'next class',
            'agli class', 'agle class mein',
            'pass kar', 'passed karo',
            'upgrade karo', 'class badhao',
        ]

        if not any(kw in msg for kw in promote_keywords):
            return None

        # ✅ FIX: Extract from_class and to_class with improved logic
        from_class, to_class = self._extract_from_to_classes(msg)

        # If to_class still not found, auto-increment from_class
        if from_class and not to_class:
            try:
                to_class = str(int(from_class) + 1)
                print(f"🔢 Auto-incremented: {from_class} → {to_class}")
            except ValueError:
                to_class = None

        print(f"🔍 Promote: from={from_class} to={to_class}")

        # Extract section
        section = self._extract_section(msg)

        # Scope
        scope = 'section' if section else 'all'

        return ParsedCommand(
            command_type=CommandType.PROMOTE_STUDENTS,
            params={
                'from_class': from_class,
                'to_class':   to_class,
                'section':    section,
                'scope':      scope,
                'result':     'promoted',
            },
            raw_message=original,
            confidence=0.9 if from_class else 0.6,
            requires_confirmation=True,
            is_destructive=True,
        )

    # ══════════════════════════════════════════════════════
    # ATTENDANCE
    # ══════════════════════════════════════════════════════

    def _parse_mark_attendance(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect bulk attendance marking
        
        Examples:
        - "mark all class 10 present today"
        - "class 10A ko aaj absent mark karo"
        - "sab students ko present karo aaj"
        """
        attendance_keywords = [
            'mark attendance', 'attendance mark',
            'present karo', 'absent karo',
            'mark present', 'mark absent',
            'sab present', 'all present',
            'attendance lagao',
        ]

        if not any(kw in msg for kw in attendance_keywords):
            return None

        # Status
        status = 'present'
        if any(w in msg for w in ['absent', 'absentee', 'nahi aaye']):
            status = 'absent'

        # Class
        cls = self._extract_class(msg, context='from')

        # Section
        section = self._extract_section(msg)

        # Scope
        scope = 'all'
        if cls and section:
            scope = 'class_section'
        elif cls:
            scope = 'class'

        return ParsedCommand(
            command_type=CommandType.MARK_ATTENDANCE,
            params={
                'status':  status,
                'class':   cls,
                'section': section,
                'scope':   scope,
                'date':    datetime.now().strftime('%Y-%m-%d'),
            },
            raw_message=original,
            confidence=0.85,
            requires_confirmation=True,
            is_destructive=False,
        )

    # ══════════════════════════════════════════════════════
    # ABSENT SMS
    # ══════════════════════════════════════════════════════

    def _parse_send_absent_sms(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect absent SMS sending

        Examples:
        - "absent students ko SMS bhejo"
        - "aaj ke absent students ke parents ko message karo"
        - "send sms to absent students"
        """
        absent_sms_patterns = [
            'absent.*sms', 'sms.*absent',
            'absent.*message', 'message.*absent',
            'absent.*parents.*message',
            'absent students ko sms',
            'absentee sms',
            'aaj ke absent',
        ]

        if not any(re.search(p, msg) for p in absent_sms_patterns):
            return None

        cls     = self._extract_class(msg, context='from')
        section = self._extract_section(msg)

        return ParsedCommand(
            command_type=CommandType.SEND_ABSENT_SMS,
            params={
                'class':   cls,
                'section': section,
                'date':    datetime.now().strftime('%Y-%m-%d'),
                'channel': 'sms',
            },
            raw_message=original,
            confidence=0.90,
            requires_confirmation=True,
            is_destructive=False,
        )

    # ══════════════════════════════════════════════════════
    # FEE REMINDER
    # ══════════════════════════════════════════════════════

    def _parse_send_fee_reminder(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect fee reminder commands

        Examples:
        - "fee reminder bhejo sab parents ko"
        - "pending fee wale parents ko SMS karo"
        - "fee defaulters ko message karo"
        - "send fee reminder to all"
        - "WhatsApp karo fee pending walo ko"
        """
        fee_reminder_patterns = [
            'fee reminder',
            'fee.*sms', 'sms.*fee',
            'fee.*message', 'message.*fee',
            'fee.*whatsapp', 'whatsapp.*fee',
            'fee defaulter.*message',
            'pending fee.*send',
            'fee pending.*parents',
            'fee reminder bhejo',
            'fee walo ko',
        ]

        if not any(re.search(p, msg) for p in fee_reminder_patterns):
            return None

        # Channel
        channel = 'sms'
        if 'whatsapp' in msg:
            channel = 'whatsapp'
        elif 'email' in msg or 'mail' in msg:
            channel = 'email'

        cls     = self._extract_class(msg, context='from')
        section = self._extract_section(msg)

        return ParsedCommand(
            command_type=CommandType.SEND_FEE_REMINDER,
            params={
                'channel': channel,
                'class':   cls,
                'section': section,
                'scope':   'all_pending',
            },
            raw_message=original,
            confidence=0.90,
            requires_confirmation=True,
            is_destructive=False,
        )

    # ══════════════════════════════════════════════════════
    # NOTICE
    # ══════════════════════════════════════════════════════

    def _parse_send_notice(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect notice creation

        Examples:
        - "holiday notice create karo kal school band hai"
        - "exam notice bhejo class 10 ko"
        - "send notice to all parents"
        - "notice banao - sports day next week"
        """
        notice_patterns = [
            'notice banao', 'notice create',
            'notice bhejo', 'send notice',
            'notice likho', 'create notice',
            'notice post', 'notice dal',
            'announcement karo',
            'sabko batao',
        ]

        if not any(re.search(p, msg) for p in notice_patterns):
            return None

        # Target
        target = 'all'
        if 'parents' in msg or 'parent' in msg:
            target = 'parent'
        elif 'students' in msg or 'student' in msg:
            target = 'student'
        elif 'teachers' in msg or 'teacher' in msg:
            target = 'teacher'

        # Extract notice content from message
        content_match = re.search(
            r'[-–:]\s*(.+)$|notice\s+(?:that|ki|ke liye)\s+(.+)',
            msg, re.IGNORECASE
        )
        notice_hint = ''
        if content_match:
            notice_hint = (content_match.group(1) or content_match.group(2) or '').strip()

        cls = self._extract_class(msg, context='from')

        return ParsedCommand(
            command_type=CommandType.SEND_NOTICE,
            params={
                'target':       target,
                'class':        cls,
                'notice_hint':  notice_hint,
                'needs_content': True,
            },
            raw_message=original,
            confidence=0.85,
            requires_confirmation=True,
            is_destructive=False,
        )

    # ══════════════════════════════════════════════════════
    # BULK MESSAGE
    # ══════════════════════════════════════════════════════

    def _parse_send_message(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect general bulk message commands

        Examples:
        - "sab parents ko SMS bhejo - exam next week"
        - "class 10 ke parents ko WhatsApp karo"
        - "send SMS to all: school closed tomorrow"
        """
        message_patterns = [
            r'sab.*ko\s+(?:sms|message|whatsapp)\s+bhejo',
            r'(?:sms|message|whatsapp)\s+bhejo\s+sab',
            r'send\s+(?:sms|message|whatsapp)\s+to\s+all',
            r'all.*(?:parents|students).*(?:sms|message)',
            r'(?:parents|students)\s+ko\s+(?:sms|message|whatsapp)',
            r'bulk\s+(?:sms|message|whatsapp)',
        ]

        if not any(re.search(p, msg) for p in message_patterns):
            return None

        # Channel
        channel = 'sms'
        if 'whatsapp' in msg:
            channel = 'whatsapp'
        elif 'email' in msg:
            channel = 'email'

        # Target
        target = 'all'
        if 'parent' in msg:
            target = 'parents'
        elif 'student' in msg:
            target = 'students'
        elif 'teacher' in msg:
            target = 'teachers'

        # Content hint
        content_match = re.search(
            r'[-–:]\s*(.+)$|bhejo\s+ki\s+(.+)',
            original, re.IGNORECASE
        )
        content_hint = ''
        if content_match:
            content_hint = (content_match.group(1) or content_match.group(2) or '').strip()

        cls     = self._extract_class(msg, context='from')
        section = self._extract_section(msg)

        return ParsedCommand(
            command_type=CommandType.SEND_SMS,
            params={
                'channel':      channel,
                'target':       target,
                'class':        cls,
                'section':      section,
                'content_hint': content_hint,
                'needs_content': not bool(content_hint),
            },
            raw_message=original,
            confidence=0.80,
            requires_confirmation=True,
            is_destructive=False,
        )

    # ══════════════════════════════════════════════════════
    # MESSAGE TEMPLATE GENERATION
    # ══════════════════════════════════════════════════════

    def _parse_generate_message(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect message template generation request

        Examples:
        - "exam ke liye SMS template banao"
        - "holiday message likhna hai"
        - "fee reminder ke liye message suggest karo"
        - "sports day ka message draft karo"
        """
        generate_patterns = [
            'template banao', 'message banao',
            'message draft', 'draft karo',
            'message likhna hai', 'message suggest',
            'message generate', 'generate message',
            'sms template', 'whatsapp template',
            'message ka format', 'kya likhu',
            'kya likhna hai', 'message help',
        ]

        if not any(p in msg for p in generate_patterns):
            return None

        # What type of message
        msg_type = 'general'
        if any(w in msg for w in ['exam', 'test', 'result']):
            msg_type = 'exam'
        elif any(w in msg for w in ['holiday', 'band', 'closed', 'chutti']):
            msg_type = 'holiday'
        elif any(w in msg for w in ['fee', 'payment', 'fees']):
            msg_type = 'fee_reminder'
        elif any(w in msg for w in ['sports', 'event', 'function', 'program']):
            msg_type = 'event'
        elif any(w in msg for w in ['admit', 'admission']):
            msg_type = 'admission'
        elif any(w in msg for w in ['result', 'marks', 'report card']):
            msg_type = 'result'

        # Channel
        channel = 'sms'
        if 'whatsapp' in msg:
            channel = 'whatsapp'
        elif 'email' in msg:
            channel = 'email'

        return ParsedCommand(
            command_type=CommandType.GENERATE_MESSAGE,
            params={
                'message_type': msg_type,
                'channel':      channel,
                'topic':        original,
            },
            raw_message=original,
            confidence=0.85,
            requires_confirmation=False,
            is_destructive=False,
        )

    # ══════════════════════════════════════════════════════
    # STUDENT TRANSFER
    # ══════════════════════════════════════════════════════

    def _parse_transfer_student(
        self, msg: str, original: str
    ) -> Optional[ParsedCommand]:
        """
        Detect student transfer commands

        Examples:
        - "Rahul ko class 10A se 10B mein transfer karo"
        - "transfer student from section A to B"
        """
        transfer_patterns = [
            'transfer', 'badlo', 'section change',
            'move student', 'shift karo',
        ]

        if not any(p in msg for p in transfer_patterns):
            return None

        # Extract student name
        student_match = re.search(
            r'(?:transfer|move|shift)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            original
        )
        student_name = student_match.group(1) if student_match else None

        cls     = self._extract_class(msg, context='from')
        section = self._extract_section(msg)

        return ParsedCommand(
            command_type=CommandType.TRANSFER_STUDENT,
            params={
                'student_name': student_name,
                'class':        cls,
                'to_section':   section,
            },
            raw_message=original,
            confidence=0.75 if student_name else 0.5,
            requires_confirmation=True,
            is_destructive=False,
        )
    


    # ══════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════

    def _extract_from_to_classes(self, msg: str):
        """
        ✅ NEW: Extract both from_class and to_class in one pass
        
        Handles all patterns:
        - "class 10 to 11"          → from=10, to=11
        - "class 10 to class 11"    → from=10, to=11
        - "10 se 11 mein"           → from=10, to=11
        - "class 10 ko 11 mein"     → from=10, to=11
        - "promote class 10"        → from=10, to=None (auto-increment)
        """

        # ── Pattern 1: "class X to Y" or "class X to class Y" ──
        match = re.search(
            r'class\s*(\d+)\s*(?:to|→|se)\s*(?:class\s*)?(\d+)',
            msg, re.IGNORECASE
        )
        if match:
            return match.group(1), match.group(2)

        # ── Pattern 2: "X to Y" with numbers ──────────────────
        match = re.search(
            r'\b(\d+)\s*(?:to|→|se)\s*(\d+)\b',
            msg, re.IGNORECASE
        )
        if match:
            return match.group(1), match.group(2)

        # ── Pattern 3: "class X ko Y mein" ────────────────────
        match = re.search(
            r'class\s*(\d+)\s*(?:ko|ke)?\s*(\d+)\s*(?:mein|me)',
            msg, re.IGNORECASE
        )
        if match:
            return match.group(1), match.group(2)

        # ── Pattern 4: "Xth to Yth" ───────────────────────────
        match = re.search(
            r'(\d+)(?:th|st|nd|rd)?\s*(?:to|→|se)\s*(\d+)',
            msg, re.IGNORECASE
        )
        if match:
            return match.group(1), match.group(2)

        # ── Pattern 5: Single class mentioned (auto-increment) ─
        match = re.search(
            r'class\s*(\d+)',
            msg, re.IGNORECASE
        )
        if match:
            return match.group(1), None

        return None, None


    def _extract_class(self, msg: str, context: str = 'from') -> Optional[str]:
        """
        Extract class number from message
        Used for non-promotion commands (attendance, fee reminder etc.)
        """
        patterns = [
            r'class\s*(\d+)',
            r'(\d+)(?:th|st|nd|rd)?\s+class',
            r'klass\s*(\d+)',
            r'kaksha\s*(\d+)',
            r'std\s*(\d+)',
        ]

        if context == 'to':
            to_patterns = [
                r'to\s+class\s*(\d+)',
                r'mein\s+class\s*(\d+)',
                r'→\s*class\s*(\d+)',
                r'class\s*(\d+)\s*mein',
                # ✅ NEW: "to 11" without "class" keyword
                r'to\s+(\d+)\b',
                r'se\s+(\d+)\b',
            ]
            for pattern in to_patterns:
                match = re.search(pattern, msg, re.IGNORECASE)
                if match:
                    return match.group(1)

        all_classes = []
        for pattern in patterns:
            matches = re.findall(pattern, msg, re.IGNORECASE)
            all_classes.extend(matches)

        if all_classes:
            return all_classes[0] if context == 'from' else all_classes[-1]

        return None

    def _extract_section(self, msg: str) -> Optional[str]:
        """
        Extract section letter from message
        
        Examples:
        - "10A" → "A"
        - "section B" → "B"
        - "class 10 A" → "A"
        """
        patterns = [
            r'section\s*([A-E])',
            r'class\s*\d+\s*([A-E])',
            r'\b(\d+)([A-E])\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                return match.group(-1).upper()

        return None


# ══════════════════════════════════════════════════════════
# SINGLETON
# ══════════════════════════════════════════════════════════

_parser_instance = None

def get_command_parser() -> AdminCommandParser:
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = AdminCommandParser()
    return _parser_instance