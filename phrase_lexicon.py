"""Extract a fine-grained lexicon of phrase structures from the parsed corpus.

Pass 1 (this script, deterministic): walk every sentence, pull out phrase
units (subordinate clauses, absolutes, participial phrases, infinitive
clauses, gerund(ive) phrases, relative constructions...) and give each a
fine structural signature built from marker lemma + traditional mood/tense
+ structural flags. Also record each sentence's clause skeleton
("architecture"). Outputs:

  phrase_inventory.json   families -> signatures -> counts, lexical anchors,
                          matrix-verb counts, highlighted examples
  architectures.json      frequent clause skeletons per author, with examples
  lemma_requests.json     lemma lists that a small model should sort into
                          semantic fields (input to the refine step)
"""
import html as html_mod
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

# The parser mis-tags future active participles (facturus) as perfect
# passive; the -turus/-surus morphology is unambiguous on VERB participle
# rows, so recover them lexically.
FUT_PTCP_RE = re.compile(r"[ts]ur(us|a|um|i|ae|o|am|os|as|is|orum|arum|e)$", re.I)

# 3rd-plural perfects in -ere (habuere, credidere) are sometimes mis-parsed
# as present infinitives with a fabricated lemma (habuo, credido). A
# fabricated lemma never occurs as a finite verb anywhere in the corpus,
# so a finite-lemma census (filled by a pre-pass in main) exposes them.
FINITE_LEMMAS = Counter()


def suspicious_inf(r):
    return (r["form"].lower().endswith("ere")
            and FINITE_LEMMAS
            and FINITE_LEMMAS.get(r["lemma"].lower(), 0) == 0)

from readability import PARSED_DIR, TEXTS, parse_conllu


def parse_conllu_meta(path):
    """Like readability.parse_conllu, but also yields the sentence's comment
    metadata (sent_id, book, chapter) so examples can carry citations."""
    meta, sentence = {}, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                if sentence:
                    yield meta, sentence
                meta, sentence = {}, []
                continue
            if line.startswith("#"):
                if " = " in line:
                    k, v = line[1:].split(" = ", 1)
                    meta[k.strip()] = v.strip()
                continue
            cols = line.split("\t")
            sentence.append(
                {
                    "id": int(cols[0]),
                    "form": cols[1],
                    "lemma": cols[2],
                    "upos": cols[3],
                    "feats": cols[5],
                    "head": int(cols[6]),
                    "deprel": cols[7],
                }
            )
    if sentence:
        yield meta, sentence

random.seed(0)
OUT_DIR = Path("/Users/mimno/Documents/Data/LatinHistorians")

# Optional lemma -> semantic-field tables (produced by a small model from
# lemma_requests.json). When present, several families get refined,
# field-crossed signatures; without it the script emits pure-structure sigs.
FIELDS = {"verbs": {}, "nouns": {}}
_fields_path = OUT_DIR / "lemma_fields.json"
if _fields_path.exists():
    FIELDS = json.loads(_fields_path.read_text())
    print(f"Loaded semantic fields: {len(FIELDS['verbs'])} verbs, {len(FIELDS['nouns'])} nouns")


def vfield(lemma):
    return FIELDS["verbs"].get(lemma) if lemma else None


def nfield(lemma):
    return FIELDS["nouns"].get(lemma) if lemma else None

# ---------------------------------------------------------------- helpers

def feats_dict(s):
    if not s or s == "_":
        return {}
    out = {}
    for kv in s.split("|"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out


def build_indices(sent):
    by_id = {r["id"]: r for r in sent}
    children = defaultdict(list)
    for r in sent:
        if r["head"] != 0 and r["head"] in by_id:
            children[r["head"]].append(r["id"])
    return by_id, children


def subtree_span(tid, children):
    ids = {tid}
    frontier = [tid]
    while frontier:
        nxt = []
        for node in frontier:
            for c in children.get(node, []):
                if c not in ids:
                    ids.add(c)
                    nxt.append(c)
        frontier = nxt
    return min(ids), max(ids)


def render(sent, span=None):
    """Plain-ish text with the span wrapped in <mark>. Forms are escaped:
    some sources carry editorial angle brackets (<si>, <sagum) that would
    otherwise open stray HTML tags."""
    out, open_mark = [], False
    for r in sent:
        in_span = span is not None and span[0] <= r["id"] <= span[1]
        if in_span and not open_mark:
            out.append("<mark>")
            open_mark = True
        elif not in_span and open_mark:
            out.append("</mark>")
            open_mark = False
        out.append(html_mod.escape(r["form"]))
        out.append(" ")
    if open_mark:
        out.append("</mark>")
    text = "".join(out).strip()
    for p in [",", ".", ";", ":", "!", "?"]:
        text = text.replace(" " + p, p)
    return text


# Traditional tense from the CLTK Tense x Aspect encoding.
def trad_tense(fd):
    t, a = fd.get("Tense"), fd.get("Aspect")
    if t == "present":
        return "pres"
    if t == "future":
        return "futperf" if a == "perfective" else "fut"
    if t == "pluperfect":
        return "plup"
    if t == "past":
        return "perf" if a == "perfective" else "impf"
    return None


MOOD_ABBR = {"indicative": "ind", "subjunctive": "subj", "imperative": "imper"}


def clause_moodtense(head_row, children, by_id):
    """Mood.tense of a clause whose head is head_row; falls back to a
    sum-copula/aux child for nominal predicates. Returns e.g. 'subj.impf',
    'ind.perf', 'nominal+ind.pres', or None."""
    fd = head_row["feats_d"]
    m = fd.get("Mood")
    if m:
        return f"{MOOD_ABBR.get(m, m)}.{trad_tense(fd) or '?'}"
    for c in children.get(head_row["id"], []):
        cr = by_id[c]
        if cr["deprel"] in ("cop", "aux", "aux:pass") and cr["feats_d"].get("Mood"):
            cf = cr["feats_d"]
            base = f"{MOOD_ABBR.get(cf['Mood'], cf['Mood'])}.{trad_tense(cf) or '?'}"
            if fd.get("VerbForm") == "participle" and cr["deprel"] == "aux:pass":
                return base  # periphrastic finite passive: treat as finite
            return f"nom+{base}"
    if fd.get("VerbForm") == "infinitive":
        return "inf"
    return None


def norm_marker(lemma):
    l = lemma.lower().replace("u", "u").replace("v", "v")
    l = l.replace("uelut", "velut")
    return {
        "uti": "ut", "utque": "ut", "cumque": "cum", "sicuti": "sicut",
        "veluti": "velut", "ueluti": "velut", "uelut": "velut",
        "posteaquam": "postquam", "neu": "neve", "seu": "sive",
    }.get(l, l)


# marker -> family routing
COND_MARKERS = {"si", "nisi", "ni", "sin", "sive"}
CONC_MARKERS = {"quamquam", "quamvis", "quamuis", "etsi", "tametsi", "etiamsi", "licet", "quamlibet"}
CAUSAL_MARKERS = {"quod", "quia", "quoniam", "quippe", "siquidem", "quando"}
TEMPORAL_MARKERS = {"postquam", "ubi", "simul", "simulac", "simulatque", "dum", "donec", "quoad", "priusquam", "antequam"}
COMP_MARKERS = {"quam", "velut", "tamquam", "sicut", "quasi", "ceu", "prout", "quemadmodum"}
FINAL_MARKERS = {"ut", "ne", "quo", "quin", "quominus", "neve"}
INDQ_MARKERS = {"num", "an", "utrum", "anne", "necne", "cur", "quare", "quomodo", "quorsum", "unde", "quando"}
INTERROG_LEMMAS = INDQ_MARKERS | {"quis", "quid", "uter", "qualis", "quantus", "quot", "quotiens", "ubi"}

# correlative signals in the matrix clause for result-clause detection
CORRELATIVES = {"ita", "sic", "adeo", "tam", "tantus", "talis", "totiens", "tantum", "usque", "eo", "tantopere", "is"}

FAM_ORDER = [
    "cum_clause", "conditional", "purpose_result", "causal", "temporal",
    "concessive", "comparative", "relative", "rel_connective",
    "indirect_question", "aci", "compl_inf", "historic_inf",
    "abl_abs", "participle", "gerundive", "case_usage",
]


def classify_marker_clause(marker, head, children, by_id, sent):
    """Return (family, signature) for a clause introduced by `marker`
    (already normalized) whose clausal head row is `head`."""
    mt = clause_moodtense(head, children, by_id)
    if mt is None:
        return None
    deprel = head["deprel"]
    kids = [by_id[c] for c in children.get(head["id"], [])]
    has_non = any(k["deprel"] == "advmod:neg" or k["lemma"].lower() == "non" for k in kids)

    if marker == "cum":
        return ("cum_clause", f"cum+{mt}")
    if marker in COND_MARKERS:
        return ("conditional", f"{marker}+{mt}")
    if marker in CONC_MARKERS:
        return ("concessive", f"{marker}+{mt}")
    if marker in CAUSAL_MARKERS:
        # quod as ccomp/csubj = substantive ("the fact that")
        if marker == "quod" and deprel in ("ccomp", "csubj", "csubj:pass"):
            return ("causal", f"quod-substantive+{mt}")
        return ("causal", f"{marker}+{mt}")
    if marker in TEMPORAL_MARKERS:
        return ("temporal", f"{marker}+{mt}")
    if marker in COMP_MARKERS:
        return ("comparative", f"{marker}+{mt}")
    if marker in FINAL_MARKERS:
        if marker == "ut" and mt.startswith("ind"):
            return ("comparative", f"ut+{mt}")
        # correlative in matrix clause -> likely result
        correl = False
        matrix_id = head["head"]
        matrix = by_id.get(matrix_id)
        if matrix_id in by_id:
            for c in children.get(matrix_id, []):
                if by_id[c]["lemma"].lower() in CORRELATIVES and by_id[c]["upos"] in ("ADV", "DET", "ADJ"):
                    correl = True
                    break
        role = "comp" if deprel in ("ccomp", "csubj", "csubj:pass") else "adv"
        mf = vfield(matrix["lemma"].lower()) if matrix and matrix["upos"] in ("VERB", "AUX") else None
        if FIELDS["verbs"] and marker in ("ut", "ne"):
            # resolve the classic purpose/result/command/fear ambiguity
            if marker == "ne" and mf == "fear":
                subtype = "fear-clause"
            elif mf == "command" and role == "comp":
                subtype = "indirect-command"
            elif marker == "ut" and mf == "happen" and role == "comp":
                subtype = "result-substantive"
            elif marker == "ut" and (correl or has_non):
                subtype = "result"
            elif mt.startswith("subj"):
                subtype = "purpose"
            else:
                subtype = role
            return ("purpose_result", f"{marker}+{mt}|{subtype}")
        neg = "+non" if (marker == "ut" and has_non) else ""
        return ("purpose_result", f"{marker}+{mt}{neg}{'+correl' if correl else ''}|{role}")
    if marker in INDQ_MARKERS and mt.startswith("subj"):
        return ("indirect_question", f"{marker}+{mt}")
    return None


def extract_units(sent, by_id, children):
    """Yield (family, sig, lex_anchor, matrix_lemma, head_id) tuples."""
    units = []
    root_id = next((r["id"] for r in sent if r["head"] == 0), None)
    non_punct = [r for r in sent if r["upos"] != "PUNCT"]
    seen_clause_heads = set()  # avoid double-marking one clause

    # --- marker-introduced clauses
    for r in sent:
        if r["deprel"] != "mark":
            continue
        head = by_id.get(r["head"])
        if head is None or head["id"] in seen_clause_heads:
            continue
        res = classify_marker_clause(norm_marker(r["lemma"]), head, children, by_id, sent)
        if res:
            fam, sig = res
            matrix = by_id.get(head["head"])
            units.append((fam, sig, r["lemma"].lower() + " " + head["lemma"].lower(),
                          matrix["lemma"].lower() if matrix and matrix["upos"] in ("VERB", "AUX") else None,
                          head["id"]))
            seen_clause_heads.add(head["id"])

    # --- indirect questions without a mark deprel (wh-word inside ccomp)
    for r in sent:
        if r["deprel"] in ("ccomp", "ccomp:relcl") and r["id"] not in seen_clause_heads:
            mt = clause_moodtense(r, children, by_id)
            if not mt or not mt.startswith("subj"):
                continue
            lo, hi = subtree_span(r["id"], children)
            wh = None
            for cid in range(lo, hi + 1):
                cr = by_id.get(cid)
                if cr and (cr["feats_d"].get("PronominalType") == "interrogative"
                           or cr["lemma"].lower() in INDQ_MARKERS):
                    wh = cr["lemma"].lower()
                    break
            if wh:
                matrix = by_id.get(r["head"])
                units.append(("indirect_question", f"{wh}+{mt}",
                              wh + " " + r["lemma"].lower(),
                              matrix["lemma"].lower() if matrix and matrix["upos"] == "VERB" else None,
                              r["id"]))
                seen_clause_heads.add(r["id"])

    # --- relative clauses
    for r in sent:
        if r["deprel"] in ("acl:relcl", "csubj:relcl", "ccomp:relcl") and r["id"] not in seen_clause_heads:
            mt = clause_moodtense(r, children, by_id)
            if mt is None:
                continue
            lo, hi = subtree_span(r["id"], children)
            pron = None
            for cid in range(lo, hi + 1):
                cr = by_id.get(cid)
                if cr and cr["feats_d"].get("PronominalType") == "relative" and cr["lemma"].lower() in ("qui", "quicumque", "quisquis"):
                    pron = cr
                    break
            if pron is None:
                continue
            case = pron["feats_d"].get("Case", "?")[:3]
            mood = mt.split(".")[0].replace("nom+", "")
            sig = f"qui[{case}:{pron['deprel']}]+{mood}" if mood == "ind" else f"qui[{case}:{pron['deprel']}]+{mt}"
            ant = by_id.get(r["head"])
            units.append(("relative", sig,
                          (ant["lemma"].lower() + " qui" if ant else "qui") + " " + r["lemma"].lower(),
                          None, r["id"]))
            seen_clause_heads.add(r["id"])

    # --- connecting relative (sentence-initial relative pronoun, main clause)
    if non_punct:
        first = non_punct[0]
        if first["feats_d"].get("PronominalType") == "relative" and first["lemma"].lower() == "qui":
            in_relcl = False
            node = first
            for _ in range(30):
                if node["deprel"] in ("acl:relcl", "csubj:relcl", "ccomp:relcl"):
                    in_relcl = True
                    break
                if node["head"] == 0 or node["head"] not in by_id:
                    break
                node = by_id[node["head"]]
            if not in_relcl:
                second = non_punct[1] if len(non_punct) > 1 else None
                follower = second["lemma"].lower() if second and second["upos"] == "SCONJ" else ""
                sig = f"{first['form'].lower()}+{follower}" if follower else first["form"].lower()
                units.append(("rel_connective", sig, first["form"].lower(), None, first["id"]))

    # --- infinitive clauses: AcI, complementary, historic
    for r in sent:
        fd = r["feats_d"]
        is_inf = fd.get("VerbForm") == "infinitive" and not suspicious_inf(r)
        is_fut_ptcp = fd.get("VerbForm") == "participle" and (
            (fd.get("Aspect") == "prospective" and fd.get("Voice") == "active")
            or (r["upos"] == "VERB" and FUT_PTCP_RE.search(r["form"])))
        if not (is_inf or is_fut_ptcp):
            continue
        kids = [by_id[c] for c in children.get(r["id"], [])]
        subj = next((k for k in kids if k["deprel"] in ("nsubj", "nsubj:pass")), None)
        matrix = by_id.get(r["head"])
        matrix_lemma = matrix["lemma"].lower() if matrix and matrix["upos"] in ("VERB", "AUX") else None
        if r["deprel"] in ("ccomp", "xcomp", "csubj", "csubj:pass") and subj is not None:
            if is_fut_ptcp:
                tense = "fut"
            else:
                tense = "perf" if fd.get("Aspect") == "perfective" else "pres"
            refl = "+se" if subj["lemma"].lower() == "sui" else ""
            voice = ".pass" if fd.get("Voice") == "passive" and not is_fut_ptcp else ""
            mf = vfield(matrix_lemma)
            after = f"|after-{mf}" if mf else ""
            units.append(("aci", f"inf.{tense}{voice}{refl}{after}",
                          r["lemma"].lower(), matrix_lemma, r["id"]))
        elif is_inf and r["deprel"] == "xcomp" and subj is None and matrix_lemma:
            mf = vfield(matrix_lemma)
            sig = f"inf-after-{mf}" if mf else "matrix-verb+inf"
            units.append(("compl_inf", sig, r["lemma"].lower(), matrix_lemma, r["id"]))
        elif is_inf and (r["head"] == 0 or (matrix and matrix["head"] == 0 and r["deprel"] == "conj")):
            if subj is not None and subj["feats_d"].get("Case") == "nominative":
                hf = vfield(r["lemma"].lower())
                sig = f"historic-inf|{hf}" if hf else "historic-inf"
                units.append(("historic_inf", sig, r["lemma"].lower(), None, r["id"]))

    # --- ablative absolute
    for r in sent:
        if r["deprel"] != "advcl:abs":
            continue
        fd = r["feats_d"]
        if fd.get("VerbForm") == "participle":
            asp, voice = fd.get("Aspect"), fd.get("Voice")
            if asp == "perfective":
                sub = "perf-pass"
            elif asp == "imperfective":
                sub = "pres-act"
            else:
                sub = "gerundive"
        else:
            sub = "verbless"
        lo, hi = subtree_span(r["id"], children)
        initial = "+initial" if lo <= 2 else ""
        subj = next((by_id[c] for c in children.get(r["id"], [])
                     if by_id[c]["deprel"] in ("nsubj", "nsubj:pass")), None)
        pair = (subj["lemma"].lower() + " " if subj else "") + r["lemma"].lower()
        hf = vfield(r["lemma"].lower()) if sub != "verbless" else None
        field_sfx = f"|{hf}" if hf else ""
        units.append(("abl_abs", f"ablabs:{sub}{initial}{field_sfx}", pair, None, r["id"]))

    # --- participium coniunctum (non-absolute, non-periphrastic participles)
    for r in sent:
        fd = r["feats_d"]
        if fd.get("VerbForm") != "participle" or fd.get("Aspect") == "prospective":
            continue
        if r["deprel"] in ("advcl:abs", "root", "amod"):
            continue
        kids = [by_id[c] for c in children.get(r["id"], [])]
        if any(k["deprel"] in ("aux", "aux:pass", "cop") for k in kids):
            continue  # periphrastic finite form
        if r["deprel"] not in ("acl", "advcl:pred", "advcl"):
            continue
        asp, voice, case = fd.get("Aspect"), fd.get("Voice"), fd.get("Case", "?")
        if r["upos"] == "VERB" and FUT_PTCP_RE.search(r["form"]):
            vlabel = "fut-act"
        else:
            vlabel = "perf-pass" if (asp == "perfective" and voice == "passive") else \
                     "pres-act" if asp == "imperfective" else f"{asp}-{voice}"
        role = {"nominative": "of-subject", "accusative": "of-object"}.get(case, "other-case")
        pf = vfield(r["lemma"].lower())
        field_sfx = f"|{pf}" if pf else ""
        units.append(("participle", f"ptcp:{vlabel}:{role}{field_sfx}", r["lemma"].lower(), None, r["id"]))

    # --- gerund / gerundive phrases (prospective participles)
    for r in sent:
        fd = r["feats_d"]
        if fd.get("VerbForm") != "participle" or fd.get("Aspect") != "prospective":
            continue
        if fd.get("Voice") == "active":  # future active participle, handled in aci/other
            continue
        if r["deprel"] == "advcl:abs":
            continue
        kids = [by_id[c] for c in children.get(r["id"], [])]
        if any(k["deprel"] in ("aux", "aux:pass", "cop") and k["lemma"].lower() == "sum" for k in kids):
            units.append(("gerundive", "periphrastic(sum)", r["lemma"].lower(), None, r["id"]))
            continue
        case = fd.get("Case")
        prep = next((k["lemma"].lower() for k in kids if k["deprel"] == "case"), None)
        head = by_id.get(r["head"])
        if case == "accusative" and prep == "ad":
            sig = "ad+acc(purpose)"
        elif case == "genitive" and (
            (head and head["lemma"].lower() in ("causa", "gratia"))
            or any(k["lemma"].lower() in ("causa", "gratia") for k in kids)
        ):
            sig = "gen+causa(purpose)"
        elif case == "genitive":
            sig = "genitive(objective)"
        elif case == "ablative" and prep:
            sig = f"{prep}+abl"
        elif case == "ablative":
            sig = "ablative(means)"
        elif case == "dative":
            sig = "dative"
        else:
            sig = f"{case or '?'}"
        units.append(("gerundive", sig, r["lemma"].lower(), None, r["id"]))

    # --- selected case-usage patterns
    for r in sent:
        if r["upos"] != "NOUN":
            continue
        fd = r["feats_d"]
        kids = [by_id[c] for c in children.get(r["id"], [])]
        has_prep = any(k["deprel"] == "case" for k in kids)
        if r["deprel"] == "obl" and fd.get("Case") == "ablative" and not has_prep:
            nf = nfield(r["lemma"].lower())
            sig = f"abl-bare:{nf}" if nf else "abl-bare"
            units.append(("case_usage", sig, r["lemma"].lower(), None, r["id"]))
        elif r["deprel"] in ("obl:arg", "obl") and fd.get("Case") == "dative":
            head = by_id.get(r["head"])
            if head and head["lemma"].lower() == "sum" and head["deprel"] == "root":
                units.append(("case_usage", "dat-possession", r["lemma"].lower(), None, r["id"]))

    return units


# ------------------------------------------------- architecture skeletons

ARCH_LABEL = {
    "cum_clause": "cum", "conditional": "si", "purpose_result": "ut/ne",
    "causal": "quod/quia", "temporal": "temp", "concessive": "conc",
    "comparative": "cmp", "relative": "rel", "indirect_question": "indQ",
    "aci": "AcI", "abl_abs": "AblAbs", "participle": "Ptcp",
    "historic_inf": "HistInf",
}


def skeleton(sent, by_id, children, units):
    root_id = next((r["id"] for r in sent if r["head"] == 0), None)
    if root_id is None:
        return None
    marks = []
    for fam, sig, lex, matrix, head_id in units:
        lab = ARCH_LABEL.get(fam)
        if lab is None or head_id is None:
            continue
        if fam == "conditional":
            lab = sig.split("+")[0]
        if fam == "temporal":
            lab = sig.split("+")[0]
        lo, _ = subtree_span(head_id, children)
        marks.append((lo, lab))
    marks.append((root_id, "MAIN"))
    marks.sort()
    labels = [m[1] for m in marks]
    if len(labels) > 9:
        return None
    non_punct = [r for r in sent if r["upos"] != "PUNCT"]
    vfinal = non_punct and non_punct[-1]["id"] == root_id
    return " · ".join(labels) + (" ‹V-final›" if vfinal else "")


# ------------------------------------------------------------------ main

def main():
    inventory = defaultdict(lambda: defaultdict(lambda: {
        "counts": Counter(), "lex": Counter(), "matrix": Counter(), "examples": defaultdict(list),
    }))
    arch_counts = defaultdict(Counter)
    arch_examples = {}
    totals = {"sentences": Counter(), "words": Counter()}

    # pre-pass: census of lemmas attested with finite forms (see suspicious_inf)
    print("Finite-lemma census...", flush=True)
    for name in TEXTS:
        with open(PARSED_DIR / f"{name}.conllu", encoding="utf-8") as f:
            for line in f:
                if "VerbForm=finite" in line:
                    cols = line.split("\t")
                    if len(cols) > 5 and cols[3] in ("VERB", "AUX"):
                        FINITE_LEMMAS[cols[2].lower()] += 1

    examples_f = open(OUT_DIR / "phrase_examples.jsonl", "w", encoding="utf-8")
    for name in TEXTS:
        print(f"Scanning {name}...", flush=True)
        for meta, sent in parse_conllu_meta(PARSED_DIR / f"{name}.conllu"):
            for r in sent:
                r["feats_d"] = feats_dict(r["feats"])
            by_id, children = build_indices(sent)
            totals["sentences"][name] += 1
            n_words = sum(1 for r in sent if r["upos"] != "PUNCT")
            totals["words"][name] += n_words

            units = extract_units(sent, by_id, children)
            for fam, sig, lex, matrix, head_id in units:
                span = subtree_span(head_id, children) if head_id else None
                unit_html = render(sent, span)
                examples_f.write(json.dumps(
                    {"fam": fam, "sig": sig, "author": name,
                     "sent_id": meta.get("sent_id", ""), "book": meta.get("book", ""),
                     "chapter": meta.get("chapter", ""),
                     "n_words": n_words, "html": unit_html},
                    ensure_ascii=False) + "\n")
                cell = inventory[fam][sig]
                cell["counts"][name] += 1
                if lex:
                    cell["lex"][lex] += 1
                if matrix:
                    cell["matrix"][matrix] += 1
                ex = cell["examples"][name]
                if len(ex) < 6 and (n_words <= 32 or len(ex) < 2):
                    ex.append({"author": name, "n_words": n_words, "html": unit_html})

            sk = skeleton(sent, by_id, children, units)
            if sk:
                arch_counts[sk][name] += 1
                if sk not in arch_examples and n_words <= 40:
                    arch_examples[sk] = {"author": name, "html": render(sent)}
    examples_f.close()

    # ---- write inventory
    out = {"totals": {k: dict(v) for k, v in totals.items()}, "families": {}, "key_map": {}}
    lemma_requests = {"matrix_verbs": Counter(), "unit_verbs": Counter(), "abl_nouns": Counter()}

    for fam in FAM_ORDER:
        sigs = inventory.get(fam, {})
        fam_out = {}
        # Hierarchical merge: a rare field-crossed sig falls back to its
        # structural base (strip the trailing |suffix); bases that are still
        # rare after pooling go to (other).
        totals_by_sig = {sig: sum(cell["counts"].values()) for sig, cell in sigs.items()}
        target1 = {sig: (sig if t >= 25 else sig.split("|")[0])
                   for sig, t in totals_by_sig.items()}
        pooled = Counter()
        for sig, tgt in target1.items():
            pooled[tgt] += totals_by_sig[sig]
        fam_map = {}
        for sig, cell in sorted(sigs.items(), key=lambda kv: -sum(kv[1]["counts"].values())):
            tgt = target1[sig]
            key = tgt if pooled[tgt] >= 25 else f"(other {fam})"
            fam_map[sig] = key
            tgt = fam_out.setdefault(key, {"counts": Counter(), "lex": Counter(),
                                           "matrix": Counter(), "examples": []})
            tgt["counts"].update(cell["counts"])
            tgt["lex"].update(cell["lex"])
            tgt["matrix"].update(cell["matrix"])
            if len(tgt["examples"]) < 24:
                per_author = defaultdict(int)
                for e in tgt["examples"]:
                    per_author[e["author"]] += 1
                for author, exs in cell["examples"].items():
                    for e in exs:
                        if per_author[author] < 3 and len(tgt["examples"]) < 24:
                            tgt["examples"].append(e)
                            per_author[author] += 1
        for key, cell in fam_out.items():
            cell["counts"] = dict(cell["counts"])
            cell["top_lex"] = cell.pop("lex").most_common(15)
            cell["top_matrix"] = cell.pop("matrix").most_common(15)
        out["families"][fam] = fam_out
        out["key_map"][fam] = fam_map

        # collect lemmas for semantic-field classification
        for sig, cell in sigs.items():
            for (lemma, n) in cell["matrix"].most_common(80):
                lemma_requests["matrix_verbs"][lemma] += n
            if fam in ("abl_abs", "participle", "gerundive", "compl_inf", "aci", "historic_inf"):
                for (lex, n) in cell["lex"].most_common(80):
                    lemma_requests["unit_verbs"][lex.split()[-1]] += n
            if fam == "case_usage":
                for (lex, n) in cell["lex"].most_common(200):
                    lemma_requests["abl_nouns"][lex] += n

    with open(OUT_DIR / "phrase_inventory.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    # ---- write architectures
    arch_out = []
    for sk, counts in sorted(arch_counts.items(), key=lambda kv: -sum(kv[1].values()))[:120]:
        arch_out.append({"skeleton": sk, "total": sum(counts.values()),
                         "counts": dict(counts), "example": arch_examples.get(sk)})
    with open(OUT_DIR / "architectures.json", "w", encoding="utf-8") as f:
        json.dump({"totals": {k: dict(v) for k, v in totals.items()},
                   "architectures": arch_out}, f, ensure_ascii=False)

    # ---- write lemma requests (top lists, for the small-model field pass)
    req = {
        "matrix_verbs": [l for l, n in lemma_requests["matrix_verbs"].most_common(400) if n >= 5],
        "unit_verbs": [l for l, n in lemma_requests["unit_verbs"].most_common(400) if n >= 5],
        "abl_nouns": [l for l, n in lemma_requests["abl_nouns"].most_common(300) if n >= 8],
    }
    with open(OUT_DIR / "lemma_requests.json", "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False, indent=1)

    n_sigs = sum(len(v) for v in out["families"].values())
    print(f"\n{n_sigs} fine-grained signatures across {len(out['families'])} families")
    for fam, sigs in out["families"].items():
        top = sorted(sigs.items(), key=lambda kv: -sum(kv[1]["counts"].values()))[:4]
        summary = ", ".join(f"{k}({sum(c['counts'].values())})" for k, c in top)
        print(f"  {fam:20s} {len(sigs):3d} sigs | {summary}")
    print(f"\narchitectures: {len(arch_out)} skeletons kept")
    print(f"lemma requests: { {k: len(v) for k, v in req.items()} }")


if __name__ == "__main__":
    main()
