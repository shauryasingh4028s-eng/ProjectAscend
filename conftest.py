"""Project Ascend test bootstrap.

This file lives at the project root so pytest adds the project directory to
sys.path, making ``Modules`` and ``Database`` importable from the tests.
"""

import os

# Run every Qt-based test headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
