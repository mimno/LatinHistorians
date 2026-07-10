# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "spacy>=3.8.11",
#   "click>=8.1",
#   "la-core-web-lg @ https://huggingface.co/latincy/la_core_web_lg/resolve/main/la_core_web_lg-3.9.6-py3-none-any.whl",
# ]
# ///
"""Annotate the Latin historian texts with LatinCy (spaCy la_core_web_lg),
writing one CoNLL-U file per source text into parsed_latincy/.

Run with `uv run parse_texts_latincy.py [names...]` -- the PEP 723 header
gives this script its own environment (LatinCy needs spaCy >= 3.8.11, which
conflicts with the cltk pin in the project env).
"""
import sys
from pathlib import Path

import spacy

from textprep import TEXTS, iter_paragraphs, write_record

OUT_DIR = Path("/Users/mimno/Documents/Data/LatinHistorians/parsed_latincy")


def sent_rows(sent):
    """Format one spaCy Span (sentence) as CoNLL-U token lines."""
    tokens = [t for t in sent if not t.is_space]
    local = {t.i: i + 1 for i, t in enumerate(tokens)}
    rows = []
    for t in tokens:
        if t.dep_ == "ROOT" or t.head.i not in local:
            head, dep = 0, "root" if t.dep_ == "ROOT" else t.dep_
        else:
            head, dep = local[t.head.i], t.dep_
        feats = str(t.morph) or "_"
        rows.append("\t".join([
            str(local[t.i]), t.text, t.lemma_ or "_", t.pos_ or "_",
            t.tag_ or "_", feats, str(head), dep or "_", "_", "_",
        ]))
    return rows


def process_file(nlp, name: str):
    out_path = OUT_DIR / f"{name}.conllu"
    sent_counter = 0
    stream = ((text, (book, chapter)) for text, book, chapter in iter_paragraphs(name))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(f"# newdoc id = {name}\n")
        for doc, (book, chapter) in nlp.pipe(stream, as_tuples=True, batch_size=32):
            for sent in doc.sents:
                rows = sent_rows(sent)
                if not rows:
                    continue
                sent_counter += 1
                meta = []
                if book:
                    meta.append(f"book = {book}")
                if chapter:
                    meta.append(f"chapter = {chapter}")
                text = " ".join(t.text for t in sent if not t.is_space)
                write_record(fh, meta, text, rows, f"{name}-{sent_counter}")
    return sent_counter


def main():
    names = sys.argv[1:] or TEXTS
    OUT_DIR.mkdir(exist_ok=True)
    nlp = spacy.load("la_core_web_lg")
    for name in names:
        print(f"Processing {name}...", flush=True)
        n = process_file(nlp, name)
        print(f"  -> {n} sentences written to parsed_latincy/{name}.conllu", flush=True)


if __name__ == "__main__":
    main()
