"""Character Asset Infrastructure & Pixel-Art Sprite Renderer.

Manages 32 production character sprites (8 archetypes x 4 evolution stages).
Enforces nearest-neighbor pixel-art scaling (Qt.FastTransformation) and preserves
transparency, hard pixel edges, and cache performance.
"""

from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPixmapCache,
)

from UI.theme.design_system import Colors, ThemeManager

CHARACTER_MANIFEST = {
    "architect": {
        "id": "architect",
        "name": "The Architect",
        "identity": "Focus & Planning Mastery",
        "description": "Master of structure, vision, and strategic focus.",
        "icon": "📐",
        "primary_color": "#7C5CFF",
        "secondary_color": "#3B82F6",
    },
    "catalyst": {
        "id": "catalyst",
        "name": "The Catalyst",
        "identity": "Execution & Speed Mastery",
        "description": "Spark of momentum, high output, and swift execution.",
        "icon": "⚡",
        "primary_color": "#3B82F6",
        "secondary_color": "#60A5FA",
    },
    "sentinel": {
        "id": "sentinel",
        "name": "The Sentinel",
        "identity": "Consistency & Habit Mastery",
        "description": "Guardian of daily routines, endurance, and unbroken streaks.",
        "icon": "🛡",
        "primary_color": "#F59E0B",
        "secondary_color": "#D97706",
    },
    "vanguard": {
        "id": "vanguard",
        "name": "The Vanguard",
        "identity": "Deep Work & Endurance Mastery",
        "description": "Pioneer of long flow states and deep cognitive focus.",
        "icon": "⚔",
        "primary_color": "#22C55E",
        "secondary_color": "#10B981",
    },
    "scholar": {
        "id": "scholar",
        "name": "The Scholar",
        "identity": "Knowledge & Reflection Mastery",
        "description": "Seeker of continuous learning, research, and deep insight.",
        "icon": "📜",
        "primary_color": "#6366F1",
        "secondary_color": "#818CF8",
    },
    "pathfinder": {
        "id": "pathfinder",
        "name": "The Pathfinder",
        "identity": "Goal Exploration & Direction",
        "description": "Navigator of milestone pathways and new horizons.",
        "icon": "🧭",
        "primary_color": "#EC4899",
        "secondary_color": "#F472B6",
    },
    "artisan": {
        "id": "artisan",
        "name": "The Artisan",
        "identity": "Craft & Precision Execution",
        "description": "Craftsman of meticulous detail and pristine completion quality.",
        "icon": "🎨",
        "primary_color": "#8B5CF6",
        "secondary_color": "#A78BFA",
    },
    "paragon": {
        "id": "paragon",
        "name": "The Paragon",
        "identity": "Balanced Holistic Mastery",
        "description": "Embodiment of harmony across planning, focus, and consistency.",
        "icon": "👑",
        "primary_color": "#EAB308",
        "secondary_color": "#FACC15",
    },
}

STAGE_NAMES = {
    1: "Initiated",
    2: "Established",
    3: "Ascended",
    4: "Sovereign",
}


class CharacterAssetManager:
    """Manages 32 production character sprites, nearest-neighbor scaling, and neutral fallback visual rendering."""

    _pixmap_memory_cache = {}

    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = Path(__file__).resolve().parent.parent
        else:
            self.base_dir = Path(base_dir)

    def resolve_asset_path(self, character_id, stage=1):
        """Return the expected path for a character evolution stage PNG."""
        if character_id not in CHARACTER_MANIFEST:
            character_id = "architect"
        stage = max(1, min(int(stage), 4))

        # 1. Canonical subfolder: assets/characters/<character_id>/stage_<stage>.png
        canonical_path = self.base_dir / "assets" / "characters" / character_id / f"stage_{stage}.png"
        if canonical_path.exists() and canonical_path.is_file():
            return canonical_path

        # 2. Flat filename: assets/characters/<character_id>_stage_<stage>.png
        flat_path = self.base_dir / "assets" / "characters" / f"{character_id}_stage_{stage}.png"
        if flat_path.exists() and flat_path.is_file():
            return flat_path

        # 3. Desktop source directory fallback
        desktop_path = Path.home() / "OneDrive" / "Desktop" / "Sprites_Asset" / f"{character_id}_stage_{stage}.png"
        if desktop_path.exists() and desktop_path.is_file():
            return desktop_path

        return canonical_path

    def asset_exists(self, character_id, stage=1):
        """Return True if the specific character stage image file exists on disk."""
        path = self.resolve_asset_path(character_id, stage)
        return path.exists() and path.is_file()

    def get_character_pixmap(self, character_id, stage=1, width=128, height=128):
        """Retrieve cached pixmap or load/render fallback image at requested dimensions.
        
        Enforces pixel-art nearest-neighbor scaling (Qt.FastTransformation) to preserve hard pixel edges.
        """
        if character_id not in CHARACTER_MANIFEST:
            character_id = "architect"
        stage = max(1, min(int(stage), 4))
        width = max(16, int(width))
        height = max(16, int(height))

        cache_key = f"char_pixmap_{character_id}_s{stage}_{width}x{height}_{ThemeManager.current_theme}"

        # 1. Check in-memory dictionary cache
        if cache_key in self._pixmap_memory_cache:
            return self._pixmap_memory_cache[cache_key]

        # 2. Check QPixmapCache
        cached_pixmap = QPixmap()
        if QPixmapCache.find(cache_key, cached_pixmap):
            self._pixmap_memory_cache[cache_key] = cached_pixmap
            return cached_pixmap

        # 3. Load from disk if exists (Using Qt.FastTransformation for pixel-art integrity)
        asset_path = self.resolve_asset_path(character_id, stage)
        if asset_path.exists() and asset_path.is_file():
            loaded_pixmap = QPixmap(str(asset_path))
            if not loaded_pixmap.isNull():
                scaled_pixmap = loaded_pixmap.scaled(
                    width,
                    height,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,  # Nearest-neighbor filtering preserves hard pixel art edges
                )
                QPixmapCache.insert(cache_key, scaled_pixmap)
                self._pixmap_memory_cache[cache_key] = scaled_pixmap
                return scaled_pixmap

        # 4. Generate polished neutral fallback QPixmap if file missing/unreadable
        fallback_pixmap = self._generate_fallback_pixmap(character_id, stage, width, height)
        QPixmapCache.insert(cache_key, fallback_pixmap)
        self._pixmap_memory_cache[cache_key] = fallback_pixmap
        return fallback_pixmap

    def _generate_fallback_pixmap(self, character_id, stage, width, height):
        """Generate a theme-aware, intentional geometric avatar representation when asset PNG is missing."""
        meta = CHARACTER_MANIFEST.get(character_id, CHARACTER_MANIFEST["architect"])
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(2, 2, width - 4, height - 4)
        radius = min(width, height) * 0.22

        primary_color = QColor(meta["primary_color"])

        bg_gradient = QLinearGradient(0, 0, width, height)
        if ThemeManager.current_theme == "light":
            bg_gradient.setColorAt(0.0, QColor("#F0F4FA"))
            bg_gradient.setColorAt(1.0, QColor("#E1E8F5"))
            border_color = primary_color.lighter(130)
        else:
            bg_gradient.setColorAt(0.0, QColor("#0D131F"))
            bg_gradient.setColorAt(1.0, QColor("#141E30"))
            border_color = primary_color

        painter.setBrush(QBrush(bg_gradient))

        border_width = 1.5 + (stage * 0.5)
        pen = QPen(border_color, border_width)
        if stage == 4:
            pen.setColor(QColor("#EAB308"))  # Sovereign gold border accent
        painter.setPen(pen)
        painter.drawRoundedRect(rect, radius, radius)

        if stage >= 2:
            inner_rect = rect.adjusted(4, 4, -4, -4)
            inner_color = QColor(primary_color)
            inner_color.setAlpha(128)
            inner_pen = QPen(inner_color, 1.0, Qt.DotLine if stage == 2 else Qt.SolidLine)
            painter.setPen(inner_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(inner_rect, radius - 2, radius - 2)

        painter.setPen(QPen(QColor(Colors.TEXT_PRIMARY)))
        icon_font_size = int(min(width, height) * 0.4)
        font = QFont("Segoe UI Emoji, Apple Color Emoji, Segoe UI", icon_font_size)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, meta["icon"])

        pill_w = max(22.0, width * 0.24)
        pill_h = max(16.0, height * 0.18)
        pill_rect = QRectF(width - pill_w - 4, height - pill_h - 4, pill_w, pill_h)

        pill_path = QPainterPath()
        pill_path.addRoundedRect(pill_rect, 4, 4)

        pill_bg = QColor(Colors.SURFACE_ELEVATED)
        pill_bg.setAlpha(220)
        painter.setBrush(QBrush(pill_bg))
        painter.setPen(QPen(primary_color, 1.0))
        painter.drawPath(pill_path)

        pill_font_size = max(8, int(height * 0.11))
        pill_font = QFont("Segoe UI, Inter, sans-serif", pill_font_size, QFont.Bold)
        painter.setFont(pill_font)
        painter.setPen(QPen(QColor(Colors.TEXT_PRIMARY)))
        painter.drawText(pill_rect, Qt.AlignCenter, f"S{stage}")

        painter.end()
        return pixmap

    def validate_all_assets(self):
        """Validate all 32 expected character evolution stage production sprites."""
        results = {}
        for cid in CHARACTER_MANIFEST:
            for st in range(1, 5):
                key = f"{cid}_stage_{st}"
                path = self.resolve_asset_path(cid, st)
                exists = self.asset_exists(cid, st)
                pixmap = self.get_character_pixmap(cid, st, 64, 64)
                valid = exists and (pixmap is not None) and not pixmap.isNull()
                results[key] = {
                    "character_id": cid,
                    "stage": st,
                    "path": str(path),
                    "exists": exists,
                    "valid": valid,
                }
        return results

    def clear_cache(self):
        """Clear memory and QPixmapCache."""
        self._pixmap_memory_cache.clear()
        QPixmapCache.clear()

    def preload_character_assets(self, character_ids=None, stages=None, width=128, height=128):
        """Preload pixmaps into cache for smooth instant UI presentation."""
        if character_ids is None:
            character_ids = list(CHARACTER_MANIFEST.keys())
        if stages is None:
            stages = [1, 2, 3, 4]

        for cid in character_ids:
            for st in stages:
                self.get_character_pixmap(cid, st, width, height)
