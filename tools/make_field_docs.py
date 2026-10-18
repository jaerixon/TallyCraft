"""Refresh the generated packing-list field docs from packing_docx.FIELDS.

    python tools/make_field_docs.py   # -> docs/TEMPLATE_FIELDS.md and the README.txt field section

The starter template itself is designed in Word; tools/adapt_template.py turns a
Word design into assets/templates/packing_list_template.docx.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tallycraft.packing_docx import field_reference_markdown, field_reference_text  # noqa: E402


def write_docs() -> None:
    (ROOT / "docs" / "TEMPLATE_FIELDS.md").write_text(field_reference_markdown() + "\n", encoding="utf-8",
                                                      newline="\n")
    readme = ROOT / "dist_template" / "README.txt"
    text = readme.read_text(encoding="utf-8")
    start, end = "<<TEMPLATE FIELDS START>>", "<<TEMPLATE FIELDS END>>"
    if start in text and end in text:
        a, b = text.index(start) + len(start), text.index(end)
        text = text[:a] + "\n" + field_reference_text() + "\n" + text[b:]
        readme.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    write_docs()
    print("Refreshed docs/TEMPLATE_FIELDS.md and the README.txt field section")


if __name__ == "__main__":
    main()
