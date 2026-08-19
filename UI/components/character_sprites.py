"""Bundled original 2D sprite assets for Project Ascend characters.

Each character has five coherent, level-derived PNG stages under
``Assets/characters``.  Qt only loads and scales those assets at runtime; no
third-party renderer or network access is required.  A restrained fallback is
kept solely for a damaged/missing installation asset.
"""

from functools import lru_cache
from pathlib import Path
import sys

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from Modules.gamification_config import CHARACTER_BY_ID, DEFAULT_CHARACTER_ID
from UI.theme.design_system import Colors


ASSET_SIZE = 320


def _project_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def character_asset_path(character_id, stage_identifier="stage_1"):
    safe_character = (
        character_id if character_id in CHARACTER_BY_ID else DEFAULT_CHARACTER_ID
    )
    safe_stage = stage_identifier if stage_identifier in {
        "stage_1", "stage_2", "stage_3", "stage_4", "stage_5"
    } else "stage_1"
    return (
        _project_root()
        / "Assets"
        / "characters"
        / safe_character
        / f"{safe_stage}.png"
    )


@lru_cache(maxsize=48)
def _source_pixmap(character_id, stage_identifier):
    pixmap = QPixmap(str(character_asset_path(character_id, stage_identifier)))
    if not pixmap.isNull():
        return pixmap

    # Packaging-safe fallback. It is intentionally quiet and only appears if
    # an expected bundled sprite cannot be loaded.
    fallback = QPixmap(ASSET_SIZE, ASSET_SIZE)
    fallback.fill(Qt.transparent)
    painter = QPainter(fallback)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(Colors.ACCENT_SOFT))
    painter.drawEllipse(QRectF(48, 48, 224, 224))
    painter.setPen(QColor(Colors.ACCENT))
    font = QFont()
    font.setPixelSize(88)
    font.setBold(True)
    painter.setFont(font)
    name = CHARACTER_BY_ID[character_id].name
    painter.drawText(fallback.rect(), Qt.AlignCenter, name[:1])
    painter.end()
    return fallback


def character_pixmap(character, stage_identifier="stage_1", size=96):
    """Return one high-quality scaled stage while preserving transparency."""
    source = _source_pixmap(character.identifier, stage_identifier)
    return source.scaled(
        max(1, int(size)),
        max(1, int(size)),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


class CharacterSprite(QWidget):
    """Scalable hero presentation for one bundled character sprite."""

    def __init__(
        self,
        character_id=DEFAULT_CHARACTER_ID,
        stage_identifier="stage_1",
        parent=None,
    ):
        super().__init__(parent)
        self.character_id = character_id
        self.stage_identifier = stage_identifier
        self.setMinimumSize(170, 170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def sizeHint(self):
        return QSize(220, 220)

    def set_character(self, character_id, stage_identifier=None):
        self.character_id = (
            character_id if character_id in CHARACTER_BY_ID else DEFAULT_CHARACTER_ID
        )
        if stage_identifier is not None:
            self.stage_identifier = stage_identifier
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        side = max(1, min(self.width(), self.height()) - 4)
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2

        # Controlled depth belongs to the presentation surface, not the asset.
        field = QColor(Colors.ACCENT)
        field.setAlpha(20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(field)
        painter.drawEllipse(QRectF(x + side * .12, y + side * .08, side * .76, side * .76))
        shadow = QColor(0, 0, 0, 45)
        painter.setBrush(shadow)
        painter.drawEllipse(QRectF(x + side * .25, y + side * .83, side * .5, side * .08))

        character = CHARACTER_BY_ID.get(
            self.character_id,
            CHARACTER_BY_ID[DEFAULT_CHARACTER_ID],
        )
        pixmap = character_pixmap(character, self.stage_identifier, int(side))
        painter.drawPixmap(
            int(x + (side - pixmap.width()) / 2),
            int(y + (side - pixmap.height()) / 2),
            pixmap,
        )
        painter.end()


def character_icon(character, stage_identifier="stage_1", size=96):
    return QIcon(character_pixmap(character, stage_identifier, size))
