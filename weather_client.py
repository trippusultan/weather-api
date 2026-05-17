# ── Visual Crossing Weather Proxy ───────────────────────────────────
import os, requests, time

BASE_URL = 'https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline'
API_KEY  = os.environ.get('VC_API_KEY', '')

_TIMEOUT = int(os.environ.get('VC_TIMEOUT', '8'))


_DEMO_MODE = os.environ.get('DEMO', '').lower() in ('1', 'true', 'yes', 'on')


_HARDCODED = {
    'ok': True, 'source': 'hardcoded-demo', 'city': 'Demo City', 'tz': 'UTC',
    'unit_group': 'metric',
    'current': {
        'temp': 22.1, 'feels_like': 23.0, 'humidity': 65,
        'wind_speed': 12.3, 'wind_dir': 'SW',
        'conditions': 'Partly Cloudy', 'icon': 'partly-cloudy-day',
        'dew_point': 14.2, 'pressure': 1013.2, 'visibility': 10.0,
        'uv_index': 5, 'sunrise': '06:00', 'sunset': '20:30',
    },
    'forecast_days': [
        {'date': '2025-06-12', 'temp_max': 25.0, 'temp_min': 16.0,
         'conditions': 'Partly Cloudy', 'description': '',
         'icon': 'partly-cloudy-day', 'precip': 0.0, 'precip_prob': 10,
         'wind_speed': 11.0, 'wind_dir': 'W', 'humidity': 62},
        {'date': '2025-06-13', 'temp_max': 23.5, 'temp_min': 15.5,
         'conditions': 'Sunny', 'description': '',
         'icon': 'clear-day', 'precip': 0.0, 'precip_prob': 0,
         'wind_speed': 9.0,  'wind_dir': 'N', 'humidity': 58},
        {'date': '2025-06-14', 'temp_max': 21.0, 'temp_min': 14.0,
         'conditions': 'Rain', 'description': 'Light rain expected',
         'icon': 'rain', 'precip': 3.2, 'precip_prob': 75,
         'wind_speed': 18.0, 'wind_dir': 'SE', 'humidity': 82},
        {'date': '2025-06-15', 'temp_max': 19.0, 'temp_min': 12.5,
         'conditions': 'Overcast', 'description': 'Cloudy throughout',
         'icon': 'overcast', 'precip': 0.0, 'precip_prob': 5,
         'wind_speed': 15.0, 'wind_dir': 'S', 'humidity': 70},
        {'date': '2025-06-16', 'temp_max': 24.0, 'temp_min': 15.0,
         'conditions': 'Clear', 'description': '',
         'icon': 'clear-day', 'precip': 0.0, 'precip_prob': 0,
         'wind_speed': 6.0,  'wind_dir': 'E', 'humidity': 50},
    ],
    'alerts': [],
}


def fetch_weather(city: str, unit_group: str = 'us', lang: str = 'en') -> dict:
    """
    Returns a normalised dict:
      { ok: true,  source: 'api'|'hardcoded-demo',  city, unit_group,
        current, forecast_days:[...], cached: False }
    or
      { ok: false, error: '<str>' }
    """
    if _DEMO_MODE:
        demo = dict(_HARDCODED)
        demo['source'] = 'hardcoded-demo'
        demo['city']   = city
        demo['unit_group'] = unit_group
        return demo

    if not API_KEY:
        return {'ok': False, 'error': 'VC_API_KEY environment variable is not set. Set DEMO=true for demo mode.'}

    resp = _call_external(city, unit_group, lang)
    return resp


def _call_external(city: str, unit_group: str, lang: str) -> dict:
    try:
        url = f'{BASE_URL}/{requests.utils.quote(city)}'
        params = {
            'key':         API_KEY,
            'unitGroup':   unit_group,
            'lang':        lang,
            'contentType': 'json',
            'include':     'current,days',
            'iconSet':     'icons1',
        }
        r = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.exceptions.Timeout:
        return {'ok': False, 'error': 'Weather API timed out. Try again in a moment.'}
    except requests.exceptions.ConnectionError:
        return {'ok': False, 'error': 'Cannot reach Weather API. Check your network.'}
    except Exception as exc:
        return {'ok': False, 'error': f'Request failed: {exc}'}

    if r.status_code == 401:
        return {'ok': False, 'error': 'Invalid API key. Set VC_API_KEY env var.'}
    if r.status_code == 403:
        return {'ok': False, 'error': 'API key quota exceeded or access forbidden.'}
    if r.status_code == 404:
        return {'ok': False, 'error': f'Location "{city}" not found.'}
    if r.status_code != 200:
        return {'ok': False, 'error': f'Weather API returned HTTP {r.status_code}.'}

    try:
        data = r.json()
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'Weather API returned malformed JSON.'}

    return _normalise(data, city, unit_group)


def _normalise(data: dict, city: str, unit_group: str) -> dict:
    current = (data.get('currentConditions') or {})

    def d(d, *keys, default=None):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return default

    days = []
    for day in (data.get('days') or [])[:7]:
        tmax = d(day, 'tempmax', 'tempMax')
        tmin = d(day, 'tempmin', 'tempMin')
        days.append({
            'date':           day.get('datetime', ''),
            'temp_max':       tmax if tmax is not None else '—',
            'temp_min':       tmin if tmin is not None else '—',
            'conditions':     d(day, 'conditions', 'description', default='—'),
            'description':    d(day, 'description', default=''),
            'icon':           d(day, 'icon', default='cloudy'),
            'precip':         d(day, 'precip', 'precipMM', default=0),
            'precip_prob':    d(day, 'precipprob', 'pop', default=0),
            'wind_speed':     d(day, 'windspeed', default='—'),
            'wind_dir':       d(day, 'winddir', default=''),
            'humidity':       d(day, 'humidity', default='—'),
            'sunrise':        d(day, 'sunrise', default=''),
            'sunset':         d(day, 'sunset',  default=''),
            'uv_index':       d(day, 'uvindex', default='—'),
        })

    resolved = d(data, 'resolvedAddress', 'address', default=city)
    timezone = d(data, 'timezone', default='UTC')

    return {
        'ok':            True,
        'source':        'api',
        'city':          resolved or city,
        'tz':            timezone,
        'unit_group':    unit_group,
        'current': {
            'temp':       d(current, 'temp', 'temperature', default='—'),
            'feels_like': d(current, 'feelslike', default='—'),
            'humidity':   d(current, 'humidity', default='—'),
            'wind_speed': d(current, 'windspeed', default='—'),
            'wind_dir':   d(current, 'winddir', default=''),
            'conditions': d(current, 'conditions', 'description', default='—'),
            'icon':       d(current, 'icon', default='cloudy'),
            'dew_point':  d(current, 'dew', default='—'),
            'pressure':   d(current, 'pressure', default='—'),
            'visibility': d(current, 'visibility', default='—'),
            'uv_index':   d(current, 'uvindex', default='—'),
            'sunrise':    d(current, 'sunrise', default=''),
            'sunset':     d(current, 'sunset',  default=''),
            'precip':     d(current, 'precip', default=0),
        },
        'forecast_days': days,
        'alerts':       data.get('alerts', []),
    }
