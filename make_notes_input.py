"""Prepare the translation task for a small model: one representative example
per cluster (shortest available), plus the cluster's display name. Writes
notes_input.json; the model fills cluster_notes.json keyed by 'family|sig'.
"""
import json
import re
from pathlib import Path

from build_lexicon_html import describe

DIR = Path("/Users/mimno/Documents/Data/LatinHistorians")


def main():
    inv = json.loads((DIR / "phrase_inventory.json").read_text())
    items = []
    for fam, sigs in inv["families"].items():
        for sig, cell in sigs.items():
            if sig.startswith("(other"):
                continue
            exx = sorted(cell["examples"], key=lambda e: e["n_words"])
            if not exx:
                continue
            ex = exx[0]
            plain = re.sub(r"</?mark>", lambda m: "[[" if m.group(0) == "<mark>" else "]]", ex["html"])
            name, _ = describe(fam, sig)
            items.append({"key": f"{fam}|{sig}", "construction": name,
                          "latin": plain, "author": ex["author"]})
    out = DIR / "notes_input.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=0))
    print(f"Wrote {out}: {len(items)} clusters")


if __name__ == "__main__":
    main()
