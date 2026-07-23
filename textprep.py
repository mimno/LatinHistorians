"""Shared text preparation for the Latin historian corpus: line
classification, editorial-marker stripping, paragraph iteration with
book/chapter metadata, and CoNLL-U record writing. No parser imports --
usable from both the CLTK (parse_texts.py) and the LatinCy
(parse_texts_latincy.py) parsing scripts.
"""
import re
from pathlib import Path

CORPUS_DIR = Path("/Users/mimno/Documents/Data/LatinHistorians/txt")
TEXTS = [
    "caesar",
    "suetonius",
    "tacitus",
    "ammianus",
    "historiaaugusta",
    "curtius",
    "livy",
    "sallust",
]

NUMBER_LINE_RE = re.compile(r"^\d+(\s+\d+)*$")
# Chapter markers are usually "[N]" but Tacitus's fragmentary Annals 5-6 cite
# chapters as "[book.chapter]" (e.g. "[5.6]", "[6.1]"); accept both.
BRACKET_CHAPTER_RE = re.compile(r"^\[(\d+(?:\.\d+)?)\]\s*")
ROMAN_CHAPTER_RE = re.compile(r"^((?:[IVXLCDM]+|[ivxlcdm]+))\.\s+")
# Historia Augusta's Tacitus/Florianus lives carry a secondary cross-reference
# number in parens after the usual roman-numeral chapter marker, e.g.
# "XIV. (Flor. 1) 1 Hic frater..." or "XV. (2) 1 Horum statuae...". It's a
# citation, not content -- drop it like the other section-number markers.
PAREN_CITATION_RE = re.compile(r"^\(\s*(?:[A-Za-z]+\.\s*)?\d+\s*\)\s*")
# A line built only from roman numerals / digits / dots / spaces is never a
# genuine title (titles always contain ordinary Latin words) -- it's either a
# lacuna marker ("......."), a chapter-index list ("I  II  III  IV  V  VI",
# ammianus.txt's roman-numeral equivalent of the arabic "1 2 3 4 5" index
# lines), or a standalone chapter marker for books XXIII-XXXI ("VI", or the
# duplicated arabic+roman "4 IV"). It's easy to conflate all of these with a
# book title (also all-caps), so they need their own line classification,
# checked before the general title check -- see classify_numeral_line().
NUMERAL_OR_DOT_LINE_RE = re.compile(r"^[IVXLCDM0-9. ]+$")
ROMAN_TOKEN_RE = re.compile(r"^[IVXLCDM]+$")
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(s):
        val = ROMAN_VALUES[ch]
        total += -val if val < prev else val
        prev = max(prev, val)
    return total


def token_value(tok: str):
    if tok.isdigit():
        return int(tok)
    if ROMAN_TOKEN_RE.match(tok):
        return roman_to_int(tok)
    return None


def classify_numeral_line(stripped: str):
    """Classify a line made only of roman numerals / digits / dots / spaces.

    Returns ('blank', ...) for pure lacuna dots, ('number_line', ...) for a
    sequential index list to discard, or ('chapter_line', label) for a
    standalone chapter marker (possibly written twice, as in "4 IV").
    """
    core = stripped.replace(".", "").strip()
    if not core:
        return "blank", stripped
    tokens = core.split()
    values = [token_value(t) for t in tokens]
    if any(v is None for v in values):
        return "content", stripped
    if len(set(values)) == 1:
        return "chapter_line", tokens[0]
    return "number_line", stripped


# Editorial subsection numbers embedded in the prose (e.g. "...fecerunt. 2 Ipse...",
# "...exirent: 2 perfacile...", "...important, 4 proximique...", or glued directly
# onto adjacent punctuation with no space as in "...retentabant.22 Nunc...",
# "...petiverunt 3, parsque...", or "...59.... sub imis..." next to a lacuna's
# ellipsis). Classical Latin prose never uses bare Arabic digits as number-words,
# so any isolated 1-3 digit token is always one of these markers -- rather than
# enumerate every punctuation mark that might come before/after it, just require
# that it isn't glued to a letter/digit on either side (which would mean it's
# part of a larger token instead of standing alone).
INLINE_SECTION_NUM_RE = re.compile(r"(?<!\w)\d{1,3}\.?(?![A-Za-z0-9])")
TITLE_LINE_RE = re.compile(r"^[A-Z0-9 .,'\-]+$")


def classify_line(line: str):
    """Return ('blank'|'number_line'|'title'|'chapter_line'|'content', stripped_line)."""
    stripped = line.strip()
    if not stripped:
        return "blank", stripped
    # Inter-book site-navigation breadcrumb left over from extraction, e.g.
    # "Caesar The Latin Library The Classics Page" or (tab-separated)
    # "Suetonius\tThe Latin Library\tThe Classics Page" -- not Latin content.
    if "The Latin Library" in stripped and "The Classics Page" in stripped:
        return "blank", stripped
    if NUMBER_LINE_RE.match(stripped):
        return "number_line", stripped
    # Must be checked before the title check: lines made only of roman
    # numerals/digits/dots are also all-caps and would otherwise be misread
    # as a new book title (see classify_numeral_line for why ammianus.txt
    # needs this).
    if NUMERAL_OR_DOT_LINE_RE.match(stripped):
        kind, value = classify_numeral_line(stripped)
        if kind != "content":
            return kind, value
    if TITLE_LINE_RE.match(stripped) and stripped.upper() == stripped:
        return "title", stripped
    return "content", stripped


LEADING_SECTION_NUM_RE = re.compile(r"^\d+\.?\s+")


def strip_editorial_markers(text: str):
    """Remove chapter markers and inline section numbers; return
    (clean_text, chapter_label_or_None)."""
    chapter_label = None
    # Prefix markers can appear in either order ("14 [14] Cum..." or
    # "[14] Cum..." or "I. 1 Origo..." or "XIV. (Flor. 1) 1 Hic..."); strip
    # repeatedly until none match.
    while True:
        m = BRACKET_CHAPTER_RE.match(text)
        if m:
            chapter_label = m.group(1)
            text = text[m.end():]
            continue
        m = ROMAN_CHAPTER_RE.match(text)
        if m:
            chapter_label = m.group(1)
            text = text[m.end():]
            continue
        m = PAREN_CITATION_RE.match(text)
        if m:
            text = text[m.end():]
            continue
        m = LEADING_SECTION_NUM_RE.match(text)
        if m:
            text = text[m.end():]
            continue
        break
    text = INLINE_SECTION_NUM_RE.sub("", text)
    # The Latin Library marks editorial supplements -- letters or words an
    # editor restored to a damaged or corrupt manuscript -- with [square] or
    # <angle> brackets, e.g. "renite[n]tem", "c<ivit>a<te>s", "[post]quam".
    # These are meant to be read as ordinary running text, so drop just the
    # delimiters and keep the supplied content. This isn't only cosmetic:
    # when a bracket lands with no surrounding space it glues to the next
    # word (e.g. "]quam"), and that malformed token was observed to corrupt
    # LatinCy's sentence segmenter for the rest of the paragraph, merging
    # dozens of real sentences into one -- see the "ch. 14 / livy-11172"
    # bug report this fix addresses.
    text = re.sub(r"[\[\]<>]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    # Stripping a bare digit can leave a stray space before punctuation
    # (e.g. "petiverunt 3, parsque" -> "petiverunt , parsque"); tidy it up.
    text = re.sub(r" ([,.;:!?])", r"\1", text)
    return text.strip(), chapter_label


def iter_paragraphs(name: str):
    """Yield (clean_text, book, chapter) for every content paragraph."""
    src_path = CORPUS_DIR / f"{name}.txt"
    lines = src_path.read_text(encoding="utf-8").split("\n")

    current_book = None
    current_chapter = None
    for raw_line in lines:
        kind, stripped = classify_line(raw_line)
        if kind in ("blank", "number_line"):
            continue
        if kind == "title":
            current_book = stripped
            current_chapter = None
            continue
        if kind == "chapter_line":
            current_chapter = stripped
            continue

        clean_text, chapter_label = strip_editorial_markers(stripped)
        if chapter_label is not None:
            current_chapter = chapter_label
        if not clean_text:
            continue
        yield clean_text, current_book, current_chapter


def write_record(fh, meta_comments, text, rows, sent_id):
    for comment in meta_comments:
        fh.write(f"# {comment}\n")
    fh.write(f"# sent_id = {sent_id}\n")
    fh.write(f"# text = {text}\n")
    for row in rows:
        fh.write(row + "\n")
    fh.write("\n")
