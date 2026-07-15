"""Generate the synthetic 3-talk conference deck + schedule CSV for P3.

Each talk = one title slide (multi-line title, presenter buried in a
multi-author list — exactly what the OCR matcher must be robust to)
followed by two content slides. Run once; outputs are committed:

    tests/pdfs/conference2026.pdf
    tests_gui_agent/fixtures/conference2026.csv
"""
from pathlib import Path

import fitz

HERE = Path(__file__).parent
PDF_OUT = HERE.parent / "tests" / "pdfs" / "conference2026.pdf"
CSV_OUT = HERE / "fixtures" / "conference2026.csv"

# (title, presenter-of-record, full author line)
TALKS = [
    ("Adaptive Mesh Refinement\nfor Turbulent Fluid Simulation",
     "Alice Chen",
     "Alice Chen, David Kim, Maria Lopez"),
    ("Neural Program Synthesis\nin Modern Compiler Pipelines",
     "Robert Martinez",
     "Wei Zhang, Robert Martinez, Sofia Rossi"),
    ("Fault-Tolerant Quantum\nError Correction Codes",
     "Carol Tanaka",
     "Carol Tanaka, James Wright"),
]

CONTENT = [
    ["Motivation and Prior Work",
     "Problem Formulation",
     ],
    ["Benchmark Results",
     "Limitations and Future Work",
     ],
]

W, H = 1280, 800
INK, ACCENT, MUTED = (0.12, 0.13, 0.17), (0.05, 0.35, 0.65), (0.45, 0.47, 0.52)


def _title_slide(page, n, title, authors):
    page.draw_rect(fitz.Rect(0, 0, W, 14), color=None, fill=ACCENT)
    page.insert_textbox(fitz.Rect(90, 190, W - 90, 460), title,
                        fontsize=56, fontname="hebo", color=INK, align=1)
    page.insert_textbox(fitz.Rect(90, 480, W - 90, 540), authors,
                        fontsize=30, fontname="helv", color=ACCENT, align=1)
    page.insert_textbox(fitz.Rect(90, 700, W - 90, 750),
                        "Harness Research Symposium 2026",
                        fontsize=20, fontname="helv", color=MUTED, align=1)


def _content_slide(page, n, talk_no, heading):
    page.draw_rect(fitz.Rect(0, 0, W, 14), color=None, fill=ACCENT)
    page.insert_textbox(fitz.Rect(70, 60, W - 70, 140), heading,
                        fontsize=40, fontname="hebo", color=INK)
    bullets = "\n\n".join(
        f"•  {heading} — key point {i} of talk {talk_no}, "
        f"with distinct wording so deduplication never merges pages."
        for i in range(1, 5))
    page.insert_textbox(fitz.Rect(90, 200, W - 90, 660), bullets,
                        fontsize=24, fontname="helv", color=INK)
    page.insert_textbox(fitz.Rect(70, 740, W - 70, 780),
                        f"slide {n}", fontsize=14, fontname="helv", color=MUTED)


def main():
    doc = fitz.open()
    n = 0
    for t, (title, _presenter, authors) in enumerate(TALKS, 1):
        n += 1
        _title_slide(doc.new_page(width=W, height=H), n, title, authors)
        for heading in CONTENT[0] if t % 2 else CONTENT[1]:
            n += 1
            _content_slide(doc.new_page(width=W, height=H), n, t,
                           f"{heading}")
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(PDF_OUT))

    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{title.replace(chr(10), ' ')},{presenter}"
            for title, presenter, _ in TALKS]
    CSV_OUT.write_text("\n".join(rows) + "\n")
    print(f"wrote {PDF_OUT} ({n} pages) and {CSV_OUT}")


if __name__ == "__main__":
    main()
