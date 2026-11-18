"""Keyless Open-Meteo weather tool."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from openjarvis.tools.free_weather import FreeWeatherTool, geocode


def _resp(body):
    r = MagicMock()
    r.json.return_value = body
    return r


PLACES = {
    "results": [
        {
            "name": "Augusta",
            "admin1": "Maine",
            "country_code": "US",
            "latitude": 44.3,
            "longitude": -69.8,
        },
        {
            "name": "Augusta",
            "admin1": "Georgia",
            "country_code": "US",
            "latitude": 33.5,
            "longitude": -82.0,
        },
    ]
}


def test_state_abbreviation_picks_the_right_city():
    http = MagicMock()
    http.get.return_value = _resp(PLACES)
    assert geocode("Augusta, GA", http)["admin1"] == "Georgia"
    assert geocode("Augusta", http)["admin1"] == "Maine"


def test_returns_current_conditions_and_days():
    http = MagicMock()
    http.get.side_effect = [
        _resp(PLACES),
        _resp(
            {
                "current": {"time": "t", "temperature_2m": 62, "weather_code": 0},
                "daily": {
                    "time": ["2026-11-18"],
                    "weather_code": [61],
                    "temperature_2m_max": [68],
                    "temperature_2m_min": [40],
                    "precipitation_probability_max": [70],
                },
            }
        ),
    ]
    out = FreeWeatherTool(http=http).execute(location="Augusta, GA")
    data = json.loads(out.content)
    assert out.success and data["place"] == "Augusta, Georgia"
    assert data["now"]["sky"] == "clear"
    assert data["days"][0] == {
        "date": "2026-11-18",
        "sky": "light rain",
        "high": 68,
        "low": 40,
        "rain_chance_percent": 70,
    }
    assert http.get.call_args.kwargs["params"]["temperature_unit"] == "fahrenheit"


def test_unknown_place_and_network_errors_fail_cleanly():
    http = MagicMock()
    http.get.return_value = _resp({})
    assert not FreeWeatherTool(http=http).execute(location="Nowhereville").success
    http.get.side_effect = OSError("down")
    out = FreeWeatherTool(http=http).execute(location="Atlanta")
    assert not out.success and "failed" in out.content
