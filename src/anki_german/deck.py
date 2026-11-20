"""Choose cards for a learner level and write them to an APKG."""

from __future__ import annotations

import html
from collections.abc import Iterable
from pathlib import Path

import genanki

from .analysis import SentenceRecord, level_label
from .config import CARDS_DIR, DECK_ID, DECK_NAME, DECK_OUTPUT_PATH, MODEL_ID, MODEL_NAME

FIELDS = ("Key", "KeyDisplay", "Sentence", "English", "Level", "Grammar", "Source")


def select_cards(
    records: Iterable[SentenceRecord],
    *,
    level: float,
    span: float = 1.0,
    limit: int | None = None,
) -> list[SentenceRecord]:
    """One sentence per target word, easiest first.

    A target sits between half a level below ``level`` (consolidation) and
    ``span`` above it. Every other word must be at or below ``level``, so each
    card adds one new word, and grammar may reach at most half a level above.
    """
    best: dict[str, SentenceRecord] = {}
    for record in records:
        if not level - 0.5 <= record.target_level <= level + span:
            continue
        if record.support_level > level or record.grammar_level > level + 0.5:
            continue
        current = best.get(record.target_lemma)
        rank = (record.difficulty, record.words, record.id)
        if current is None or rank < (current.difficulty, current.words, current.id):
            best[record.target_lemma] = record
    ordered = sorted(best.values(), key=lambda r: (r.difficulty, r.target_lemma))
    return ordered[:limit] if limit else ordered


def _card_file(name: str) -> str:
    return (CARDS_DIR / name).read_text(encoding="utf-8")


def _model() -> genanki.Model:
    return genanki.Model(
        MODEL_ID,
        MODEL_NAME,
        fields=[{"name": name} for name in FIELDS],
        templates=[
            {"name": "Reading", "qfmt": _card_file("front.html"), "afmt": _card_file("back.html")}
        ],
        css=_card_file("style.css"),
    )


def _fields(record: SentenceRecord) -> list[str]:
    source = (
        f'<a href="https://tatoeba.org/de/sentences/show/{record.id}">Tatoeba #{record.id}</a>'
        " · CC BY 2.0 FR"
    )
    return [
        record.target_lemma,
        record.target_display,
        record.html,
        html.escape(record.english, quote=False),
        f"{level_label(record.difficulty)} · {record.difficulty:.1f}",
        ", ".join(record.grammar),
        source,
    ]


def _tags(record: SentenceRecord) -> list[str]:
    tags = ["source::tatoeba", f"level::{level_label(record.difficulty).rstrip('+')}"]
    tags += [f"grammar::{name}" for name in record.grammar]
    if record.separable:
        tags.append("separable")
    return tags


def build_deck(cards: list[SentenceRecord], output: Path = DECK_OUTPUT_PATH) -> Path:
    """Write the APKG. New cards keep the given order; each word's note keeps its GUID."""
    model = _model()
    deck = genanki.Deck(DECK_ID, DECK_NAME)
    for position, record in enumerate(cards):
        deck.add_note(
            genanki.Note(
                model=model,
                fields=_fields(record),
                tags=_tags(record),
                guid=genanki.guid_for("german-tatoeba", record.target_lemma),
                due=position,
            )
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(output))
    return output
