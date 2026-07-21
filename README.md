# A Phrase-Structure Lexicon of the Roman Historians

A browsable lexicon of ~450 fine-grained Latin constructions — from *cum* +
pluperfect subjunctive to sentence-initial ablative absolutes with verbs of
perception — extracted from ~70,000 parsed sentences of eight Roman
historians: Caesar, Sallust, Livy, Curtius, Tacitus, Suetonius, Ammianus,
and the Historia Augusta.

**Browse the lexicon: the `docs/` site (GitHub Pages).** Each construction
has a per-author frequency profile (per 1,000 sentences), typical lexical
formulas, and highlighted corpus examples, plus a page listing every corpus
instance with citations. A final section catalogs whole-sentence clause
skeletons ("architectures").

## Pipeline

```
txt/*.txt              source texts (The Latin Library)
  └─ parse_texts_latincy.py   LatinCy (spaCy la_core_web_lg) morphology +
       │                      dependency parses → parsed_latincy/*.conllu  (not committed)
       └─ phrase_lexicon.py      deterministic construction extraction:
       │                         structural signatures (marker + mood/tense + flags),
       │                         semantic-field refinement, clause skeletons
       │                         → phrase_inventory.json, architectures.json,
       │                           phrase_examples.jsonl, lemma_requests.json
       ├─ lemma_fields.json      lemma → semantic field table (small-model generated)
       └─ build_lexicon_html.py  renders docs/index.html + docs/examples/
```

Everything structural is deterministic code; a small LLM (Claude Haiku)
contributed one bounded lookup table, lemma→semantic-field assignments,
which is committed so the site rebuilds without model calls: `uv run
phrase_lexicon.py && uv run build_lexicon_html.py` (requires the parses;
regenerate those first with `uv run parse_texts_latincy.py` — a PEP 723
script with its own environment, since LatinCy needs a newer spaCy than
the project env). `parse_texts.py` is the legacy CLTK parser, kept for
comparison; set `PARSED_DIR=parsed` in the environment to analyze its
output instead. Text-prep helpers shared by both parsers live in
`textprep.py`.

An earlier version of this pipeline also generated a per-cluster English
translation via a small model (`make_notes_input.py` /
`cluster_notes.json`, rendered as a translation line under each example).
That step is not currently in the published site — repeated attempts
produced either literal word-for-word calques or ran out of budget
mid-batch — and would need a stronger model or tighter verification loop
before being reinstated.

## Parser notes

The corpus was originally parsed with CLTK/Stanza and migrated to LatinCy
(`la_core_web_lg` 3.9.6 under spaCy 3.8.14, pinned by wheel URL in
parse_texts_latincy.py), which fixed several systematic errors: pluperfect subjunctives in -issent
were tagged as perfects; future active participles (-turus) as perfect
passives; 3rd-plural perfects in -ere as present infinitives with invented
lemmas (*habuo*); gerund/gerundive/supine shared one tag. The extraction
code retains defensive guards for all of these (they are harmless under
LatinCy) plus a normalization layer that reads both tagsets. LatinCy's
own quirks: no PronType features (relative/interrogative pronouns are
identified by lemma), consistently u-for-v orthography, and somewhat more
unresolved attachments (`dep`, `orphan`) than CLTK produced.

## Caveats

Parses are automatic and imperfect. Construction labels, semantic
groupings, and translations are automatic and may contain errors.

## Attribution

Latin texts from [The Latin Library](https://www.thelatinlibrary.com/).
Parsing by [LatinCy](https://huggingface.co/latincy) (Patrick J. Burns,
*LatinCy: Synthetic trained pipelines for Latin NLP*, 2023);
earlier parses by [CLTK](https://cltk.org/).
