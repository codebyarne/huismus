# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop app (SPEC.md M11): double-click, and a window opens.

At start: one window with "Huismus start…", then Django is set up, the
migrations run and the server starts on 127.0.0.1, on port 8765 or a free port
(desktop/server.py), and the window opens Huismus with a token that is new
at every start (huismus/core/desktop.py). If that fails, the window says so, with
"Opnieuw proberen" and "Logbestand bewaren". Once it runs, a daily backup
goes to the folder the user chose. Closing the window stops the server;
nothing keeps running.
"""

import logging
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time

from desktop import lock, paths, screens
from desktop.lock import AlreadyOpen
from desktop.server import MigrationFailed, Server

logger = logging.getLogger("huismus.desktop")
BACKUP_CHECK_SECONDS = 60 * 60


def main():
    if getattr(sys, "frozen", False):
        _use_the_apps_own_pango()
    if "--check" in sys.argv and not os.environ.get("HUISMUS_DATA_DIR"):
        # A check migrates and creates the user: never on your own records
        # unless asked for.
        os.environ["HUISMUS_DATA_DIR"] = tempfile.mkdtemp(prefix="huismus-check-")
    data = paths.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    _log_to_file()
    _configure_django(data)
    if "--check" in sys.argv:
        sys.exit(check())
    lang = screens.language(_system_languages())
    app = App(lang, data)
    if sys.platform == "win32" and not _ready_on_windows(app):
        return

    import webview

    if sys.platform == "darwin":
        from desktop import webkit

        webkit.install()
    if sys.platform == "win32":
        from desktop import webview2

        webview2.install()
    webview.settings["ALLOW_DOWNLOADS"] = True

    app.window = webview.create_window(
        "Huismus",
        html=screens.starting(lang),
        js_api=app.api,
        width=1280,
        height=860,
        min_size=(400, 560),
    )
    try:
        # The title of pywebview's own save dialog ("Logbestand bewaren").
        webview.start(app.boot, localization={"global.saveFile": screens.TEXTS[lang]["save_file"]})
    finally:
        app.server.stop()


def _ready_on_windows(app) -> bool:
    """Before any window: WebView2 must be there, and this start takes the
    lock, so App.boot's own take_lock does nothing more. A second start
    brings the first one's window forward and ends, as Windows users expect
    (on macOS the system does that itself). If that window can't be found,
    the start goes on without the lock, and boot's take_lock fails again
    and shows "al-geopend"."""
    from desktop import windows

    if not windows.webview2_installed():
        windows.offer_webview2(app.lang)
        return False
    try:
        app.take_lock()
    except AlreadyOpen:
        pid = lock.holder(paths.lock_file(app.data))
        if pid is not None and windows.bring_forward(pid):
            return False
    return True


class App:
    def __init__(self, lang, data):
        self.lang = lang
        self.data = data
        self.server = Server()
        self.window = None
        self.api = Api(self)
        self._lock = None
        self._background = None

    def boot(self):
        """In pywebview's own thread, after the window is shown."""
        try:
            self.take_lock()
            url = self.server.start()
        except Exception as error:
            logger.exception("Huismus kon niet starten")
            pending = _pending_update() if isinstance(error, MigrationFailed) else {}
            if pending:
                # The first start after an update (huismus/core/updates.py).
                self.window.load_html(screens.update_failed(self.lang, **_failed_update(pending)))
            else:
                self.window.load_html(screens.failed(self.lang, _code(error)))
            return
        _updated_if_pending()
        from huismus.assistants import claude
        from huismus.core import updates

        claude.write_address(url)
        claude.remove_saved()

        updates.installer = self.install_update
        updates.precheck = self.check_replaceable
        if updates.install_at_start():
            # A version downloaded earlier: installed before anyone works
            # (huismus-intern/besluiten.md, 2026-11-04). The window closes.
            return
        from huismus.core.desktop import START_PATH

        if sys.platform == "win32":
            from desktop import webview2

            webview2.serve(url)
        self.window.load_url(f"{url}{START_PATH}?token={os.environ['HUISMUS_WINDOW_TOKEN']}")
        if self._background is None:
            self._background = threading.Thread(target=_every_hour, daemon=True)
            self._background.start()

    def install_update(self, package, sha256):
        """core.updates.installer: hands package to desktop/updater.py and
        closes, so the script can replace the app."""
        from desktop import updater
        from huismus.core import updates

        app = self.check_replaceable()
        updater.start(package, sha256, app)
        version = updates.load_status().pending.get("to_version", "")
        self.window.load_html(screens.updating(self.lang, version))
        # A moment later, so the request that started it has its answer;
        # the script waits for this process to end, however long it takes.
        threading.Timer(1.0, self.window.destroy).start()

    def check_replaceable(self):
        """core.updates.precheck: the installed app, or UpdateError when
        it can't be replaced where it is."""
        from desktop import updater
        from huismus.core.updates import UpdateError

        app = updater.installed_app()
        if app is None:
            raise UpdateError("not-an-app")
        if not os.access(app.parent, os.W_OK):
            raise UpdateError("not-writable")
        return app

    def take_lock(self):
        """Never two copies on the same administration (SPEC.md M11). Once
        taken (on Windows before the window, _ready_on_windows), again
        does nothing."""
        if self._lock is None:
            self._lock = lock.acquire(paths.lock_file(self.data))


def check() -> int:
    """`Huismus.app/Contents/MacOS/Huismus --check`, or `Huismus.exe
    --check` on Windows: starts everything except the window, checks the
    lock, opens the first page as the window would and makes
    a PDF, so a build can be checked without anyone looking at it. On an
    empty temporary administration, unless HUISMUS_DATA_DIR says which."""
    import urllib.request

    from huismus.core.desktop import START_PATH

    server = Server()
    try:
        _check_the_lock()
        url = server.start()
        window = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        start = f"{url}{START_PATH}?token={os.environ['HUISMUS_WINDOW_TOKEN']}"
        with window.open(start, timeout=30) as page:
            assert page.status == 200 and page.url == f"{url}/", page.url
        from django.urls import reverse

        from huismus.documents.models import Document

        # An issued document's own PDF when there is one (a copy of an
        # administration, or demo_data), else WeasyPrint on its own.
        issued = Document.objects.filter(status="issued").first()
        if issued is not None:
            with window.open(url + reverse("documents:pdf", args=[issued.pk]), timeout=60) as page:
                pdf = page.read()
        else:
            import weasyprint

            pdf = weasyprint.HTML(string="<p>Huismus</p>").write_pdf()
        assert pdf.startswith(b"%PDF"), "geen PDF"
        _check_the_certificates()
    except Exception:
        logger.exception("Controle mislukt")
        print("Controle mislukt; zie", paths.log_file())  # noqa: T201
        return 1
    finally:
        server.stop()
    print("Huismus werkt:", url, f"PDF van {len(pdf)} bytes")  # noqa: T201
    return 0


def _check_the_certificates():
    """HTTPS works on a computer without Homebrew. On a Mac the root
    certificates come from inside the app (SSL_CERT_FILE, _configure_django);
    on every platform the list of them isn't empty."""
    import ssl

    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        cafile = ssl.get_default_verify_paths().cafile or ""
        assert cafile.startswith(str(paths.bundle_dir())), f"certificaten buiten de app: {cafile}"
    assert ssl.create_default_context().cert_store_stats()["x509_ca"] > 0, "geen certificaten"


def _check_the_lock():
    """The lock against opening twice, which works differently on Windows
    and macOS (desktop/lock.py): a second attempt must fail."""
    path = paths.lock_file(paths.data_dir())
    held = lock.acquire(path)
    try:
        # On Windows the id sits beside the locked byte, readable by others.
        assert lock.holder(path) == os.getpid(), "het slot zegt niet wie het heeft"
        lock.acquire(path).close()
    except AlreadyOpen:
        return
    finally:
        held.close()
    raise AssertionError("Huismus kon twee keer geopend worden")


class Api:
    """What the error screen's buttons (desktop/screens.py) and "Kiezen…" on
    Instellingen → Back-ups call."""

    def __init__(self, app):
        self._app = app

    def retry(self):
        self._app.window.load_html(screens.starting(self._app.lang))
        threading.Thread(target=self._app.boot, daemon=True).start()

    def save_log(self):
        import webview

        target = self._app.window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="huismus.log"
        )
        if target:
            shutil.copyfile(paths.log_file(), target if isinstance(target, str) else target[0])

    def restore_before_update(self):
        """ "Back-up terugzetten" on the screen after a failed update. The
        server stays off: this version would try the same migration again."""
        from pathlib import Path

        from django.db import connections

        from huismus.core import updates
        from huismus.core.backup import restore_backup

        pending = updates.load_status().pending
        backup = pending["backup"]
        try:
            connections.close_all()
            restore_backup(Path(backup))
        except Exception:
            logger.exception("Terugzetten na een update mislukt")
            self._app.window.load_html(screens.restore_failed(self._app.lang, backup))
            return
        failed = _failed_update(pending)
        self._app.window.load_html(
            screens.update_restored(
                self._app.lang, previous=failed["previous"], moment=failed["moment"]
            )
        )

    def open_previous_release(self):
        """In the system's browser: the version before the failed update."""
        import webbrowser

        from huismus.core import updates

        previous = updates.load_status().pending.get("from_version", "")
        webbrowser.open(updates.release_page(previous))

    def choose_folder(self):
        """ "Kiezen…" on Instellingen → Back-ups (core/app.js): the system's
        folder dialog. The page puts the path in its form; saving checks it."""
        import webview

        chosen = self._app.window.create_file_dialog(webview.FileDialog.FOLDER)
        if not chosen:
            return None
        return chosen if isinstance(chosen, str) else chosen[0]


def _every_hour():
    """When the app opens and, while it stays open, every hour: a backup if
    today has none yet (huismus/core/auto_backups.py), and a look for a new
    version once a day if that's on, downloaded ahead for the next start
    (huismus/core/updates.py)."""
    from huismus.core import auto_backups, updates

    while True:
        try:
            auto_backups.run_if_due()
        except Exception:
            logger.exception("Back-up mislukt")
        try:
            updates.check_if_due()
            updates.prepare()
        except Exception:
            logger.exception("Zoeken naar een nieuwe versie mislukt")
        time.sleep(BACKUP_CHECK_SECONDS)


def _pending_update() -> dict:
    """The update whose migrations just failed: one is pending, and this is
    the version it went to (not the previous one, reinstalled by hand).
    Django is set up by now (desktop/server.py, before migrating)."""
    try:
        from huismus.core import updates

        pending = updates.load_status().pending
        if pending and pending["to_version"] == updates.current_version():
            return pending
    except Exception:
        logger.exception("De update-status is niet te lezen")
    return {}


def _failed_update(pending) -> dict:
    from pathlib import Path

    from huismus.core.backup import archive_created_at
    from huismus.core.templatetags.backups import moment

    try:
        when = moment(archive_created_at(Path(pending["backup"])))
    except Exception:
        # Unreadable: the file's name, which carries the time too.
        when = Path(pending["backup"]).name
    return {"to": pending["to_version"], "previous": pending["from_version"], "moment": when}


def _updated_if_pending():
    """The migrations ran: the update is done, and the overview says so."""
    from huismus.core import updates

    pending = updates.load_status().pending
    if not pending:
        return
    # Not updated: the script couldn't replace the app and opened the old one
    # again (desktop/updater.py), or the previous version was reinstalled.
    # Either way the downloaded file is gone (the script removes it).
    if pending["to_version"] == updates.current_version():
        updates.update_status(pending={}, downloaded={}, just_updated=pending["to_version"])
    else:
        updates.update_status(
            pending={},
            downloaded={},
            not_installed=pending["to_version"],
            # Not again automatically: the button on Updates still can.
            auto_failed=pending["to_version"],
        )


def _code(error) -> str:
    """The short code on the error screen, so a log is easy to match."""
    if isinstance(error, AlreadyOpen):
        return "al-geopend"
    if "database is locked" in str(error):
        return "database-vergrendeld"
    return type(error).__name__


def _configure_django(data):
    os.environ["DJANGO_SETTINGS_MODULE"] = "huismus.config.settings"
    os.environ["HUISMUS_DESKTOP"] = "true"
    os.environ["HUISMUS_DATA_DIR"] = str(data)
    os.environ["HUISMUS_WINDOW_TOKEN"] = secrets.token_urlsafe(32)
    if getattr(sys, "frozen", False):
        # Fontconfig (for WeasyPrint's PDFs) looks for its configuration
        # where Homebrew or MSYS2 put it on the build machine; the app
        # brings its own.
        name = "fonts-windows.conf" if sys.platform == "win32" else "fonts.conf"
        os.environ["FONTCONFIG_FILE"] = str(paths.bundle_dir() / "desktop" / name)
        # OpenSSL looks for root certificates where Homebrew put them on the
        # build machine, so HTTPS (the update check, "Hoe gebruik je
        # Huismus?") fails on a Mac without Homebrew. The app brings
        # certifi's. Windows reads its own certificate store either way.
        # setdefault: an SSL_CERT_FILE someone set on purpose still wins.
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())


def _use_the_apps_own_pango():
    """WeasyPrint opens Pango and friends by name ("pango-1.0",
    "libpango-1.0-0"), and the system looks for such a name in its own
    folders (and Homebrew's or MSYS2's, on a build machine), never inside
    the app, where desktop/huismus.spec put them. So a name is looked up
    only among the app's own copies, before WeasyPrint is imported: a
    computer without Homebrew or MSYS2 gets the same libraries as this one.

    For every cffi user in the process, but WeasyPrint is the only one that
    opens a library by name (pywebview's clr_loader, on Windows, passes
    full paths), and it tries several names and skips those that raise
    OSError. A new dependency that opens a library through cffi must be in
    the app too."""
    import cffi

    folder = paths.bundle_dir()
    suffix = ".dll" if sys.platform == "win32" else ".dylib"
    if sys.platform == "win32":
        # Where Windows looks for the libraries Pango itself needs.
        os.add_dll_directory(str(folder))
    original = cffi.FFI.dlopen

    def dlopen(self, name, flags=0):
        if isinstance(name, str) and "/" not in name and "\\" not in name:
            name = _bundled(folder, name, suffix)
        return original(self, name, flags)

    cffi.FFI.dlopen = dlopen


def _bundled(folder, name, suffix=".dylib") -> str:
    stem = name.removesuffix(suffix)
    for candidate in (f"{stem}{suffix}", f"lib{stem}{suffix}"):
        if (folder / candidate).exists():
            return str(folder / candidate)
    versioned = sorted(folder.glob(f"{stem}.*{suffix.lstrip('.')}"))
    if versioned:
        return str(versioned[0])
    raise OSError(f"{name} zit niet in de app")


def _log_to_file():
    log = paths.log_file()
    log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # A line per step of every PDF otherwise.
    logging.getLogger("weasyprint").setLevel(logging.WARNING)
    logging.getLogger("fontTools").setLevel(logging.WARNING)


def _system_languages() -> list[str]:
    if sys.platform == "darwin":
        from Foundation import NSLocale

        return [str(code) for code in NSLocale.preferredLanguages()]
    if sys.platform == "win32":
        from desktop import windows

        return windows.languages()
    return []
