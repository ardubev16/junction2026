"""Numbers that editions state differently: a language-independent hint of a factual discrepancy.

Digits read the same in fi, sv and en; only the thousands separator differs (space, no-break space,
comma or dot). Passages about the same subject that each have a number the other lacks, close in
value to each other, likely disagree about one fact: "25,904 dead" vs "23 576 stupade". With three
or more editions, the one that disagrees with a majority is the outlier.
"""

import re
from collections import Counter

# A number with thousands groups ("126 875", "126,875", "126.875") or plain digits.
NUMBER = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ \u00a0\u202f,.]\d{3})+|\d+)(?!\d)")
MIN_NUMBER = 100  # smaller numbers are days, counts and units: too common to mean anything
YEAR_TOLERANCE = 2  # years differing by more than this are different events, not a disagreement
YEAR_MAX_DISTANCE = 0.3  # years only count in passages this close: dates differ wildly otherwise
QUANTITY_RATIO = 0.6  # quantities within this ratio of each other may be the same figure


def numbers(text: str) -> dict[int, list[str]]:
    """Value -> how it is written in the text, for the numbers worth comparing."""
    found: dict[int, list[str]] = {}
    for m in NUMBER.finditer(text):
        value = int(re.sub(r"\D", "", m.group(1)))
        if value >= MIN_NUMBER:
            found.setdefault(value, []).append(m.group(1))
    return found


def is_year(n: int) -> bool:
    return 1000 <= n <= 2100


def value(written: str) -> int:
    """'126 875', '126,875', '126.875' -> 126875."""
    return int(re.sub(r"\D", "", written))


def conflicts(a: str, b: str, distance: float) -> list[tuple[str, str]]:
    """Pairs of numbers (as written in a, as written in b) that likely state one fact differently.

    Each number is used at most once, matched to its closest counterpart, so one big figure does not
    conflict with every other figure in the other passage.
    """
    na, nb = numbers(a), numbers(b)
    candidates = []
    for x in na.keys() - nb.keys():
        for y in nb.keys() - na.keys():
            if is_year(x) and is_year(y):
                if distance < YEAR_MAX_DISTANCE and abs(x - y) <= YEAR_TOLERANCE:
                    candidates.append((abs(x - y) / x, x, y))
            elif not is_year(x) and not is_year(y) and QUANTITY_RATIO <= x / y <= 1 / QUANTITY_RATIO:
                candidates.append((abs(x - y) / max(x, y), x, y))
    used, out = set(), []
    for _, x, y in sorted(candidates):
        if x not in used and y not in used:
            used |= {x, y}
            out.append((na[x][0], nb[y][0]))
    return out


def anchored_conflicts(a: str, b: str) -> list[tuple[str, str]]:
    """Conflicting quantities in two passages that share at least one identical number: the shared
    number ("43,557 wounded" in both) shows they report the same statistics. Years can anchor but never
    conflict here: two passages share many years, and differing ones are usually different events."""
    if not numbers(a).keys() & numbers(b).keys():
        return []
    return conflicts(a, b, distance=1.0)  # past YEAR_MAX_DISTANCE: years are not compared


def figure_slots(texts: dict[str, str], pair_conflicts) -> list[dict]:
    """The figures a group of texts (one per language, about one subject) states differently.

    `pair_conflicts(lang_a, lang_b)` gives the conflicting numbers of two of the texts, like `conflicts`. Conflicting
    numbers that touch form one slot, i.e. one fact; a language stating one of the slot's values
    exactly backs it. A value held by more than half of the slot makes the others outliers; two
    languages, or no majority, give no outlier. Returns [{"values": {lang: as written}, "outliers": [lang]}].
    """
    langs = list(texts)
    nums = {lang: numbers(text) for lang, text in texts.items()}
    parent: dict[tuple, tuple] = {}

    def find(node):
        while parent.setdefault(node, node) != node:
            node = parent[node]
        return node

    for i, a in enumerate(langs):
        for b in langs[i + 1 :]:
            for x, y in pair_conflicts(a, b):
                parent[find((a, value(x)))] = find((b, value(y)))
    slots: dict[tuple, set] = {}
    for node in parent:
        slots.setdefault(find(node), set()).add(node)

    out = []
    for nodes in slots.values():
        stated: dict[str, set[int]] = {}
        for lang, v in nodes:
            stated.setdefault(lang, set()).add(v)
        if any(len(vs) > 1 for vs in stated.values()):
            continue  # one language with two figures for the same fact: ambiguous
        stated = {lang: vs.pop() for lang, vs in stated.items()}
        for lang in langs:  # a language that states one of the values exactly agrees with it
            if lang not in stated and len(same := {v for v in stated.values() if v in nums[lang]}) == 1:
                stated[lang] = same.pop()
        top, n = Counter(stated.values()).most_common(1)[0]
        majority = n >= 2 and n > len(stated) / 2
        out.append({
            "values": {lang: nums[lang][stated[lang]][0] for lang in langs if lang in stated},
            "outliers": [lang for lang in langs if lang in stated and stated[lang] != top] if majority else [],
        })
    return out
