"""Choose cards for a learner level and write them to an APKG."""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping
from pathlib import Path

import genanki
from wordfreq import zipf_frequency

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


def _gloss(record: SentenceRecord, glosses: Mapping[str, str]) -> str:
    """English meaning of the target word; the parser sometimes capitalizes a
    sentence-initial verb ("Amüsieren"), so other cases are tried too."""
    if record.source != "tatoeba":
        return ""  # idioms carry their own meaning
    lemma = record.target_lemma
    if gloss := _lookup(lemma, glosses, whole=True) or _lookup(lemma, glosses):
        return f'<div class="gloss">{html.escape(gloss, quote=False)}</div>'
    # Compound nouns missing from Wiktionary (Lieblingshemd) show their parts.
    # English for each part would often pick the wrong sense (Stunden "to defer"),
    # so only the split is shown, choosing the one whose rarer part is most common
    # (Handtasche + Dieb, not Hand + Taschendieb).
    if lemma[:1].isupper():
        splits = [
            (stem, head)
            for cut in range(3, len(lemma) - 2)
            for link in ("", "s", "n", "e", "en", "es")
            if lemma[:cut].endswith(link)
            for stem, head in [(lemma[: cut - len(link)], lemma[cut:].capitalize())]
            if len(stem) >= 3 and _lookup(stem, glosses) and _lookup(head, glosses)
        ]
        if splits:
            stem, head = max(splits, key=lambda s: min(zipf_frequency(p, "de") for p in s))
            return f'<div class="gloss">{html.escape(f"{stem} + {head}", quote=False)}</div>'
    return ""


def _lookup(word: str, glosses: Mapping[str, str], *, whole: bool = False) -> str:
    """First gloss among the word's case forms; with ``whole``, skip cut-down ones."""
    forms = (word, word.lower(), word.capitalize())
    found = (glosses[f] for f in forms if f in glosses)
    return next((g for g in found if not (whole and g.endswith("…"))), "")


def _fields(record: SentenceRecord, glosses: Mapping[str, str]) -> list[str]:
    source = (
        f'<a href="https://tatoeba.org/de/sentences/show/{record.id}">Tatoeba #{record.id}</a>'
        " · CC BY 2.0 FR"
        if record.source == "tatoeba"
        else "Redewendung"
    )
    return [
        record.target_lemma,
        record.target_display + _gloss(record, glosses),
        record.html,
        html.escape(record.english, quote=False),
        f"{level_label(record.difficulty)} · {record.difficulty:.1f}",
        ", ".join(record.grammar),
        source,
    ]


def _tags(record: SentenceRecord) -> list[str]:
    tags = [f"source::{record.source}", f"level::{level_label(record.difficulty).rstrip('+')}"]
    tags += [f"grammar::{name}" for name in record.grammar]
    if record.separable:
        tags.append("separable")
    return tags


def build_deck(
    cards: list[SentenceRecord],
    output: Path = DECK_OUTPUT_PATH,
    glosses: Mapping[str, str] | None = None,
) -> Path:
    """Write the APKG. New cards keep the given order; each word's note keeps its GUID."""
    model = _model()
    deck = genanki.Deck(DECK_ID, DECK_NAME)
    for position, record in enumerate(cards):
        deck.add_note(
            genanki.Note(
                model=model,
                fields=_fields(record, glosses or {}),
                tags=_tags(record),
                guid=genanki.guid_for(f"german-{record.source}", record.target_lemma),
                due=position,
            )
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(output))
    return output
