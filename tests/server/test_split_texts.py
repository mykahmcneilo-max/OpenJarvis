"""iMessage replies go out as a few short texts, like a person texting."""

from __future__ import annotations

from openjarvis.server.webhook_routes import split_into_texts


def test_blank_lines_become_separate_texts():
    assert split_into_texts("yo that's tmrw\n\n6-8:30 at atdc\n\nu going?") == [
        "yo that's tmrw",
        "6-8:30 at atdc",
        "u going?",
    ]


def test_long_paragraph_splits_at_sentence_ends():
    para = " ".join(f"sentence number {i} is right here." for i in range(12))
    texts = split_into_texts(para)
    assert len(texts) > 1
    assert all(t.endswith(".") for t in texts)
    assert " ".join(texts) == para


def test_short_reply_stays_one_text_and_lists_stay_together():
    assert split_into_texts("62 and clear rn") == ["62 and clear rn"]
    listing = "- milk\n- eggs\n- " + "bread " * 40
    assert split_into_texts(listing) == [listing.strip()]


def test_never_floods_more_than_five_texts():
    texts = split_into_texts("\n\n".join(f"text {i}" for i in range(9)))
    assert len(texts) == 5
    assert texts[-1] == "text 4 text 5 text 6 text 7 text 8"
