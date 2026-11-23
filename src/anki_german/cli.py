"""anki-german: fetch Tatoeba, grade sentences, and build a deck for your level."""

from __future__ import annotations

import json
from collections import Counter

import typer

from .analysis import LemmaLevels, SentenceRecord, analyze, level_label
from .config import DECK_OUTPUT_PATH, SENTENCES_PATH
from .deck import build_deck, select_cards
from .idioms import load_idioms
from .sources import fetch_sources, load_glosses, load_goethe_levels, load_pairs

app = typer.Typer(
    help="German deck from Tatoeba. Levels use one scale: A1=1, A2=2, B1=3, B2=4, C1=5, C2=6.",
    no_args_is_help=True,
)


def _histogram(records: list[SentenceRecord]) -> str:
    counts = Counter(level_label(r.difficulty) for r in records)
    return "  ".join(f"{band}: {counts[band]}" for band in sorted(counts))


@app.command()
def fetch(force: bool = typer.Option(False, help="Download again even if cached.")) -> None:
    """Download Tatoeba sentences, the Goethe A1-B1 lists, and Wiktionary meanings."""
    written = fetch_sources(force=force)
    typer.echo("\n".join(f"Downloaded {path}" for path in written) or "All sources cached.")


@app.command("analyze")
def analyze_command() -> None:
    """Parse and grade every conversational sentence (deterministic, a few minutes)."""
    levels = LemmaLevels(load_goethe_levels())
    records = analyze(load_pairs(), levels, progress=lambda n: typer.echo(f"  parsed {n:,}"))
    SENTENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SENTENCES_PATH.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    typer.echo(f"Wrote {len(records):,} graded sentences to {SENTENCES_PATH}")
    typer.echo(_histogram(records))


@app.command()
def build(
    level: float = typer.Option(..., help="Your level, e.g. 3.5 for borderline B1/B2."),
    span: float = typer.Option(1.0, help="How far above your level targets may reach."),
    limit: int | None = typer.Option(None, help="Keep only the easiest N cards."),
    dry_run: bool = typer.Option(False, help="Show the selection without writing the APKG."),
) -> None:
    """Pick one sentence per new word for LEVEL, add the idioms, and write the APKG."""
    if not SENTENCES_PATH.exists():
        raise typer.BadParameter("Run `anki-german fetch` and `anki-german analyze` first.")
    with SENTENCES_PATH.open(encoding="utf-8") as handle:
        records = [SentenceRecord.from_dict(json.loads(line)) for line in handle]
    # Idioms are always included and slot in among the sentences by level.
    cards = sorted(
        select_cards(records, level=level, span=span, limit=limit) + load_idioms(),
        key=lambda r: (r.difficulty, r.target_lemma),
    )
    typer.echo(f"{len(cards):,} cards for level {level} ({level_label(level)})")
    typer.echo(_histogram(cards))
    for card in cards[:: max(1, len(cards) // 10)][:10]:
        typer.echo(f"  {card.difficulty:.1f}  {card.target_lemma:<18} {card.german}")
    if not dry_run:
        typer.echo(f"Wrote {build_deck(cards, DECK_OUTPUT_PATH, load_glosses())}")
