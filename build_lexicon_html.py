"""Render phrase_inventory.json + architectures.json (+ optional
cluster_notes.json with small-model example translations) into a single
self-contained browsable HTML page: phrase_lexicon.html.

Display names for signatures are generated from templates here, so they are
deterministic and grammatically conventional; the model contributes only
translations / reader notes.
"""
import hashlib
import html
import json
import re
from collections import defaultdict
from pathlib import Path

DIR = Path("/Users/mimno/Documents/Data/LatinHistorians")
SITE_DIR = DIR / "docs"          # served by GitHub Pages (main branch, /docs)
EX_DIR = SITE_DIR / "examples"


def slug(fam, sig):
    base = re.sub(r"[^a-z0-9]+", "-", f"{fam}-{sig}".lower()).strip("-")
    h = hashlib.md5(f"{fam}|{sig}".encode()).hexdigest()[:6]
    return f"{base}-{h}"

AUTHOR_ORDER = ["caesar", "sallust", "livy", "curtius", "tacitus", "suetonius", "ammianus", "historiaaugusta"]
AUTHOR_LABEL = {
    "caesar": "Caesar", "sallust": "Sallust", "livy": "Livy", "curtius": "Curtius",
    "tacitus": "Tacitus", "suetonius": "Suetonius", "ammianus": "Ammianus",
    "historiaaugusta": "Hist. Augusta",
}

TENSE = {"pres": "present", "impf": "imperfect", "perf": "perfect", "plup": "pluperfect",
         "fut": "future", "futperf": "future perfect", "?": "(tense unclear)"}
MOOD = {"ind": "indicative", "subj": "subjunctive", "imper": "imperative"}
FIELD_NAME = {
    "say": "speech", "think": "cognition", "perceive": "perception", "command": "commanding/urging",
    "fear": "fearing", "wish": "wishing/striving", "modal": "ability/obligation/phase",
    "happen": "happening/resulting", "motion": "motion", "war": "war & violence",
    "give": "giving/taking", "do": "doing/accomplishing", "emotion": "emotion", "be": "being/remaining",
    "time": "time", "place": "place", "military": "military", "body": "body",
    "speech": "speech & writing", "person": "persons", "abstract": "abstract", "other": "miscellaneous",
}

FAMILY_INFO = {
    "cum_clause": ("Cum-clauses", "The subordinator cum with every mood/tense combination. Indicative cum dates an event; subjunctive cum gives attendant circumstances, cause, or concession, with tense following the sequence-of-tenses rule."),
    "conditional": ("Conditionals", "Si / nisi / ni / sin / sive protases, split by mood and tense — the mood-and-tense combination is what tells a reader whether a condition is open, future, or contrary to fact."),
    "purpose_result": ("Ut / ne clauses (purpose, result, command, fear)", "Subjunctive clauses in ut, ne, quo, quin, quominus. Subtypes are resolved from the matrix verb's semantic field and from correlatives (ita, adeo, tam ... ut = result)."),
    "causal": ("Causal & substantive quod-clauses", "Quod, quia, quoniam, quippe. Indicative gives the narrator's own reason; subjunctive marks an alleged or reported reason. Quod as subject/object clause = 'the fact that'."),
    "temporal": ("Temporal clauses", "Postquam, ubi, dum, donec, priusquam, antequam... Note dum + present indicative ('while', even in past narrative) vs. dum/donec + subjunctive ('until', anticipatory)."),
    "concessive": ("Concessive clauses", "Quamquam (usually indicative), quamvis / licet (subjunctive), etsi."),
    "comparative": ("Comparative clauses", "Ut + indicative ('as'), sicut, velut, tamquam, quasi, quam. Tamquam/quasi + subjunctive present a comparison as imagined or alleged."),
    "relative": ("Relative clauses", "Split by the case and grammatical role of the relative pronoun and by mood — a subjunctive relative clause expresses characteristic, purpose, or cause."),
    "rel_connective": ("Connecting relative", "A sentence-initial relative pronoun linking back to the previous sentence (quod ubi audivit... = 'when he heard this'). A hallmark of periodic historical prose."),
    "indirect_question": ("Indirect questions", "A question word + subjunctive after a verb of asking, knowing, or wondering. The subjunctive tense encodes sequence of tenses."),
    "aci": ("Accusative + infinitive (indirect statement)", "An infinitive with its own accusative subject after verbs of saying, thinking, perceiving. Infinitive tense is relative: present = same time, perfect = earlier, future = later. '+se' = reflexive subject (he said that he himself...)."),
    "compl_inf": ("Complementary infinitive", "A bare infinitive completing a matrix verb (possum, volo, coepi, conor...), grouped by the matrix verb's semantic field."),
    "historic_inf": ("Historic infinitive", "An infinitive used as a main-clause narrative verb ('trepidare, festinare' = they rushed about, they hurried) — a rapid-narration mannerism beloved of Sallust and Tacitus."),
    "abl_abs": ("Ablative absolute", "Participle + noun in the ablative, detached from the main clause. Sub-grouped by participle type, sentence-initial position (the classic scene-setter), and the participle's semantic field."),
    "participle": ("Participium coniunctum", "A participle agreeing with a noun of the main clause and carrying its own clause-like content — the single most Latin way to pack two events into one sentence."),
    "gerundive": ("Gerund & gerundive phrases", "Grouped by case frame: ad + accusative (purpose), genitive + causa (purpose), objective genitive, bare ablative (means), and the passive periphrastic with sum (obligation)."),
    "case_usage": ("Bare-case usage: the plain ablative", "Ablative nouns with no preposition, grouped by the noun's semantic field — time nouns give ablative of time, abstract nouns manner/means, place nouns place/route."),
}

FAM_ORDER = list(FAMILY_INFO)

SIG_NOTE = {
    "cum+subj.impf": "The workhorse narrative cum: 'when/since X was happening'.",
    "cum+subj.plup": "'When X had happened' — backgrounded prior event.",
    "cum+ind.pres": "Purely temporal cum, often generalizing.",
    "dum+ind.pres": "Dum keeps the present indicative even in past narrative: 'while this was going on'.",
    "priusquam+subj": "Anticipatory: 'before X could happen'.",
    "antequam+subj": "Anticipatory: 'before X could happen'.",
    "quod+subj": "Subjunctive quod: a reason reported or alleged, not vouched for by the narrator.",
    "tamquam+subj": "Presented as imagined or alleged ('as if').",
    "quasi+subj": "Presented as imagined or alleged ('as if').",
}

COND_NOTE = {
    ("si", "subj.plup"): "past contrary-to-fact ('if X had happened...')",
    ("si", "subj.impf"): "present contrary-to-fact ('if X were now the case...')",
    ("si", "subj.pres"): "future less vivid ('should X happen...')",
    ("si", "ind.futperf"): "future more vivid, future-perfect protasis",
    ("si", "ind.fut"): "future more vivid",
}

PR_SUBTYPE = {
    "purpose": "purpose clause",
    "result": "result clause",
    "indirect-command": "indirect command",
    "fear-clause": "fear clause (ne = 'that')",
    "result-substantive": "substantive result (accidit/efficitur ut)",
    "adv": "adverbial", "comp": "complement",
}


def moodtense(mt):
    nominal = mt.startswith("nom+")
    if nominal:
        mt = mt[4:]
    if mt == "inf":
        return "infinitive"
    parts = mt.split(".")
    s = f"{TENSE.get(parts[1], parts[1])} {MOOD.get(parts[0], parts[0])}" if len(parts) == 2 else mt
    return s + (" (nominal predicate)" if nominal else "")


def describe(fam, sig):
    """(name, note) for a signature key."""
    note = ""
    for prefix, n in SIG_NOTE.items():
        if sig.startswith(prefix):
            note = n
    if sig.startswith("(other"):
        return ("Rarer patterns (merged)", "Signatures with fewer than 25 corpus hits.")

    if fam in ("cum_clause", "conditional", "causal", "temporal", "concessive", "comparative"):
        marker, _, rest = sig.partition("+")
        name = f"{marker} + {moodtense(rest)}"
        if fam == "conditional":
            key = (marker if marker == "si" else "si",
                   rest if not rest.startswith("nom+") else rest[4:])
            if marker == "si" and key in COND_NOTE:
                note = COND_NOTE[key]
        if sig.startswith("quod-substantive"):
            name = f"quod ('the fact that') + {moodtense(rest)}"
        return (name, note)

    if fam == "purpose_result":
        core, _, subtype = sig.partition("|")
        marker, _, mt = core.partition("+")
        sub = PR_SUBTYPE.get(subtype, subtype)
        return (f"{marker} + {moodtense(mt)} — {sub}", note)

    if fam == "relative":
        # qui[nom:nsubj]+ind or +subj.impf
        inner = sig[sig.index("[") + 1:sig.index("]")]
        case, _, role = inner.partition(":")
        _, _, mood = sig.partition("]+")
        role_lbl = {"nsubj": "subject", "nsubj:pass": "subject (passive)", "obj": "object",
                    "obl": "oblique", "obl:arg": "oblique argument", "nmod": "possessive",
                    "det": "adjectival"}.get(role, role)
        casename = {"nom": "nominative", "acc": "accusative", "abl": "ablative",
                    "gen": "genitive", "dat": "dative"}.get(case, case)
        if mood == "ind":
            name = f"qui {casename} as {role_lbl} + indicative"
        else:
            name = f"qui {casename} as {role_lbl} + {moodtense(mood)}"
            note = note or "Subjunctive relative: characteristic, purpose, or cause."
        return (name, note)

    if fam == "rel_connective":
        if "+" in sig:
            pron, _, follower = sig.partition("+")
            return (f"Sentence-initial {pron} + {follower}", f"e.g. '{pron} {follower}...' — 'and when/since ... this'")
        return (f"Sentence-initial {sig}", note)

    if fam == "indirect_question":
        wh, _, mt = sig.partition("+")
        return (f"{wh} + {moodtense(mt)}", note)

    if fam == "aci":
        core, _, after = sig.partition("|")
        bits = core.split(".")
        tense = TENSE.get(bits[1].split("+")[0], bits[1])
        passive = ".pass" in core
        refl = "+se" in core
        name = f"{tense} infinitive"
        if passive:
            name += " (passive/deponent)"
        if refl:
            name += ", reflexive subject (se ... )"
        if after:
            name += f" after a verb of {FIELD_NAME.get(after.replace('after-', ''), after)}"
        return (name, note)

    if fam == "compl_inf":
        f = sig.replace("inf-after-", "")
        if f == "matrix-verb+inf":
            return ("infinitive after unclassified verb", note)
        return (f"infinitive after a verb of {FIELD_NAME.get(f, f)}", note)

    if fam == "historic_inf":
        _, _, f = sig.partition("|")
        return (f"historic infinitive — verbs of {FIELD_NAME.get(f, f)}" if f else "historic infinitive", note)

    if fam == "abl_abs":
        body = sig.replace("ablabs:", "")
        body, _, f = body.partition("|")
        initial = "+initial" in body
        body = body.replace("+initial", "")
        sub = {"perf-pass": "perfect passive participle", "pres-act": "present active participle",
               "verbless": "verbless (noun + noun/adjective)", "gerundive": "gerundive"}.get(body, body)
        name = sub
        if f:
            name += f", verb of {FIELD_NAME.get(f, f)}"
        if initial:
            name += " — sentence-initial"
            note = note or "The classic scene-setting opener."
        return (name, note)

    if fam == "participle":
        body = sig.replace("ptcp:", "")
        body, _, f = body.partition("|")
        parts = body.split(":")
        vlab = {"perf-pass": "perfect passive", "pres-act": "present active",
                "fut-act": "future active"}.get(parts[0], parts[0])
        role = {"of-subject": "agreeing with the subject", "of-object": "agreeing with the object",
                "other-case": "in an oblique case"}.get(parts[1], parts[1])
        name = f"{vlab} participle {role}"
        if f:
            name += f", verb of {FIELD_NAME.get(f, f)}"
        return (name, note)

    if fam == "gerundive":
        names = {
            "periphrastic(sum)": ("passive periphrastic (gerundive + sum): obligation", "'must be done'"),
            "ad+acc(purpose)": ("ad + accusative gerund(ive): purpose", "'ad urbem capiendam' = to take the city"),
            "gen+causa(purpose)": ("genitive gerund(ive) + causa/gratia: purpose", ""),
            "genitive(objective)": ("objective genitive gerund(ive)", "'cupiditas bellandi' = desire of waging war"),
            "ablative(means)": ("bare ablative gerund(ive): means", "'pugnando' = by fighting"),
            "dative": ("dative gerund(ive)", ""),
        }
        if sig in names:
            return names[sig]
        return (sig.replace("+", " + "), note)

    if fam == "case_usage":
        f = sig.replace("abl-bare:", "").replace("abl-bare", "")
        if f:
            hint = {"time": "ablative of time when/within", "place": "ablative of place/route",
                    "abstract": "ablative of manner, means, or respect",
                    "military": "ablative of means or accompaniment (military)",
                    "body": "ablative of means (body parts)", "speech": "ablative of means (speech acts)",
                    "person": "ablative of accompaniment/agent-like uses"}.get(f, "")
            return (f"bare ablative — {FIELD_NAME.get(f, f)} nouns", hint)
        return ("bare ablative (unclassified nouns)", "")

    return (sig, note)


def freq_bars(counts, totals):
    """Per-author frequency (per 1000 sentences) as small HTML bars."""
    per1k = {a: 1000 * counts.get(a, 0) / totals["sentences"][a] for a in AUTHOR_ORDER}
    mx = max(per1k.values()) or 1
    cells = []
    for a in AUTHOR_ORDER:
        v = per1k[a]
        pct = 100 * v / mx
        cells.append(
            f'<div class="fb"><span class="fb-a">{AUTHOR_LABEL[a]}</span>'
            f'<span class="fb-bar"><span style="width:{pct:.0f}%"></span></span>'
            f'<span class="fb-v">{v:.1f}</span></div>'
        )
    return '<div class="fbs">' + "".join(cells) + "</div>"


def main():
    inv = json.loads((DIR / "phrase_inventory.json").read_text())
    arch = json.loads((DIR / "architectures.json").read_text())
    notes_path = DIR / "cluster_notes.json"
    notes = json.loads(notes_path.read_text()) if notes_path.exists() else {}

    totals = inv["totals"]
    parts = []
    toc = []

    fam_totals = {fam: sum(sum(c["counts"].values()) for c in inv["families"].get(fam, {}).values())
                  for fam in FAM_ORDER}
    for fam in sorted(FAM_ORDER, key=lambda f: -fam_totals[f]):
        sigs = inv["families"].get(fam, {})
        if not sigs:
            continue
        label, desc = FAMILY_INFO[fam]
        fam_total = fam_totals[fam]
        toc.append(f'<a href="#{fam}">{html.escape(label)} <span class="n">{len(sigs)}</span></a>')
        parts.append(f'<section id="{fam}"><h2>{html.escape(label)}'
                     f' <span class="fam-n">{fam_total:,} instances · {len(sigs)} patterns</span></h2>'
                     f'<p class="fam-desc">{html.escape(desc)}</p>')

        ordered = sorted(sigs.items(), key=lambda kv: -sum(kv[1]["counts"].values()))
        for sig, cell in ordered:
            total = sum(cell["counts"].values())
            name, gnote = describe(fam, sig)
            note = notes.get(f"{fam}|{sig}", {})
            tr = note.get("translation", "")
            if tr:
                tr = html.escape(tr)
                # **span** -> <mark>, alternating
                while "**" in tr:
                    tr = tr.replace("**", "<mark>", 1).replace("**", "</mark>", 1)
            # shortest example first: it is the one the translation renders
            exx = sorted(cell["examples"], key=lambda e: e["n_words"])[:6]
            ex_html = []
            for i, e in enumerate(exx):
                tr_line = f'<div class="tr">→ {tr}</div>' if (i == 0 and tr) else ""
                ex_html.append(f'<li><span class="au">{AUTHOR_LABEL.get(e["author"], e["author"])}</span> '
                               f'{e["html"]}{tr_line}</li>')
            rd_note = note.get("note", "")
            lex = ", ".join(f"<i>{html.escape(l)}</i>&thinsp;×{n}" for l, n in cell.get("top_lex", [])[:8])
            mtx = ", ".join(f"<i>{html.escape(l)}</i>&thinsp;×{n}" for l, n in cell.get("top_matrix", [])[:8])
            parts.append(f"""
<details class="sig">
 <summary><span class="sig-name">{html.escape(name)}</span>
  <code class="sig-key">{html.escape(sig)}</code>
  <span class="sig-n">{total:,}</span></summary>
 <div class="sig-body">
  {f'<p class="gnote">{html.escape(gnote)}</p>' if gnote else ''}
  {f'<p class="rnote">{html.escape(rd_note)}</p>' if rd_note else ''}
  {freq_bars(cell["counts"], totals)}
  {f'<p class="lex"><b>Typical words:</b> {lex}</p>' if lex else ''}
  {f'<p class="lex"><b>Matrix verbs:</b> {mtx}</p>' if mtx else ''}
  <ul class="exx">{''.join(ex_html)}</ul>
  <p class="all-ex"><a href="examples/{slug(fam, sig)}.html">all {total:,} examples →</a></p>
 </div>
</details>""")
        parts.append("</section>")

    # architectures
    toc.append('<a href="#arch">Sentence architectures</a>')
    parts.append('<section id="arch"><h2>Sentence architectures</h2>'
                 '<p class="fam-desc">The most frequent whole-sentence clause skeletons: the linear '
                 'order of subordinate units around the main verb (MAIN). ‹V-final› marks a '
                 'verb-final main clause. <b>Total</b> is the raw number of sentences with that '
                 'skeleton in the whole corpus. The per-author columns are <b>rates, not counts</b>: '
                 'sentences per 1,000 of that author\'s sentences (each author\'s whole text counts '
                 'once — there is no averaging over books). Rates are used because corpus sizes are '
                 'wildly unequal (Sallust 2,075 sentences, Livy 32,481), so raw counts would mostly '
                 'measure text length; a value of 12.3 means about 1.2% of that author\'s sentences '
                 'follow the skeleton. Frequencies differ strikingly between the paratactic and the '
                 'periodic historians.</p><table class="arch">'
                 f'<tr><th></th><th></th><th colspan="{len(AUTHOR_ORDER)}" class="grp">'
                 'sentences per 1,000, by author</th></tr>'
                 '<tr><th>skeleton</th><th>total</th>'
                 + "".join(f"<th>{AUTHOR_LABEL[a][:4]}</th>" for a in AUTHOR_ORDER) + "</tr>")
    for a in arch["architectures"][:80]:
        counts = a["counts"]
        cells = "".join(
            f"<td>{1000 * counts.get(au, 0) / totals['sentences'][au]:.1f}</td>" for au in AUTHOR_ORDER)
        ex = a.get("example")
        ex_row = (f'<tr class="arch-ex"><td colspan="{2 + len(AUTHOR_ORDER)}">'
                  f'<span class="au">{AUTHOR_LABEL.get(ex["author"], "")}</span> {ex["html"]}</td></tr>'
                  if ex else "")
        parts.append(f'<tr><td class="sk">{html.escape(a["skeleton"])}</td>'
                     f'<td>{a["total"]:,}</td>{cells}</tr>{ex_row}')
    parts.append("</table></section>")

    css = """
body{font-family:Georgia,serif;margin:0;background:#faf8f4;color:#222;line-height:1.5}
.wrap{display:flex;max-width:1200px;margin:0 auto}
nav{width:230px;flex-shrink:0;padding:24px 12px;position:sticky;top:0;align-self:flex-start;
    max-height:100vh;overflow-y:auto;font-family:Helvetica,Arial,sans-serif;font-size:13px}
nav a{display:block;padding:4px 8px;color:#444;text-decoration:none;border-radius:4px}
nav a:hover{background:#eee8dc}
nav .n{color:#999;font-size:11px}
main{flex:1;padding:24px 32px;min-width:0}
h1{font-size:26px;margin:8px 0 2px}
.sub{color:#777;margin:0 0 24px;font-style:italic}
h2{font-size:20px;border-bottom:2px solid #d8cfbc;padding-bottom:4px;margin-top:40px}
.fam-n{font-size:13px;color:#999;font-family:Helvetica,Arial,sans-serif;font-weight:normal}
.fam-desc{color:#555;font-size:14px}
details.sig{background:#fff;border:1px solid #e3dccd;border-radius:6px;margin:8px 0;padding:0}
details.sig summary{cursor:pointer;padding:8px 12px;display:flex;align-items:baseline;gap:10px}
.sig-name{font-weight:bold}
.sig-key{font-size:11px;color:#a08c5a;background:#f5efe2;padding:1px 5px;border-radius:3px}
.sig-n{margin-left:auto;color:#888;font-family:Helvetica,Arial,sans-serif;font-size:13px}
.sig-body{padding:4px 16px 12px;border-top:1px solid #eee8dc}
.gnote{color:#6b5d3f;font-size:14px;font-style:italic;margin:6px 0}
.rnote{color:#444;font-size:14px;margin:6px 0}
.fbs{margin:8px 0;font-family:Helvetica,Arial,sans-serif;font-size:11px}
.fb{display:flex;align-items:center;gap:6px;margin:1px 0}
.fb-a{width:90px;text-align:right;color:#666}
.fb-bar{flex:0 0 220px;background:#f0ead9;border-radius:3px;height:10px;overflow:hidden}
.fb-bar span{display:block;height:100%;background:#b08d3e;border-radius:3px}
.fb-v{color:#999}
.lex{font-size:13px;color:#555;margin:4px 0}
ul.exx{margin:8px 0;padding-left:18px;font-size:14px}
ul.exx li{margin:5px 0}
.au{font-family:Helvetica,Arial,sans-serif;font-size:10px;color:#fff;background:#a5946c;
    border-radius:3px;padding:1px 5px;vertical-align:1px;margin-right:4px}
mark{background:#ffe9a8;padding:0 2px;border-radius:2px}
.tr{font-size:13px;color:#3a6351;margin:4px 0}
.all-ex{font-family:Helvetica,Arial,sans-serif;font-size:12px;margin:6px 0 2px}
.all-ex a{color:#8a6d1f}
table.arch{border-collapse:collapse;font-size:12px;font-family:Helvetica,Arial,sans-serif;width:100%}
table.arch th,table.arch td{border:1px solid #e3dccd;padding:3px 7px;text-align:right}
table.arch th.grp{text-align:center;font-weight:normal;color:#8a795a;background:#f5efe2}
.foot{color:#999;font-size:12px;font-family:Helvetica,Arial,sans-serif;margin-top:36px;
      border-top:1px solid #e3dccd;padding-top:8px}
.foot a{color:#8a6d1f}
table.arch td.sk{text-align:left;font-family:Georgia,serif;font-size:13px}
tr.arch-ex td{text-align:left;color:#666;background:#fcfaf5;font-family:Georgia,serif;font-size:12px}
@media(max-width:800px){.wrap{flex-direction:column}nav{position:static;width:auto;display:flex;flex-wrap:wrap}}
"""
    n_sents = sum(totals["sentences"].values())
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>A Phrase-Structure Lexicon of the Roman Historians</title>
<style>{css}</style></head><body><div class="wrap">
<nav>{''.join(toc)}</nav>
<main>
<h1>A Phrase-Structure Lexicon of the Roman Historians</h1>
<p class="sub">Fine-grained constructions extracted from {n_sents:,} parsed sentences of
Caesar, Sallust, Livy, Curtius, Tacitus, Suetonius, Ammianus, and the Historia Augusta.
Bars show frequency per 1,000 sentences.</p>
{''.join(parts)}
<p class="foot">Latin texts from <a href="https://www.thelatinlibrary.com/">The Latin Library</a>.
Morphology and dependency parses by <a href="https://cltk.org/">CLTK</a>; construction extraction,
semantic-field grouping, and example translations are automatic and may contain errors.</p>
</main></div></body></html>"""
    SITE_DIR.mkdir(exist_ok=True)
    out = SITE_DIR / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB)")

    write_example_pages(inv)


EX_CSS = """
body{font-family:Georgia,serif;margin:0;background:#faf8f4;color:#222;line-height:1.55}
main{max-width:900px;margin:0 auto;padding:24px 32px}
h1{font-size:22px;margin:8px 0 2px}
.sub{color:#777;font-style:italic;margin:0 0 6px}
.back{font-family:Helvetica,Arial,sans-serif;font-size:13px}
h2{font-size:17px;border-bottom:2px solid #d8cfbc;padding-bottom:3px;margin-top:28px}
h2 .n{color:#999;font-size:13px;font-family:Helvetica,Arial,sans-serif;font-weight:normal}
ul.exx{margin:8px 0;padding-left:18px;font-size:14px}
ul.exx li{margin:6px 0}
.cite{font-family:Helvetica,Arial,sans-serif;font-size:10px;color:#8a795a;background:#f0ead9;
      border-radius:3px;padding:1px 5px;margin-right:4px;white-space:nowrap}
mark{background:#ffe9a8;padding:0 2px;border-radius:2px}
.gnote{color:#6b5d3f;font-size:14px;font-style:italic}
.foot{color:#999;font-size:12px;font-family:Helvetica,Arial,sans-serif;margin-top:36px;
      border-top:1px solid #e3dccd;padding-top:8px}
.foot a{color:#8a6d1f}
"""


def write_example_pages(inv):
    """One page per cluster with every corpus instance, grouped by author in
    corpus order, with chapter/sent_id citations."""
    EX_DIR.mkdir(exist_ok=True)
    key_map = inv.get("key_map", {})
    groups = defaultdict(lambda: defaultdict(list))  # (fam, key) -> author -> [<li>...]
    with open(DIR / "phrase_examples.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            key = key_map.get(e["fam"], {}).get(e["sig"], e["sig"])
            cite = " · ".join(b for b in
                              (f"ch. {e['chapter']}" if e.get("chapter") else "",
                               e.get("sent_id", "")) if b)
            book = html.escape(e.get("book", "")[:70])
            groups[(e["fam"], key)][e["author"]].append(
                f'<li><span class="cite" title="{book}">{html.escape(cite)}</span> {e["html"]}</li>')

    for (fam, key), by_author in groups.items():
        fam_label, _ = FAMILY_INFO[fam]
        name, gnote = describe(fam, key)
        total = sum(len(v) for v in by_author.values())
        secs = []
        for a in AUTHOR_ORDER:
            lis = by_author.get(a)
            if lis:
                secs.append(f'<h2>{AUTHOR_LABEL[a]} <span class="n">({len(lis):,})</span></h2>'
                            f'<ul class="exx">{"".join(lis)}</ul>')
        page = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{html.escape(name)} — all examples</title>
<style>{EX_CSS}</style></head><body><main>
<p class="back"><a href="../index.html#{fam}">← back to the lexicon</a></p>
<h1>{html.escape(name)}</h1>
<p class="sub">{html.escape(fam_label)} · <code>{html.escape(key)}</code> · {total:,} examples</p>
{f'<p class="gnote">{html.escape(gnote)}</p>' if gnote else ''}
{''.join(secs)}
<p class="foot">Latin texts from <a href="https://www.thelatinlibrary.com/">The Latin Library</a>.
Parses by <a href="https://cltk.org/">CLTK</a>; extraction is automatic and may contain errors.</p>
</main></body></html>"""
        (EX_DIR / f"{slug(fam, key)}.html").write_text(page, encoding="utf-8")
    print(f"Wrote {len(groups)} example pages to {EX_DIR}/")


if __name__ == "__main__":
    main()
