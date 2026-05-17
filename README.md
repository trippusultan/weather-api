# Weather Cache API

Production-grade weather proxy built with **Flask + Flask-Limiter + requests**.
Fetches from **Visual Crossing** (free tier), serves results through a thin REST
API with automatic TTL cache (Redis or in-memory fallback).

**Project URL:** https://github.com/trippusultan/weather-api

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Environment Reference](#environment-reference)
5. [API Reference](#api-reference)
6. [Response Reference](#response-reference)
7. [Rate Limiting](#rate-limiting)
8. [Cache Strategy](#cache-strategy)
9. [Testing Guide](#testing-guide)
10. [Deployment](#deployment)
11. [Redis Setup](#redis-setup)
12. [Demo Mode](#demo-mode)
13. [Troubleshooting](#troubleshooting)
14. [Project Map](#project-map)

---

## Features

### Core API
- `GET /weather?city=<name>` — current conditions + 5–7 day forecast
- `GET /weather?city=<name>&units=<group>` — switch between `us`, `metric`, `uk`, `base`
- `GET /health` — service health check with cache stats
- `GET /cache` — in-memory / Redis cache statistics
- `DELETE /cache` — clear in-memory cache
- `GET /` — this documentation

### Caching
- **TTL-based LRU in-memory cache** using a doubly-linked `OrderedDict` — O(1) eviction
- **Optional Redis backend** — set `REDIS_URL` for shared production cache
- Cache key format: `weather:{city.lower()}:{units}`
- Configurable TTL via `CACHE_TTL` env var (default: **12 h / 43,200 s**)
- On cache **hit**: returns same shape, adds `"cached": true`
- On cache **miss**: fetches upstream, caches result, returns fresh data

### Rate Limiting
- **Flask-Limiter**: `60/minute` global default
- **30/minute** on `/weather` per IP (most expensive route)
- **429 Too Many Requests** response with `retry-after` header
- Graceful handling with structured error body

### Error Handling
All errors return a uniform `{ "ok": false, "error": "<human-readable message>" }` body
with an appropriate HTTP status code.

| HTTP | Condition |
|---|---|
| `400` | Missing/invalid `city` or `units` parameter |
| `400` | `VC_API_KEY` not set (and not demo mode) |
| `404` | Location not found by upstream API |
| `429` | Rate limit exceeded |
| `502` | Bad gateway — API key invalid, quota exceeded, timeout, network failure |
| `500` | Unhandled internal server error |

### Demo Mode
Set `DEMO=true` — returns a realistic 5-day hardcoded forecast for any city
without requiring a Visual Crossing API key.

| `DEMO` | `VC_API_KEY` | Behaviour |
|---|---|---|
| `true` | any | Returns demo data (no network call) |
| `false` | set | Calls Visual Crossing production data |
| `false` | empty | Returns `400` error with key-set hint |

### Upstream API
- **Provider**: Visual Crossing Weather API
- **Rows included**: `currentConditions` + `days` (forecast)
- **Icons**: `icons1` set
- **Timeout**: configurable via `VC_TIMEOUT` (default 8 s)

---

## Architecture

```
┌─────────────┐
│   Client    │  GET /weather?city=London&units=us
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                    Flask App (app.py)                     │
│  ┌──────────────────┐    ┌──────────────────────────┐   │
│  │  Flask-Limiter   │    │  Weather Proxy            │   │
│  │  30 req/min      │───►│  cache → upstream fetch   │   │
│  └──────────────────┘    └──────────┬───────────────┘   │
│                                       │ TTL=43200 s       │
│  ┌───────────────────────────────────▼─────────────────┐  │
│  │  cache.py (Redis / in-memory LRU w/ per-key expiry) │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
       │
       ▼  [DEMO=false only]
┌──────────────────────────────────────────────────────────┐
│         Visual Crossing REST API (3rd party)              │
│   https://weather.visualcrossing.com/VisualCrossing…      │
└──────────────────────────────────────────────────────────┘
```

### Request Lifecycle

```
1. HTTP GET /weather?city=Tokyo&units=metric
         │
         ▼
2. Flask-Limiter checks per-IP quota (30/min on /weather, 60/min global)
   → 429 if exceeded
         │
         ▼
3. cache.get("weather:tokyo:metric")
   → HIT  → return cached JSON immediately  (+ "cached": true)
   → MISS → continue to #4
         │
         ▼
4. DEMO mode?
   → YES → return hardcoded forecast, cache it, return
   → NO  → call Visual Crossing
         │
         ▼
5. Normalise upstream JSON → flat canonical schema
         │
         ▼
6. cache.set(key, result, ttl=CACHE_TTL)
         │
         ▼
7. Return JSON response (200)
```

---

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Application runtime |
| Python `pip` | bundled | Package installation |
| Redis | any (optional) | Persistent shared cache |

### 1. Clone & Install

```bash
git clone https://github.com/trippusultan/weather-api.git
cd weather-api

# Use the bundled venv on WSL/Linux/macOS
source venv/bin/activate
# or just run the helper script (it auto-bootstraps):
./run.sh
```

### 2. Set Environment Variables

```bash
cp .env.example .env
# Edit .env in your editor and fill in your API key
```

| Variable | Required | Example |
|---|---|---|
| `VC_API_KEY` | No if `DEMO=true` | `ABC123…` from visualcrossing.com/sign-up |
| `DEMO` | No | `true` or `false` |
| `REDIS_URL` | No | `redis://localhost:6379/0` |
| `CACHE_TTL` | No | `43200` (seconds) |
| `PORT` | No | `8000` |
| `VC_TIMEOUT` | No | `8` (seconds) |

### 3. Run

```bash
# Option A — bootstrap script (recommended)
./run.sh

# Option B — explicit env
DEMO=true VC_API_KEY="" venv/bin/python app.py

# Option C — system Python with venv site-packages
PYTHONPATH=venv/lib/python3.12/site-packages venv/bin/python app.py
```

Expected output:
```
Weather API  → http://localhost:8000
Endpoints    → GET /weather?city=<location>  [30 req/min]
Redis URL    → not set — using in-memory
VC_API_KEY   → not set — returns error
```

---

## Environment Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `VC_API_KEY` | Conditional | — | Visual Crossing API key. Required unless `DEMO=true`. Get free key at https://www.visualcrossing.com/sign-up |
| `DEMO` | No | `false` | Set to `true` to serve hardcoded demo data without any API key or network call |
| `REDIS_URL` | No | empty | Redis connection string. Enables shared cache across workers. Falls back to in-memory when empty. |
| `CACHE_TTL` | No | `43200` | Cache key TTL in seconds. Set to `60` for dev, `43200` for prod |
| `PORT` | No | `8000` | Flask TCP port |
| `HOST` | No | `0.0.0.0` | Flask bind interface |
| `VC_TIMEOUT` | No | `8` | Upstream HTTP request timeout in seconds |
| `FLASK_ENV` | No | `development` | Set to `production` to disable Flask debug reloader |

---

## API Reference

### Base URL

```
http://localhost:8000
```

---

## Response Reference

### `GET /weather?city=<location>&units=<unit_group>`

Returns current conditions + 7-day forecast for the requested location. Responses
are cached and return `source` and `cached` tracking fields.

**Query Parameters**

| Parameter | Required | Default | Accepted Values |
|---|---|---|---|
| `city` | ✅ Yes | — | Any city, address, ZIP/postal code, or airport code recognised by Visual Crossing |
| `units` | No | `us` | `us` · `metric` · `uk` · `base` |

---

#### 200 OK

```json
{
  "ok": true,
  "source": "api",                    // or  "hardcoded-demo" (when DEMO=true)
  "city": "London, UK",               // resolved by the upstream API
  "tz": "Europe/London",
  "unit_group": "us",
  "cached": false,                    // true on any cache hit
  "cache_key": "weather:london:us",   // cache storage key (for debugging)

  "current": {
    "temp": 52.3,
    "feels_like": 50.1,
    "humidity": 72,
    "wind_speed": 11.2,
    "wind_dir": "NW",
    "conditions": "Partly Cloudy",
    "description": "",
    "icon": "partly-cloudy-day",
    "dew_point": 43.1,
    "pressure": 30.15,
    "visibility": 10.0,
    "uv_index": 3,
    "sunrise": "06:12:34",
    "sunset": "20:41:12"
  },

  "forecast_days": [
    {
      "date": "2025-06-12",
      "temp_max": 62.1,
      "temp_min": 51.7,
      "conditions": "Rain",
      "description": "Light rain expected",
      "icon": "rain",
      "precip": 0.25,
      "precip_prob": 65,
      "wind_speed": 14.5,
      "wind_dir": "SE",
      "humidity": 82
    }
  ],

  "alerts": []    // populated when severe weather alerts are active
}
```

**`forecast_days` length** — 5 with hardcoded demo mode; up to 7 from the live API.

---

#### Error Responses

All errors follow a uniform structure:

```json
{ "ok": false, "error": "<human-readable message>" }
```

| HTTP | `error` Message | Trigger |
|---|---|---|
| `400` | `Query parameter ?city=<location> is required.` | `city` omitted |
| `400` | `Invalid units "celsius". Use us, metric, uk, or base.` | `units` not in allowed list |
| `400` | `VC_API_KEY environment variable is not set. Set DEMO=true for demo mode.` | No key + no demo flag |
| `400` | `Location "X" not found.` | Upstream 404 |
| `401` | *passthrough* | Invalid API key (upstream) |
| `403` | *passthrough* | API key quota exceeded (upstream) |
| `429` | `Rate limit exceeded. Slow down.` | Exceeded 30 req/min on `/weather` |
| `502` | `Weather API returned HTTP <n>.` | Non-200 upstream response |
| `502` | `Weather API timed out. Try again in a moment.` | Request timeout |
| `500` | `Internal error: <exc>` | Unhandled server exception |

---

### `GET /health`

Service diagnostic. No query parameters.

**200 OK**
```json
{
  "ok": true,
  "service": "weather-api",
  "cache": {
    "backend": "memory",      // or "redis"
    "size": 3,
    "max": 2048,
    "used_memory_human": "1.2M"  // only when Redis backend
  },
  "timestamp": 1718824400.12  // Unix epoch with fractional seconds
}
```

---

### `GET /cache`

Returns cache statistics.

**200 OK**
```json
{
  "backend": "memory",
  "size": 42,
  "max": 2048
}
```

---

### `DELETE /cache`

Clears all entries from the in-memory cache. Redis is not cleared.

**200 OK**
```json
{ "ok": true, "message": "In-memory cache cleared." }
```

---

## Rate Limiting

| Endpoint | Limit | Scoped to |
|---|---|---|
| `/weather` | 30 req/min | Client IP |
| all others | 60 req/min | Client IP |

Rate-limited responses:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"ok": false, "error": "Rate limit exceeded. Slow down."}
```

---

## Cache Strategy

### Key Format
```
weather:{city.lower()}:{units}
```
Example: `weather:london:us`, `weather:paris:metric`

### Backend Priority (`cache.py`)
1. **Redis** — used when `REDIS_URL` is set and the `redis` package is importable
2. **In-memory OrderedDict** — fallback, always available
3. Both backends are **thread-safe** (`threading.Lock`)

### TTL & Eviction
- **TTL**: defaults to 43,200 s (12 hours), set via `CACHE_TTL`
- **Eviction**: `OrderedDict` pops `(key, value)` pairs from the front when `size > max` (2048)
- **Expiry sweep**: triggered on every `get()` call via `_evict_expired()`

### Redis Connection String
```env
# Single DB, no password
REDIS_URL=redis://localhost:6379/0

# With password
REDIS_URL=redis://:mypassword@redis-host:6379/0

# Docker service name
REDIS_URL=redis://redis:6379/0
```

---

## Testing Guide

### Manual curl Tests

```bash
# Health
curl -s http://localhost:8000/health | python3 -m json.tool

# Current weather (London)
curl -s "http://localhost:8000/weather?city=London" | python3 -m json.tool

# Metric forecast (Berlin)
curl -s "http://localhost:8000/weather?city=Berlin&units=metric" | python3 -m json.tool

# UK units (Manchester)
curl -s "http://localhost:8000/weather?city=Manchester&units=uk" | python3 -m json.tool

# Error — missing city
curl -s http://localhost:8000/weather | python3 -m json.tool

# Error — missing API key (non-demo)
curl -s "http://localhost:8000/weather?city=Paris" \     # DEMO=false
  | python3 -m json.tool

# Error — location not found
curl -s "http://localhost:8000/weather?city=XyzzyNotARealCity" | python3 -m json.tool

# Cache stats
curl -s http://localhost:8000/cache | python3 -m json.tool

# Clear cache
curl -s -X DELETE http://localhost:8000/cache | python3 -m json.tool
```

### Rate-Limit Test

```bash
# 31 requests fast = expect 429 on request #31
for i in $(seq 1 31); do
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:8000/weather?city=Test$i")
  echo "Reqs $i → HTTP $code"
done
```

Expected: 
```
Reqs 1-30  →  HTTP 200
Reqs 31    →  HTTP 429
```

### Cache Hit Test

```bash
# Call 1 — MISS (cached=false, fetched from upstream)
curl -s "http://localhost:8000/weather?city=CacheCity" | python3 -m json.tool

# Call 2 — HIT (cached=true, served from memory)
curl -s "http://localhost:8000/weather?city=CacheCity" | python3 -m json.tool
```

Second call must show `"cached": true`.

---

## Deployment

### Gunicorn + Nginx (production)

```bash
# Install Gunicorn
source venv/bin/activate
pip install gunicorn

# Run with 4 workers
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DEMO=false
EXPOSE 8000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
```

```bash
docker build -t weather-api .
docker run -p 8000:8000 -e VC_API_KEY=YOUR_KEY weather-api
```

---

## Redis Setup

### Local Redis (Windows / WSL / Linux)

```bash
# Ubuntu / WSL
sudo apt-get install redis-server
sudo service redis-server start
redis-cli ping        # → PONG

## Windows (Chocolatey)
choco install redis-64
redis-server          # keep running in separate terminal
redis-cli ping        # → PONG
```

### Docker Redis

```bash
docker run -d --name weather-redis -p 6379:6379 redis:alpine
redis-cli ping    # → PONG
```

### Verify in Application

```bash
curl -s http://localhost:8000/cache
# → {"backend": "redis", "size": null, "used_memory_human": "1.75M"}
```

---

## Demo Mode

No API key required — perfect for iterating on client integrations.

```bash
# Quick one-liner
DEMO=true VC_API_KEY="" CACHE_TTL=60 venv/bin/python app.py

# Or via .env
# ── .env ──
VC_API_KEY=
DEMO=true
CACHE_TTL=60
PORT=8000
HOST=0.0.0.0
```

Demo response shape:
```json
{
  "ok": true,
  "source": "hardcoded-demo",
  "city": "Paris",          // echo of queried city
  "tz": "UTC",
  "unit_group": "metric",   // echo of requested units
  "current": { "temp": 22.1,  "conditions": "Partly Cloudy", … },
  "forecast_days": [ … ],   // 5 entries
  "alerts": [],
  "cached": true
}
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `VC_API_KEY environment variable is not set.` | Running without demo + no key | Set `DEMO=true` in `.env` or add `VC_API_KEY` |
| `Address already in use` | Port 8000 occupied | `PORT=8001` in `.env` or `lsof -ti :8000 \| xargs kill` |
| `Redis connection refused` | Redis not running | Start Redis or leave `REDIS_URL` empty for in-memory |
| `Cannot apply unknown utility class` (CSS) | Transferred from another project | This is not this project — see `templates/` |
| `ModuleNotFoundError: No module named flask` | venv not activated | `source venv/bin/activate` or use `run.sh` |
| `Rate limit exceeded` | Too many requests in 60 s | Wait and reduce query frequency; raise limit in `app.py` |
| `ModuleNotFoundError: No module named redis` even with `REDIS_URL` set | Redis package not installed | `pip install redis` |
| `Weather API timed out` | Upstream slow | Increase `VC_TIMEOUT` (e.g. `VC_TIMEOUT=15`) |

---

## Project Map

```
weather-api/
├── app.py                Flask app (routes, limiter, error handling)
│                            ├ GET /weather   — cached proxy → upstream
│                            ├ GET /health    — liveness + cache stats
│                            ├ GET /cache     — cache info
│                            └ DELETE /cache  — clear in-memory
├── weather_client.py    Visual Crossing REST wrapper + normalizer
├── cache.py             TTL in-memory LRU + optional Redis backend
├── run.sh               Bootstrap venv, load .env, start Flask
├── run.py               (same as run.sh, Windows-compatible entry point)
├── requirements.txt     pip dependencies
├── .env.example         Env var template — copy to .env
└── README.md            This file
```

---

## Contributing

1. Fork https://github.com/trippusultan/weather-api
2. `git checkout -b feat/my-feature`
3. Make changes, update `README.md` if the API shape changes
4. `pytest` (if tests are added) + `python app.py` smoke test locally
5. PR against `master` — describe the endpoint shape change or new feature

---

## License

MIT — free for personal and commercial use.  
Free tier of Visual Crossing Weather applies [their own terms](https://www.visualcrossing.com/weather-api/terms).
