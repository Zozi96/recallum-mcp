"""Advisory, dependency-free heuristic for likely-non-English content.

The corpus policy is English-only: the full-text index uses the English
search configuration, so a memory stored in another language loses the
lexical retrieval legs (and dedup, being an exact hash, treats a translated
restatement as an unrelated new memory). This module never blocks a write --
it only decides whether the caller should be nudged to store the content in
English.

Deliberately conservative: identifiers, commands, paths and short snippets
must never be flagged. False negatives (missing genuinely non-English prose)
are cheap; false positives (flagging code) are not, because they would train
callers to ignore the advisory.
"""

from __future__ import annotations

import re

# High-frequency function words that are near-universal in ordinary English
# sentences (articles, pronouns, prepositions, auxiliaries, conjunctions).
_ENGLISH_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "so", "of", "to", "in",
        "on", "at", "for", "with", "is", "are", "was", "were", "be", "been",
        "this", "that", "these", "those", "it", "its", "we", "you", "they",
        "i", "he", "she", "not", "no", "as", "by", "from", "when", "then",
        "than", "into", "about", "will", "would", "should", "can", "could",
        "do", "does", "did", "have", "has", "had",
    }
)

# High-frequency function words from other languages that rarely appear in
# English prose. Spanish is weighted heaviest since it is the bulk of the
# non-English corpus today, but a few common words from other Romance/other
# languages are included so the heuristic is not Spanish-only.
_NON_ENGLISH_STOPWORDS = frozenset(
    {
        # Spanish
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
        "al", "en", "que", "es", "son", "para", "por", "con", "sin", "pero",
        "como", "porque", "cuando", "donde", "muy", "más", "también", "esta",
        "este", "estos", "estas", "eso", "esa", "ese", "fue", "ser", "está",
        "están", "se", "su", "sus", "lo", "le", "les", "mi", "tu", "si",
        "sí", "todo", "todos", "toda", "todas", "entre", "sobre", "hasta",
        "desde", "según", "aunque", "mientras", "nunca", "siempre", "ahora",
        "después", "antes", "nosotros", "ellos", "usamos", "prefiero",
        "debe", "hay",
        # Portuguese
        "não", "então", "são", "isso", "muito",
        # French
        "des", "une", "est", "sont", "avec", "dans",
        "mais", "ne", "pas", "qui",
        # German
        "der", "die", "das", "und", "nicht", "ist", "sind", "mit", "für",
        "auch",
    }
)

# Letters that virtually never appear in English words but are common in
# Spanish/Portuguese/French prose. A single occurrence in otherwise ordinary
# text is a strong signal.
_DIACRITIC_CHARS = re.compile(r"[áéíóúñüàèìòùâêîôûçãõ]", re.IGNORECASE)

# A "word" inside a token that survived the code-ish filter: letters (incl.
# accented) and internal apostrophes/hyphens, so contractions count as one.
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:['’-][A-Za-zÀ-ÿ]+)*")

# Raw (punctuation-attached) tokens that look identifier-, path-, command- or
# code-like rather than prose. These are dropped whole -- not just stripped of
# punctuation -- so a path or flag never contributes a "word" at all: keeping
# it would let code-heavy content masquerade as short prose, or (in
# principle) let a path component collide with a stopword.
_CODE_ISH_RE = re.compile(
    r"""^(
        [A-Za-z0-9_]+([./\\:][A-Za-z0-9_.-]+)+   # paths, module.paths, a:b
        | [a-z0-9]+(_[a-z0-9]+)+                  # snake_case
        | [a-zA-Z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*   # camelCase / PascalCase
        | --?[A-Za-z][\w-]*                       # --flag / -f
        | [A-Za-z0-9_]+\(\)                       # func()
        | [\w.+-]+@[\w-]+                         # user@host-ish
    )$""",
    re.VERBOSE,
)

_MIN_WORDS = 4


def _is_code_ish(raw_token: str) -> bool:
    return bool(_CODE_ISH_RE.match(raw_token.strip(".,;:!?()[]{}\"'")))


def looks_non_english(content: str) -> bool:
    """Best-effort, conservative guess that ``content`` is not English prose.

    Returns False for anything short, identifier-heavy, or merely ambiguous.
    Only clear non-English signals -- a majority of recognized function words
    coming from another language, or diacritics uncommon in English -- trip
    it. Meant purely as an advisory input; never raises.
    """
    if not content:
        return False

    prose_tokens: list[str] = []
    for raw in content.split():
        if _is_code_ish(raw):
            continue
        prose_tokens.extend(_WORD_RE.findall(raw))
    if len(prose_tokens) < _MIN_WORDS:
        return False

    lowered = [t.lower() for t in prose_tokens]
    non_english_hits = sum(1 for t in lowered if t in _NON_ENGLISH_STOPWORDS)
    english_hits = sum(1 for t in lowered if t in _ENGLISH_STOPWORDS)

    if non_english_hits >= 2 and non_english_hits > english_hits:
        return True

    diacritic_hits = len(_DIACRITIC_CHARS.findall(content))
    if diacritic_hits >= 2 and non_english_hits >= 1:
        return True

    return False


LANGUAGE_WARNING = (
    "This content looks like it may not be in English. Recallum's full-text "
    "index and dedup are English-only, so please store memories in English "
    "(keep identifiers, commands, paths and error strings verbatim)."
)
