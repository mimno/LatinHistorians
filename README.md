# A Phrase-Structure Lexicon of the Roman Historians

A browsable lexicon of ~470 fine-grained Latin constructions — from *cum* +
pluperfect subjunctive to sentence-initial ablative absolutes with verbs of
perception — extracted from ~73,000 parsed sentences of eight Roman
historians: Caesar, Sallust, Livy, Curtius, Tacitus, Suetonius, Ammianus,
and the Historia Augusta.

**Browse the lexicon: the `docs/` site (GitHub Pages).** Each construction
has a per-author frequency profile (per 1,000 sentences), typical lexical
formulas, highlighted corpus examples with an English translation of one
exemplar, and a page listing every corpus instance with citations. A final
section catalogs whole-sentence clause skeletons ("architectures").

## Pipeline

```
txt/*.txt              source texts (The Latin Library)
  └─ parse_texts.py    CLTK morphology + dependency parses → parsed/*.conllu  (not committed)
       └─ phrase_lexicon.py      deterministic construction extraction:
       │                         structural signatures (marker + mood/tense + flags),
       │                         semantic-field refinement, clause skeletons
       │                         → phrase_inventory.json, architectures.json,
       │                           phrase_examples.jsonl, lemma_requests.json
       ├─ lemma_fields.json      lemma → semantic field table (small-model generated)
       ├─ cluster_notes.json     exemplar translations (small-model generated)
       │    (make_notes_input.py prepares the translation task)
       └─ build_lexicon_html.py  renders docs/index.html + docs/examples/
```

Everything structural is deterministic code; a small LLM (Claude Haiku)
contributed only two bounded lookup tables: lemma→semantic-field
assignments and exemplar translations. Both are committed, so the site
rebuilds without model calls: `uv run phrase_lexicon.py && uv run
build_lexicon_html.py` (requires the parses; regenerate those first with
`uv run parse_texts.py`).

## Caveats

Parses are automatic (CLTK) and imperfect. Known quirks worked around in
code: future active participles mis-tagged as perfect passive (recovered
from -turus/-surus morphology); 3rd-plural perfects in -ere mis-parsed as
infinitives (filtered by a finite-lemma census); gerund and gerundive share
one tag (disambiguated structurally). Lemmatizer errors (e.g. *iussisto*)
surface in some word lists. Construction labels, semantic groupings, and
translations are automatic and may contain errors.

## Attribution

Latin texts from [The Latin Library](https://www.thelatinlibrary.com/).
Parsing by [CLTK](https://cltk.org/).
