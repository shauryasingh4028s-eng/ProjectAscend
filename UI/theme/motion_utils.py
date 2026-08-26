"""Motion utilities and reduced-motion preference handling for Project Ascend.

Provides lightweight reduced-motion checks and safe animation helpers.
When reduced motion is active, animations apply final target state directly
without instantiating running QPropertyAnimation / QVariantAnimation loops.
"""

from PySide6.QtCore import QSettings


def is_reduced_motion_enabled() -> bool:
    """Return True if the user has requested reduced motion."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    return settings.value("reduced_motion", False, type=bool)


def set_reduced_motion_enabled(enabled: bool) -> None:
    """Persist the reduced motion preference."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    settings.setValue("reduced_motion", bool(enabled))
    settings.sync()
