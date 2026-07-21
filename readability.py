"""Compute reading-difficulty metrics per author from the parsed CoNLL-U
corpus: sentence length, dependency distance, non-projectivity (hyperbaton),
subordination, tree depth, and lexical rarity.
"""
import json
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path

# LatinCy parses (parsed_latincy/) are the default; set PARSED_DIR=parsed in
# the environment to analyze the legacy CLTK parses instead.
PARSED_DIR = Path("/Users/mimno/Documents/Data/LatinHistorians") / os.environ.get(
    "PARSED_DIR", "parsed_latincy")
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

CLAUSAL_DEPRELS = {"advcl", "acl", "acl:relcl", "ccomp", "csubj", "csubj:pass", "xcomp"}
CONTENT_UPOS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN"}


def parse_conllu(path):
    """Yield one sentence (list of row-dicts) at a time."""
    sentence = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                if sentence:
                    yield sentence
                sentence = []
                continue
            if line.startswith("#"):
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
        yield sentence


def sentence_metrics(sent):
    ids = {r["id"] for r in sent}
    n_tokens = len(sent)
    n_words = sum(1 for r in sent if r["upos"] != "PUNCT")

    distances = []
    edges = []
    root_id = None
    children = defaultdict(list)
    for r in sent:
        if r["head"] == 0:
            root_id = r["id"]
            continue
        if r["head"] not in ids:
            # Defensive: a rare upstream CLTK bug (dropped MWT enclitic,
            # ~4 sentences in the whole 73k-sentence corpus) can leave a
            # dangling head reference; skip just that edge.
            continue
        distances.append(abs(r["id"] - r["head"]))
        edges.append((min(r["id"], r["head"]), max(r["id"], r["head"])))
        children[r["head"]].append(r["id"])

    # Non-projectivity: count pairs of edges whose spans partially overlap
    # ("cross") rather than nest or stay disjoint -- the standard signature
    # of a discontinuous constituent (hyperbaton).
    crossing_pairs = 0
    n = len(edges)
    for i in range(n):
        a1, b1 = edges[i]
        for j in range(i + 1, n):
            a2, b2 = edges[j]
            if (a1 < a2 < b1 < b2) or (a2 < a1 < b2 < b1):
                crossing_pairs += 1

    # Max tree depth via BFS from the root.
    depth = 0
    if root_id is not None:
        frontier = [root_id]
        visited = {root_id}
        while True:
            next_frontier = [c for node in frontier for c in children.get(node, []) if c not in visited]
            if not next_frontier:
                break
            visited.update(next_frontier)
            frontier = next_frontier
            depth += 1

    n_clausal = sum(1 for r in sent if r["deprel"] in CLAUSAL_DEPRELS)
    n_sconj = sum(1 for r in sent if r["upos"] == "SCONJ")

    return {
        "n_tokens": n_tokens,
        "n_words": n_words,
        "distances": distances,
        "n_edges": n,
        "crossing_pairs": crossing_pairs,
        "has_nonproj": crossing_pairs > 0,
        "tree_depth": depth,
        "n_clausal": n_clausal,
        "n_sconj": n_sconj,
    }


def analyze_text(name):
    sentences = []
    lemma_counts = Counter()
    for sent in parse_conllu(PARSED_DIR / f"{name}.conllu"):
        m = sentence_metrics(sent)
        sentences.append(m)
        for r in sent:
            if r["upos"] in CONTENT_UPOS:
                lemma_counts[r["lemma"].lower()] += 1
    return sentences, lemma_counts


def summarize(name, sentences, lemma_counts, other_lemma_counts):
    n_sent = len(sentences)
    words_per_sent = [s["n_words"] for s in sentences]
    all_distances = [d for s in sentences for d in s["distances"]]
    depths = [s["tree_depth"] for s in sentences]
    total_words = sum(words_per_sent)
    total_sconj = sum(s["n_sconj"] for s in sentences)
    total_clausal = sum(s["n_clausal"] for s in sentences)
    total_edges = sum(s["n_edges"] for s in sentences)
    total_crossing_pairs = sum(s["crossing_pairs"] for s in sentences)
    n_nonproj_sent = sum(1 for s in sentences if s["has_nonproj"])

    # Lexical rarity against a leave-one-out reference (all other 7 authors).
    other_total = sum(other_lemma_counts.values())
    content_tokens = sum(lemma_counts.values())
    hapax_tokens = 0
    log_freqs = []
    for lemma, count in lemma_counts.items():
        ref_count = other_lemma_counts.get(lemma, 0)
        if ref_count == 0:
            hapax_tokens += count
            # Assign a floor frequency of 0.5 occurrences for a well-defined log.
            freq_per_million = 0.5 / other_total * 1_000_000
        else:
            freq_per_million = ref_count / other_total * 1_000_000
        import math

        log_freqs.extend([math.log10(freq_per_million)] * count)

    return {
        "name": name,
        "n_sentences": n_sent,
        "n_words": total_words,
        "mean_words_per_sentence": statistics.mean(words_per_sent),
        "median_words_per_sentence": statistics.median(words_per_sent),
        "p90_words_per_sentence": statistics.quantiles(words_per_sent, n=10)[8],
        "mean_dependency_distance": statistics.mean(all_distances),
        "mean_tree_depth": statistics.mean(depths),
        "p90_tree_depth": statistics.quantiles(depths, n=10)[8],
        "sconj_per_100_words": 100 * total_sconj / total_words,
        "clausal_deps_per_100_words": 100 * total_clausal / total_words,
        "mean_clausal_per_sentence": total_clausal / n_sent,
        "nonprojective_sentence_pct": 100 * n_nonproj_sent / n_sent,
        "crossing_pairs_per_100_edges": 100 * total_crossing_pairs / total_edges,
        "mean_log_lemma_freq": statistics.mean(log_freqs),
        "hapax_rate_pct": 100 * hapax_tokens / content_tokens,
    }


def main():
    per_text_sentences = {}
    per_text_lemmas = {}
    for name in TEXTS:
        print(f"Analyzing {name}...", flush=True)
        sentences, lemma_counts = analyze_text(name)
        per_text_sentences[name] = sentences
        per_text_lemmas[name] = lemma_counts

    results = []
    for name in TEXTS:
        other_counts = Counter()
        for other_name, counts in per_text_lemmas.items():
            if other_name != name:
                other_counts.update(counts)
        summary = summarize(name, per_text_sentences[name], per_text_lemmas[name], other_counts)
        results.append(summary)

    out_path = Path("/Users/mimno/Documents/Data/LatinHistorians/readability_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {out_path}")

    for r in results:
        print(
            f"{r['name']:16s} words/sent={r['mean_words_per_sentence']:.1f} "
            f"dep_dist={r['mean_dependency_distance']:.2f} "
            f"tree_depth={r['mean_tree_depth']:.2f} "
            f"nonproj%={r['nonprojective_sentence_pct']:.1f} "
            f"sconj/100w={r['sconj_per_100_words']:.2f} "
            f"clausal/sent={r['mean_clausal_per_sentence']:.2f} "
            f"log_freq={r['mean_log_lemma_freq']:.2f} "
            f"hapax%={r['hapax_rate_pct']:.1f}"
        )


if __name__ == "__main__":
    main()
