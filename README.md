# anki-german

Build a German Anki deck for an upper-intermediate learner: conversational
sentences graded by difficulty, separable verbs highlighted, and everyday
idioms.

[![CI](https://github.com/CalvinCoder66/anki-german/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/CalvinCoder66/anki-german/actions/workflows/ci.yml?query=branch%3Amaster)

## What it does

- Takes short conversational German sentences with English translations from
  [Tatoeba](https://tatoeba.org) (CC BY 2.0 FR)
- Grades every word and sentence on one continuous scale (A1=1, A2=2, B1=3,
  B2=4, C1=5, C2=6), so 3.5 means borderline B1/B2
- Gives each card one target word, in a sentence whose other words are at or
  below your level; new cards arrive easiest first
- Shows the target word's English meaning on the back of the card (see
  [Word meanings](#word-meanings))
- Highlights both parts of separable verbs (*Ich **bog** rechts **ab***), and
  keeps modal particles and contractions (doch, mal, *hab's*) in sentences
  without ever making them the target
- Adds the everyday idioms in `data/source/german_idioms.json` and B2–C1
  vocabulary from *Frieren – Präludium* in `data/source/german_praeludium.json`
  (see [Hand-written phrases](#hand-written-phrases))

## Start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Anki desktop](https://apps.ankiweb.net). uv installs the right Python by itself.

```bash
git clone https://github.com/CalvinCoder66/anki-german.git
cd anki-german
uv sync
uv run anki-german fetch            # Tatoeba, Goethe lists, Wiktionary: ~140 MB
uv run anki-german analyze          # grade ~240k sentences, a few minutes, once
uv run anki-german build --level 3.5
```

`fetch` and `analyze` run once. `build` takes seconds; add `--dry-run` to
preview the selection without writing the deck.

## Import into Anki

1. Open Anki desktop and choose **File → Import**, or double-click the file.
2. Pick `data/build/decks/german_tatoeba.apkg`.
3. The cards appear under the **German → Tatoeba** deck. Click it, then
   **Study Now**.

To study on your phone, sign in to a free AnkiWeb account in Anki desktop and
press **Sync**, then sign in to the same account in AnkiDroid (free) or
AnkiMobile (iOS). Later rebuilds reach your phone the same way.

## Word meanings

When you reveal a card, the highlighted word appears in its dictionary form
with a short English meaning underneath:

- Long meanings show their first ten words; tap the highlighted **…** to read
  the rest.
- Compound nouns that the dictionary lacks show how they split instead, such
  as *Ski + Unfall*, so you can work out the meaning from the parts.
- A few words have no meaning yet (about 6% at level 3.5); the sentence
  translation above still gives the sense.
- Idiom and novel-vocabulary cards show a hand-written meaning instead, with a
  literal translation for figurative phrases; both lists have been reviewed.

> **Where this comes from, and how far it is checked.** Meanings are taken
> automatically from English Wiktionary's German entries (via
> [kaikki.org](https://kaikki.org), CC BY-SA), and sentence translations come
> from [Tatoeba](https://tatoeba.org) volunteers. The tool also picks each
> card's dictionary form automatically. A review of 250 sample cards
> (about 5% of the deck) found mostly accurate translations but some
> meanings in the wrong sense or under the wrong dictionary form; those are
> corrected, but the rest of the deck has not been checked card by card.
> Treat a meaning as a hint and trust the sentence translation when they
> disagree.

To fix a card, edit `data/source/german_corrections.json` and rebuild. It
holds the hand corrections applied on every build: `meanings` replaces
Wiktionary's meaning for a word, `translations` replaces a sentence's English
(keyed by the Tatoeba ID shown on each card), and `drop_sentences` removes a
sentence from the deck.

## Move up a level

Rebuild with a higher level and import the new file:

```bash
uv run anki-german build --level 3.8
```

Notes are keyed by their target word or idiom, so re-importing updates
existing cards and keeps your review history instead of duplicating them.
`--span` sets how far above your level targets may reach (default 1.0), and
`--limit` keeps only the easiest N sentences.

## Hand-written phrases

Two lists are always added, slotted in among the sentences by level:

- `data/source/german_idioms.json`: everyday idioms (*Ich verstehe nur Bahnhof*).
- `data/source/german_praeludium.json`: about 180 B2–C1 words and phrases met
  in the preview of the novel *Frieren – Präludium* (levels 3.5–5.5). The
  example sentences are new and everyday, with no names or plot, so they
  spoil nothing; the cards are tagged `source::praeludium`.

A word that one of these lists covers gets no second, Tatoeba card. To add an
entry, edit the file and rebuild. Each entry has the phrase, an English
meaning, an optional literal translation, a level, and an example sentence. In
`example` (and `phrase`), `[...]` marks the target words and `{...}` a
separable particle:

```json
{
  "phrase": "jemandem einen Bären {auf}binden",
  "meaning": "to pull someone's leg; to tell someone a tall tale",
  "literal": "to tie a bear onto someone",
  "level": 4.5,
  "example": "Jetzt [bindest] du mir aber [einen Bären] [{auf}]!",
  "example_en": "Now you're pulling my leg!"
}
```

## How difficulty is graded

- **Words:** a word on the Goethe A1, A2, or B1 list gets that level. Other
  words are graded by how common they are, continuing the frequency drop seen
  across the Goethe levels; rare compounds are graded by their parts.
- **Sentences:** the higher of the hardest word and the hardest grammar
  (subordinate clauses A2; Konjunktiv II, passive, relative clauses B1;
  genitive B1+; *je … desto* B2; Konjunktiv I C1), plus a little for length.
- Pre-1996 spellings such as *daß* are skipped.

Downloads stay in gitignored folders under `data/reference/`; the Goethe lists
are copyrighted and are not committed.

## Mandarin tooling from the fork

This repository was forked from
[anki-chinese](https://github.com/ColinCee/anki-chinese), and its Mandarin deck
tooling is still here under the `anki-chinese` command. The German deck does not
use it. See [Workflows](docs/workflows.md), [Reference](docs/reference.md), and
[Decisions](docs/decisions/) for that tooling; its first rebuild is:

```bash
uv run anki-chinese sync --skip-audio
```

## Contributing

- [Contributing](CONTRIBUTING.md): code map, checks, and documentation maintenance.
- [Security](SECURITY.md): private data and vulnerability reporting.
