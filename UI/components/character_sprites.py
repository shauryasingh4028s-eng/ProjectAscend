"""Original 2D vector sprites for Project Ascend.

The artwork is drawn with Qt primitives so it is resolution-independent,
ships without external character IP and can evolve through restrained visual
details. It is deliberately illustrative rather than realistic or 3D.
"""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from Modules.gamification_config import CHARACTER_BY_ID, DEFAULT_CHARACTER_ID
from UI.theme.design_system import Colors


def _stage_number(stage_identifier):
    try:
        return max(1, min(5, int(str(stage_identifier).rsplit("_", 1)[1])))
    except (IndexError, TypeError, ValueError):
        return 1


def _color(value, alpha=255):
    color = QColor(value)
    color.setAlpha(alpha)
    return color


def draw_character(painter, rect, character, stage_identifier="stage_1"):
    """Paint one compact, original Ascend character into ``rect``."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / 200.0, rect.height() / 200.0)

    stage = _stage_number(stage_identifier)
    primary = QColor(character.primary)
    accent = QColor(character.accent)
    outline = _color("#182235" if primary.lightness() > 145 else "#D9E3F3")
    skin = _color("#F2C6A0")

    # Calm progression field: one soft disc, with restrained rings at higher
    # stages. No particles, glow loops or cinematic effects.
    painter.setPen(Qt.NoPen)
    painter.setBrush(_color(character.accent, 28))
    painter.drawEllipse(QRectF(22, 15, 156, 156))
    if stage >= 4:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_color(character.accent, 90), 2))
        painter.drawArc(QRectF(16, 9, 168, 168), 25 * 16, 130 * 16)
        painter.drawArc(QRectF(28, 21, 144, 144), 205 * 16, 90 * 16)

    # Body and shoulders.
    body = QPainterPath()
    body.moveTo(55, 180)
    body.cubicTo(58, 139, 75, 126, 100, 126)
    body.cubicTo(125, 126, 142, 139, 145, 180)
    body.closeSubpath()
    painter.setPen(QPen(outline, 3))
    painter.setBrush(primary)
    painter.drawPath(body)

    # Head. Android and space explorer receive specialised treatments below.
    if character.archetype == "android":
        painter.setBrush(_color("#B7C6D3"))
        painter.drawRoundedRect(QRectF(62, 48, 76, 75), 22, 22)
    else:
        painter.setBrush(skin if character.archetype != "forestling" else _color("#A8C98A"))
        painter.drawEllipse(QRectF(65, 45, 70, 78))

    # Archetype silhouettes and signature details.
    if character.archetype == "explorer":
        painter.setBrush(primary.darker(125))
        painter.drawRoundedRect(QRectF(57, 42, 86, 13), 5, 5)
        painter.drawRoundedRect(QRectF(72, 26, 56, 25), 10, 10)
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(79, 42, 42, 5))
        painter.setPen(QPen(outline, 3))
    elif character.archetype == "mage":
        hood = QPainterPath()
        hood.moveTo(100, 20)
        hood.lineTo(145, 68)
        hood.lineTo(132, 112)
        hood.cubicTo(120, 127, 80, 127, 68, 112)
        hood.lineTo(55, 68)
        hood.closeSubpath()
        painter.setBrush(primary.darker(115))
        painter.drawPath(hood)
        painter.setBrush(skin)
        painter.drawEllipse(QRectF(72, 54, 56, 63))
    elif character.archetype == "knight":
        painter.setBrush(primary.lighter(125))
        painter.drawRoundedRect(QRectF(61, 38, 78, 83), 30, 25)
        painter.setBrush(_color("#263449"))
        painter.drawRoundedRect(QRectF(69, 73, 62, 16), 4, 4)
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(96, 38, 8, 36))
        painter.setPen(QPen(outline, 3))
    elif character.archetype == "shinobi":
        painter.setBrush(primary.darker(150))
        painter.drawPie(QRectF(61, 36, 78, 90), 0, 180 * 16)
        painter.drawRoundedRect(QRectF(65, 79, 70, 37), 12, 12)
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(61, 57, 78, 8))
        painter.setPen(QPen(outline, 3))
    elif character.archetype == "android":
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(95, 28, 10, 10))
        painter.setPen(QPen(outline, 3))
        painter.drawLine(100, 38, 100, 49)
        painter.setBrush(_color("#263449"))
        painter.drawRoundedRect(QRectF(72, 72, 56, 27), 8, 8)
    elif character.archetype == "fox":
        painter.setBrush(primary)
        left_ear = QPainterPath()
        left_ear.moveTo(69, 58)
        left_ear.lineTo(66, 22)
        left_ear.lineTo(91, 48)
        left_ear.closeSubpath()
        right_ear = QPainterPath()
        right_ear.moveTo(109, 48)
        right_ear.lineTo(134, 22)
        right_ear.lineTo(131, 58)
        right_ear.closeSubpath()
        painter.drawPath(left_ear)
        painter.drawPath(right_ear)
        painter.setBrush(_color("#FFF0DB"))
        painter.drawEllipse(QRectF(84, 83, 32, 28))
    elif character.archetype == "forestling":
        painter.setBrush(primary)
        painter.setPen(Qt.NoPen)
        for leaf_rect in (
            QRectF(62, 31, 29, 15), QRectF(83, 21, 32, 17), QRectF(109, 33, 29, 15)
        ):
            painter.drawEllipse(leaf_rect)
        painter.setPen(QPen(outline, 3))
    elif character.archetype == "space_explorer":
        painter.setBrush(_color("#DDE8F8", 120))
        painter.drawEllipse(QRectF(53, 32, 94, 98))
        painter.setBrush(_color("#263449"))
        painter.drawEllipse(QRectF(66, 49, 68, 67))
        painter.setBrush(skin)
        painter.drawEllipse(QRectF(75, 57, 50, 55))
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(58, 103, 84, 9))
        painter.setPen(QPen(outline, 3))

    # Face stays simple and legible at small sizes.
    eye_y = 82 if character.archetype not in ("android", "knight") else 84
    painter.setPen(QPen(_color("#172033"), 4, Qt.SolidLine, Qt.RoundCap))
    if character.archetype == "knight":
        painter.setPen(QPen(accent, 3, Qt.SolidLine, Qt.RoundCap))
    painter.drawPoint(87, eye_y)
    painter.drawPoint(113, eye_y)
    if character.archetype not in ("knight", "shinobi", "android"):
        painter.setPen(QPen(_color("#8D5E55"), 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(QRectF(91, 91, 18, 12), 200 * 16, 140 * 16)

    # Evolution is additive: scarf/badge, refined trim, shoulder details and a
    # final crest. The base character always remains recognisably the same.
    if stage >= 2:
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(72, 126, 56, 9), 4, 4)
        painter.drawEllipse(QRectF(94, 139, 12, 12))
    if stage >= 3:
        painter.setBrush(accent.lighter(120))
        painter.drawRoundedRect(QRectF(57, 139, 22, 12), 5, 5)
        painter.drawRoundedRect(QRectF(121, 139, 22, 12), 5, 5)
        painter.setPen(QPen(accent, 3))
        painter.drawLine(77, 164, 123, 164)
    if stage >= 5:
        painter.setPen(QPen(accent, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        crest = QPainterPath()
        crest.moveTo(88, 28)
        crest.lineTo(94, 17)
        crest.lineTo(100, 28)
        crest.lineTo(106, 17)
        crest.lineTo(112, 28)
        painter.drawPath(crest)

    painter.restore()


def character_pixmap(character, stage_identifier="stage_1", size=72):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    draw_character(
        painter,
        QRectF(0, 0, size, size),
        character,
        stage_identifier,
    )
    painter.end()
    return pixmap


class CharacterSprite(QWidget):
    """A scalable 2D character illustration used by Player Progress."""

    def __init__(
        self,
        character_id=DEFAULT_CHARACTER_ID,
        stage_identifier="stage_1",
        parent=None,
    ):
        super().__init__(parent)
        self.character_id = character_id
        self.stage_identifier = stage_identifier
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def sizeHint(self):
        return QSize(180, 180)

    def set_character(self, character_id, stage_identifier=None):
        self.character_id = (
            character_id if character_id in CHARACTER_BY_ID else DEFAULT_CHARACTER_ID
        )
        if stage_identifier is not None:
            self.stage_identifier = stage_identifier
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        margin = 4
        side = min(self.width(), self.height()) - (margin * 2)
        rect = QRectF(
            (self.width() - side) / 2,
            (self.height() - side) / 2,
            side,
            side,
        )
        draw_character(
            painter,
            rect,
            CHARACTER_BY_ID.get(
                self.character_id,
                CHARACTER_BY_ID[DEFAULT_CHARACTER_ID],
            ),
            self.stage_identifier,
        )
        painter.end()


def character_icon(character, stage_identifier="stage_1", size=72):
    return QIcon(character_pixmap(character, stage_identifier, size))
