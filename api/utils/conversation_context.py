# api/utils/conversation_context.py
"""
Conversation Context Manager
Tracks conversation topics and resolves follow-up questions

Example Flow:
User: "fee summary dikhao"
AI: "Pending: ₹50,000, Collected: ₹2,00,000"
[Context saved: topic='fee_summary', data={...}]

User: "kaun kaun pending hai?"
[Context resolved: "kaun kaun pending hai?" → "pending fees list dikhao"]
AI: Shows list of students with pending fees
"""

from typing import Dict, Optional, List
from datetime import datetime, timedelta
import re


class ConversationContext:
    """
    Manages conversation context for intelligent follow-ups
    
    Features:
    - Topic tracking
    - Pronoun resolution
    - Entity memory
    - Context expiry
    """
    
    def __init__(self, expiry_minutes: int = 30):
        """
        Args:
            expiry_minutes: Context expires after this duration
        """
        self.contexts: Dict[str, Dict] = {}
        self.expiry_minutes = expiry_minutes
    
    def set_context(
        self, 
        conv_id: str, 
        topic: str, 
        data: Dict,
        entities: Optional[Dict] = None
    ):
        """
        Save conversation context
        
        Args:
            conv_id: Conversation ID
            topic: Tool/topic name (e.g., 'fee_summary', 'attendance_today')
            data: Tool response data
            entities: Named entities (students, classes, etc.)
        """
        self.contexts[conv_id] = {
            'topic': topic,
            'data': data,
            'entities': entities or {},
            'timestamp': datetime.now(),
        }
        
        print(f"📝 Context saved: {conv_id[:8]} → {topic}")
    
    def get_context(self, conv_id: str) -> Optional[Dict]:
        """
        Get active context for conversation
        
        Returns:
            Context dict or None if expired/not found
        """
        context = self.contexts.get(conv_id)
        
        if not context:
            return None
        
        # Check expiry
        age = datetime.now() - context['timestamp']
        if age > timedelta(minutes=self.expiry_minutes):
            print(f"⏰ Context expired: {conv_id[:8]}")
            del self.contexts[conv_id]
            return None
        
        return context
    
    def clear_context(self, conv_id: str):
        """Clear context for conversation"""
        if conv_id in self.contexts:
            del self.contexts[conv_id]
            print(f"🗑️  Context cleared: {conv_id[:8]}")
    
    def resolve_message(
        self,
        message: str,
        conv_id: str,
        role:    str,
    ) -> tuple[str, bool]:
        """
        Resolve pronouns and context-dependent queries
        
        ✅ FIXED: Don't resolve if message is a new command/topic
        """
        context = self.get_context(conv_id)

        if not context:
            return message, False

        topic     = context['topic']
        data      = context['data']
        msg_lower = message.lower().strip()

        # ✅ CRITICAL FIX: Don't resolve if message is a clear new topic
        # These indicate user wants something NEW, not follow-up
        new_topic_signals = [
            # Action commands
            'bhejo', 'send', 'create', 'banao', 'mark',
            'promote', 'generate', 'dikhao', 'show',
            # Navigation
            'lets start', 'new task', 'new chat', 'start new',
            'nayi baat', 'alag kaam',
            # New questions with full context
            'school closed', 'holiday', 'exam', 'salary',
            'email to', 'sms to', 'message to',
            'sab parents', 'all parents', 'all students',
        ]

        # ✅ If message clearly starts a new topic, don't resolve
        if any(signal in msg_lower for signal in new_topic_signals):
            # But allow follow-ups like "kaun kaun?" or "list dikhao"
            # Only block if message has meaningful new content
            word_count = len(msg_lower.split())
            if word_count > 3:  # Short messages = follow-ups, Long = new topic
                return message, False

        # ✅ Don't resolve pending_command context
        # It's handled separately in portal_chat.py
        if topic == 'pending_command':
            return message, False

        # ── Pronoun Resolution ─────────────────────────────
        # (rest of existing code stays same)
        
        # ── "kaun kaun?" / "who?" ─────────────────────────
        if self._is_pronoun_query(msg_lower, ['kaun', 'who', 'kon']):
            if topic == 'get_fee_summary':
                return "pending fees list dikhao", True
            if topic == 'get_attendance_today':
                if data.get('absent', 0) > 0:
                    return "absent students kaun hain", True
            if topic == 'get_student_count':
                return "students ki list dikhao", True

        # ── "kitne?" / "how many?" ────────────────────────
        if self._is_pronoun_query(msg_lower, ['kitne', 'how many', 'kitna']):
            if topic == 'get_fee_summary':
                if any(w in msg_lower for w in ['pending', 'baaki', 'due']):
                    return "total pending fee kitni hai", True
                if any(w in msg_lower for w in ['collect', 'aaya', 'paid']):
                    return "total collected fee kitni hai", True
            if topic == 'get_attendance_today':
                if any(w in msg_lower for w in ['absent', 'nahi', 'missing']):
                    return "aaj kitne absent hain", True
                if any(w in msg_lower for w in ['present', 'aaye', 'came']):
                    return "aaj kitne present hain", True
            if topic == 'get_student_count':
                return "total students kitne hain", True

        # ── "list dikhao" ─────────────────────────────────
        if self._is_list_query(msg_lower):
            # ✅ FIX: Only resolve if it's ambiguous (no other context)
            # Don't resolve if user has new topic in message
            if topic == 'get_fee_summary':
                return "pending fees ki list dikhao", True
            if topic == 'get_attendance_today':
                return "absent students ki list", True

        # ── "details" ─────────────────────────────────────
        if self._is_details_query(msg_lower):
            if topic == 'get_school_stats':
                return "aaj ki attendance dikhao", True
            if topic == 'get_attendance_today':
                return "absent students kaun hain", True

        # ── "send SMS" after attendance ───────────────────
        if self._is_action_query(msg_lower, ['sms', 'message', 'bhejo', 'send']):
            if topic == 'get_attendance_today':
                absent = data.get('absent', 0)
                if absent > 0:
                    # ✅ FIX: Only if message is short/ambiguous
                    word_count = len(msg_lower.split())
                    if word_count <= 5:
                        return f"send sms to {absent} absent students", True
        
        # ══════════════════════════════════════════════════
        # ENTITY RESOLUTION
        # ══════════════════════════════════════════════════
        
        # Remember entities (class, student name, etc.)
        entities = context.get('entities', {})
        
        # If asking about "iska" / "uska" / "this" / "that"
        if self._has_pronoun_reference(msg_lower):
            last_student = entities.get('last_student')
            last_class = entities.get('last_class')
            
            if last_student and any(w in msg_lower for w in ['iska', 'uska', 'his', 'her']):
                resolved = message.replace('iska', last_student).replace('uska', last_student)
                print(f"🔄 Resolved: '{message}' → '{resolved}'")
                return resolved, True
            
            if last_class and 'class' not in msg_lower:
                resolved = f"{message} class {last_class}"
                print(f"🔄 Resolved: '{message}' → '{resolved}'")
                return resolved, True
        
        # No resolution needed
        return message, False
    
    # ══════════════════════════════════════════════════════
    # HELPER METHODS
    # ══════════════════════════════════════════════════════
    
    def _is_pronoun_query(self, msg: str, pronouns: List[str]) -> bool:
        """Check if message is a pronoun query"""
        # Must start with or only contain pronoun
        words = msg.split()
        
        # Single word query
        if len(words) == 1:
            return words[0] in pronouns
        
        # Starts with pronoun
        if words[0] in pronouns:
            return True
        
        # Contains pronoun + question word
        has_pronoun = any(p in words for p in pronouns)
        has_question = any(w in words for w in ['hai', 'hain', 'kya', '?'])
        
        return has_pronoun and has_question
    
    def _is_list_query(self, msg: str) -> bool:
        """Check if asking for list"""
        list_keywords = [
            'list', 'dikhao', 'show', 'batao', 'tell',
            'names', 'naam', 'sab', 'all', 'kon kon'
        ]
        return any(kw in msg for kw in list_keywords)
    
    def _is_details_query(self, msg: str) -> bool:
        """Check if asking for more details"""
        detail_keywords = [
            'detail', 'zyada', 'more', 'full', 'complete',
            'aur', 'bhi', 'explain', 'samjhao'
        ]
        return any(kw in msg for kw in detail_keywords)
    
    def _is_action_query(self, msg: str, actions: List[str]) -> bool:
        """Check if requesting an action"""
        return any(action in msg for action in actions)
    
    def _has_pronoun_reference(self, msg: str) -> bool:
        """Check if message has pronoun reference"""
        pronouns = ['iska', 'uska', 'yeh', 'woh', 'this', 'that', 'his', 'her']
        return any(p in msg for p in pronouns)
    
    def extract_entities(self, message: str, data: Dict) -> Dict:
        """
        Extract entities from message and data
        
        Returns:
            Dictionary of entities (student_name, class, etc.)
        """
        entities = {}
        
        # Extract class mentions
        class_match = re.search(r'\bclass\s*(\d+|[A-Z])', message, re.IGNORECASE)
        if class_match:
            entities['last_class'] = class_match.group(1)
        
        # Extract student names (if in data)
        if 'student_name' in data:
            entities['last_student'] = data['student_name']
        
        # Extract from absent_students list
        if 'absent_students' in data and data['absent_students']:
            entities['absent_students'] = [s['name'] for s in data['absent_students']]
        
        return entities
    
    def get_stats(self) -> Dict:
        """Get context manager statistics"""
        active = len(self.contexts)
        
        # Count by topic
        topics = {}
        for ctx in self.contexts.values():
            topic = ctx['topic']
            topics[topic] = topics.get(topic, 0) + 1
        
        return {
            'active_contexts': active,
            'by_topic': topics,
            'expiry_minutes': self.expiry_minutes
        }