"""Download and read Tatoeba sentence pairs, the Goethe word lists, and English meanings."""

from __future__ import annotations

import bz2
import csv
import gzip
import json
import re
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config import (
    CORRECTIONS_PATH,
    GLOSSES_PATH,
    GOETHE_DIR,
    GOETHE_FILES,
    KAIKKI_PATH,
    KAIKKI_URL,
    TATOEBA_DIR,
    TATOEBA_FILES,
)


@dataclass(frozen=True)
class SentencePair:
    id: int
    german: str
    english: str


def fetch_sources(*, force: bool = False) -> list[Path]:
    """Download missing source files into the gitignored reference cache."""
    targets = [(TATOEBA_DIR / name, url) for name, url in TATOEBA_FILES.items()]
    targets += [(GOETHE_DIR / f"{level}.csv", url) for level, url in GOETHE_FILES.items()]
    targets.append((KAIKKI_PATH, KAIKKI_URL))
    written: list[Path] = []
    for path, url in targets:
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "anki-german/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
        written.append(path)
    if force or KAIKKI_PATH in written or not GLOSSES_PATH.exists():
        build_glossary(KAIKKI_PATH, GLOSSES_PATH)
        written.append(GLOSSES_PATH)
    return written


# Senses that only point at another word ("preterite of biegen") or are no longer
# current English Wiktionary usage are left out.
_SKIP_SENSE_TAGS = frozenset({"form-of", "alt-of", "obsolete", "archaic", "dated", "rare"})


# "agent noun of schlagen" names a word without saying what it means, so the
# glossary follows it one step to the base word's meaning.
_DERIVED = re.compile(
    r"^(?:gerund|agent noun|verbal noun|nominalization|diminutive|female equivalent) of (\S+)$"
)


@dataclass(frozen=True)
class Glossary:
    glosses: dict[str, str]
    names: frozenset[str]  # only ever a person or place in Wiktionary (Eduard): not vocabulary


def build_glossary(source: Path, output: Path) -> None:
    """Reduce kaikki's German JSONL to card-sized English meanings and a list of names."""
    common: dict[str, list[str]] = {}
    proper: dict[str, list[str]] = {}
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            bucket = proper if entry.get("pos") == "name" else common
            meanings = bucket.setdefault(entry["word"], [])
            for sense in entry.get("senses", []):
                if _SKIP_SENSE_TAGS & set(sense.get("tags", [])):
                    continue
                # Card-sized: no (notes) or [grammar], at most three synonyms per sense.
                gloss = re.sub(r"\s*(\([^)]*\)|\[[^\]]*\])", "", (sense.get("glosses") or [""])[0])
                gloss = ", ".join(part.strip() for part in gloss.split(",")[:3]).strip()
                if gloss and gloss not in meanings:
                    meanings.append(gloss)
    # A proper-name entry counts only when the word has nothing else: Latein the
    # language yes, Nebelhorn the mountain no (it is also a foghorn). Names other
    # than languages are not vocabulary.
    names = sorted(
        word
        for word, meanings in proper.items()
        if meanings and not common.get(word) and not any("language" in m for m in meanings)
    )
    for word, meanings in proper.items():
        if meanings and not common.get(word):
            common[word] = meanings
    plain = {word: _join(meanings) for word, meanings in common.items() if meanings}

    def resolve(meaning: str) -> str:
        match = _DERIVED.match(meaning)
        base = match and (plain.get(match[1]) or plain.get(match[1].lower()))
        return f"{meaning}: {base.split('; ')[0]}" if base else meaning

    glosses = {
        word: _join([resolve(m) for m in meanings]) for word, meanings in common.items() if meanings
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"glosses": glosses, "names": names}, ensure_ascii=False), encoding="utf-8"
    )


def _join(meanings: list[str]) -> str:
    """Up to three senses of at most 100 characters each; a word with only
    encyclopedic senses (Abitur) keeps its first one whole. Cards show the first
    words and expand the rest on tap."""
    short = [m for m in meanings if len(m) <= 100]
    return "; ".join(short[:3]) if short else meanings[0]


def load_glossary(path: Path = GLOSSES_PATH) -> Glossary:
    if not path.exists():
        return Glossary({}, frozenset())
    data = json.loads(path.read_text(encoding="utf-8"))
    return Glossary(data["glosses"], frozenset(data["names"]))


@dataclass(frozen=True)
class Corrections:
    drop_sentences: frozenset[int]
    translations: dict[int, str]
    meanings: dict[str, str]


def load_corrections(path: Path = CORRECTIONS_PATH) -> Corrections:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Corrections(
        frozenset(data["drop_sentences"]),
        {int(sentence_id): text for sentence_id, text in data["translations"].items()},
        data["meanings"],
    )


def _read_sentences(path: Path) -> dict[int, str]:
    sentences: dict[int, str] = {}
    with bz2.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            sentence_id, _lang, text = line.rstrip("\n").split("\t", 2)
            sentences[int(sentence_id)] = text
    return sentences


def load_pairs(directory: Path = TATOEBA_DIR) -> Iterator[SentencePair]:
    """Yield each German sentence once, with its first English translation."""
    german = _read_sentences(directory / "deu_sentences.tsv.bz2")
    english = _read_sentences(directory / "eng_sentences.tsv.bz2")
    seen: set[int] = set()
    with bz2.open(directory / "deu-eng_links.tsv.bz2", "rt", encoding="utf-8") as handle:
        for line in handle:
            german_id, english_id = (int(part) for part in line.split())
            if german_id in seen or german_id not in german or english_id not in english:
                continue
            seen.add(german_id)
            yield SentencePair(german_id, german[german_id], english[english_id])


def load_goethe_levels(directory: Path = GOETHE_DIR) -> dict[str, float]:
    """Map each Goethe lemma to the first level that lists it (A1 = 1.0 ... B1 = 3.0)."""
    levels: dict[str, float] = {}
    for value, band in enumerate(("A1", "A2", "B1"), start=1):
        with (directory / f"{band}.csv").open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                levels.setdefault(row["Lemma"], float(value))
    return levels
