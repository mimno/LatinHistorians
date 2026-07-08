"""Annotate the Latin historian texts with parts of speech and dependency
parse trees using CLTK (backed by Stanza's Latin ITTB model), writing one
CoNLL-U file per source text into parsed/.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

# Local models are already downloaded; skip Stanza's per-run check of
# resources.json on GitHub, which otherwise gets rate-limited (HTTP 429)
# when the pipeline is initialized repeatedly.
import stanza.pipeline.core as _stanza_core

_stanza_core.download_resources_json = lambda *a, **k: None

from cltk.alphabet.processes import LatinNormalizeProcess
from cltk.core.data_types import Language
from cltk.dependency.processes import LatinStanzaProcess
from cltk.languages.utils import get_lang
from cltk.nlp import NLP, Pipeline

CORPUS_DIR = Path("/Users/mimno/Documents/Data/LatinHistorians/txt")
OUT_DIR = Path("/Users/mimno/Documents/Data/LatinHistorians/parsed")
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


@dataclass
class LatinLitePipeline(Pipeline):
    """POS tagging + dependency parsing only (skips embeddings/lexicon)."""

    description: str = "Lite pipeline for Latin (POS + dependency parse only)"
    language: Language = get_lang("lat")
    processes: list = field(
        default_factory=lambda: [LatinNormalizeProcess, LatinStanzaProcess]
    )


def feats_to_conllu(features) -> str:
    if not features or not features.features:
        return "_"
    parts = []
    for feat_cls in sorted(features.features.keys(), key=lambda c: c.__name__):
        # CLTK files UD features it can't map to a known enum (see the
        # "Unrecognized UD feature ..." warnings from stanza_to_cltk_word)
        # under the literal class NoneType with value [None]; skip those
        # rather than emitting a bogus "NoneType=None" FEATS entry.
        if feat_cls is type(None):
            continue
        values = features.features[feat_cls]
        val_str = ",".join(str(v) for v in values)
        parts.append(f"{feat_cls.__name__}={val_str}")
    return "|".join(parts) if parts else "_"


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
    text = re.sub(r"[ \t]+", " ", text)
    # Stripping a bare digit can leave a stray space before punctuation
    # (e.g. "petiverunt 3, parsque" -> "petiverunt , parsque"); tidy it up.
    text = re.sub(r" ([,.;:!?])", r"\1", text)
    return text.strip(), chapter_label


def sentence_to_rows(sent) -> list:
    """Format one CLTK Sentence's words as CoNLL-U token-line strings."""
    rows = []
    for w in sent.words:
        idx = w.index_token + 1
        head = 0 if w.governor is None or w.governor < 0 else w.governor + 1
        rows.append(
            "\t".join(
                [
                    str(idx),
                    w.string or "_",
                    w.lemma or "_",
                    w.upos or "_",
                    w.xpos or "_",
                    feats_to_conllu(w.features),
                    str(head),
                    w.dependency_relation or "_",
                    "_",
                    "_",
                ]
            )
        )
    return rows


def write_conllu_sentence(fh, sent, sent_id, meta_comments):
    write_record(fh, meta_comments, " ".join(w.string for w in sent.words if w.string), sentence_to_rows(sent), sent_id)


def write_record(fh, meta_comments, text, rows, sent_id):
    for comment in meta_comments:
        fh.write(f"# {comment}\n")
    fh.write(f"# sent_id = {sent_id}\n")
    fh.write(f"# text = {text}\n")
    for row in rows:
        fh.write(row + "\n")
    fh.write("\n")


# Batching: feeding one paragraph at a time to nlp.analyze() keeps each
# neural-net forward pass tiny, so per-call overhead dominates and torch's
# thread pool sits mostly idle. Instead we join many paragraphs into one
# large chunk per analyze() call (much better throughput/CPU utilization),
# using this sentinel as a paragraph separator so we can still recover which
# source paragraph (and thus which book/chapter) each sentence came from.
BATCH_MARKER = "ZZZPARAGRAPHBREAKZZZ"
BATCH_CHAR_LIMIT = 200_000  # ~ a few hundred paragraphs per analyze() call


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


def is_marker_sentence(sent) -> bool:
    words = [w for w in sent.words if w.string]
    return len(words) >= 1 and words[0].string == BATCH_MARKER


def analyze_batch(nlp, batch_paragraphs):
    """Run one analyze() call over a batch of (text, book, chapter) tuples.

    Returns a list of (meta_comments, text, rows) records, in order, with
    no sent_id assigned yet -- that's cheap bookkeeping the caller does
    after collecting results, which is what lets this function run
    independently (and in parallel) across worker processes.
    """
    chunk = f"\n\n{BATCH_MARKER}.\n\n".join(text for text, _, _ in batch_paragraphs)
    doc = nlp.analyze(text=chunk)

    records = []
    para_idx = 0
    for sent in doc.sentences:
        if not sent.words:
            continue
        if is_marker_sentence(sent):
            para_idx += 1
            continue
        # Guard against an unexpected miscount so metadata never derails.
        para_idx = min(para_idx, len(batch_paragraphs) - 1)
        _, book, chapter = batch_paragraphs[para_idx]
        meta = []
        if book:
            meta.append(f"book = {book}")
        if chapter:
            meta.append(f"chapter = {chapter}")
        text = " ".join(w.string for w in sent.words if w.string)
        records.append((meta, text, sentence_to_rows(sent)))
    return records


def process_batch(nlp, out_fh, name, batch_paragraphs, sent_counter):
    """Serial helper: analyze one batch and write it immediately."""
    records = analyze_batch(nlp, batch_paragraphs)
    for meta, text, rows in records:
        sent_counter += 1
        write_record(out_fh, meta, text, rows, f"{name}-{sent_counter}")
    return sent_counter


def iter_batches(name: str):
    """Group a text's paragraphs into ~BATCH_CHAR_LIMIT-sized batches."""
    batch: list = []
    batch_chars = 0
    for clean_text, book, chapter in iter_paragraphs(name):
        batch.append((clean_text, book, chapter))
        batch_chars += len(clean_text)
        if batch_chars >= BATCH_CHAR_LIMIT:
            yield batch
            batch = []
            batch_chars = 0
    if batch:
        yield batch


def process_file(nlp, name: str):
    out_path = OUT_DIR / f"{name}.conllu"
    sent_counter = 0
    with open(out_path, "w", encoding="utf-8") as out_fh:
        out_fh.write(f"# newdoc id = {name}\n")
        for batch in iter_batches(name):
            sent_counter = process_batch(nlp, out_fh, name, batch, sent_counter)
            print(
                f"    ...batch of {len(batch)} paragraphs "
                f"({sent_counter} sentences so far)",
                flush=True,
            )
    return sent_counter


# --- Parallel processing ---------------------------------------------------
#
# A single analyze() call doesn't parallelize well across many CPU threads
# (Stanza's tagger/parser has sequential recurrent layers), so a lone process
# tops out around 2.5-3x CPU even on a big batch. Independent batches have no
# such dependency, though, so running many one-thread worker processes in a
# pool gets much closer to using the whole machine. Benchmarked on this
# 14-core (10P+4E) machine: 1 worker ~1880 tok/s, 6 workers x1 thread ~8070
# tok/s (4.3x); going wider (8-12 workers) didn't help further.
DEFAULT_NUM_WORKERS = 6
DEFAULT_THREADS_PER_WORKER = 1

_WORKER_NLP = None


def _init_worker(threads_per_worker: int):
    import os

    os.environ["OMP_NUM_THREADS"] = str(threads_per_worker)
    os.environ["MKL_NUM_THREADS"] = str(threads_per_worker)
    import torch

    torch.set_num_threads(threads_per_worker)

    global _WORKER_NLP
    _WORKER_NLP = NLP(language="lat", custom_pipeline=LatinLitePipeline(), suppress_banner=True)


def _run_job(job):
    name, batch_idx, batch_paragraphs = job
    records = analyze_batch(_WORKER_NLP, batch_paragraphs)
    return name, batch_idx, len(batch_paragraphs), records


def run_parallel(names, num_workers=DEFAULT_NUM_WORKERS, threads_per_worker=DEFAULT_THREADS_PER_WORKER):
    from concurrent.futures import ProcessPoolExecutor, as_completed

    OUT_DIR.mkdir(exist_ok=True)

    jobs = []
    for name in names:
        for batch_idx, batch in enumerate(iter_batches(name)):
            jobs.append((name, batch_idx, batch))
    print(f"Dispatching {len(jobs)} batches across {len(names)} texts to {num_workers} workers...", flush=True)

    # batch_idx -> records, gathered per text so we can write each file in
    # original order once all its batches are back.
    pending = {name: {} for name in names}
    total_batches = {name: sum(1 for _ in iter_batches(name)) for name in names}

    with ProcessPoolExecutor(
        max_workers=num_workers, initializer=_init_worker, initargs=(threads_per_worker,)
    ) as pool:
        futures = [pool.submit(_run_job, job) for job in jobs]
        for future in as_completed(futures):
            name, batch_idx, n_paragraphs, records = future.result()
            pending[name][batch_idx] = records
            print(
                f"  {name}: batch {batch_idx + 1}/{total_batches[name]} done "
                f"({n_paragraphs} paragraphs, {len(records)} sentences)",
                flush=True,
            )

    sentence_counts = {}
    for name in names:
        out_path = OUT_DIR / f"{name}.conllu"
        sent_counter = 0
        with open(out_path, "w", encoding="utf-8") as out_fh:
            out_fh.write(f"# newdoc id = {name}\n")
            for batch_idx in sorted(pending[name]):
                for meta, text, rows in pending[name][batch_idx]:
                    sent_counter += 1
                    write_record(out_fh, meta, text, rows, f"{name}-{sent_counter}")
        sentence_counts[name] = sent_counter
    return sentence_counts


def main():
    import sys

    args = sys.argv[1:]
    serial = "--serial" in args
    args = [a for a in args if a != "--serial"]
    names = args or TEXTS

    if serial:
        OUT_DIR.mkdir(exist_ok=True)
        nlp = NLP(language="lat", custom_pipeline=LatinLitePipeline(), suppress_banner=True)
        for name in names:
            print(f"Processing {name}...", flush=True)
            n = process_file(nlp, name)
            print(f"  -> {n} sentences written to parsed/{name}.conllu", flush=True)
        return

    counts = run_parallel(names)
    for name in names:
        print(f"  -> {counts[name]} sentences written to parsed/{name}.conllu", flush=True)


if __name__ == "__main__":
    main()
