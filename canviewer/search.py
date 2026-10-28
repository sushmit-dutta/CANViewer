"""Signal search: forgiving, multi-term, and independent of the UI.

A query is split on whitespace/commas; every term must match somewhere in a
signal's searchable text (signal name, message name, sender node, unit, DBC
comment, CAN ID). Matching ignores case and separators, so ``batt volt``
finds ``Battery_Voltage`` and ``bms 0x1a4`` finds signals of that message.
Terms may use ``*`` and ``?`` wildcards. If nothing matches, a subsequence
("fuzzy") match on the signal name is tried so typos and abbreviations still
land somewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from canviewer.data import SignalInfo

_SEPARATORS = re.compile(r"[\s_\-.:/]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_TERM_SPLIT = re.compile(r"[\s,]+")
_ID_TERM = re.compile(r"^0x[0-9a-fA-F]+$")

# Lower rank sorts first.
_RANK_EXACT, _RANK_PREFIX, _RANK_WORD, _RANK_NAME, _RANK_MESSAGE, _RANK_OTHER = range(6)


def squash(text: str) -> str:
    """Lowercase and drop separators: ``Battery_Voltage`` -> ``batteryvoltage``."""
    return _SEPARATORS.sub("", text).lower()


def words(text: str) -> List[str]:
    """Split a name into lowercase words on separators and camelCase humps."""
    out: List[str] = []
    for chunk in _SEPARATORS.split(text):
        out.extend(w.lower() for w in _CAMEL.split(chunk) if w)
    return out


def _term_matcher(term: str):
    """Return a predicate on squashed text for one query term."""
    needle = squash(term.replace("*", "\0").replace("?", "\1"))
    if "\0" not in needle and "\1" not in needle:
        return lambda text: needle in text
    pattern = re.compile(re.escape(needle).replace("\0", ".*").replace("\1", "."))
    return lambda text: pattern.search(text) is not None


def _is_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


@dataclass(frozen=True)
class _Entry:
    info: SignalInfo
    name: str  # squashed signal name
    name_words: Tuple[str, ...]
    message: str  # squashed message name
    other: str  # squashed senders + unit + comment + CAN ID
    id_hex: str  # lowercase hex CAN ID, '' if unknown
    message_text: str  # squashed message-level text (message, senders, ID)


@dataclass
class SearchResult:
    """Ranked matches. `messages` are message names that matched as a whole."""

    signals: List[SignalInfo] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    total: int = 0  # matching signals before `limit` was applied
    fuzzy: bool = False


class SearchIndex:
    """Pre-normalised catalog; build once, query on every keystroke."""

    def __init__(self, catalog: Iterable[SignalInfo]):
        self._entries: List[_Entry] = []
        self._message_text: Dict[str, str] = {}
        for info in catalog:
            id_text = ""
            if info.message_id is not None:
                id_text = f"{info.message_id:x} {info.message_id}"
            message_text = squash(f"{info.message} {' '.join(info.senders)} {id_text}")
            other = squash(f"{' '.join(info.senders)} {info.unit} {info.comment} {id_text}")
            self._entries.append(
                _Entry(
                    info=info,
                    name=squash(info.name),
                    name_words=tuple(words(info.name)),
                    message=squash(info.message),
                    other=other,
                    id_hex=f"{info.message_id:x}" if info.message_id is not None else "",
                    message_text=message_text,
                )
            )
            if info.message:
                self._message_text[info.message] = message_text

    def search(self, query: str, limit: Optional[int] = None) -> SearchResult:
        terms = [t for t in _TERM_SPLIT.split(query.strip()) if squash(t)]
        if not terms:
            return SearchResult()
        matchers = [_term_matcher(t) for t in terms]

        ranked: List[Tuple[int, str, SignalInfo]] = []
        for e in self._entries:
            rank = self._rank(e, terms, matchers)
            if rank is not None:
                ranked.append((rank, e.info.name, e.info))
        ranked.sort(key=lambda r: (r[0], r[1].lower()))

        messages = sorted(
            m for m, text in self._message_text.items() if all(fn(text) for fn in matchers)
        )
        signals = [r[2] for r in ranked]
        result = SearchResult(signals=signals[:limit], messages=messages, total=len(signals))
        if not ranked and not messages:
            fuzzy = self._fuzzy(terms)
            result = SearchResult(
                signals=fuzzy[:limit], messages=[], total=len(fuzzy), fuzzy=bool(fuzzy)
            )
        return result

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _rank(e: _Entry, terms: Sequence[str], matchers) -> Optional[int]:
        """Rank of the weakest-matching term (so every term must match), or None."""
        worst = _RANK_EXACT
        for term, fn in zip(terms, matchers):
            sq = squash(term)
            if _ID_TERM.match(term):
                if e.id_hex.startswith(term[2:].lower().lstrip("0") or "0"):
                    rank = _RANK_OTHER
                else:
                    return None
            elif "*" in term or "?" in term:
                if fn(e.name):
                    rank = _RANK_NAME
                elif fn(e.message):
                    rank = _RANK_MESSAGE
                elif fn(e.other):
                    rank = _RANK_OTHER
                else:
                    return None
            elif e.name == sq:
                rank = _RANK_EXACT
            elif e.name.startswith(sq):
                rank = _RANK_PREFIX
            elif any(w.startswith(sq) for w in e.name_words):
                rank = _RANK_WORD
            elif fn(e.name):
                rank = _RANK_NAME
            elif fn(e.message):
                rank = _RANK_MESSAGE
            elif fn(e.other):
                rank = _RANK_OTHER
            else:
                return None
            worst = max(worst, rank)
        return worst

    def _fuzzy(self, terms: Sequence[str]) -> List[SignalInfo]:
        needle = squash("".join(t for t in terms if "*" not in t and "?" not in t))
        if len(needle) < 4:
            return []
        hits = [e.info for e in self._entries if _is_subsequence(needle, e.name)]
        hits.sort(key=lambda i: (len(i.name), i.name.lower()))
        return hits
