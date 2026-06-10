"""Validator: Mid-Sentence Keyword Capitalization.

MTG templating capitalizes a keyword ability only when it **begins** a line or a
sentence — the standalone keyword line ("Flying", "Trample, lifelink") or the
first word of an ability ("Trample. When ~ attacks, ..."). Anywhere *inside*
running text the keyword is **lowercase**: "this creature gains flying until end
of turn", "creatures you control have trample and lifelink", "target creature
gains indestructible". Local card-gen models routinely over-capitalize the
running-text case (observed live 2026-06-10: card 047 Princess Celestia, "gains
Indestructible until end of turn", "gains Lifelink").

This is the running-text complement to ``rules_text.fix_keyword_capitalization``,
which only lowercases the second-and-later entries of a *comma-separated keyword
list line* ("Flying, Trample" -> "Flying, trample"). That fixer never touches a
keyword embedded in a sentence; this one does, and only that.

Rules (deliberately conservative — a false fix corrupts a name, so we only act
when we're confident the token is a keyword used as a common noun/verb):

* **Vocabulary** is ``rules_text.all_keywords()`` — evergreen keywords plus the
  active set's custom mechanic names. Only single-word keywords are handled;
  multi-word keywords ("double strike", "first strike") are skipped (the
  mid-sentence multi-word case is rare and the casing rules for an internal
  multi-word run are murkier — left to the council).
* **Reminder text is skipped** byte-for-byte (parenthesized spans), per the
  validators-skip-parenthesized-text contract — a reminder may legitimately
  capitalize a keyword.
* **Quoted spans are skipped** — a granted ability in quotes (gains "Flying")
  is its own ability text whose first word is legitimately capitalized.
* **Sentence/line starts are skipped** — a keyword is only lowercased when it is
  *not* the first word of its line and *not* the first word after a sentence
  terminator (``.`` ``!`` ``?`` ``:`` ``;`` ``•`` ``—`` and a following space).
  The standalone keyword line and the "Trample." lead keyword stay capitalized.
* **Capitalized multi-word runs are skipped** — when the capitalized keyword is
  adjacent (immediately before or after) to *another* capitalized word, it is
  most likely part of a proper name ("Flying Men", "Reach of the Wild"), so it
  is left alone. A lone capitalized keyword surrounded by lowercase running text
  is the clear "gains Flying" case we fix.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity
from mtgai.validation.rules_text import _is_keyword_only_line, all_keywords

# Splits oracle text into alternating non-paren / paren / non-quote / quote
# spans so the casing pass runs only on the running-text spans. A paren span is
# reminder text; a double-quoted span is a granted ability's own text — both
# keep their casing verbatim.
_SKIP_SPAN_RE = re.compile(r'\([^)]*\)|"[^"]*"')

# Characters that, immediately before a keyword (skipping spaces), mark the
# keyword as the first word of a clause — where capitalization is correct.
_SENTENCE_START_CHARS = frozenset(".!?:;•—")


def _single_word_keywords() -> set[str]:
    """The keyword vocabulary restricted to single-word keywords (lowercased)."""
    return {kw for kw in all_keywords() if " " not in kw}


def _is_sentence_start(text: str, idx: int) -> bool:
    """True if the token at ``idx`` is the first word of its line/clause.

    Walks backward over whitespace; a start-of-string, a newline, or a
    sentence-terminating character before the token means the keyword
    legitimately begins a clause (capitalization is correct, leave it).
    """
    j = idx - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] == "\n":
        return True
    return text[j] in _SENTENCE_START_CHARS


def _adjacent_capitalized(text: str, start: int, end: int) -> bool:
    """True if a capitalized word sits immediately before or after [start, end).

    A capitalized keyword next to another capitalized word is most likely part
    of a proper name ("Flying Men", "Storm Reach"), so we leave it alone.
    """
    # Previous word.
    j = start - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j >= 0 and text[j].isalpha():
        # Walk to the start of that previous word.
        k = j
        while k >= 0 and (text[k].isalpha() or text[k] in "'-"):
            k -= 1
        if text[k + 1].isupper():
            return True
    # Next word.
    j = end
    while j < len(text) and text[j] in " \t":
        j += 1
    return j < len(text) and text[j].isupper()


def _scan_span(span: str) -> list[str]:
    """Return the over-capitalized single-word keywords found in a running-text span."""
    kws = _single_word_keywords()
    if not kws:
        return []
    found: list[str] = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'-]*", span):
        word = m.group()
        if not word[0].isupper():
            continue
        if word.lower() not in kws:
            continue
        if _is_sentence_start(span, m.start()):
            continue
        if _adjacent_capitalized(span, m.start(), m.end()):
            continue
        found.append(word)
    return found


def _lowercase_span(span: str) -> str:
    """Lowercase the leading letter of every over-capitalized keyword in a span."""
    kws = _single_word_keywords()
    if not kws:
        return span

    out: list[str] = []
    last = 0
    for m in re.finditer(r"[A-Za-z][A-Za-z'-]*", span):
        word = m.group()
        if (
            word[0].isupper()
            and word.lower() in kws
            and not _is_sentence_start(span, m.start())
            and not _adjacent_capitalized(span, m.start(), m.end())
        ):
            out.append(span[last : m.start()])
            out.append(word[0].lower() + word[1:])
            last = m.end()
    out.append(span[last:])
    return "".join(out)


def _map_span_aware(line: str, fn) -> str:
    """Apply ``fn`` to each running-text span of ``line``, leaving paren/quote verbatim."""
    out: list[str] = []
    last = 0
    for m in _SKIP_SPAN_RE.finditer(line):
        out.append(fn(line[last : m.start()]))
        out.append(m.group())
        last = m.end()
    out.append(fn(line[last:]))
    return "".join(out)


def _scan_line(line: str) -> list[str]:
    """Over-capitalized keywords in a line's running-text spans (paren/quote excluded)."""
    found: list[str] = []
    last = 0
    for m in _SKIP_SPAN_RE.finditer(line):
        found += _scan_span(line[last : m.start()])
        last = m.end()
    found += _scan_span(line[last:])
    return found


def validate_keyword_casing(card: Card) -> list[ValidationError]:
    """Flag keywords capitalized mid-sentence in running oracle text — AUTO.

    A pure keyword-list line ("Flying, Trample") is the
    ``rules_text.keyword_capitalization`` fixer's domain — skip it so the two
    checks don't double-flag the same token.
    """
    oracle = card.oracle_text or ""
    if not oracle:
        return []

    found: list[str] = []
    for line in oracle.split("\n"):
        if _is_keyword_only_line(line.strip()):
            continue
        found += _scan_line(line)

    if not found:
        return []

    sample = ", ".join(dict.fromkeys(found))  # de-dup, preserve order
    return [
        ValidationError(
            validator="rules_text",
            severity=ValidationSeverity.AUTO,
            field="oracle_text",
            message=f"Keyword(s) capitalized mid-sentence: {sample}",
            suggestion="Keywords are lowercase in running text (e.g. 'gains flying').",
            error_code="rules_text.keyword_casing",
        )
    ]


def fix_keyword_casing(card: Card, error: ValidationError) -> Card:
    """Lowercase keywords used mid-sentence in running oracle text.

    Skips parenthesized reminder spans and double-quoted granted-ability spans;
    leaves a keyword that begins a line/clause or sits in a capitalized
    multi-word run (likely a proper name) untouched.
    """
    if not card.oracle_text:
        return card
    new_lines = []
    for line in card.oracle_text.split("\n"):
        if _is_keyword_only_line(line.strip()):
            new_lines.append(line)  # keyword_capitalization's domain
        else:
            new_lines.append(_map_span_aware(line, _lowercase_span))
    new_oracle = "\n".join(new_lines)
    if new_oracle == card.oracle_text:
        return card
    return card.model_copy(update={"oracle_text": new_oracle})
