# api/utils/smart_suggestions.py
"""
Smart Suggestions Engine
Generates contextual quick action buttons based on AI responses

Features:
- Context-aware suggestions
- Role-based actions
- Priority scoring
- Action metadata for frontend
"""

from typing import List, Dict, Optional


class SmartSuggestions:
    """
    Generate smart action suggestions based on tool responses
    
    Analyzes tool data and generates relevant next-step actions
    """
    
    def __init__(self):
        # Action templates by tool
        self.action_templates = self._init_action_templates()
    
    def get_suggestions(
        self,
        tool: str,
        data: Dict,
        role: str,
        max_suggestions: int = 4
    ) -> List[Dict]:
        """
        Generate smart suggestions for a tool response
        
        Args:
            tool: Tool name (e.g., 'get_attendance_today')
            data: Tool response data
            role: User role
            max_suggestions: Maximum suggestions to return
        
        Returns:
            List of suggestion dicts with text, action, priority
        """
        suggestions = []
        
        # Get role-specific suggestions
        if role == 'admin' or role == 'staff':
            suggestions = self._admin_suggestions(tool, data)
        elif role == 'teacher':
            suggestions = self._teacher_suggestions(tool, data)
        elif role == 'student':
            suggestions = self._student_suggestions(tool, data)
        elif role == 'parent':
            suggestions = self._parent_suggestions(tool, data)
        elif role == 'superadmin':
            suggestions = self._superadmin_suggestions(tool, data)
        
        # Sort by priority (higher first)
        suggestions.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        # Return top N
        return suggestions[:max_suggestions]
    
    # ══════════════════════════════════════════════════════
    # ADMIN SUGGESTIONS
    # ══════════════════════════════════════════════════════
    
    def _admin_suggestions(self, tool: str, data: Dict) -> List[Dict]:
        """Generate admin-specific suggestions"""
        suggestions = []
        
        # ── Attendance Today ──────────────────────────────
        if tool == 'get_attendance_today':
            absent = data.get('absent', 0)
            percentage = data.get('percentage', 100)
            
            # High priority: Send SMS to absent students
            if absent > 0:
                suggestions.append({
                    'text': f'📨 Send SMS to {absent} absent students',
                    'action': 'send_absent_sms',
                    'icon': '📨',
                    'priority': 10,
                    'params': {
                        'count': absent,
                        'date': data.get('date_str', '')
                    },
                    'color': 'blue'
                })
            
            # Low attendance alert
            if percentage < 75:
                suggestions.append({
                    'text': '⚠️ Send low attendance alert',
                    'action': 'send_low_attendance_alert',
                    'icon': '⚠️',
                    'priority': 9,
                    'params': {'percentage': percentage},
                    'color': 'orange'
                })
            
            # Always show download option
            suggestions.append({
                'text': '📊 Download attendance report',
                'action': 'download_attendance_report',
                'icon': '📊',
                'priority': 7,
                'params': {'date': data.get('date_str', '')},
                'color': 'green'
            })
            
            # Mark late entries
            not_marked = data.get('not_marked', 0)
            if not_marked > 0:
                suggestions.append({
                    'text': f'⏰ Mark {not_marked} pending entries',
                    'action': 'mark_pending_attendance',
                    'icon': '⏰',
                    'priority': 8,
                    'params': {'count': not_marked},
                    'color': 'yellow'
                })
        
        # ── Fee Summary ───────────────────────────────────
        if tool == 'get_fee_summary':
            overdue = data.get('overdue_count', 0)
            partial = data.get('partial_count', 0)
            pending = data.get('total_pending', 0)
            
            # Call overdue parents
            if overdue > 0:
                suggestions.append({
                    'text': f'📞 Call {overdue} overdue parents',
                    'action': 'call_overdue_parents',
                    'icon': '📞',
                    'priority': 10,
                    'params': {'count': overdue},
                    'color': 'red'
                })
            
            # Send fee reminder
            if pending > 0:
                suggestions.append({
                    'text': '💬 Send fee reminder SMS',
                    'action': 'send_fee_reminder',
                    'icon': '💬',
                    'priority': 9,
                    'params': {'amount': pending},
                    'color': 'orange'
                })
            
            # Download report
            suggestions.append({
                'text': '📊 Download fee report',
                'action': 'download_fee_report',
                'icon': '📊',
                'priority': 7,
                'params': {},
                'color': 'green'
            })
            
            # Follow up partial payments
            if partial > 0:
                suggestions.append({
                    'text': f'💰 Follow {partial} partial payments',
                    'action': 'follow_partial_payments',
                    'icon': '💰',
                    'priority': 8,
                    'params': {'count': partial},
                    'color': 'yellow'
                })
        
        # ── Pending Fees List ─────────────────────────────
        if tool == 'get_pending_fees':
            count = data.get('count', 0)
            
            if count > 0:
                suggestions.append({
                    'text': f'📨 Send reminder to {count} parents',
                    'action': 'send_fee_reminder_bulk',
                    'icon': '📨',
                    'priority': 10,
                    'params': {'count': count},
                    'color': 'blue'
                })
                
                suggestions.append({
                    'text': '📄 Generate fee receipts',
                    'action': 'generate_fee_receipts',
                    'icon': '📄',
                    'priority': 8,
                    'params': {},
                    'color': 'green'
                })
        
        # ── School Stats ──────────────────────────────────
        if tool == 'get_school_stats':
            suggestions.append({
                'text': '📊 View detailed analytics',
                'action': 'view_analytics_dashboard',
                'icon': '📊',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
            
            suggestions.append({
                'text': '📈 Generate monthly report',
                'action': 'generate_monthly_report',
                'icon': '📈',
                'priority': 7,
                'params': {},
                'color': 'green'
            })
        
        # ── Student Count ─────────────────────────────────
        if tool == 'get_student_count':
            suggestions.append({
                'text': '📋 Export student list',
                'action': 'export_student_list',
                'icon': '📋',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
            
            suggestions.append({
                'text': '➕ Add new student',
                'action': 'add_student',
                'icon': '➕',
                'priority': 6,
                'params': {},
                'color': 'green'
            })
        
        # ── Staff Count ───────────────────────────────────
        if tool == 'get_staff_count':
            suggestions.append({
                'text': '📋 View staff details',
                'action': 'view_staff_list',
                'icon': '📋',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
            
            suggestions.append({
                'text': '➕ Add new staff',
                'action': 'add_staff',
                'icon': '➕',
                'priority': 6,
                'params': {},
                'color': 'green'
            })
        
        # ── Recent Notices ────────────────────────────────
        if tool == 'get_recent_notices':
            suggestions.append({
                'text': '📝 Create new notice',
                'action': 'create_notice',
                'icon': '📝',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
            
            suggestions.append({
                'text': '📢 Send notice to all',
                'action': 'broadcast_notice',
                'icon': '📢',
                'priority': 7,
                'params': {},
                'color': 'green'
            })
        
        return suggestions
    
    # ══════════════════════════════════════════════════════
    # TEACHER SUGGESTIONS
    # ══════════════════════════════════════════════════════
    
    def _teacher_suggestions(self, tool: str, data: Dict) -> List[Dict]:
        """Generate teacher-specific suggestions"""
        suggestions = []
        
        # ── My Class Attendance ───────────────────────────
        if tool == 'get_my_class_attendance_today':
            is_marked = data.get('is_marked', False)
            
            if not is_marked:
                suggestions.append({
                    'text': '✅ Mark attendance now',
                    'action': 'mark_attendance',
                    'icon': '✅',
                    'priority': 10,
                    'params': {},
                    'color': 'blue'
                })
            else:
                absent = data.get('absent', 0)
                if absent > 0:
                    suggestions.append({
                        'text': f'📨 Notify {absent} absent parents',
                        'action': 'notify_absent_parents',
                        'icon': '📨',
                        'priority': 9,
                        'params': {'count': absent},
                        'color': 'orange'
                    })
                
                suggestions.append({
                    'text': '📊 View attendance history',
                    'action': 'view_attendance_history',
                    'icon': '📊',
                    'priority': 7,
                    'params': {},
                    'color': 'green'
                })
        
        # ── My Students ───────────────────────────────────
        if tool == 'get_my_students':
            total = data.get('total', 0)
            
            suggestions.append({
                'text': '✅ Mark today\'s attendance',
                'action': 'mark_attendance',
                'icon': '✅',
                'priority': 9,
                'params': {},
                'color': 'blue'
            })
            
            suggestions.append({
                'text': '📝 Assign homework',
                'action': 'assign_homework',
                'icon': '📝',
                'priority': 8,
                'params': {},
                'color': 'green'
            })
            
            if total > 0:
                suggestions.append({
                    'text': '📊 Enter marks',
                    'action': 'enter_marks',
                    'icon': '📊',
                    'priority': 7,
                    'params': {},
                    'color': 'purple'
                })
        
        # ── Pending Homework ──────────────────────────────
        if tool == 'get_pending_homework':
            count = data.get('count', 0)
            
            suggestions.append({
                'text': '📝 Create new homework',
                'action': 'create_homework',
                'icon': '📝',
                'priority': 9,
                'params': {},
                'color': 'blue'
            })
            
            if count > 0:
                suggestions.append({
                    'text': f'✅ Check {count} submissions',
                    'action': 'check_homework_submissions',
                    'icon': '✅',
                    'priority': 8,
                    'params': {'count': count},
                    'color': 'green'
                })
        
        return suggestions
    
    # ══════════════════════════════════════════════════════
    # STUDENT SUGGESTIONS
    # ══════════════════════════════════════════════════════
    
    def _student_suggestions(self, tool: str, data: Dict) -> List[Dict]:
        """Generate student-specific suggestions"""
        suggestions = []
        
        # ── My Attendance ─────────────────────────────────
        if tool == 'get_my_attendance':
            percentage_str = data.get('attendance_percentage', '0%')
            percentage = int(percentage_str.replace('%', ''))
            
            suggestions.append({
                'text': '📅 View full calendar',
                'action': 'view_attendance_calendar',
                'icon': '📅',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
            
            if percentage < 75:
                suggestions.append({
                    'text': '📈 Improve attendance tips',
                    'action': 'attendance_tips',
                    'icon': '📈',
                    'priority': 9,
                    'params': {},
                    'color': 'orange'
                })
        
        # ── My Fees ───────────────────────────────────────
        if tool == 'get_my_fees':
            pending_count = data.get('pending_count', 0)
            
            if pending_count > 0:
                suggestions.append({
                    'text': '💳 Pay fees online',
                    'action': 'pay_fees_online',
                    'icon': '💳',
                    'priority': 10,
                    'params': {},
                    'color': 'blue'
                })
                
                suggestions.append({
                    'text': '📄 Download fee structure',
                    'action': 'download_fee_structure',
                    'icon': '📄',
                    'priority': 7,
                    'params': {},
                    'color': 'green'
                })
            else:
                suggestions.append({
                    'text': '📄 Download receipts',
                    'action': 'download_receipts',
                    'icon': '📄',
                    'priority': 8,
                    'params': {},
                    'color': 'green'
                })
        
        # ── My Homework ───────────────────────────────────
        if tool == 'get_my_homework':
            pending = data.get('pending_count', 0)
            
            if pending > 0:
                suggestions.append({
                    'text': f'📚 Start {pending} pending tasks',
                    'action': 'view_homework_details',
                    'icon': '📚',
                    'priority': 10,
                    'params': {},
                    'color': 'blue'
                })
                
                suggestions.append({
                    'text': '❓ Get AI help',
                    'action': 'homework_ai_help',
                    'icon': '❓',
                    'priority': 9,
                    'params': {},
                    'color': 'purple'
                })
        
        # ── My Notices ────────────────────────────────────
        if tool == 'get_my_notices':
            suggestions.append({
                'text': '📢 View all notices',
                'action': 'view_all_notices',
                'icon': '📢',
                'priority': 7,
                'params': {},
                'color': 'blue'
            })
        
        return suggestions
    
    # ══════════════════════════════════════════════════════
    # PARENT SUGGESTIONS
    # ══════════════════════════════════════════════════════
    
    def _parent_suggestions(self, tool: str, data: Dict) -> List[Dict]:
        """Generate parent-specific suggestions"""
        suggestions = []
        
        # ── Child Attendance ──────────────────────────────
        if tool == 'get_child_attendance':
            percentage_str = data.get('percentage', '0%')
            percentage = int(percentage_str.replace('%', ''))
            
            if percentage < 75:
                suggestions.append({
                    'text': '📞 Talk to class teacher',
                    'action': 'contact_teacher',
                    'icon': '📞',
                    'priority': 10,
                    'params': {},
                    'color': 'orange'
                })
            
            suggestions.append({
                'text': '📅 View attendance report',
                'action': 'view_attendance_report',
                'icon': '📅',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
        
        # ── Child Fees ────────────────────────────────────
        if tool == 'get_child_fees':
            pending_count = data.get('pending_count', 0)
            
            if pending_count > 0:
                suggestions.append({
                    'text': '💳 Pay fees now',
                    'action': 'pay_fees_online',
                    'icon': '💳',
                    'priority': 10,
                    'params': {},
                    'color': 'blue'
                })
                
                suggestions.append({
                    'text': '📞 Request fee waiver',
                    'action': 'request_fee_waiver',
                    'icon': '📞',
                    'priority': 7,
                    'params': {},
                    'color': 'green'
                })
            
            suggestions.append({
                'text': '📄 Download receipts',
                'action': 'download_receipts',
                'icon': '📄',
                'priority': 8,
                'params': {},
                'color': 'purple'
            })
        
        # ── Child Notices ─────────────────────────────────
        if tool == 'get_child_notices':
            suggestions.append({
                'text': '📢 View all notices',
                'action': 'view_all_notices',
                'icon': '📢',
                'priority': 8,
                'params': {},
                'color': 'blue'
            })
            
            suggestions.append({
                'text': '📞 Contact school',
                'action': 'contact_school',
                'icon': '📞',
                'priority': 7,
                'params': {},
                'color': 'green'
            })
        
        return suggestions
    
    # ══════════════════════════════════════════════════════
    # SUPERADMIN SUGGESTIONS
    # ══════════════════════════════════════════════════════
    
    def _superadmin_suggestions(self, tool: str, data: Dict) -> List[Dict]:
        """Generate superadmin-specific suggestions"""
        suggestions = []
        
        # ── Platform Stats ────────────────────────────────
        if tool == 'get_platform_stats':
            trial_schools = data.get('trial_schools', 0)
            
            suggestions.append({
                'text': '📊 View detailed analytics',
                'action': 'view_analytics_dashboard',
                'icon': '📊',
                'priority': 9,
                'params': {},
                'color': 'blue'
            })
            
            if trial_schools > 0:
                suggestions.append({
                    'text': f'🎯 Convert {trial_schools} trials',
                    'action': 'view_trial_schools',
                    'icon': '🎯',
                    'priority': 10,
                    'params': {},
                    'color': 'orange'
                })
        
        # ── Expiring Trials ───────────────────────────────
        if tool == 'get_expiring_trials':
            count = data.get('count', 0)
            
            if count > 0:
                suggestions.append({
                    'text': f'📞 Call {count} schools',
                    'action': 'call_expiring_schools',
                    'icon': '📞',
                    'priority': 10,
                    'params': {'count': count},
                    'color': 'red'
                })
                
                suggestions.append({
                    'text': '📧 Send discount offers',
                    'action': 'send_discount_offers',
                    'icon': '📧',
                    'priority': 9,
                    'params': {},
                    'color': 'orange'
                })
        
        # ── Revenue Summary ───────────────────────────────
        if tool == 'get_revenue_summary':
            suggestions.append({
                'text': '📈 Export revenue report',
                'action': 'export_revenue_report',
                'icon': '📈',
                'priority': 8,
                'params': {},
                'color': 'green'
            })
        
        return suggestions
    
    def _init_action_templates(self) -> Dict:
        """Initialize action templates (for future use)"""
        return {
            # Can add pre-defined templates here if needed
        }


# ══════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ══════════════════════════════════════════════════════════

_smart_suggestions_instance = None

def get_smart_suggestions() -> SmartSuggestions:
    """Get SmartSuggestions singleton"""
    global _smart_suggestions_instance
    if _smart_suggestions_instance is None:
        _smart_suggestions_instance = SmartSuggestions()
    return _smart_suggestions_instance