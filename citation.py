"""Turn a (author, book-title-string, chapter) triple from the CoNLL-U
metadata into a short scholarly-style citation, e.g. "Caes. B Gall. 1.14",
"Liv. 21.14", "Sall. Cat. 14", "HA Hadr. 14".

The raw "book" field is the source text's title line verbatim (e.g. "C.
IVLI CAESARIS COMMENTARIORVM DE BELLO GALLICO LIBER PRIMVS"), copied
through unprocessed by the parser -- so it mixes u/v spelling and, for
Historia Augusta, has no consistent word order at all. Work/book parsing
is therefore per-author, keyed off the substrings each author's title
lines are actually built from (checked against every unique title in the
corpus; see the migration notes in README.md).
"""
import re

from textprep import roman_to_int

_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")
_COMPOSITE_RE = re.compile(r"^\d+\.\d+$")


def _norm_chapter(chapter):
    """The source texts label chapters inconsistently: plain Arabic in most
    books, literal Roman numerals in others (Curtius and Historia Augusta
    are Roman throughout; Suetonius/Ammianus mix both), and -- uniquely --
    a book.chapter composite ('5.6') for Tacitus's fragmentary Annals 5-6,
    which cite by an old combined numbering that doesn't match the book's
    own 'LIBER SEXTVS' heading. Returns (chapter_str, is_composite); a
    composite already IS the full book.chapter locator, so the caller must
    not additionally prepend a book number for it."""
    if not chapter:
        return "", False
    if _COMPOSITE_RE.match(chapter):
        return chapter, True
    if _ROMAN_RE.match(chapter):
        return str(roman_to_int(chapter)), False
    return chapter, False

AUTHOR_ABBR = {
    "caesar": "Caes.", "sallust": "Sall.", "livy": "Liv.", "curtius": "Curt.",
    "tacitus": "Tac.", "suetonius": "Suet.", "ammianus": "Amm.",
    "historiaaugusta": "HA",
}

# True for authors whose corpus spans more than one work, so the citation
# needs a work abbreviation as well as (or instead of) a book number.
MULTI_WORK = {"caesar", "sallust", "tacitus", "suetonius", "historiaaugusta"}

ORDINAL_WORDS = {
    "PRIMUS": 1, "SECUNDUS": 2, "TERTIUS": 3, "QUARTUS": 4, "QUINTUS": 5,
    "SEXTUS": 6, "SEPTIMUS": 7, "OCTAUUS": 8, "NONUS": 9, "DECIMUS": 10,
    "UNDECIMUS": 11, "DUODECIMUS": 12,
}

LIBER_RE = re.compile(r"\bLIBER\b\s*([A-Z]+(?:\s+[A-Z]+)?)?\s*$")


def _fold(s):
    return s.upper().replace("V", "U")


def _book_number(tail):
    """tail is whatever followed 'LIBER' (roman numeral, an ordinal word,
    an ordinal-word pair like 'QVARTVS DECIMVS', or nothing). Returns an
    int, or None if there's no book number to show."""
    if not tail:
        return None
    tail = tail.strip()
    if ROMAN_TOKEN_RE_MATCH(tail):
        return roman_to_int(tail)
    words = _fold(tail).split()
    if len(words) == 1:
        return ORDINAL_WORDS.get(words[0])
    if len(words) == 2 and words[1] == "DECIMUS":
        base = ORDINAL_WORDS.get(words[0])
        return base + 10 if base else None
    return None


def ROMAN_TOKEN_RE_MATCH(s):
    return bool(re.fullmatch(r"[IVXLCDMivxlcdm]+", s))


def _caesar(book):
    fb = _fold(book)
    if "BELLO GALLICO" in fb:
        work = "B Gall."
    elif "BELLO CIVILI" in fb:
        work = "B Civ."
    elif "BELLO AFRICO" in fb:
        work = "B Afr."
    elif "BELLO ALEXANDRINO" in fb:
        work = "B Alex."
    elif "BELLO HISPANIENSI" in fb:
        work = "B Hisp."
    else:
        work = None
    m = LIBER_RE.search(book)
    num = _book_number(m.group(1)) if m else None
    return work, num


def _sallust(book):
    fb = _fold(book)
    if "CATILINAE" in fb:
        return "Cat.", None
    if "IUGURTHINUM" in fb:
        return "Iug.", None
    return None, None


def _tacitus(book):
    fb = _fold(book)
    if "ANNALIUM" in fb:
        work = "Ann."
    elif "HISTORIARUM" in fb:
        work = "Hist."
    elif "AGRICOLA" in fb:
        return "Agr.", None
    elif "GERMANORUM" in fb:
        return "Ger.", None
    elif "ORATORIBUS" in fb:
        return "Dial.", None
    else:
        work = None
    m = LIBER_RE.search(book)
    num = _book_number(m.group(1)) if m else None
    return work, num


SUETONIUS_LIVES = [
    ("AUGUSTI", "Aug."), ("CLAUDI", "Claud."), ("IULI", "Iul."), ("TITI", "Tit."),
    ("UESPASIANI", "Vesp."), ("DOMITIANI", "Dom."), ("GAI", "Cal."), ("GALBAE", "Galb."),
    ("NERONIS", "Ner."), ("OTHONIS", "Otho"), ("TIBERI", "Tib."), ("UITELLII", "Vit."),
]


def _suetonius(book):
    fb = _fold(book)
    for needle, abbr in SUETONIUS_LIVES:
        if needle in fb:
            return abbr, None
    return None, None


def _livy(book):
    if "PRAEFATIO" in _fold(book):
        return "praef.", None
    m = LIBER_RE.search(book)
    num = _book_number(m.group(1)) if m else None
    return None, num


def _ammianus(book):
    m = LIBER_RE.search(book)
    num = _book_number(m.group(1)) if m else None
    return None, num


def _curtius(book):
    m = LIBER_RE.search(book)
    num = _book_number(m.group(1)) if m else None
    return None, num


# Historia Augusta: each "book" line is a separate biography, with no fixed
# word order (author name and persona name interleave differently per
# vita). Strip the recurring author/editorial boilerplate and abbreviate
# whatever persona-name words are left, rather than hand-mapping ~65 titles.
HA_BOILERPLATE = {
    "DE", "VITA", "DIVUS", "AELI", "AELII", "AELIUS", "SPARTIANI", "LAMPRIDI",
    "LAMPRIDII", "CAPITOLINI", "IULI", "IULII", "POLLIONIS", "TREBELLI",
    "TEBELLI", "VOPISCI", "FLAVI", "SYRACUSII", "GALLICANI", "VULCACII", "V.C.",
}
HA_SPECIAL = {
    "DUO": "Duo", "TRES": "Tres", "IUNIOR": "Iun.", "SENIOR": "Sen.",
    "SUPERIOR": "Sup.", "TERTIUS": "III", "SECUNDUS": "II", "ET": "et",
}


def _historia_augusta(book):
    kept = [w for w in book.split() if w.rstrip(".") not in HA_BOILERPLATE]
    if not kept:
        kept = book.split()
    parts = []
    for w in kept[:3]:
        if w in HA_SPECIAL:
            parts.append(HA_SPECIAL[w])
        else:
            parts.append(w.rstrip(".")[:4].capitalize() + ".")
    return " ".join(parts), None


_PARSERS = {
    "caesar": _caesar, "sallust": _sallust, "tacitus": _tacitus,
    "suetonius": _suetonius, "livy": _livy, "ammianus": _ammianus,
    "curtius": _curtius, "historiaaugusta": _historia_augusta,
}


def short_citation(author, book, chapter):
    """e.g. 'Caes. B Gall. 1.14', 'Liv. 21.14', 'Sall. Cat. 14', 'HA Hadr. 14'."""
    abbr = AUTHOR_ABBR.get(author, author)
    work, num = _PARSERS.get(author, lambda b: (None, None))(book or "")
    chapter, is_composite = _norm_chapter(chapter)
    loc = chapter if is_composite else ".".join(str(x) for x in (num, chapter) if x)
    bits = [abbr]
    if work:
        bits.append(work)
    if loc:
        bits.append(loc)
    return " ".join(bits)
