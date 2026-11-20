"""Download and read Tatoeba sentence pairs and the Goethe word lists."""

from __future__ import annotations

import bz2
import csv
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config import GOETHE_DIR, GOETHE_FILES, TATOEBA_DIR, TATOEBA_FILES


@dataclass(frozen=True)
class SentencePair:
    id: int
    german: str
    english: str


def fetch_sources(*, force: bool = False) -> list[Path]:
    """Download missing source files into the gitignored reference cache."""
    targets = [(TATOEBA_DIR / name, url) for name, url in TATOEBA_FILES.items()]
    targets += [(GOETHE_DIR / f"{level}.csv", url) for level, url in GOETHE_FILES.items()]
    written: list[Path] = []
    for path, url in targets:
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "anki-german/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
        written.append(path)
    return written


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
