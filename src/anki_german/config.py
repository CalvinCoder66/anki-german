"""Paths, Anki identity, and level scale for the German deck.

MODEL_ID and DECK_ID are random integers generated once. Changing them after the
first import makes Anki treat the next import as a new deck and note type.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CARDS_DIR = Path(__file__).resolve().parent / "cards"

DATA_DIR = PROJECT_ROOT / "data"
TATOEBA_DIR = DATA_DIR / "reference" / "tatoeba"
GOETHE_DIR = DATA_DIR / "reference" / "goethe"
# Hand corrections from reviewing cards: dropped sentences, fixed translations,
# and meanings that Wiktionary lacks or gets wrong for the deck.
CORRECTIONS_PATH = DATA_DIR / "source" / "german_corrections.json"
IDIOMS_PATH = DATA_DIR / "source" / "german_idioms.json"
SENTENCES_PATH = DATA_DIR / "state" / "german_sentences.jsonl"
DECK_OUTPUT_PATH = DATA_DIR / "build" / "decks" / "german_tatoeba.apkg"

TATOEBA_FILES = {
    "deu_sentences.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/deu/deu_sentences.tsv.bz2",
    "eng_sentences.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
    "deu-eng_links.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/deu/deu-eng_links.tsv.bz2",
}
# English Wiktionary's German entries, extracted by kaikki.org (CC BY-SA). The
# 100 MB download is reduced to a small word -> meaning file once, on fetch.
KAIKKI_URL = "https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz"
KAIKKI_PATH = DATA_DIR / "reference" / "kaikki" / "german.jsonl.gz"
GLOSSES_PATH = DATA_DIR / "reference" / "kaikki" / "glosses.json"
# Goethe-Institut word lists, published through the DWDS API. They are
# copyrighted, so they stay in the gitignored download cache.
GOETHE_FILES = {
    level: f"https://www.dwds.de/api/lemma/goethe/{level}.csv" for level in ("A1", "A2", "B1")
}

MODEL_ID = 1_946_215_803
DECK_ID = 1_946_215_804
MODEL_NAME = "German Sentences"
DECK_NAME = "German::Tatoeba"

# One continuous scale: A1 = 1.0, A2 = 2.0, B1 = 3.0, B2 = 4.0, C1 = 5.0, C2 = 6.0.
BANDS = ("A1", "A2", "B1", "B2", "C1", "C2")
