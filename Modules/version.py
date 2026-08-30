"""Single authoritative source of truth for the Project Ascend app version.

Every runtime consumer of the build version (telemetry envelopes, version
update detection, future "About" surfaces) must import APP_VERSION from here
so a release only ever bumps the number in one place.

Note: packaging metadata (ProjectAscendInstaller.iss) has its own copy that
is stamped at release time and is intentionally not read at runtime.
"""

APP_VERSION = "1.5.0"
