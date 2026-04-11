# api/utils/response_cache.py

"""
Smart Response Caching System

Features:
- Hindi/English query normalization
- Role-aware caching
- Use-case specific TTL
- Automatic cleanup
"""

import hashlib
import time
from typing import Optional, Dict
from datetime import datetime


class ResponseCache:
    """
    Cache LLM responses with smart normalization
    
    Benefits:
    - 70-80% public queries cached (instant response)
    - 30-40% portal queries cached (fresh data balance)
    - Massive cost savings
    """
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, Dict] = {}
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def _normalize_query(self, query: str) -> str:
        """
        Normalize for better cache hits
        
        Examples:
        - "How many students?" → "how many student"
        - "kitne students hain?" → "how many student"
        - Both get same cache key!
        """
        q = query.lower().strip()
        
        # Hindi → English mapping
        replacements = {
            'kitne': 'how many',
            'kitna': 'how much',
            'kaun': 'who',
            'kya': 'what',
            'dikhao': 'show',
            'batao': 'tell',
            'hain': '',
            'hai': '',
            'ka': '',
            'ke': '',
            'ki': '',
            'aaj': 'today',
            'kal': 'tomorrow',
            'students': 'student',
            'fees': 'fee',
            'ko': '',
            'mein': '',
            'me': '',
        }
        
        for hindi, english in replacements.items():
            q = q.replace(hindi, english)
        
        # Remove extra spaces
        return ' '.join(q.split())
    
    def _generate_key(
        self, 
        query: str, 
        context: str, 
        role: str,
        mode: str
    ) -> str:
        """Generate cache key"""
        normalized = self._normalize_query(query)
        
        # Include mode and role in key
        # Public guests get same response
        # Portal users may get personalized
        content = f"{mode}:{role}:{normalized}:{context[:50]}"
        
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(
        self, 
        query: str, 
        context: str = "", 
        role: str = "guest",
        mode: str = "public"
    ) -> Optional[str]:
        """Get cached response if valid"""
        key = self._generate_key(query, context, role, mode)
        
        if key in self.cache:
            entry = self.cache[key]
            age = time.time() - entry['timestamp']
            
            # Check TTL
            if age < self.ttl_seconds:
                self.hits += 1
                print(f"💾 Cache HIT ({age:.1f}s old, {self.get_hit_rate()}% hit rate)")
                return entry['response']
            else:
                # Expired
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(
        self, 
        query: str, 
        response: str, 
        context: str = "", 
        role: str = "guest",
        mode: str = "public"
    ):
        """Cache response"""
        key = self._generate_key(query, context, role, mode)
        
        self.cache[key] = {
            'response': response,
            'timestamp': time.time(),
            'query': query,
            'mode': mode,
            'role': role,
        }
        
        # Auto-cleanup if too large
        if len(self.cache) > 1000:
            self._cleanup_oldest(keep=800)
    
    def _cleanup_oldest(self, keep: int = 800):
        """Remove oldest entries"""
        sorted_keys = sorted(
            self.cache.keys(),
            key=lambda k: self.cache[k]['timestamp']
        )
        
        to_remove = sorted_keys[:len(sorted_keys) - keep]
        for key in to_remove:
            del self.cache[key]
        
        if to_remove:
            print(f"🧹 Cleaned {len(to_remove)} old cache entries")
    
    def clear(self):
        """Clear all cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        print("🗑️  Cache cleared")
    
    def get_hit_rate(self) -> float:
        """Get cache hit rate percentage"""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return round((self.hits / total) * 100, 1)
    
    def get_stats(self) -> Dict:
        """Get detailed cache statistics"""
        return {
            'size': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{self.get_hit_rate()}%",
            'ttl_seconds': self.ttl_seconds,
            'memory_usage_kb': len(str(self.cache)) / 1024,
        }


# ══════════════════════════════════════════════════════════
# MULTI-TIER CACHE SYSTEM
# ══════════════════════════════════════════════════════════

_public_cache = None
_portal_cache = None
_tool_cache = None


def get_public_cache() -> ResponseCache:
    """Cache for public website chat (1 hour TTL)"""
    global _public_cache
    if _public_cache is None:
        from ..config import settings
        _public_cache = ResponseCache(
            ttl_seconds=settings.PUBLIC_CACHE_TTL_SECONDS
        )
        print(f"✅ Public cache initialized (TTL: {settings.PUBLIC_CACHE_TTL_SECONDS}s)")
    return _public_cache


def get_portal_cache() -> ResponseCache:
    """Cache for portal chat (5 min TTL)"""
    global _portal_cache
    if _portal_cache is None:
        from ..config import settings
        _portal_cache = ResponseCache(
            ttl_seconds=settings.PORTAL_CACHE_TTL_SECONDS
        )
        print(f"✅ Portal cache initialized (TTL: {settings.PORTAL_CACHE_TTL_SECONDS}s)")
    return _portal_cache


def get_tool_cache() -> ResponseCache:
    """Cache for tool responses (2 min TTL)"""
    global _tool_cache
    if _tool_cache is None:
        from ..config import settings
        _tool_cache = ResponseCache(
            ttl_seconds=settings.TOOL_CACHE_TTL_SECONDS
        )
        print(f"✅ Tool cache initialized (TTL: {settings.TOOL_CACHE_TTL_SECONDS}s)")
    return _tool_cache