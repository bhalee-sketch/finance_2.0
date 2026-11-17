"""Stable-launcher readiness protocol and read-only update status."""
import os
from pathlib import Path
import sys
from release_update import release_metadata


def signal_ready():
    marker=os.environ.pop('WORKSPACE_READY_FILE',None)
    if not marker:return
    version=release_metadata(Path(sys.executable).parent)['version']
    Path(marker).write_text(version,encoding='utf-8')



def open_updates(parent,application):
    """Compatibility entry point: update status is shown inline; no modal menu."""
    from version_status import version_status
    return version_status(application)
