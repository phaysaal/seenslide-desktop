"""Crisp, theme-tinted line icons drawn with QPainter.

No external assets: each icon is stroked on a transparent pixmap in a 24×24
viewbox and scaled to the requested size, so it stays sharp at any DPI and
takes the caller's colour. Used for sidebar nav, mode-card tiles, and the
current-session card to match the web mockup's line-icon style.
"""

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QPainterPath


def _pen(p, color, w=1.8):
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def _home(p, c):
    _pen(p, c)
    path = QPainterPath()
    path.moveTo(4, 10)
    path.lineTo(12, 4)
    path.lineTo(20, 10)
    p.drawPath(path)
    p.drawPath(_rounded_rect(6, 10, 12, 9, 1.2))
    _pen(p, c, 1.6)
    p.drawLine(QPointF(10, 19), QPointF(10, 14))
    p.drawLine(QPointF(14, 19), QPointF(14, 14))
    p.drawLine(QPointF(10, 14), QPointF(14, 14))


def _present(p, c):
    _pen(p, c)
    p.drawPath(_rounded_rect(3.5, 5, 17, 11, 2))
    _pen(p, c, 1.6)
    p.drawLine(QPointF(9, 19), QPointF(15, 19))
    p.drawLine(QPointF(12, 16), QPointF(12, 19))


def _conference(p, c):
    _pen(p, c)
    # left + right small heads
    p.drawEllipse(QRectF(3.5, 6, 4.2, 4.2))
    p.drawEllipse(QRectF(16.3, 6, 4.2, 4.2))
    # center larger head
    p.drawEllipse(QRectF(9.4, 4.4, 5.2, 5.2))
    _pen(p, c, 1.6)
    # shoulders
    path = QPainterPath()
    path.moveTo(7.5, 19)
    path.cubicTo(7.5, 14.5, 16.5, 14.5, 16.5, 19)
    p.drawPath(path)
    p.drawLine(QPointF(2.6, 18), QPointF(2.6, 15.6))
    p.drawLine(QPointF(21.4, 18), QPointF(21.4, 15.6))


def _sessions(p, c):
    _pen(p, c, 1.7)
    for x in (4, 13.5):
        for y in (4, 13.5):
            p.drawPath(_rounded_rect(x, y, 6.5, 6.5, 1.6))


def _mic(p, c):
    _pen(p, c)
    p.drawPath(_rounded_rect(9, 3, 6, 11, 3))
    path = QPainterPath()
    path.moveTo(5.5, 11)
    path.cubicTo(5.5, 18, 18.5, 18, 18.5, 11)
    p.drawPath(path)
    _pen(p, c, 1.6)
    p.drawLine(QPointF(12, 17), QPointF(12, 20.5))
    p.drawLine(QPointF(8.5, 20.5), QPointF(15.5, 20.5))


def _people(p, c):
    _pen(p, c)
    p.drawEllipse(QRectF(8, 4, 8, 8))
    path = QPainterPath()
    path.moveTo(4.5, 20)
    path.cubicTo(4.5, 12.5, 19.5, 12.5, 19.5, 20)
    p.drawPath(path)


def _open(p, c):
    # external-link: box with an arrow leaving the top-right
    _pen(p, c, 1.7)
    path = QPainterPath()
    path.moveTo(13, 5)
    path.lineTo(5.5, 5)
    path.lineTo(5.5, 18.5)
    path.lineTo(19, 18.5)
    path.lineTo(19, 11)
    p.drawPath(path)
    p.drawLine(QPointF(12, 12), QPointF(19.5, 4.5))
    path2 = QPainterPath()
    path2.moveTo(14.5, 4.5)
    path2.lineTo(19.5, 4.5)
    path2.lineTo(19.5, 9.5)
    p.drawPath(path2)


def _play(p, c):
    _pen(p, c, 1.6)
    path = QPainterPath()
    path.moveTo(8, 6)
    path.lineTo(18, 12)
    path.lineTo(8, 18)
    path.closeSubpath()
    p.setBrush(QColor(c))
    p.drawPath(path)


def _rounded_rect(x, y, w, h, r):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


_ICONS = {
    "home": _home,
    "present": _present,
    "conference": _conference,
    "sessions": _sessions,
    "mic": _mic,
    "people": _people,
    "monitor": _present,
    "open": _open,
    "play": _play,
}


def icon_pixmap(name, size=20, color="#ffffff"):
    """Return a QPixmap of the named line icon, tinted `color`, at `size` px."""
    dpr = 2  # render at 2× for crispness on hiDPI
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size * dpr / 24.0, size * dpr / 24.0)
    fn = _ICONS.get(name)
    if fn:
        fn(p, color)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm
