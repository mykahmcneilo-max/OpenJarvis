"""Texts Jarvis sends over iMessage: corrections turned into checks.

Each case comes from a real Jarvis text (2026-11-17/18) that broke a SOUL.md
rule. The prompt rule alone didn't stop it, so the cleaner now enforces it.
"""

from __future__ import annotations

from openjarvis.server.webhook_routes import _format_for_sms


def test_trailing_sources_list_is_dropped():
    reply = (
        "Sunny and cool in Atlanta today, about 66 this afternoon. "
        "Sources: YouTube Atlanta weather update (Nov 18, 2026), "
        "Weather Underground hourly forecast for Atlanta."
    )
    expected = "Sunny and cool in Atlanta today, about 66 this afternoon."
    assert _format_for_sms(reply) == expected


def test_sources_block_on_its_own_lines_is_dropped():
    reply = "62 and clear rn\n\nSources:\n- [Open-Meteo](https://open-meteo.com)\n- NWS"
    assert _format_for_sms(reply) == "62 and clear rn"


def test_a_reply_that_is_only_sources_is_kept():
    assert _format_for_sms("Sources: Open-Meteo") == "Sources: Open-Meteo"


def test_assistant_sign_off_is_dropped():
    reply = (
        "Mom, Sam and Alex are who u text most. "
        "Let me know if you want to see what you talk about with any of them!"
    )
    assert _format_for_sms(reply) == "Mom, Sam and Alex are who u text most."


def test_sign_off_in_its_own_bubble_is_dropped():
    reply = (
        "Nothing due tmrw\n\n"
        "Hope this helps! Feel free to ask if you need anything else."
    )
    assert _format_for_sms(reply) == "Nothing due tmrw"


def test_assistant_opener_is_dropped():
    assert _format_for_sms("Certainly! It's 62 and clear rn") == "It's 62 and clear rn"
    reply = "Great question! I'd be happy to help. Spark Before Basel is Fri"
    assert _format_for_sms(reply) == "Spark Before Basel is Fri"


def test_a_reply_that_is_only_a_sign_off_is_kept():
    assert _format_for_sms("Let me know!") == "Let me know!"


def test_casual_let_me_know_mid_reply_is_kept():
    reply = "Let me know when u leave, I'll text u the address"
    assert _format_for_sms(reply) == reply


def test_underscores_inside_links_and_names_survive():
    reply = "tickets at posh.vip/e/hive_art_social, ask for dj_tunez"
    assert _format_for_sms(reply) == reply


def test_markdown_emphasis_is_still_stripped():
    assert _format_for_sms("**Fri** 8pm, _bring_ ID") == "Fri 8pm, bring ID"


def test_math_asterisks_are_left_alone():
    assert _format_for_sms("that's 5*3*2 = 30") == "that's 5*3*2 = 30"


def test_code_block_keeps_its_text_without_stray_backticks():
    out = _format_for_sms("run this:\n```bash\njarvis serve\n```")
    assert "`" not in out
    assert "jarvis serve" in out
