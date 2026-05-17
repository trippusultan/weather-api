# Weather Cache API

Production-grade weather proxy built with **Flask + Flask-Limiter + requests**.
Fetches from **Visual Crossing** (free tier), serves results through a thin REST
API with automatic TTL cache (Redis or in-memory fallback).

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
│  │  Flask-Limiter   │◄──►│  Weather Proxy            │   │
│  │  60 req/min      │    │  cache → upstream fetch   │   │
│  └──────────────────┘    └──────────┬───────────────┘   │
│                                      │ TTL=12h          │
│  ┌──────────────────────────────────▼───────────────┐   │
│  │  cache.py (Redis  /  in-memory LRU)              │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│         Visual Crossing REST API (3rd party)              │
│   https://weather.visualcrossing.com/VisualCrossing…      │
└──────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Prerequisites
| Tool | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| Redis *(optional)* | Persistent shared cache; in-memory used as fallback |

### 2. Install
```bash
pip install -r requirements.txt
# or using the already-prepared venv
source venv/bin/activate
pushd venv/bin && pip install -r ../requirements.txt && popd
```

### 3. Environment
```bash
cp .env.example .env
# Edit .env and add your Visual Crossing API key:
#   https://www.visualcrossing.com/sign-up
```

### 4. Run

With the repo's embedded venv:
```bash
./run.sh
```

Output:
```
Weather API  → http://localhost:8000
Endpoints    → GET /weather?city=<location>  [30 req/min]
Redis URL    → memory:// or redis://localhost:6379
VC_API_KEY   → set / not set
```

---

## API Reference

### `GET /weather?city=<location>&units=<unit_group>`

Returns current conditions + 7-day forecast.

| Param | Default | Values |
|---|---|---|
| `city` *(required)* | — | Any city name, ZIP, or address |
| `units` | `us` | `us` · `metric` · `uk` · `base` |

#### 200 OK
```json
{
  "ok": true,
  "city": "London, UK",
  "tz": "Europe/London",
  "unit_group": "us",
  "current": {
    "temp": 52.3, "feels_like": 50.1,
    "humidity": 72, "wind_speed": 11.2,
    "wind_dir": "NW", "conditions": "Partly Cloudy",
    "icon": "partly-cloudy-day", "dew_point": 43.1,
    "pressure": 30.15, "visibility": 10.0,
    "uv_index": 3, "sunrise": "06:12:34", "sunset": "20:41:12"
  },
  "forecast_days": [
    {
      "date": "2025-06-12",
      "temp_max": 62.1, "temp_min": 51.7,
      "conditions": "Rain", "description": "Light rain",
      "icon": "rain",
      "precip": 0.25, "precip_prob": 65,
      "wind_speed": 14.5, "humidity": 82
    }
  ],
  "cached": false
}
```

#### Errors
```json
{ "ok": false, "error": "Location \"Mars\" not found." }   // 400
{ "ok": false, "error": "VC_API_KEY env var not set." }     // 400
{ "ok": false, "error": "Invalid API key." }                // 502
{ "ok": false, "error": "Quota exceeded." }                 // 502
{ "ok": false, "error": "Rate limit exceeded." }            // 429
```

### `GET /health`
```
{ "ok": true, "cache": {...}, "timestamp": ... }
```

### `GET /cache`
Returns cache stats (backend, size, used_memory for Redis).

### `DELETE /cache`
Clears in-memory cache.

---

## Cache Strategy

| Step | Action |
|---|---|
| Key | `weather:{city.lower()}:{units}` |
| Backend | Redis if `REDIS_URL` set; plain Python dict fallback |
| TTL | 43 200 s (12 h) — configurable via `CACHE_TTL` env var |
| On hit | Return cached response with `"cached": true` |
| On miss | Call Visual Crossing, store result, return fresh response |

---

## Docker / Redis

```bash
# local Redis
sudo apt-get install redis-server
sudo service redis-server start

# or Docker
docker run -d -p 6379:6379 redis:alpine

# then set in .env
REDIS_URL=redis://localhost:6379/0
```

---

## Project Map

```
weather-api/
├── app.py            Flask app  (routes, limiter, error handling)
├── weather_client.py  Visual Crossing API wrapper + normaliser
├── cache.py           LRU in-memory cache + optional Redis wrapper
├── run.py             Bootstrap + dev-server launcher
├── requirements.txt
├── .env.example
└── README.md
```
