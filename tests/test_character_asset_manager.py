"""Unit tests for Character Asset Manager, 32-Sprite Matrix, and Pixel-Art Caching Infrastructure."""

import os
from pathlib import Path
import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from Modules.character_asset_manager import CHARACTER_MANIFEST, CharacterAssetManager
from UI.theme.design_system import ThemeManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_manifest_integrity():
    assert len(CHARACTER_MANIFEST) == 8
    expected_ids = ["architect", "catalyst", "sentinel", "vanguard", "scholar", "pathfinder", "artisan", "paragon"]
    for cid in expected_ids:
        assert cid in CHARACTER_MANIFEST
        meta = CHARACTER_MANIFEST[cid]
        assert meta["id"] == cid
        assert "name" in meta
        assert "identity" in meta
        assert "description" in meta
        assert "icon" in meta


def test_resolve_asset_path():
    mgr = CharacterAssetManager()
    path = mgr.resolve_asset_path("architect", stage=2)
    assert "stage_2.png" in path.name
    assert "architect" in str(path)


def test_invalid_character_or_stage_safety():
    mgr = CharacterAssetManager()

    # Invalid character ID falls back to architect
    path_invalid_char = mgr.resolve_asset_path("unknown_dragon", stage=1)
    assert "architect" in str(path_invalid_char)

    # Stage clamped between 1 and 4
    path_stage_low = mgr.resolve_asset_path("catalyst", stage=0)
    assert "stage_1.png" in path_stage_low.name

    path_stage_high = mgr.resolve_asset_path("catalyst", stage=99)
    assert "stage_4.png" in path_stage_high.name


def test_32_sprite_matrix_validation(qapp):
    """Test loading and validating all 8 characters x 4 stages = 32 production sprites."""
    mgr = CharacterAssetManager()
    archetypes = ["architect", "catalyst", "sentinel", "vanguard", "scholar", "pathfinder", "artisan", "paragon"]
    stages = [1, 2, 3, 4]

    validated_count = 0
    for cid in archetypes:
        for st in stages:
            assert mgr.asset_exists(cid, st), f"Asset missing for character {cid} stage {st}"
            pixmap = mgr.get_character_pixmap(cid, st, width=128, height=128)
            assert isinstance(pixmap, QPixmap)
            assert not pixmap.isNull(), f"Pixmap null for character {cid} stage {st}"
            assert pixmap.hasAlphaChannel(), f"Alpha channel missing for {cid} stage {st}"
            validated_count += 1

    assert validated_count == 32


def test_validate_all_assets_helper(qapp):
    """Test CharacterAssetManager.validate_all_assets() report structure."""
    mgr = CharacterAssetManager()
    results = mgr.validate_all_assets()
    assert len(results) == 32
    for key, res in results.items():
        assert res["exists"] is True
        assert res["valid"] is True


def test_fallback_pixmap_generation(qapp):
    mgr = CharacterAssetManager()
    pixmap = mgr._generate_fallback_pixmap("architect", stage=2, width=100, height=100)

    assert isinstance(pixmap, QPixmap)
    assert not pixmap.isNull()
    assert pixmap.width() == 100
    assert pixmap.height() == 100


def test_pixmap_caching_and_invalidation(qapp):
    mgr = CharacterAssetManager()
    mgr.clear_cache()

    pixmap1 = mgr.get_character_pixmap("vanguard", stage=3, width=128, height=128)
    pixmap2 = mgr.get_character_pixmap("vanguard", stage=3, width=128, height=128)

    # Should return cached pixmap object
    assert pixmap1 is pixmap2

    mgr.clear_cache()
    assert len(mgr._pixmap_memory_cache) == 0


def test_theme_awareness_pixmap(qapp):
    mgr = CharacterAssetManager()
    mgr.clear_cache()

    ThemeManager.set_theme("dark")
    dark_pixmap = mgr.get_character_pixmap("scholar", stage=1, width=64, height=64)

    ThemeManager.set_theme("light")
    light_pixmap = mgr.get_character_pixmap("scholar", stage=1, width=64, height=64)

    assert not dark_pixmap.isNull()
    assert not light_pixmap.isNull()

    ThemeManager.set_theme("dark")  # Restore
