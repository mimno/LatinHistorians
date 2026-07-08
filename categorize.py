"""Detect classic Latin syntactic constructions and stylistic/complexity
phenomena in the parsed corpus, for a browsable examples display.
"""
import json
import random
from collections import defaultdict
from pathlib import Path

from readability import CLAUSAL_DEPRELS, PARSED_DIR, TEXTS, parse_conllu

random.seed(0)

CATEGORY_INFO = {
    "abl_absolute": ("Ablative Absolute", "A participle + noun/pronoun pair, both ablative, standing free of the main clause (e.g. \"his rebus gestis\")."),
    "aci": ("Indirect Statement (AcI)", "An infinitive with its own accusative subject, the standard Latin way to report speech or thought."),
    "cum_causal": ("Cum + Subjunctive (circumstantial/causal)", "\"Cum\" introducing a subjunctive clause -- \"since/although/when\" with an implied causal or circumstantial link."),
    "cum_temporal": ("Cum + Indicative (temporal)", "\"Cum\" simply dating an event -- \"when X happened\", indicative mood."),
    "purpose_result": ("Purpose/Result Clause (ut/ne)", "\"Ut\" or \"ne\" introducing a subjunctive clause of purpose (\"in order to\") or result (\"so that\")."),
    "relative_clause": ("Relative Clause", "A clause attached to a noun via a relative pronoun (qui, quae, quod...)."),
    "indirect_question": ("Indirect Question", "A subordinate question (introduced by an interrogative word) with its verb in the subjunctive."),
    "gerundive_periphrastic": ("Passive Periphrastic (Gerundive of Obligation)", "Gerundive + a form of \"sum\", expressing necessity: \"must be done\". Caveat: this tagset marks gerunds (verbal nouns, e.g. \"pugnandi\") the same way as gerundives, so a few genitive/ablative gerunds slip in alongside true gerundives here."),
    "gerundive_other": ("Gerundive (purpose/attributive)", "A gerundive used adjectivally or in a purpose expression, without \"sum\". Same gerund/gerundive caveat as above applies."),
    "conditional_real": ("Conditional Clause -- indicative (\"real\")", "\"Si/nisi\" + indicative: a straightforward factual condition."),
    "conditional_ideal": ("Conditional Clause -- subjunctive (\"ideal/unreal\")", "\"Si/nisi\" + subjunctive: a hypothetical, potential, or contrary-to-fact condition."),
    "direct_speech": ("Direct Speech", "A sentence containing quoted dialogue or an oration."),
    "long_sentence": ("Longest Sentences", "The longest sentences (by word count) for this author."),
    "hyperbaton": ("Most Hyperbatic (scrambled word order)", "Sentences with the most dependency arcs that cross one another -- discontinuous phrases, a hallmark of elevated/artful Latin word order."),
}

INTERROGATIVE_LEMMAS = {"num", "utrum", "an", "cur", "quare", "quomodo", "quando", "quantus", "qualis", "uter"}


def build_indices(sent):
    by_id = {r["id"]: r for r in sent}
    children = defaultdict(list)
    for r in sent:
        if r["head"] != 0 and r["head"] in by_id:
            children[r["head"]].append(r["id"])
    return by_id, children


def subtree_span(token_id, children):
    ids = {token_id}
    frontier = [token_id]
    while frontier:
        nxt = []
        for node in frontier:
            for c in children.get(node, []):
                if c not in ids:
                    ids.add(c)
                    nxt.append(c)
        frontier = nxt
    return min(ids), max(ids)


def feats_dict(feats_str):
    if feats_str == "_" or not feats_str:
        return {}
    out = {}
    for kv in feats_str.split("|"):
        k, v = kv.split("=", 1)
        out[k] = v
    return out


def find_categories(sent):
    """Return list of (category_key, head_token_id) for one sentence's rows
    (each row augmented with a 'feats_d' dict for convenience)."""
    for r in sent:
        r["feats_d"] = feats_dict(r["feats"])
    by_id, children = build_indices(sent)
    matches = []

    for r in sent:
        fd = r["feats_d"]

        if r["deprel"] == "advcl:abs":
            matches.append(("abl_absolute", r["id"]))

        if (
            r["upos"] == "VERB"
            and fd.get("VerbForm") == "infinitive"
            and r["deprel"] in ("ccomp", "xcomp")
        ):
            for c in children.get(r["id"], []):
                cr = by_id[c]
                if cr["deprel"] == "nsubj":
                    matches.append(("aci", r["id"]))
                    break

        if r["deprel"] == "mark" and r["lemma"].lower() == "cum":
            head = by_id.get(r["head"])
            if head and head["deprel"] in CLAUSAL_DEPRELS | {"advcl"}:
                mood = head["feats_d"].get("Mood")
                if mood == "subjunctive":
                    matches.append(("cum_causal", r["head"]))
                elif mood == "indicative":
                    matches.append(("cum_temporal", r["head"]))

        if r["deprel"] == "mark" and r["lemma"].lower() in ("ut", "ne"):
            head = by_id.get(r["head"])
            if head and head["feats_d"].get("Mood") == "subjunctive" and head["deprel"] in ("advcl", "ccomp"):
                matches.append(("purpose_result", r["head"]))

        if r["deprel"] in ("acl:relcl", "csubj:relcl", "ccomp:relcl"):
            matches.append(("relative_clause", r["id"]))

        if r["deprel"] == "mark" and r["lemma"].lower() in ("si", "nisi", "sin"):
            head = by_id.get(r["head"])
            if head and head["deprel"] == "advcl":
                mood = head["feats_d"].get("Mood")
                if mood == "indicative":
                    matches.append(("conditional_real", r["head"]))
                elif mood == "subjunctive":
                    matches.append(("conditional_ideal", r["head"]))

        if (
            fd.get("VerbForm") == "participle"
            and fd.get("Aspect") == "prospective"
            and fd.get("Voice") == "passive"
        ):
            has_copula = any(
                by_id[c]["deprel"] in ("cop", "aux", "aux:pass") and by_id[c]["lemma"].lower() == "sum"
                for c in children.get(r["id"], [])
            )
            matches.append(("gerundive_periphrastic" if has_copula else "gerundive_other", r["id"]))

    # Indirect question: a ccomp verb in the subjunctive with an interrogative descendant.
    for r in sent:
        if r["deprel"] == "ccomp" and r["feats_d"].get("Mood") == "subjunctive":
            _, hi = subtree_span(r["id"], children)
            lo, _ = subtree_span(r["id"], children)
            has_interrogative = False
            for c_id in range(lo, hi + 1):
                cr = by_id.get(c_id)
                if cr and (
                    cr["feats_d"].get("PronominalType") == "interrogative"
                    or cr["lemma"].lower() in INTERROGATIVE_LEMMAS
                ):
                    has_interrogative = True
                    break
            if has_interrogative:
                matches.append(("indirect_question", r["id"]))

    if any(r["form"] in ('"', "'") for r in sent):
        matches.append(("direct_speech", None))

    return matches, by_id, children


def render_sentence(sent, by_id, highlight_span=None):
    """Join tokens into a display string, wrapping the highlighted span (a
    (min_id, max_id) tuple of token ids) in a single <mark>...</mark>."""
    out = []
    open_mark = False
    for r in sent:
        in_span = highlight_span is not None and highlight_span[0] <= r["id"] <= highlight_span[1]
        if in_span and not open_mark:
            out.append("<mark>")
            open_mark = True
        elif not in_span and open_mark:
            out.append("</mark>")
            open_mark = False
        out.append(r["form"])
        out.append(" ")
    if open_mark:
        out.append("</mark>")
    text = "".join(out).strip()
    for p in [",", ".", ";", ":", "!", "?"]:
        text = text.replace(" " + p, p)
    return text


def analyze_all():
    per_category = defaultdict(list)  # category_key -> list of example dicts
    counts = defaultdict(lambda: defaultdict(int))  # category_key -> author -> count
    total_sentences = defaultdict(int)
    total_words = defaultdict(int)

    for name in TEXTS:
        print(f"Scanning {name}...", flush=True)
        for sent in parse_conllu(PARSED_DIR / f"{name}.conllu"):
            total_sentences[name] += 1
            total_words[name] += sum(1 for r in sent if r["upos"] != "PUNCT")
            matches, by_id, children = find_categories(sent)
            if not matches:
                continue
            text_plain = " ".join(r["form"] for r in sent)
            seen_this_sentence = set()
            for cat_key, head_id in matches:
                counts[cat_key][name] += 1
                if cat_key in seen_this_sentence:
                    continue  # avoid many near-duplicate examples from one very busy sentence
                seen_this_sentence.add(cat_key)
                span = subtree_span(head_id, children) if head_id is not None else None
                per_category[cat_key].append(
                    {
                        "author": name,
                        "n_words": sum(1 for r in sent if r["upos"] != "PUNCT"),
                        "html": render_sentence(sent, by_id, span),
                        "plain": text_plain,
                    }
                )

            # complexity-based categories computed alongside
            n_words = sum(1 for r in sent if r["upos"] != "PUNCT")
            per_category["long_sentence"].append(
                {"author": name, "n_words": n_words, "html": render_sentence(sent, by_id, None), "plain": text_plain}
            )
            edges = []
            for r in sent:
                if r["head"] != 0 and r["head"] in by_id:
                    edges.append((min(r["id"], r["head"]), max(r["id"], r["head"])))
            crossing = 0
            worst_pair = None
            for i in range(len(edges)):
                for j in range(i + 1, len(edges)):
                    a1, b1 = edges[i]
                    a2, b2 = edges[j]
                    if (a1 < a2 < b1 < b2) or (a2 < a1 < b2 < b1):
                        crossing += 1
                        span = (min(a1, a2, b1, b2), max(a1, a2, b1, b2))
                        if worst_pair is None or (span[1] - span[0]) > (worst_pair[1] - worst_pair[0]):
                            worst_pair = span
            if crossing > 0:
                counts["hyperbaton"][name] += 1
                per_category["hyperbaton"].append(
                    {
                        "author": name,
                        "n_words": n_words,
                        "crossing_pairs": crossing,
                        "html": render_sentence(sent, by_id, worst_pair),
                        "plain": text_plain,
                    }
                )

    return per_category, counts, total_sentences, total_words


def main():
    per_category, counts, total_sentences, total_words = analyze_all()

    # For counting purposes we recorded every match above; for grammar
    # categories that's a per-sentence count already (deduped per sentence).
    for name in TEXTS:
        counts["long_sentence"][name] = total_sentences[name]

    output = {"categories": {}, "totals": {"sentences": total_sentences, "words": total_words}}

    for cat_key, (label, desc) in CATEGORY_INFO.items():
        examples = per_category.get(cat_key, [])
        if cat_key == "long_sentence":
            sample = []
            for name in TEXTS:
                author_examples = sorted([e for e in examples if e["author"] == name], key=lambda e: -e["n_words"])[:15]
                sample.extend(author_examples)
        elif cat_key == "hyperbaton":
            sample = []
            for name in TEXTS:
                author_examples = sorted(
                    [e for e in examples if e["author"] == name], key=lambda e: -e["crossing_pairs"]
                )[:15]
                sample.extend(author_examples)
        else:
            # Random sample capped per author for manageable file size.
            sample = []
            for name in TEXTS:
                author_examples = [e for e in examples if e["author"] == name]
                random.shuffle(author_examples)
                sample.extend(author_examples[:20])

        output["categories"][cat_key] = {
            "label": label,
            "description": desc,
            "counts_by_author": dict(counts[cat_key]),
            "examples": sample,
        }
        n_total = sum(counts[cat_key].values()) if cat_key != "long_sentence" else sum(total_sentences.values())
        print(f"{label:55s} total={n_total:6d} sampled={len(sample)}")

    out_path = Path("/Users/mimno/Documents/Data/LatinHistorians/categories_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
