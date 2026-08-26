from PySide6.QtCore import QSettings

class MotionUtils:
    @staticmethod
    def reduced_motion_enabled() -> bool:
        """
        Returns True if reduced motion is enabled by the user.
        Uses QSettings to read the 'accessibility/reduced_motion' preference.
        Defaults to False.
        """
        settings = QSettings("ProjectAscend", "ProjectAscend")
        return settings.value("accessibility/reduced_motion", False, type=bool)
