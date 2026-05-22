"""
Geocoder module: city + state -> (lat, lon) via OpenStreetMap Nominatim.
Results are cached to disk so each city is only looked up once.
Rate limited to 1 request/second per Nominatim usage policy.
"""

import json
import logging
import os
import time

from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)

_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "cache", "geocode_cache.json")
_RATE_LIMIT_DELAY = 1.1  # seconds between requests (Nominatim: max 1/sec)

_cache: dict = {}
_geolocator = Nominatim(user_agent="spacex_capex_intelligence_v1", timeout=10)


def _load_cache() -> None:
    global _cache
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r") as f:
                _cache = json.load(f)
            logger.info(f"Geocode cache loaded: {len(_cache)} entries")
    except Exception as e:
        logger.warning(f"Could not load geocode cache: {e}")
        _cache = {}


def _save_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(_cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save geocode cache: {e}")


def geocode_city_state(city: str, state: str) -> tuple:
    """
    Returns (lat, lon) tuple or (None, None) if lookup fails.
    Uses disk cache to avoid re-querying known cities.
    """
    if not city or not state:
        return None, None

    # Normalize bad city values from the DB (e.g., "001" from GA records)
    city_clean = city.strip()
    if not city_clean or city_clean.isdigit() or city_clean in ("001", "N/A", "-"):
        return None, None

    cache_key = f"{city_clean.upper()}|{state.strip().upper()}"

    if cache_key in _cache:
        cached = _cache[cache_key]
        return (cached[0], cached[1]) if cached else (None, None)

    query = f"{city_clean}, {state.strip()}, USA"
    try:
        location = _geolocator.geocode(query)
        time.sleep(_RATE_LIMIT_DELAY)

        if location:
            result = [location.latitude, location.longitude]
            logger.debug(f"Geocoded: {query} -> {result}")
        else:
            result = None
            logger.debug(f"Geocode miss: {query}")

        _cache[cache_key] = result
        _save_cache()
        return (result[0], result[1]) if result else (None, None)

    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        logger.warning(f"Geocoder error for '{query}': {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected geocoder error for '{query}': {e}")
        return None, None


def geocode_batch(leads: list, progress_callback=None) -> list:
    """
    Geocodes a batch of lead dicts in-place, adding 'lat' and 'lon' fields.
    Calls optional progress_callback(done, total) after each lookup.
    Returns the same list with lat/lon populated.
    """
    total = len(leads)
    done = 0

    for lead in leads:
        city = lead.get("city", "")
        state = lead.get("state", "")
        lat, lon = geocode_city_state(city, state)
        lead["lat"] = lat
        lead["lon"] = lon
        done += 1
        if progress_callback:
            progress_callback(done, total)

    return leads


# Load cache at import time
_load_cache()
