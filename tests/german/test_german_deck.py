import gzip
import json
import re
import sqlite3
import zipfile
from dataclasses import replace

import pytest

from anki_german.analysis import (
    LemmaLevels,
    SentenceRecord,
    analyze,
    level_label,
    load_nlp,
)
from anki_german.deck import build_deck, select_cards
from anki_german.idioms import load_idioms
from anki_german.sources import SentencePair, build_glossary, load_glossary


@pytest.fixture(scope="module")
def nlp():
    return load_nlp()


def _analyze(nlp, sentences: list[str], levels: dict[str, float]) -> dict[str, SentenceRecord]:
    pairs = [SentencePair(i, german, f"en {i}") for i, german in enumerate(sentences)]
    return {r.german: r for r in analyze(pairs, LemmaLevels(levels), nlp=nlp)}


def test_separable_verbs_are_one_target_and_highlight_both_parts(nlp):
    split = "Wir brechen morgen sehr früh auf."
    joined = "Weil wir so früh aufbrechen, sollten wir jetzt schlafen."
    never_split = "Wir müssen den Plan noch einmal überdenken."
    common = {"morgen": 1.0, "sehr": 1.0, "früh": 1.0, "schlafen": 1.0, "jetzt": 1.0}
    records = _analyze(
        nlp,
        [split, joined, never_split],
        {**common, "aufbrechen": 4.0, "brechen": 2.0, "überdenken": 4.5, "Plan": 1.0},
    )

    assert records[split].target_lemma == "aufbrechen"
    assert records[split].separable
    assert '<b class="target">brechen</b>' in records[split].html
    assert '<b class="target"><span class="sep">auf</span></b>' in records[split].html
    # A joined form is marked only because the corpus showed the verb split.
    assert records[joined].target_lemma == "aufbrechen"
    assert '<span class="sep">auf</span>brechen' in records[joined].html
    assert records[never_split].target_lemma == "überdenken"
    assert not records[never_split].separable
    assert "sep" not in records[never_split].html


def test_particles_and_contractions_stay_in_text_but_never_become_targets(nlp):
    sentence = "Ich hab's dir doch schon mal gesagt!"
    levels = {"sagen": 1.0, "doch": 6.0, "schon": 6.0, "mal": 6.0}
    record = _analyze(nlp, [sentence], levels)[sentence]

    assert record.target_lemma == "sagen"
    assert "hab's" in record.html and "doch schon mal" in record.html


def test_sentence_initial_verbs_are_not_mistaken_for_nouns(nlp):
    verb_first = "Amüsieren ihr euch nicht?"
    noun_first = "Leben ist schön, findest du nicht?"
    corpus = [
        verb_first,
        "Wir amüsieren uns sehr gut.",
        noun_first,
        "Ich liebe das Leben sehr.",
        "Wir leben jetzt in Berlin.",
    ]
    levels = {"amüsieren": 4.0, "Leben": 4.0, "leben": 4.0, "schön": 1.0, "finden": 1.0}

    records = _analyze(nlp, corpus, levels)

    assert records[verb_first].target_lemma == "amüsieren"
    assert records[noun_first].target_lemma == "Leben"


def test_lemmas_prefer_dictionary_headwords_and_names_are_never_targets(nlp):
    participle = "Ich habe diese Möhren selbst angebaut."
    imperative = "Fangen wir hier endlich an!"
    name = "Ich heiße Eduard, aber alle nennen mich Eddi."
    brand = "Ich spiele mit der PlayStation 3."
    headwords = frozenset({"anbauen", "Möhre", "anfangen", "fangen"})
    pairs = [SentencePair(i, g, "") for i, g in enumerate([participle, imperative, name, brand])]
    levels = LemmaLevels(
        {"anbauen": 4.0, "Möhre": 3.0, "anfangen": 4.0, "Eduard": 5.0, "PlayStation": 5.0}
    )

    records = {
        r.german: r
        for r in analyze(pairs, levels, nlp=nlp, headwords=headwords, names=frozenset({"Eduard"}))
    }

    assert records[participle].target_lemma == "anbauen"
    assert records[imperative].target_lemma == "anfangen"
    assert records[imperative].separable
    assert records[name].target_lemma != "Eduard"
    assert records[brand].target_lemma == "spielen"


def test_only_conversational_sentences_in_current_spelling_are_kept(nlp):
    kept = ["Ich weiß, dass du recht hast.", "Weißt du, dass sie kommt?"]
    dropped = ["Ich glaube, daß du recht hast.", "Die Stadt liegt am Fluss."]

    records = _analyze(nlp, kept + dropped, {})

    assert sorted(records) == sorted(kept)


def test_grammar_raises_difficulty_above_the_hardest_word(nlp):
    conditional = "Wenn ich Zeit hätte, würde ich gern mitkommen."
    reported = "Er sagte mir, er sei sehr krank."
    passive = "Das Auto wurde gestern von uns repariert."
    future = "Wir werden bald abheben."
    records = _analyze(nlp, [conditional, reported, passive, future], {})

    assert {"konjunktiv-2", "nebensatz"} <= set(records[conditional].grammar)
    assert "passiv" in records[passive].grammar
    assert "passiv" not in records[future].grammar
    assert "konjunktiv-1" in records[reported].grammar
    assert records[reported].difficulty >= 5.0


def test_levels_use_goethe_first_and_frequency_for_the_rest():
    levels = LemmaLevels({"Haus": 1.0})
    assert levels.level("haus") == 1.0
    assert levels.level("Prüfung") < levels.level("Zauberstab")
    # Unseen compounds are graded by their parts; unseen non-compounds (typos) stay hard.
    assert levels.level("Französischlehrerin") < 4.0
    assert levels.level("Tefefon") == 6.0
    assert [level_label(v) for v in (3.0, 3.49, 3.5, 6.0)] == ["B1", "B1", "B1+", "C2"]


def _record(rid: int, lemma: str, target: float, support: float = 1.0, **kw) -> SentenceRecord:
    return SentenceRecord(
        id=rid,
        german=f"Satz {rid}",
        english="",
        html=f"Satz {rid}",
        target_lemma=lemma,
        target_display=lemma,
        target_level=target,
        separable=False,
        support_level=support,
        words=kw.pop("words", 6),
        grammar=kw.pop("grammar", []),
    )


def test_selection_adds_one_new_word_per_card_easiest_first():
    records = [
        _record(1, "erschöpft", 4.0, support=3.0),
        _record(2, "Zauberstab", 4.0, support=4.0),  # two above-level words
        _record(3, "erschöpft", 4.0, support=3.0, words=14),  # same word, longer
        _record(4, "ständig", 3.2),
        _record(5, "Haus", 2.4),  # below the consolidation floor
        _record(6, "krank", 3.0, grammar=["konjunktiv-1"]),  # grammar too hard
    ]

    cards = select_cards(records, level=3.5)

    assert [(c.id, c.target_lemma) for c in cards] == [(4, "ständig"), (1, "erschöpft")]


def _notes(path, tmp_path):
    with zipfile.ZipFile(path) as apkg:
        apkg.extract("collection.anki2", tmp_path)
    db = sqlite3.connect(tmp_path / "collection.anki2")
    rows = db.execute(
        "select n.guid, n.sfld, c.due, n.flds from notes n join cards c on c.nid = n.id"
        " order by c.due"
    ).fetchall()
    db.close()
    return rows


def test_rebuilding_keeps_each_words_note_and_orders_new_cards(tmp_path):
    first = [_record(1, "ständig", 3.2), _record(2, "erschöpft", 4.0)]
    second = [replace(first[0], id=9, html="Anderer Satz"), first[1]]

    a = _notes(build_deck(first, tmp_path / "a.apkg"), tmp_path)
    b = _notes(build_deck(second, tmp_path / "b.apkg"), tmp_path)

    assert [row[1] for row in a] == ["ständig", "erschöpft"]
    assert [row[0] for row in a] == [row[0] for row in b]


def test_glossary_keeps_current_meanings_and_cards_show_them(tmp_path):
    entries = [
        {"word": "Kater", "senses": [{"glosses": ["tomcat"]}]},
        {
            "word": "Kater",
            "senses": [
                {"glosses": ["hangover"]},
                {"glosses": ["ellipsis of Muskelkater"], "tags": ["alt-of"]},
            ],
        },
        {"word": "bog", "senses": [{"glosses": ["preterite of biegen"], "tags": ["form-of"]}]},
        {"word": "amüsieren", "senses": [{"glosses": [g]} for g in ("a", "b", "c", "d")]},
        {
            "word": "Kuh",
            "senses": [{"glosses": ["cow (female bovine) [informal], cattle, heifer, kine"]}],
        },
        {"word": "Nebelhorn", "senses": [{"glosses": ["foghorn"]}]},
        {"word": "Nebelhorn", "pos": "name", "senses": [{"glosses": ["a mountain"]}]},
        {"word": "Eduard", "pos": "name", "senses": [{"glosses": ["a male given name"]}]},
        {"word": "Latein", "pos": "name", "senses": [{"glosses": ["Latin language"]}]},
        {"word": "Schläger", "senses": [{"glosses": ["agent noun of schlagen"]}]},
        {
            "word": "schlagen",
            "senses": [{"glosses": ["to hit, to beat"]}, {"glosses": ["to whip"]}],
        },
        {"word": "Spiel", "senses": [{"glosses": ["game"]}, {"glosses": ["x" * 150]}]},
        {"word": "Abitur", "senses": [{"glosses": ["final exams " + "taken by pupils " * 10]}]},
    ]
    source = tmp_path / "kaikki.jsonl.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.writelines(json.dumps(entry) + "\n" for entry in entries)
    build_glossary(source, tmp_path / "glosses.json")
    glossary = load_glossary(tmp_path / "glosses.json")
    glosses = glossary.glosses

    assert glossary.names == {"Eduard"}
    assert glosses == {
        "Kater": "tomcat; hangover",
        "amüsieren": "a; b; c",
        "Kuh": "cow, cattle, heifer",
        "Spiel": "game",
        "Abitur": ("final exams " + "taken by pupils " * 10).strip(),
        "Nebelhorn": "foghorn",
        "Eduard": "a male given name",
        "Latein": "Latin language",
        "Schläger": "agent noun of schlagen: to hit, to beat",
        "schlagen": "to hit, to beat; to whip",
    }

    # A sentence-initial verb the parser capitalized still finds its meaning, and
    # an unlisted compound shows its most plausible split without guessing senses.
    glosses = {**glosses, "Handtasche": "handbag", "Dieb": "thief", "Hand": "hand"}
    glosses["Taschendieb"] = "pickpocket"
    cards = [
        _record(1, "Amüsieren", 3.0),
        replace(_record(2, "Kater", 3.0), source="idiom"),
        _record(3, "Handtaschendieb", 3.5),
        _record(4, "Abitur", 3.0),
    ]
    fields = [
        row[3].split("\x1f")
        for row in _notes(build_deck(cards, tmp_path / "g.apkg", glosses), tmp_path)
    ]
    assert fields[0][1] == 'Amüsieren<div class="gloss">a; b; c</div>'
    assert "gloss" not in fields[1][1]  # idioms carry their own meaning
    assert fields[2][1] == 'Handtaschendieb<div class="gloss">Handtasche + Dieb</div>'
    # Long meanings show ten words; the rest waits behind a tappable "…".
    shown, more, rest = re.match(
        r'Abitur<div class="gloss">(.*?)<span class="more" onclick="[^"]+">…</span>'
        r'<span class="rest"> (.*)</span></div>$',
        fields[3][1],
    ).group(1, 0, 2)
    assert shown == "final exams taken by pupils taken by pupils taken by"
    assert f"{shown} {rest}" == glosses["Abitur"]


def test_idioms_render_their_markup_and_include_the_requested_ones():
    idioms = {r.target_lemma: r for r in load_idioms()}

    assert len(idioms) == len(load_idioms())
    assert {
        "Ich verstehe nur Bahnhof.",
        "Tomaten auf den Augen haben",
        "Das ist mir Wurst (Wurscht).",
        "jemandem einen Bären aufbinden",
        "Da wird ja der Hund in der Pfanne verrückt!",
    } <= set(idioms)
    for record in idioms.values():
        assert not re.search(r"[\[\]{}]", record.german + record.html + record.target_display)
        assert '<b class="target">' in record.html
        assert 1.0 <= record.target_level <= 6.0
    bear = idioms["jemandem einen Bären aufbinden"]
    assert bear.separable
    assert '<b class="target"><span class="sep">auf</span></b>' in bear.html
