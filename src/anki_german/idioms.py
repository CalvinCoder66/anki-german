"""Hand-written everyday idioms, turned into the same records as Tatoeba sentences.

In ``example`` and ``idiom``, ``[...]`` marks the idiom's words and ``{...}`` a
separable-verb particle, so cards highlight them like Tatoeba targets.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .analysis import SentenceRecord
from .config import IDIOMS_PATH

_MARKUP = re.compile(r"[\[\]{}]")


def _render(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\[(.+?)\]", r'<b class="target">\1</b>', escaped)
    return re.sub(r"\{(.+?)\}", r'<span class="sep">\1</span>', escaped)


def _plain(text: str) -> str:
    return _MARKUP.sub("", text)


def load_idioms(path: Path = IDIOMS_PATH) -> list[SentenceRecord]:
    records: list[SentenceRecord] = []
    for index, item in enumerate(json.loads(path.read_text(encoding="utf-8"))):
        separable = "{" in item["example"]
        gloss = html.escape(f"{item['meaning']} · lit. “{item['literal']}”", quote=False)
        badge = ' <span class="badge">trennbar</span>' if separable else ""
        records.append(
            SentenceRecord(
                id=index,
                german=_plain(item["example"]),
                english=item["example_en"],
                html=_render(item["example"]),
                target_lemma=_plain(item["idiom"]),
                target_display=f'{_render(item["idiom"])}{badge}<div class="gloss">{gloss}</div>',
                target_level=float(item["level"]),
                separable=separable,
                support_level=1.0,
                words=len(_plain(item["example"]).split()),
                source="idiom",
            )
        )
    return records
