"""Weather with no API key or account, backed by Open-Meteo.

``get_weather`` needs an OpenWeatherMap key; this one works out of the box,
so phone and chat questions like "weather in Fort Gordon?" get real numbers
instead of forecast-page titles from web search.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_US_STATES = dict(
    pair.split(":")
    for pair in (
        "al:alabama ak:alaska az:arizona ar:arkansas ca:california "
        "co:colorado ct:connecticut de:delaware fl:florida ga:georgia "
        "hi:hawaii id:idaho il:illinois in:indiana ia:iowa ks:kansas "
        "ky:kentucky la:louisiana me:maine md:maryland ma:massachusetts "
        "mi:michigan mn:minnesota ms:mississippi mo:missouri mt:montana "
        "ne:nebraska nv:nevada nh:new_hampshire nj:new_jersey "
        "nm:new_mexico ny:new_york nc:north_carolina nd:north_dakota "
        "oh:ohio ok:oklahoma or:oregon pa:pennsylvania ri:rhode_island "
        "sc:south_carolina sd:south_dakota tn:tennessee tx:texas ut:utah "
        "vt:vermont va:virginia wa:washington wv:west_virginia "
        "wi:wisconsin wy:wyoming dc:district_of_columbia"
    ).split()
)

# WMO weather codes -> words.
_CODES = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "heavy showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "thunderstorms with hail",
}


def _matches(place: dict[str, Any], region: str) -> bool:
    region = region.strip().lower()
    if not region:
        return True
    region = _US_STATES.get(region, region).replace("_", " ")
    fields = (
        place.get("admin1"),
        place.get("country"),
        place.get("country_code"),
    )
    return any(str(f or "").lower() == region for f in fields)


def geocode(location: str, http: Any = httpx) -> dict[str, Any] | None:
    """Best Open-Meteo match for "City", "City, ST" or "City, Country"."""
    name, _, region = location.partition(",")
    resp = http.get(
        _GEO_URL,
        params={"name": name.strip(), "count": 10, "language": "en"},
        timeout=10,
    )
    resp.raise_for_status()
    places = resp.json().get("results") or []
    for place in places:
        if _matches(place, region):
            return place
    return places[0] if places else None


@ToolRegistry.register("weather")
class FreeWeatherTool(BaseTool):
    """Current conditions and a 3-day forecast for any place, no key needed."""

    tool_id = "weather"
    is_local = False

    def __init__(self, http: Any = httpx) -> None:
        self._http = http

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="weather",
            description=(
                "Live weather: current conditions plus the next 7 days' "
                "highs/lows and rain chance, for any city or place. "
                "Use this for every weather question instead of web_search."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Place name, optionally with state or country: "
                            "'Atlanta', 'Augusta, GA', 'Fort Gordon', 'Paris, FR'."
                        ),
                    },
                    "units": {
                        "type": "string",
                        "enum": ["imperial", "metric"],
                        "description": "Defaults to imperial (°F, mph).",
                    },
                },
                "required": ["location"],
            },
            category="weather",
            latency_estimate=1.0,
            timeout_seconds=20.0,
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        location = str(params.get("location") or "").strip()[:200]
        if not location:
            return self._fail("Which place? Pass a location.")
        metric = params.get("units") == "metric"
        try:
            place = geocode(location, self._http)
            if place is None:
                return self._fail(f"Couldn't find a place called '{location}'.")
            resp = self._http.get(
                _FORECAST_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m,relative_humidity_2m",
                    "daily": "weather_code,temperature_2m_max,"
                    "temperature_2m_min,precipitation_probability_max",
                    "temperature_unit": "celsius" if metric else "fahrenheit",
                    "wind_speed_unit": "kmh" if metric else "mph",
                    "timezone": "auto",
                    "forecast_days": 7,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # network/HTTP errors: say so, don't crash
            return self._fail(f"Weather lookup failed: {type(exc).__name__}")

        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        days = [
            {
                "date": date,
                "sky": _CODES.get(code, "unknown"),
                "high": hi,
                "low": lo,
                "rain_chance_percent": rain,
            }
            for date, code, hi, lo, rain in zip(
                daily.get("time") or [],
                daily.get("weather_code") or [],
                daily.get("temperature_2m_max") or [],
                daily.get("temperature_2m_min") or [],
                daily.get("precipitation_probability_max") or [],
            )
        ]
        where = ", ".join(str(p) for p in (place.get("name"), place.get("admin1")) if p)
        result = {
            "place": where,
            "units": "°C, km/h" if metric else "°F, mph",
            "local_time": cur.get("time"),
            "now": {
                "temp": cur.get("temperature_2m"),
                "feels_like": cur.get("apparent_temperature"),
                "sky": _CODES.get(cur.get("weather_code"), "unknown"),
                "wind": cur.get("wind_speed_10m"),
                "humidity_percent": cur.get("relative_humidity_2m"),
            },
            "days": days,
        }
        return ToolResult(
            tool_name="weather",
            content=json.dumps(result, ensure_ascii=False),
            success=True,
            metadata={"provider": "open-meteo", "place": where},
        )

    @staticmethod
    def _fail(message: str) -> ToolResult:
        return ToolResult(tool_name="weather", content=message, success=False)


__all__ = ["FreeWeatherTool", "geocode"]
