"""Grade German sentences on one continuous CEFR scale and pick one target per sentence.

Everything here is deterministic: spaCy parses, simplemma lemmatizes, the Goethe
lists and wordfreq grade words, and fixed rules grade grammar.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import simplemma
import spacy
from spacy.language import Language
from wordfreq import zipf_frequency

from .config import BANDS
from .sources import SentencePair

# Modal particles stay in sentences but are never the word a card teaches.
SKIP_WORDS = frozenset({"doch", "mal", "eben", "halt", "ja", "noch", "schon"})
CONTENT_POS = frozenset({"NOUN", "VERB", "ADJ", "ADV"})
CONVERSATIONAL = re.compile(r"\b(ich|mich|mir|du|dich|dir|wir|uns|ihr|euch)\b", re.IGNORECASE)

GRAMMAR_LEVELS = {
    "nebensatz": 2.0,
    "konjunktiv-2": 3.0,
    "passiv": 3.0,
    "plusquamperfekt": 3.0,
    "relativsatz": 3.0,
    "infinitivsatz": 3.0,
    "genitiv": 3.5,
    "konjunktiv-2-stark": 4.0,
    "je-desto": 4.0,
    "konjunktiv-1": 5.0,
}
_KONJ2_WEAK = frozenset(
    {"werden", "haben", "sein", "können", "müssen", "dürfen", "sollen", "wollen", "mögen"}
)


def level_label(value: float) -> str:
    """3.0 -> "B1", 3.5 -> "B1+", 4.2 -> "B2"."""
    clamped = min(max(value, 1.0), 6.0)
    band = BANDS[min(int(clamped), 6) - 1]
    return f"{band}+" if clamped - int(clamped) >= 0.5 and clamped < 6.0 else band


@dataclass(frozen=True)
class LemmaLevels:
    """Grade a lemma: Goethe A1-B1 lists first, then word frequency for everything else."""

    goethe: Mapping[str, float]

    def level(self, lemma: str) -> float:
        simple = self._simple(lemma)
        if simple < 5.0 or not lemma[:1].isupper() or self._listed(lemma) is not None:
            return simple
        # Rare nouns are often transparent compounds (Französischlehrerin): grade
        # by the harder of two common parts, plus a little for the combination.
        for cut in range(3, len(lemma) - 3):
            modifier, head = lemma[:cut], lemma[cut:].capitalize()
            for link in ("", "s", "es", "n", "en", "e"):
                if link and not modifier.endswith(link):
                    continue
                stem = modifier[: len(modifier) - len(link)]
                if min(zipf_frequency(stem, "de"), zipf_frequency(head, "de")) >= 3.5:
                    return min(simple, max(self._simple(stem), self._simple(head)) + 0.25)
        return simple

    def _listed(self, lemma: str) -> float | None:
        for form in (lemma, lemma.lower(), lemma.capitalize()):
            if form in self.goethe:
                return self.goethe[form]
        return None

    def _simple(self, lemma: str) -> float:
        listed = self._listed(lemma)
        if listed is not None:
            return listed
        # Goethe list medians fall about 0.3 Zipf per level (A1 4.75, A2 4.39,
        # B1 4.12). Off-list words continue that slope: Zipf 3.8 is about B2 (4.0),
        # 3.5 about C1, 3.2 about C2. Common off-list words floor at A2.
        zipf = zipf_frequency(lemma, "de")
        return round(min(6.0, max(2.0, 4.0 + (3.8 - zipf) / 0.3)), 2)


@dataclass
class SentenceRecord:
    id: int
    german: str
    english: str
    html: str
    target_lemma: str
    target_display: str
    target_level: float
    separable: bool
    support_level: float
    words: int
    grammar: list[str] = field(default_factory=list)
    source: str = "tatoeba"  # or "idiom"

    @property
    def grammar_level(self) -> float:
        return max((GRAMMAR_LEVELS[name] for name in self.grammar), default=1.0)

    @property
    def difficulty(self) -> float:
        length = 0.05 * max(0, self.words - 8)
        return round(max(self.target_level, self.grammar_level) + length, 2)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SentenceRecord:
        return cls(**data)


@dataclass(frozen=True)
class _Token:
    text: str
    ws: str
    lemma: str
    pos: str


@dataclass(frozen=True)
class _Parsed:
    pair: SentencePair
    tokens: list[_Token]
    splits: dict[int, int]  # verb index -> separated particle index
    grammar: list[str]


@dataclass(frozen=True)
class _Unit:
    lemma: str
    indices: tuple[int, ...]
    particle: str = ""  # set for separable verbs
    joined: bool = False  # particle is the start of indices[0], as in "aufzubrechen"


def load_nlp() -> Language:
    return spacy.load("de_core_news_sm", disable=["ner"])


def is_candidate(german: str) -> bool:
    """Short conversational sentences: 4-14 words, addressed to or from a person."""
    words = len(german.split())
    return 4 <= words <= 14 and bool(
        CONVERSATIONAL.search(german) or german.rstrip().endswith(("?", "!"))
    )


def _current_spelling(pairs: list[SentencePair]) -> list[SentencePair]:
    """Drop pre-1996 spellings ("daß", "Kompromiß"): the corpus uses their ss form more.

    wordfreq folds ß into ss, so the corpus itself is the evidence.
    """
    words = Counter(w for p in pairs for w in re.findall(r"\w+", p.german.lower()))
    old = {w for w in words if "ß" in w and words[w.replace("ß", "ss")] > words[w]}
    return [p for p in pairs if not old & set(re.findall(r"\w+", p.german.lower()))]


def _lemma(text: str, pos: str) -> str:
    return simplemma.lemmatize(text if pos in {"NOUN", "PROPN"} else text.lower(), lang="de")


def _grammar(doc: Any) -> list[str]:
    found: set[str] = set()
    for token in doc:
        mood, tense = token.morph.get("Mood"), token.morph.get("Tense")
        if "Sub" in mood:
            if "Past" in tense:
                weak = _lemma(token.text, token.pos_) in _KONJ2_WEAK
                found.add("konjunktiv-2" if weak else "konjunktiv-2-stark")
            elif "3" in token.morph.get("Person"):
                found.add("konjunktiv-1")
        # The small model sometimes tags an infinitive as a participle ("Wir werden
        # bald abheben"), so a participle must differ from its infinitive.
        participle = token.tag_ == "VVPP" and token.lower_ != _lemma(token.text, token.pos_)
        if participle and token.head.tag_.startswith("VA"):
            head = _lemma(token.head.text, token.head.pos_)
            if head == "werden":
                found.add("passiv")
            elif (
                head in {"haben", "sein"}
                and "Past" in token.head.morph.get("Tense")
                and "Ind" in token.head.morph.get("Mood")
            ):
                found.add("plusquamperfekt")
        if token.tag_ == "PRELS":
            found.add("relativsatz")
        elif token.tag_ == "KOUS":
            found.add("nebensatz")
        elif token.tag_ == "KOUI":
            found.add("infinitivsatz")
        if "Gen" in token.morph.get("Case") and token.pos_ in {"NOUN", "DET"}:
            found.add("genitiv")
    if {"je", "desto"} <= {token.lower_ for token in doc}:
        found.add("je-desto")
    return sorted(found)


def _parse(pair: SentencePair, doc: Any) -> _Parsed:
    tokens = [_Token(t.text, t.whitespace_, _lemma(t.text, t.pos_), t.pos_) for t in doc]
    # A separated particle (dependency "svp") attaches to its full or auxiliary verb.
    # Modal heads are skipped: in "Wir müssen jetzt los" the particle belongs to an
    # elided verb, not to "müssen".
    splits = {
        t.head.i: t.i
        for t in doc
        if t.dep_ == "svp" and t.head.tag_[:2] in {"VV", "VA"} and t.head.i != t.i
    }
    return _Parsed(pair, tokens, splits, _grammar(doc))


def _units(parsed: _Parsed, separable: Mapping[str, str]) -> list[_Unit]:
    particles = set(parsed.splits.values())
    units: list[_Unit] = []
    for index, token in enumerate(parsed.tokens):
        if index in particles:
            continue
        if index in parsed.splits:
            particle = parsed.tokens[parsed.splits[index]].text.lower()
            lemma = particle + token.lemma.lower()
            units.append(_Unit(lemma, (index, parsed.splits[index]), particle))
            continue
        lower = token.text.lower()
        if token.pos not in CONTENT_POS or not token.text.isalpha() or lower in SKIP_WORDS:
            continue
        particle = separable.get(token.lemma, "")
        if particle and lower.startswith(particle) and len(lower) > len(particle):
            units.append(_Unit(token.lemma, (index,), particle, joined=True))
        else:
            units.append(_Unit(token.lemma, (index,)))
    return units


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _render(tokens: list[_Token], unit: _Unit) -> str:
    parts: list[str] = []
    for index, token in enumerate(tokens):
        text = _escape(token.text)
        if index in unit.indices:
            if unit.joined:
                cut = len(unit.particle)
                head, tail = _escape(token.text[:cut]), _escape(token.text[cut:])
                text = f'<span class="sep">{head}</span>{tail}'
            elif unit.particle and index == unit.indices[1]:
                text = f'<span class="sep">{text}</span>'
            text = f'<b class="target">{text}</b>'
        parts.append(text + token.ws)
    return "".join(parts).strip()


def _display(unit: _Unit) -> str:
    if not unit.particle:
        return _escape(unit.lemma)
    rest = _escape(unit.lemma[len(unit.particle) :])
    return f'<span class="sep">{_escape(unit.particle)}</span>|{rest} <span class="badge">trennbar</span>'


def analyze(
    pairs: Iterable[SentencePair],
    levels: LemmaLevels,
    *,
    nlp: Language | None = None,
    progress: Callable[[int], None] | None = None,
) -> list[SentenceRecord]:
    """Parse candidate sentences and return one graded record per usable sentence."""
    nlp = nlp or load_nlp()
    candidates = _current_spelling([pair for pair in pairs if is_candidate(pair.german)])
    parsed: list[_Parsed] = []
    for count, (pair, doc) in enumerate(
        zip(candidates, nlp.pipe((p.german for p in candidates), batch_size=512), strict=True),
        start=1,
    ):
        parsed.append(_parse(pair, doc))
        if progress and count % 10_000 == 0:
            progress(count)

    # Any verb seen split anywhere in the corpus is separable, which lets joined
    # forms ("weil wir aufbrechen", "ausgesucht") highlight their particle too,
    # without guessing for ambiguous prefixes like über- or unter-.
    separable: dict[str, str] = {}
    for item in parsed:
        for verb, particle in item.splits.items():
            prefix = item.tokens[particle].text.lower()
            separable.setdefault(prefix + item.tokens[verb].lemma.lower(), prefix)

    records: list[SentenceRecord] = []
    for item in parsed:
        units = _units(item, separable)
        if not units:
            continue
        graded = sorted(((levels.level(u.lemma), -i, u) for i, u in enumerate(units)), reverse=True)
        target_level, _, target = graded[0]
        records.append(
            SentenceRecord(
                id=item.pair.id,
                german=item.pair.german,
                english=item.pair.english,
                html=_render(item.tokens, target),
                target_lemma=target.lemma,
                target_display=_display(target),
                target_level=target_level,
                separable=bool(target.particle),
                support_level=graded[1][0] if len(graded) > 1 else 1.0,
                words=len(item.pair.german.split()),
                grammar=item.grammar,
            )
        )
    return records
