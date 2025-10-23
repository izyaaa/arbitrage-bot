"""High-performance async cache with TTL"""
import asyncio
from typing import Any, Dict, Optional, Callable, Awaitable
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class CacheEntry:
    """Cache entry with expiration"""
    value: Any
    expires_at: datetime


class AsyncCache:
    """Thread-safe async cache with automatic expiration"""
    
    def __init__(self, ttl: int = 10):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() < entry.expires_at:
                return entry.value
            else:
                async with self._lock:
                    self._cache.pop(key, None)
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL"""
        async with self._lock:
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=datetime.now() + timedelta(seconds=ttl or self._ttl)
            )
    
    async def get_or_fetch(
        self, 
        key: str, 
        fetch_fn: Callable[..., Awaitable[Any]], 
        *args, 
        **kwargs
    ) -> Any:
        """Get from cache or fetch if expired/missing"""
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        value = await fetch_fn(*args, **kwargs)
        await self.set(key, value)
        return value
    
    async def invalidate(self, key: str) -> None:
        """Remove specific key from cache"""
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self) -> None:
        """Clear all cache entries"""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count"""
        now = datetime.now()
        async with self._lock:
            expired = [k for k, v in self._cache.items() if now >= v.expires_at]
            for k in expired:
                del self._cache[k]
            return len(expired)
