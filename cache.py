# ── Weather Cache Layer ──────────────────────────────────────────────
import threading, time, hashlib, json, os
from collections import OrderedDict

# ── In-memory LRU with per-key TTL ────────────────────────────────────

class TTLCache:
    """Simple dict-based cache with expiry. Thread-safe."""

    def __init__(self, maxsize=512):
        self._store = OrderedDict()   # key → (value, expire_at)
        self._lock  = threading.Lock()
        self._max   = maxsize

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in expired:
            self._store.pop(k, None)
        # LRU trim
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def get(self, key):
        with self._lock:
            self._evict_expired()
            item = self._store.get(key)
            if not item:
                return None
            self._store.move_to_end(key)
            return item[0]

    def set(self, key, value, ttl=43200):
        expire_at = time.time() + ttl
        with self._lock:
            self._store[key] = (value, expire_at)
            self._store.move_to_end(key)
            self._evict_expired()

    def clear(self):
        with self._lock:
            self._store.clear()

    def stats(self):
        with self._lock:
            self._evict_expired()
            return {'size': len(self._store), 'max': self._max}


# ── Redis wrapper (optional) ─────────────────────────────────────────

def _redis_client():
    """Return a redis client if REDIS_URL is set and redis is importable."""
    url = os.environ.get('REDIS_URL', '').strip()
    if not url:
        return None
    try:
        import redis as redis_mod
        return redis_mod.from_url(url, decode_responses=True)
    except ImportError:
        return None


def cache_set(key, value, ttl=43200):
    """Write key→value with TTL. Prefers Redis, falls back to in-memory."""
    client = _redis_client()
    if client:
        try:
            client.setex(key, ttl, json.dumps(value))
            return
        except Exception:
            pass   # fall through to in-memory
    _memory_cache.set(key, value, ttl=ttl)


def cache_get(key):
    """Read, prefering Redis, falling back to in-memory."""
    client = _redis_client()
    if client:
        try:
            raw = client.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
    return _memory_cache.get(key)


def cache_stats():
    client = _redis_client()
    if client:
        try:
            info = client.info()
            return {'backend': 'redis', 'size': None,
                    'used_memory_human': info.get('used_memory_human', '?')}
        except Exception:
            pass
    return {'backend': 'memory', **_memory_cache.stats()}


# shared instance
_memory_cache = TTLCache(maxsize=2048)
