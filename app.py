# ── Weather API — Flask backend ─────────────────────────────────────
import sys, os

_venv_sp = os.path.join(os.path.dirname(__file__), 'venv', 'lib',
                        f'python{sys.version_info.major}.{sys.version_info.minor}',
                        'site-packages')
if os.path.isdir(_venv_sp) and _venv_sp not in sys.path:
    sys.path.insert(0, _venv_sp)

import json, time
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cache   import cache_get, cache_set, cache_stats
from weather_client import fetch_weather

app = Flask(__name__)

# ── config ──────────────────────────────────────────────────────────
app.config['JSON_SORT_KEYS'] = False

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=['60/minute'],
    storage_uri=os.environ.get('REDIS_URL', 'memory://'),
)

CACHE_TTL_SECONDS = int(os.environ.get('CACHE_TTL', '43200'))   # 12 h


# ── helpers ─────────────────────────────────────────────────────────

def _error(code, msg):
    return jsonify({'ok': False, 'error': msg}), code


# ── routes ──────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    info = cache_stats()
    return jsonify({'ok': True, 'service': 'weather-api',
                    'cache': info, 'timestamp': time.time()})


@app.route('/weather', methods=['GET'])
@limiter.limit('30/minute')
def weather():
    city  = (request.args.get('city')  or '').strip()
    units = (request.args.get('units') or 'us').strip().lower()   # us | metric | uk | base

    if not city:
        return _error(400, 'Query parameter ?city=<location> is required.')

    if units not in ('us', 'metric', 'uk', 'base'):
        return _error(400,
            f'Invalid units "{units}". Use us, metric, uk, or base.')

    # ── cache lookup ───────────────────────────────────────────────
    cache_key = f'weather:{city.lower()}:{units}'
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached), 200

    # ── upstream call ───────────────────────────────────────────────
    resp = fetch_weather(city, unit_group=units)
    if not resp.get('ok'):
        code = 502 if 'API' in resp.get('error','') or 'timeout' in resp.get('error','').lower() else 400
        return _error(code, resp['error'])

    resp.setdefault('cached', False)
    resp['cache_key'] = cache_key

    # ── persist cache ───────────────────────────────────────────────
    cache_set(cache_key, resp, ttl=CACHE_TTL_SECONDS)

    return jsonify(resp), 200


@app.route('/cache', methods=['GET'])
def cache_status():
    return jsonify(cache_stats()), 200


@app.route('/cache', methods=['DELETE'])
def cache_clear():
    from cache import _memory_cache
    _memory_cache.clear()
    return jsonify({'ok': True, 'message': 'In-memory cache cleared.'}), 200


# ── error handlers ──────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(_):
    return _error(404, 'Not found. Try /weather?city=London')

@app.errorhandler(429)
def rate_limited(_):
    return _error(429, 'Rate limit exceeded. Slow down.')

@app.errorhandler(HTTPException)
def http_exc(exc: HTTPException):
    return _error(exc.code, exc.description)

@app.errorhandler(Exception)
def server_error(exc):
    return _error(500, f'Internal error: {exc}')


# ── main ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f'  Weather API  → http://localhost:{port}')
    print(f'  Endpoints    → GET /weather?city=<location>  [30 req/min]')
    print(f'  Redis URL    → {os.environ.get("REDIS_URL","not set — using in-memory")}')
    print(f'  VC_API_KEY   → {"set" if os.environ.get("VC_API_KEY") else "not set — returns error"}')
    app.run(debug=True, host=host, port=port)
