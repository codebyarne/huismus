# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Looking sooner in the receipts folder (SPEC.md M20, "Huismus kijkt
sneller"; choices in huismus-intern/besluiten.md, 2026-11-06).

The look every ten minutes (expenses.inbox) stays, as the safety net. Next
to it one thread waits for something new and then starts a look at once:

- A folder (the desktop app, or one linked into the container): every few
  seconds a glance at the top level, names and sizes only. A file that has
  been still for a minute (inbox.SETTLE_SECONDS) and wasn't there at the
  previous glance starts a look. Plain polling, no file-system events:
  those don't reach a container through a linked folder, nor reliably
  from iCloud, and this needs no dependency.
- Dropbox: Dropbox's longpoll, a request that stays open until something
  in the folder Bonnetjes changes. Only outgoing, like the backups.

Waiting never holds the maintenance gate, so a restore never waits for it;
only the look itself goes through the gate (inbox.fetch_when_open). A
failure while waiting is silent: the look every ten minutes says it.
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from django.db import connections

from huismus.core import cloud_backups
from huismus.core.backup import sample_data_in_use

from . import inbox

# How often to glance at a folder.
FOLDER_SECONDS = 5
# How long one Dropbox wait stays open. Short enough to notice soon that
# the user chose another place; Dropbox allows 30 to 480.
DROPBOX_SECONDS = 120
# After a failure: wait a minute, then twice as long each time, at most
# the ten minutes of the safety net.
RETRY_SECONDS = 60
MAX_RETRY_SECONDS = int(inbox.INTERVAL.total_seconds())

logger = logging.getLogger("huismus.receipts")


@dataclass
class Watch:
    """What the thread remembers between two rounds."""

    place: tuple = ()  # (source, folder) watched: another place starts over
    known: frozenset | None = None  # folder: the files at the last glance
    cursor: str = ""  # Dropbox: where the folder stood
    retry: int = 0  # seconds to wait after the last failure, 0 when none


def ready_files(folder) -> frozenset:
    """The files a look would take now (names and sizes), the same rules
    as inbox.LocalFolder: top level, no symlinks, not hidden, still for a
    minute. OSError when the folder can't be read."""
    return frozenset((name, size) for name, size in folder.names() if not name.startswith("."))


def round_(watch: Watch) -> float:
    """One round: glance or wait, and a look when something is new. The
    seconds to sleep before the next round."""
    status = inbox.load()
    if not inbox.is_on(status) or sample_data_in_use():
        watch.place = ()
        return FOLDER_SECONDS
    place = (status.source, status.folder or status.dropbox_folder)
    if place != watch.place:
        watch.place, watch.known, watch.cursor, watch.retry = place, None, "", 0
    if status.source == inbox.FOLDER:
        return _glance(watch, status)
    if status.source == inbox.DROPBOX:
        return _wait(watch, status)
    return FOLDER_SECONDS


def _glance(watch: Watch, status: inbox.Status) -> float:
    try:
        now = ready_files(inbox.LocalFolder(Path(status.folder), status.done_folder))
    except OSError:
        # The look every ten minutes says the folder is gone.
        watch.known = None
        return FOLDER_SECONDS
    # The first glance only remembers: the look at start
    # (inbox.start_thread) or after choosing the folder takes what is there.
    new = watch.known is not None and now - watch.known
    if new and inbox.fetching():
        # A look is running; whether it saw the new file is unknown, so
        # the next glance tries again.
        return FOLDER_SECONDS
    # Remembered before the look: a file it leaves (not a receipt) won't
    # start another one.
    watch.known = now
    if new:
        inbox.fetch_when_open()
    return FOLDER_SECONDS


def _wait(watch: Watch, status: inbox.Status) -> float:
    dropbox = cloud_backups.remote()
    if not isinstance(dropbox, cloud_backups.Dropbox):
        return FOLDER_SECONDS
    try:
        if not watch.cursor:
            watch.cursor = dropbox.latest_cursor(status.dropbox_folder)
        changed, backoff = dropbox.wait_for_change(watch.cursor, DROPBOX_SECONDS)
        if changed and _still(watch):
            # Where the folder stands now, before the look: a receipt that
            # arrives during the look wakes the next wait. The look's own
            # moves to Opgehaald wake it once more; that look finds nothing.
            watch.cursor = dropbox.latest_cursor(status.dropbox_folder)
            inbox.fetch_when_open()
    except cloud_backups.CloudError as error:
        # Unreachable, a cursor Dropbox forgot, the folder removed (the
        # next look makes it again): start over in a while.
        watch.cursor = ""
        watch.retry = min(watch.retry * 2 or RETRY_SECONDS, MAX_RETRY_SECONDS)
        logger.info("Wachten op Dropbox mislukt: %s", error)
        return watch.retry
    watch.retry = 0
    return backoff


def _still(watch: Watch) -> bool:
    """After a wait of minutes: still on, still this place, no sample data.
    Turned off, unlinked or another place chosen meanwhile: no look."""
    status = inbox.load()
    place = (status.source, status.folder or status.dropbox_folder)
    return inbox.is_on(status) and not sample_data_in_use() and place == watch.place


def start_thread() -> threading.Thread:
    """Started next to inbox.start_thread, by the desktop app and gunicorn's
    one worker."""

    def run():
        watch = Watch()
        while True:
            try:
                pause = round_(watch)
            except Exception:
                logger.exception("Bonnetjes in de gaten houden mislukt")
                pause = RETRY_SECONDS
            finally:
                connections.close_all()
            time.sleep(pause)

    thread = threading.Thread(target=run, name="huismus-receipts-watch", daemon=True)
    thread.start()
    return thread
