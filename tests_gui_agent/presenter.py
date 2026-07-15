"""Presenter simulator: play a PDF fullscreen like a human presenting.

Renders pages with PyMuPDF and shows them frameless + stay-on-top over the
given monitor geometry, so the SeenSlide app underneath captures exactly what
a real audience projector would show. Standalone script — the harness runs it
as a subprocess and waits for it to exit (it quits after the last page).

    python -m tests_gui_agent.presenter --pdf deck.pdf \
        --geometry 0,0,1920,1200 --interval 5 --hold-first 12 --max-pages 8
"""
import argparse
import sys

import fitz
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel


def render_pages(pdf_path, w, h, max_pages=0):
    """PDF pages -> QPixmaps letterboxed to w x h (white slide on black)."""
    doc = fitz.open(pdf_path)
    n = doc.page_count if not max_pages else min(max_pages, doc.page_count)
    pixmaps = []
    for i in range(n):
        page = doc[i]
        zoom = min(w / page.rect.width, h / page.rect.height)
        pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                     QImage.Format_RGB888)
        pixmaps.append(QPixmap.fromImage(img.copy()))
    return pixmaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--geometry", required=True, help="x,y,w,h of the target monitor")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--hold-first", type=float, default=12.0,
                    help="seconds to hold page 1 (covers the app's countdown)")
    ap.add_argument("--max-pages", type=int, default=0)
    args = ap.parse_args()
    x, y, w, h = map(int, args.geometry.split(","))

    app = QApplication(sys.argv)
    pages = render_pages(args.pdf, w, h, args.max_pages)
    if not pages:
        print("no pages", file=sys.stderr)
        sys.exit(1)

    screen = QLabel()
    screen.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    screen.setStyleSheet("background: black;")
    screen.setAlignment(Qt.AlignCenter)
    screen.setCursor(Qt.BlankCursor)

    state = {"i": 0}
    screen.setPixmap(pages[0])

    # Bind to the TARGET monitor explicitly, then real-fullscreen there.
    # A frameless setGeometry() alone let Mutter place the window on
    # whichever monitor it liked (observed: the external, while capture
    # recorded the primary) — and it left the dock/panel visible. True
    # fullscreen on an explicit QScreen fixes both, and fullscreen outranks
    # the app's stay-on-top in the WM stacking order.
    target = None
    for s in QApplication.screens():
        g = s.geometry()
        if (g.x(), g.y()) == (x, y):
            target = s
            break
    screen.show()  # creates the native window handle
    if target is not None and screen.windowHandle() is not None:
        screen.windowHandle().setScreen(target)
        screen.setGeometry(target.geometry())
    else:
        screen.setGeometry(x, y, w, h)
    screen.showFullScreen()
    screen.raise_()

    def _report_placement():
        wh = screen.windowHandle()
        name = wh.screen().name() if wh and wh.screen() else "?"
        g = screen.geometry()
        print(f"window on screen {name} at {g.x()},{g.y()} {g.width()}x{g.height()}",
              flush=True)
    QTimer.singleShot(1200, _report_placement)

    def advance():
        state["i"] += 1
        if state["i"] >= len(pages):
            # small grace so the app's periodic capture gets the last page
            QTimer.singleShot(2500, app.quit)
            timer.stop()
            return
        screen.setPixmap(pages[state["i"]])
        screen.raise_()  # stay above the (also on-top) app window
        print(f"page {state['i'] + 1}/{len(pages)}", flush=True)

    timer = QTimer()
    timer.timeout.connect(advance)
    # hold page 1 for hold_first, then advance at the regular interval
    QTimer.singleShot(int(args.hold_first * 1000), timer.start)
    timer.setInterval(int(args.interval * 1000))
    print(f"presenting {len(pages)} pages "
          f"(hold {args.hold_first}s, then {args.interval}s each)", flush=True)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
