"""Second, looser pass of IDENTIFY_BY_RUNTIME for a disc the first pass could not confirm.

The first pass only considers films named exactly like the label, so labels such as
SUBSPECIES2_V2, PINEAPPLE_EXP, PRIMFEAR, CHANGINGLANES or BULLETPROOF_US find no film at all.
This pass reads the label more loosely (pressing words, glued sequel numbers, run-together
words, abbreviations), searches the provider with each reading, and still decides only by
runtime: one related title must fit the disc, with every rival clearly further off. A looser
kind of match is only weighed when no stronger kind (exact or numbered, then leading article,
then prefix or abbreviation) was found.
"""
import re
import unicodedata

from arm.ripper import identify_runtime as first

# Trailing label words that describe the pressing, not the film.
NOISE = re.compile(
    r"\s+(?:SD|HD|V\d|DC|AC|43|169|16X9|4X3|US|USA|UK|CA|NTSC|PAL|R[1-6]|REGION\s*\d|PAN(?:\s?SCAN)?|SCAN"
    r"|FF|LB|WS|FS|N\s?A|DOMESTIC|S?CE|SE|UNRATED|UNCUT|EXTENDED|THEATRICAL|DIRECTORS?\s?CUT|EDITION"
    r"|SPECIAL|COLLECTORS?|DVD|BLU[ -]?RAY|WIDESCREEN|FULLSCREEN|DIS[CK]\s*\d+|D\d)$",
    re.IGNORECASE,
)
# Labels that carry no title, such as the studio product code INU0NNW1.
PRODUCT_CODE = re.compile(r"[A-Z]{2,4}\d[A-Z0-9]{2,6}", re.IGNORECASE)
ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi", "7": "vii", "8": "viii", "9": "ix"}
FUNCTION_WORDS = ("the", "of", "and", "in", "a", "to", "on", "for", "at", "an")
# Runtime agreement for an exact and for a looser match, and the margin every rival must lose by.
FIT_SECONDS = 150
LOOSE_FIT_SECONDS = 90
RIVAL_MARGIN_SECONDS = 180
FEATURE_SECONDS = 45 * 60
# A catalog entry without a runtime and with fewer votes than this is not a rival release.
OBSCURE_VOTES = 20
MAX_PREFIX_QUERIES = 8
TIERS = (("exact", "numbered"), ("article",), ("prefix", "abbreviation"))


def words(label):
    """'SUBSPECIES2_V2' -> 'SUBSPECIES 2': trailing pressing words removed, glued numbers split"""
    text = re.sub(r"[_.\s]+", " ", str(label or "")).strip()
    if PRODUCT_CODE.fullmatch(text):
        return ""
    text = re.sub(r"\b([A-Za-z]{3,})(\d{1,2})\b", r"\1 \2", text)
    previous = None
    while previous != text:
        previous, text = text, NOISE.sub("", text).strip()
    return first.search_title(text)[0]


def segment(token):
    """Split a run-together label at English function words: INTHENAMEOFTHEKING -> in the name of the king"""
    token = token.lower()
    parts, rest = [], token
    while rest:
        word = next((w for w in FUNCTION_WORDS if rest.startswith(w) and len(rest) > len(w) + 2), None)
        if word and (not parts or parts[-1] in FUNCTION_WORDS or len(parts[-1]) >= 3):
            parts.append(word)
            rest = rest[len(word):]
            continue
        cut = min((rest.find(w, 3) for w in FUNCTION_WORDS if rest.find(w, 3) > 0), default=-1)
        parts.append(rest if cut < 0 else rest[:cut])
        rest = "" if cut < 0 else rest[cut:]
    return " ".join(parts)


def queries(title):
    """Provider searches for a cleaned label, most specific first"""
    found = [title]
    tokens = title.split()
    if len(tokens) == 1 and len(title) >= 9 and segment(title) != title.lower():
        found.append(segment(title))
    if len(tokens) > 1 and tokens[0].lower() == "the":
        found.append(" ".join(tokens[1:]))
    elif len(tokens) == 1 and title.lower().startswith("the") and len(title) > 6:
        found.append(title[3:])  # THEILLUSIONIST
    if len(tokens) > 1 and (tokens[-1].isdigit() or tokens[-1].lower() in ROMAN.values()):
        found.append(" ".join(tokens[:-1]))  # SUBSPECIES 2 also searches its series
    return list(dict.fromkeys(q for q in found if q.strip()))


def prefix_queries(title):
    """Shorter prefixes of one run-together word the provider cannot split (CHANGINGLANES, PRIMFEAR)"""
    if " " in title.strip() or len(title) < 7:
        return []
    return [title[:n] for n in range(len(title) - 1, 3, -1)][:MAX_PREFIX_QUERIES]


def title_words(name):
    name = unicodedata.normalize("NFKD", str(name or "")).casefold()
    return [w for w in re.split(r"[^0-9a-z]+", name) if w]


def abbreviates(token, names):
    """PRIMFEAR ~ Primal Fear: the token starts with a prefix of every title word in turn"""
    def fits(rest, remaining, at_start=True):
        if not rest:
            return not at_start and all(w in FUNCTION_WORDS for w in remaining)
        if not remaining:
            return False
        word = remaining[0]
        if not at_start and word in FUNCTION_WORDS and fits(rest, remaining[1:], False):
            return True
        return any(rest.startswith(word[:n]) and fits(rest[n:], remaining[1:], False)
                   for n in range(len(word), min(len(word), 3) - 1, -1))

    token = token.lower()
    for name in names:
        tw = title_words(name)
        if len(tw) > 1 and tw[0] in first.ARTICLES and fits(token, tw[1:]):
            return True
        if tw and fits(token, tw):
            return True
    return False


def numbered(title, names):
    """SUBSPECIES 2 ~ Bloodstone: Subspecies II"""
    tokens = [t.lower() for t in title.split()]
    if len(tokens) < 2 or tokens[-1] not in set(ROMAN) | set(ROMAN.values()):
        return False
    stem, number = first.normalize(" ".join(tokens[:-1])), tokens[-1]
    numerals = {number, ROMAN.get(number, number)} | {k for k, v in ROMAN.items() if v == number}
    return any(stem in first.normalize(name) and numerals & set(title_words(name)[1:]) for name in names)


def prefixes(title, names):
    """PINEAPPLE EXP ~ Pineapple Express: each label word starts the title's word in turn"""
    lw = title_words(title)
    if len(lw) < 2:
        return False  # one word starts too many titles: PRECIOUS is not Precious Bane
    for name in names:
        tw = title_words(name)
        start = 1 if tw[:1] in (["the"], ["a"], ["an"]) and lw[:1] != tw[:1] else 0
        if len(lw) < len(tw) - start and tw[start:start + len(lw)] == lw:
            return True
        if all(len(w) >= 2 for w in lw) and len(lw) <= len(tw) - start and all(
                tw[start + i].startswith(w) for i, w in enumerate(lw)):
            return True
    return False


def relation(title, names):
    """How a cleaned label names a film: exact, article, numbered, prefix, abbreviation or None"""
    names = [n for n in names if n]
    if first.normalize(title) in {first.normalize(n) for n in names}:
        return "exact"
    if first.without_article(title) in {first.without_article(n) for n in names}:
        return "article"
    if numbered(title, names):
        return "numbered"
    if prefixes(title, names):
        return "prefix"
    if " " not in title and len(first.normalize(title)) >= 6 and abbreviates(first.normalize(title), names):
        return "abbreviation"
    return None


def gap(movie, seconds):
    return abs(movie["runtime"] * 60 - seconds) if movie["runtime"] else None


def obscure(movie):
    """A runtime-less entry with almost no votes cannot be the disc's commercial release"""
    return first.placeholder(movie) or (movie["runtime"] is None and movie["votes"] is not None
                                        and movie["votes"] < OBSCURE_VOTES)


def weigh_hint(related, timed, seconds, hint):
    """(film, reason) from the crc64 answer among related titles, ((None, None) when it says nothing)"""
    hinted = next((m for m in timed if hint and m["imdb_id"] == hint["imdb_id"]), None)
    if hinted is None:
        return None, None
    if hinted is timed[0] and gap(hinted, seconds) <= first.CLOSEST_SECONDS and first.identified(hinted):
        return hinted, "crc64-hint-and-closest-runtime"
    if gap(hinted, seconds) <= FIT_SECONDS:
        return None, "the ARM online database names a different related title"
    return None, None


def choose(related, seconds, hint=None):
    """(film, method) when the runtime singles out one related title, else (None, reason)"""
    if seconds < FEATURE_SECONDS:
        return None, "the disc is shorter than a feature; a loose label match is not enough"
    timed = sorted((m for m, _ in related if m["runtime"]), key=lambda m: gap(m, seconds))
    chosen, reason = weigh_hint(related, timed, seconds, hint)
    if chosen or reason:
        return chosen, reason
    for tier in TIERS:
        members = [m for m, kind in related if kind in tier]
        if not members:
            continue
        limit = FIT_SECONDS if tier[0] == "exact" else LOOSE_FIT_SECONDS
        fitting = [m for m in timed if any(m is member for member in members)]
        if not fitting or gap(fitting[0], seconds) > limit:
            return None, f"no {tier[0]} match fits the disc runtime"
        best = fitting[0]
        kind = next(k for m, k in related if m is best)
        if not first.identified(best) or obscure(best):
            return None, "the best runtime match lacks a release year, IMDb id or votes"
        if any(gap(m, seconds) - gap(best, seconds) < RIVAL_MARGIN_SECONDS for m in fitting[1:]):
            return None, "several related titles are close to the disc runtime"
        if any(m["runtime"] is None and not obscure(m) for m in members):
            return None, "a related title without a runtime could also be this disc"
        return best, f"loose-{kind}-label-and-runtime"
    return None, "no related film found"


def gather(catalog, title, seed=()):
    """[(film, relation)] for the first pass's films and every reading of the label"""
    seen, related = set(), []

    def consider(movies):
        for movie in movies:
            key = movie["imdb_id"] or (movie["title"], movie["year"])
            kind = relation(title, movie["names"])
            if key not in seen and kind:
                seen.add(key)
                related.append((movie, kind))

    def search(query):
        hits = [h for h in catalog.search(query) if relation(title, h["names"])]
        consider(catalog.details(h["ref"]) for h in hits[:first.MAX_DETAILS])

    consider(seed)
    for query in queries(title):
        search(query)
    for query in prefix_queries(title) if not related else ():
        search(query)
        if related:
            break
    return related


def second_pass(catalog, label, seconds, hint=None, seed=()):
    """(film, method) for a disc the first pass could not confirm, else (None, reason)"""
    title = words(label)
    if first.normalize(title) in first.PLACEHOLDERS:
        return None, "the label has no usable title"
    related = gather(catalog, title, seed)
    if hint and first.label_consistent(title, hint) and all(m["imdb_id"] != hint["imdb_id"] for m, _ in related):
        related.append((hint, "hint"))  # BULLETPROOF_US: the database names Bulletproof Monk
    return choose(related, seconds, hint)
