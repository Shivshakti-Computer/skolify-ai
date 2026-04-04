# api/routes/chat.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Tuple
import uuid
from ..dependencies import get_embedding_model, get_collection, get_conversation, update_conversation
from ..config import settings

router = APIRouter(prefix="/api", tags=["chat"])

# ══════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    conversation_id: Optional[str] = None

class Source(BaseModel):
    text: str
    url: str
    page_type: str
    relevance_score: float

class ChatResponse(BaseModel):
    success: bool
    answer: str
    sources: List[Source]
    conversation_id: str
    metadata: Dict

# ══════════════════════════════════════════════════════════
# Conversation Context Analyzer
# ══════════════════════════════════════════════════════════

def analyze_context(message: str, conversation: Dict) -> Dict:
    """Analyze message in context of conversation"""
    
    msg_lower = message.lower().strip()
    context = conversation.get('context', {})
    last_messages = conversation.get('messages', [])
    
    result = {
        'requires_context': False,
        'intent': None,
        'referenced_topic': None,
        'expecting_choice': False
    }
    
    # Affirmative/negative responses
    affirmative_words = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'han', 'haan', 'ha', 'y']
    negative_words = ['no', 'nah', 'nope', 'nahi', 'na', 'n']
    
    if msg_lower in affirmative_words:
        result['requires_context'] = True
        result['is_affirmative'] = True
        
        if last_messages:
            last_ai = last_messages[-1].get('ai', '').lower()
            last_context = context.get('last_topic', '')
            
            if 'want me to suggest' in last_ai or context.get('asked_for_suggestion'):
                result['intent'] = 'confirm_plan_suggestion'
            elif 'ready to start' in last_ai or context.get('ready_to_start'):
                result['intent'] = 'confirm_start_trial'
            elif 'want to know more' in last_ai:
                result['intent'] = 'confirm_learn_more'
            elif 'pricing' in last_ai or last_context == 'about_skolify':
                result['intent'] = 'pricing'
            elif 'specific features' in last_ai or last_context == 'about_skolify':
                result['intent'] = 'features'
    
    elif msg_lower in negative_words:
        result['requires_context'] = True
        result['is_affirmative'] = False
    
    # Plan selection
    elif any(word in msg_lower for word in ['i want', 'i need', 'i choose', 'select', 'go with']):
        if 'starter' in msg_lower:
            result['intent'] = 'select_plan'
            result['selected_plan'] = 'starter'
        elif 'growth' in msg_lower:
            result['intent'] = 'select_plan'
            result['selected_plan'] = 'growth'
        elif 'pro' in msg_lower:
            result['intent'] = 'select_plan'
            result['selected_plan'] = 'pro'
        elif 'enterprise' in msg_lower:
            result['intent'] = 'select_plan'
            result['selected_plan'] = 'enterprise'
    
    # School size mention
    elif context.get('expecting_school_size'):
        import re
        numbers = re.findall(r'\d+', msg_lower)
        if numbers:
            student_count = int(numbers[0])
            result['intent'] = 'suggest_plan_by_size'
            result['student_count'] = student_count
    
    # Contextual references
    elif any(word in msg_lower for word in ['this', 'that', 'it', 'ye', 'wo', 'isse', 'usse']):
        result['requires_context'] = True
        result['has_pronoun_reference'] = True
        if context.get('last_topic'):
            result['referenced_topic'] = context['last_topic']
    
    # Follow-up questions
    elif msg_lower.startswith(('and', 'also', 'what about', 'how about', 'aur')):
        result['requires_context'] = True
        result['is_follow_up'] = True
    
    return result

# ══════════════════════════════════════════════════════════
# Intent Detection
# ══════════════════════════════════════════════════════════

def detect_intent(question: str, context_analysis: Dict) -> Optional[str]:
    """Detect user intent with better pattern matching"""
    q = question.lower().strip()
    
    # Handle contextual intents first
    if context_analysis.get('intent'):
        return context_analysis['intent']
    
    # Normalize
    q = q.replace('?', '').replace('.', '').strip()
    
    # PRICING
    pricing_patterns = [
        'price', 'pricing', 'cost', 'kitna', 'kitne',
        'plan', 'plans', 'how much', 'charge', 'fee',
        'subscription', 'monthly', 'yearly', 'paisa',
        'rupees', 'rupee', '₹', 'rs', 'paise',
        'pricing model', 'pricing plan', 'price list',
        'tell me about pric', 'what are your pric',
        'how much does', 'kya price', 'kya cost'
    ]
    if any(pattern in q for pattern in pricing_patterns):
        return "pricing"
    
    # GREETINGS
    greeting_patterns = ['hello', 'hi', 'hey', 'namaste', 'namaskar', 'hola', 'hii', 'hlo']
    if any(q.startswith(greet) for greet in greeting_patterns) or q in greeting_patterns:
        return "greeting"
    
    # WHO AM I
    identity_patterns = [
        'who are you', 'what are you', 'introduce yourself',
        'kaun ho', 'kaun ho tum', 'tum kaun', 'you are',
        'tell me about yourself', 'about you'
    ]
    if any(pattern in q for pattern in identity_patterns):
        return "who_am_i"
    
    # ABOUT SKOLIFY
    about_patterns = [
        'what is skolify', 'kya hai skolify', 'skolify kya hai',
        'about skolify', 'tell me about skolify', 'skolify ke bare',
        'what does skolify', 'skolify kya karta'
    ]
    if any(pattern in q for pattern in about_patterns):
        return "what_is_skolify"
    
    # FEATURES
    feature_patterns = [
        'feature', 'features', 'module', 'modules',
        'kya kya', 'what all', 'what can', 'capabilities',
        'functions', 'functionality', 'kya kar sakta',
        'kya hota hai', 'services', 'offer'
    ]
    if any(pattern in q for pattern in feature_patterns):
        return "features"
    
    # FREE TRIAL
    trial_patterns = [
        'trial', 'free trial', 'demo', 'test',
        'try', 'free', 'without pay', 'bina paise'
    ]
    if any(pattern in q for pattern in trial_patterns):
        return "free_trial"
    
    # GETTING STARTED
    start_patterns = [
        'how to start', 'getting started', 'kaise shuru',
        'setup', 'onboard', 'begin', 'register',
        'sign up', 'kaise use', 'how to use'
    ]
    if any(pattern in q for pattern in start_patterns):
        return "getting_started"
    
    # SUPPORT
    support_patterns = [
        'support', 'help', 'contact', 'reach',
        'call', 'email', 'phone', 'whatsapp',
        'madad', 'sahayata', 'talk to', 'connect'
    ]
    if any(pattern in q for pattern in support_patterns):
        return "support"
    
    return None

# ══════════════════════════════════════════════════════════
# Response Templates
# ══════════════════════════════════════════════════════════

def get_response_for_intent(intent: str, context: Dict = None) -> Tuple[Optional[str], Dict]:
    """Get response and updated context for intent"""
    
    if context is None:
        context = {}
    
    if intent == "greeting":
        response = """Hey there! 👋 I'm the **Skolify Assistant** — happy to help you out!

Whether you're a school admin, teacher, student, or parent, I've got answers ready for you.

**Here's what I can help with:**

• 💰 **Plans & Pricing** — find the right plan for your school
• 🎁 **Free Trial** — 60 days, no credit card needed
• 💳 **Credits System** — SMS, WhatsApp & email messaging
• 📦 **Features** — 22+ modules available
• 🔧 **Setup Help** — get your school running in 15 minutes
• 🔒 **Security & Privacy** — how we protect your data

What would you like to know? Go ahead and ask — I don't bite! 😄"""
        return response, {'last_topic': 'greeting', 'stage': 'initial'}
    
    elif intent == "who_am_i":
        response = """Hey! I'm the **Skolify AI Assistant** 🤖

Think of me as your friendly guide to everything Skolify!

**What I do:**
• Answer your questions about Skolify (pricing, features, setup)
• Help you pick the right plan for your school
• Guide you through getting started
• Connect you with our team when needed

**What I DON'T do:**
• Access your school's private data
• Make changes to your account
• Process payments (that's done securely through your admin panel)

**I'm here 24/7** to help you explore Skolify and make the right decision for your school!

What would you like to know about Skolify?"""
        return response, {'last_topic': 'intro', 'stage': 'engaged'}
    
    elif intent == "what_is_skolify":
        response = """Hey! Great question! 👋

**Skolify** is basically your school's digital backbone — think of it as having a super-organized assistant that never sleeps!

**Here's what it does:**

🎓 **Manages everything** — students, teachers, classes, all in one place
📱 **Works on any device** — phone, tablet, computer (no app download needed!)
💰 **Handles payments** — parents can pay fees online via UPI, cards, whatever
📊 **Tracks everything** — attendance, marks, homework, you name it
🌐 **Builds your website** — yes, a professional school website with zero coding
📨 **Auto-notifications** — SMS/WhatsApp to parents when kid is absent

**The best part?** You get a **60-day free trial** to test everything. No credit card, no strings attached!

Want to know about pricing, or see specific features?"""
        return response, {'last_topic': 'about_skolify', 'stage': 'interested', 'asked_about_features': True}
    
    elif intent == "pricing":
        response = """Let's talk pricing! And honestly, it's pretty straightforward:

**Quick breakdown by school size:**

**Got 100-500 students?**
→ **Starter** (₹499/mo) is perfect
→ That's literally ₹1/student/month!

**Got 500-1,000 students?**
→ **Growth** (₹999/mo) is the sweet spot
→ Includes online payments, exams, everything
→ Most schools pick this one ⭐

**Got 1,000-3,000 students?**
→ **Pro** (₹1,999/mo) for advanced features
→ Library, online classes, custom certificates

**Multiple branches or 5,000+ students?**
→ **Enterprise** (₹3,999/mo)
→ Unlimited everything, dedicated support

**All plans include:**
✓ 60-day free trial (seriously, try before you buy!)
✓ No setup fees
✓ Upgrade/downgrade anytime
✓ Free credits for SMS/WhatsApp

**Annual billing:** Pay for 10 months, get 12! (2 months free)

**Tell me your school size and I'll suggest the perfect plan!** Or want to see detailed features of each plan?"""
        return response, {'last_topic': 'pricing', 'stage': 'considering', 'asked_for_suggestion': True}
    
    elif intent == "confirm_plan_suggestion":
        response = """Perfect! Let me help you choose! 😊

**Quick questions:**

**1. How many students do you have?**
   - Under 500
   - 500-1,500
   - 1,500-5,000
   - 5,000+

**2. What's most important for you?**
   - Just the basics (attendance, fees)
   - Online fee collection
   - Complete exam/result management
   - Advanced features (library, online classes)

**Or just tell me:**
"I have [X] students and mainly need [feature]"

I'll suggest the perfect plan! 👍"""
        return response, {'last_topic': 'plan_selection', 'stage': 'gathering_requirements', 'expecting_school_size': True}
    
    elif intent == "suggest_plan_by_size":
        student_count = context.get('student_count', 500)
        
        if student_count <= 500:
            suggested_plan = "Starter"
            price = "₹499/month"
            reason = "Perfect for small schools with basic needs"
        elif student_count <= 1500:
            suggested_plan = "Growth"
            price = "₹999/month"
            reason = "Best balance of features and price"
        elif student_count <= 5000:
            suggested_plan = "Pro"
            price = "₹1,999/month"
            reason = "Advanced features for larger schools"
        else:
            suggested_plan = "Enterprise"
            price = "₹3,999/month"
            reason = "Unlimited capacity for large institutions"
        
        response = f"""Perfect! With **{student_count} students**, I'd recommend the **{suggested_plan} Plan**! 

**Why {suggested_plan}?**
{reason}

**Price:** {price}
**Capacity:** {"Up to " + str(student_count * 2) if student_count <= 2500 else "Unlimited"} students

**What you get:**"""
        
        if suggested_plan == "Starter":
            response += """
• Student & Teacher Management
• Attendance with auto SMS
• School Website Builder
• Notice Board
• 500 free SMS credits/month"""
        elif suggested_plan == "Growth":
            response += """
• Everything in Starter, PLUS:
• Online Fee Collection (UPI, cards)
• Exam & Results Management
• Homework System
• Timetable
• 1,500 credits/month"""
        elif suggested_plan == "Pro":
            response += """
• Everything in Growth, PLUS:
• Library Management
• Online Classes (LMS)
• Custom Certificates
• 3,000 credits/month"""
        else:
            response += """
• Everything in Pro, PLUS:
• HR & Payroll
• Transport Management
• Hostel Management
• Multi-branch Support
• 10,000 credits (never expire!)"""
        
        response += f"""

**Want to go with {suggested_plan}?** Or want to compare with other plans?

Ready to start your **60-day free trial**? 🎁"""
        
        return response, {
            'last_topic': 'plan_suggested',
            'suggested_plan': suggested_plan.lower(),
            'student_count': student_count,
            'stage': 'plan_recommendation',
            'ready_for_selection': True
        }
    
    elif intent == "features":
        response = """Ooh, features! This is where Skolify really shines! ✨

**📚 Core Features (All Plans):**

• **Student Management** — Bulk import, ID cards, profiles
• **Attendance** — Mark in 2 mins, auto parent SMS
• **School Website** — Professional site, zero coding
• **Notice Board** — Instant announcements
• **Photo Gallery** — Organized albums

**💰 Growth Plan & Above:**

• **Online Fee Collection** — UPI, cards, auto-receipts
• **Exams & Results** — Grade cards, parent access
• **Homework System** — Digital assignments
• **Timetable** — Automated scheduling
• **Certificates** — TC, CC, Bonafide

**🎓 Pro Plan & Above:**

• **Library Management** — Book tracking
• **Online Classes** — Video lessons, quizzes
• **Custom Certificates** — Branded design

**🏢 Enterprise:**

• **HR & Payroll** — Salary, leaves
• **Transport** — GPS tracking
• **Hostel** — Room allocation
• **Everything unlimited!**

**22+ modules total!**

Want detailed info about any specific feature? Or ready to see pricing?"""
        return response, {'last_topic': 'features', 'stage': 'exploring', 'viewed_features': True}
    
    elif intent == "free_trial":
        response = """Love that you're asking about the trial! Here's the deal:

**60-Day Free Trial** 🎁

**What you get:**
✅ Full Starter plan access
✅ 500 free SMS/WhatsApp credits
✅ Unlimited students (within Starter limit)
✅ Mobile app access
✅ Email support
✅ Free setup help!

**What you DON'T need:**
❌ Credit card
❌ Any payment info
❌ Complicated forms

**What happens after 60 days?**
• Your data stays safe (90 days)
• Pick any plan to continue
• Or just export data and leave (no hard feelings!)

**How to start:**
Just go to **skolify.in/register**
→ Enter school name + phone + city
→ Done! You're in!

**Takes 2 minutes!**

Ready to start? Just say "yes" or "start trial"! 🚀"""
        return response, {'last_topic': 'trial_info', 'stage': 'considering_trial', 'ready_to_start': True}
    
    elif intent == "getting_started":
        response = """Alright, let's get you started! It's super simple:

**The 15-Minute Setup:** ⏱️

**Step 1: Register** (1 min)
• skolify.in/register
• School name + phone + city
• Account created!

**Step 2: School Details** (2 mins)
• Upload logo
• Add address
• Set academic year

**Step 3: Add Students** (5 mins)
• Download Excel template
• Fill: Name, Class, Parent Phone
• Upload → 500 students added!

**Step 4: Add Teachers** (3 mins)
• Enter name, phone, subjects
• Auto-login credentials sent

**Step 5: Start Using!** (4 mins)
• Mark attendance
• Post notice
• You're live!

**Need help?**
• Video tutorials (built-in)
• Live chat support
• WhatsApp support
• **Free onboarding call!**

Want me to connect you with our team for a setup call?"""
        return response, {'last_topic': 'setup_guide', 'stage': 'ready_to_implement', 'needs_support': True}
    
    elif intent == "support":
        response = """Need help? We've got your back! Here's how to reach us:

**📱 WhatsApp** (Fastest!)
Direct message to support team
Response: 1-2 hours (business hours)

**📧 Email:** support@skolify.in
Detailed queries
Response: Same business day

**💬 Live Chat**
In your admin panel
Mon-Sat, 9 AM - 6 PM

**📞 Phone Support**
Urgent issues
Premium plans get priority

**🎥 Free Onboarding Call**
Video call setup help
Available for all new schools!

**What do you need help with?**
• Getting started?
• Technical issue?
• Questions about features?
• Want a demo?

Tell me and I'll guide you! Or connect you with our team directly."""
        return response, {'last_topic': 'support', 'stage': 'needs_assistance', 'can_escalate': True}
    
    return None, {}

# ══════════════════════════════════════════════════════════
# Main Answer Builder
# ══════════════════════════════════════════════════════════

def build_conversational_answer(message: str, conversation: Dict, results: List[tuple]) -> Tuple[str, Dict]:
    """Build answer with conversation context"""
    
    context_analysis = analyze_context(message, conversation)
    intent = detect_intent(message, context_analysis)
    
    if intent:
        response, new_context = get_response_for_intent(intent, conversation.get('context', {}))
        if response:
            return response, new_context
    
    fallback = """Hmm, I'm not quite sure about that one! 🤔

**Here's what I can definitely help with:**

• 💰 **Plans & Pricing** — which plan fits your school
• 🎁 **Free Trial** — 60 days, no credit card
• 📦 **Features** — what's included in each plan
• 💳 **Credits** — SMS, WhatsApp, email messaging
• 🔧 **Setup** — how to get started
• 📞 **Support** — talk to our team

Or just type your question naturally — I'll do my best! 😊

If I still can't help, I can connect you with a real person from our team right away."""
    
    return fallback, {'last_topic': 'unclear', 'needs_clarification': True}

# ══════════════════════════════════════════════════════════
# API Endpoint
# ══════════════════════════════════════════════════════════

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Conversational chat with memory"""
    try:
        conversation_id = request.conversation_id or str(uuid.uuid4())
        conversation = get_conversation(conversation_id)
        
        print(f"\n💬 [{conversation_id[:8]}] User: {request.message}")
        
        model = get_embedding_model()
        collection = get_collection()
        
        query_embedding = model.encode([request.message])[0]
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=3,
            include=['documents', 'metadatas', 'distances']
        )
        
        final_results = []
        if results['documents'][0]:
            distances = results['distances'][0]
            similarities = [1 - (d / 2) for d in distances]
            
            for doc, meta, sim in zip(results['documents'][0], results['metadatas'][0], similarities):
                if sim >= settings.MIN_SIMILARITY_SCORE:
                    final_results.append((doc, meta, sim))
        
        answer, new_context = build_conversational_answer(request.message, conversation, final_results)
        update_conversation(conversation_id, request.message, answer, new_context)
        
        sources = [
            Source(
                text=doc[:100] + "...",
                url=meta.get('url', ''),
                page_type=meta.get('page_type', 'general'),
                relevance_score=round(sim, 2)
            )
            for doc, meta, sim in final_results[:2]
        ]
        
        print(f"🤖 Response: {len(answer)} chars | Context: {new_context.get('last_topic', 'none')}")
        
        return ChatResponse(
            success=True,
            answer=answer,
            sources=sources,
            conversation_id=conversation_id,
            metadata={
                "context": new_context,
                "conversation_length": len(conversation['messages'])
            }
        )
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Health check"""
    try:
        collection = get_collection()
        return {"status": "healthy", "documents": collection.count()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}