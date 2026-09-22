import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

import pywintypes
import win32api
import win32clipboard
import win32com.client
import win32con
import win32gui


SESSION_FILE = Path.home() / "explorer-session.json"
DEFAULT_WATCH_INTERVAL = 60.0  # seconds
WATCH_STABILITY_CHECKS = 2

shell = win32com.client.Dispatch("Shell.Application")
keys = win32com.client.Dispatch("WScript.Shell")


def get_windows():
    """Return {physical_window_hwnd: [tab_location, ...]}."""
    grouped = defaultdict(list)

    for tab in shell.Windows():
        try:
            if os.path.basename(str(tab.FullName)).lower() != "explorer.exe":
                continue

            try:
                location = str(tab.Document.Folder.Self.Path or "")
            except Exception:
                location = ""

            # LocationURL is useful for some non-filesystem Shell locations.
            location = location or str(tab.LocationURL or "")

            if location:
                grouped[int(tab.HWND)].append(location)

        except Exception:
            # Explorer may close or navigate while COM is being enumerated.
            pass

    return dict(grouped)


def canonical_location(location):
    """Normalize filesystem paths and file:// URLs for comparisons."""
    value = str(location or "").strip()

    if not value:
        return ""

    if value.lower().startswith("file:"):
        parsed = urlparse(value)
        path = unquote(parsed.path).replace("/", "\\")

        if parsed.netloc:
            value = f"\\\\{parsed.netloc}{path}"
        else:
            # file:///C:/Folder becomes /C:/Folder after URL parsing.
            if len(path) >= 3 and path[0] == "\\" and path[2] == ":":
                path = path[1:]

            value = path

    # Keep virtual Shell identifiers comparable while normalizing normal paths.
    if value.startswith("::") or value.lower().startswith("shell:"):
        return value.casefold()

    value = os.path.expandvars(os.path.expanduser(value))
    return os.path.normcase(os.path.normpath(value))


def location_count(hwnd, target):
    expected = canonical_location(target)

    return sum(
        canonical_location(actual) == expected
        for actual in get_windows().get(hwnd, [])
    )


def current_session():
    """Return the current session in a stable physical-window order."""
    windows = get_windows()

    # Sorting by HWND avoids rewrites caused only by COM enumerating physical
    # windows in a different order. Tab order remains whatever IShellWindows
    # reports, which is useful but is not a documented left-to-right guarantee.
    return [windows[hwnd] for hwnd in sorted(windows)]


def session_fingerprint(session):
    """Return a normalized, immutable representation for change detection."""
    return tuple(
        tuple(canonical_location(location) for location in tabs)
        for tabs in session
    )


def write_session(session, verb="Saved"):
    """Atomically write a session snapshot to the JSON file."""
    temp = SESSION_FILE.with_suffix(".json.tmp")

    temp.write_text(
        json.dumps(session, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    temp.replace(SESSION_FILE)

    print(
        f"{verb} {sum(map(len, session))} tab(s) "
        f"in {len(session)} window(s) to {SESSION_FILE}"
    )


def save_session():
    write_session(current_session())


def watch_session(interval=DEFAULT_WATCH_INTERVAL):
    """Continuously update the JSON after Explorer's session changes."""
    if interval <= 0:
        raise SystemExit("Watch interval must be greater than zero")

    session = current_session()
    write_session(session)
    last_saved = session_fingerprint(session)

    pending_fingerprint = None
    pending_session = None
    stable_checks = 0

    print(
        f"Watching Explorer every {interval:g} second(s). "
        "Press Ctrl+C to stop."
    )

    try:
        while True:
            time.sleep(interval)

            session = current_session()
            fingerprint = session_fingerprint(session)

            if fingerprint == last_saved:
                pending_fingerprint = None
                pending_session = None
                stable_checks = 0
                continue

            if fingerprint == pending_fingerprint:
                stable_checks += 1
                pending_session = session
            else:
                pending_fingerprint = fingerprint
                pending_session = session
                stable_checks = 1

            # Explorer's COM view can be temporarily incomplete while tabs are
            # opening, closing, or navigating. Requiring the same changed state
            # twice prevents most transient snapshots from replacing the file.
            if stable_checks >= WATCH_STABILITY_CHECKS:
                write_session(pending_session, verb="Updated")

                last_saved = pending_fingerprint
                pending_fingerprint = None
                pending_session = None
                stable_checks = 0

    except KeyboardInterrupt:
        print("\nStopped watching Explorer.")


def tap_alt():
    """Hack that often allows SetForegroundWindow to succeed."""
    win32api.keybd_event(
        win32con.VK_MENU,
        0,
        0,
        0,
    )

    win32api.keybd_event(
        win32con.VK_MENU,
        0,
        win32con.KEYEVENTF_KEYUP,
        0,
    )


def activate(hwnd):
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError(f"Explorer window {hwnd} no longer exists")

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except pywintypes.error:
        pass

    time.sleep(0.25)

    if win32gui.GetForegroundWindow() != hwnd:
        tap_alt()
        time.sleep(0.08)

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)

        time.sleep(0.3)

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError(
            "Could not focus the intended Explorer window. "
            "Click the Python console and run restore again."
        )


def send(text, delay=0.2):
    keys.SendKeys(text)
    time.sleep(delay)


def put_on_clipboard(text):
    """Put text on the Windows clipboard, retrying if it is temporarily locked."""
    for _ in range(40):
        try:
            win32clipboard.OpenClipboard()

            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(
                    str(text),
                    win32con.CF_UNICODETEXT,
                )
            finally:
                win32clipboard.CloseClipboard()

            return

        except pywintypes.error:
            time.sleep(0.05)

    raise RuntimeError("Could not open the clipboard")


def wait_for_new_window(before, timeout=12):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        current = get_windows()
        new_handles = set(current) - before

        ready_handles = [
            hwnd
            for hwnd in new_handles
            if win32gui.IsWindow(hwnd) and current.get(hwnd)
        ]

        if ready_handles:
            foreground = win32gui.GetForegroundWindow()

            if foreground in ready_handles:
                return foreground

            return ready_handles[0]

        time.sleep(0.1)

    raise RuntimeError("Explorer did not create a new physical window")


def create_window():
    before = set(get_windows())

    if before:
        source = win32gui.GetForegroundWindow()

        if source not in before:
            source = next(iter(before))

        activate(source)

        # Ctrl+N: new physical Explorer window
        send("^n", 0.4)

    else:
        subprocess.Popen(["explorer.exe"])

    hwnd = wait_for_new_window(before)

    # Let the address bar and tab strip finish initializing.
    time.sleep(0.5)

    return hwnd


def wait_for_new_tab(hwnd, old_count, timeout=8):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if len(get_windows().get(hwnd, [])) > old_count:
            # COM sees the tab before its controls always accept input.
            time.sleep(0.5)
            return

        time.sleep(0.1)

    raise RuntimeError(
        f"Explorer window {hwnd} did not create a new tab"
    )


def wait_for_location(hwnd, location, minimum_count, timeout=12):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if location_count(hwnd, location) >= minimum_count:
            return True

        time.sleep(0.15)

    return False


def navigate(hwnd, location, minimum_count=1, retries=3):
    """Navigate the active tab and verify that Explorer reached the target."""
    if location_count(hwnd, location) >= minimum_count:
        return

    for attempt in range(1, retries + 1):
        activate(hwnd)
        time.sleep(0.3)

        put_on_clipboard(location)

        # Separate delays matter: a just-created Home tab often drops the first
        # address-bar shortcut or paste if they arrive too quickly.
        send("^l", 0.3)
        send("^v", 0.3)
        send("{ENTER}", 0.6)

        if wait_for_location(hwnd, location, minimum_count):
            return

        if attempt < retries:
            print(
                f"Navigation attempt {attempt}/{retries} did not reach "
                f"{location!r}; retrying..."
            )
        else:
            print(
                f"Navigation attempt {attempt}/{retries} did not reach "
                f"{location!r}."
            )

        send("{ESC}", 0.2)

    observed = get_windows().get(hwnd, [])

    raise RuntimeError(
        f"Explorer did not navigate a tab to {location!r}. "
        f"Locations currently reported for window {hwnd}: {observed!r}"
    )


def load_session():
    if not SESSION_FILE.exists():
        raise SystemExit(
            f"Session file does not exist: {SESSION_FILE}"
        )

    session = json.loads(
        SESSION_FILE.read_text(encoding="utf-8")
    )

    if not isinstance(session, list):
        raise SystemExit(
            "Session JSON must contain a list of window lists"
        )

    cleaned = []

    for window_index, saved_tabs in enumerate(session, start=1):
        if not isinstance(saved_tabs, list):
            raise SystemExit(
                f"Window {window_index} in the session JSON is not a list"
            )

        tabs = [
            str(value).strip()
            for value in saved_tabs
            if str(value).strip()
        ]

        if tabs:
            cleaned.append(tabs)

    return cleaned


def close_active_tab(hwnd):
    """
    Try to close the currently active Explorer tab.

    This is used after a newly-created tab fails to restore so that a stray
    Home/error tab is not left behind.
    """
    try:
        activate(hwnd)
        send("^w", 0.4)
    except Exception as error:
        print(
            f"Warning: could not close failed Explorer tab: {error}"
        )


def restore_session():
    """
    Restore the saved Explorer session.

    A single missing, inaccessible, or otherwise broken location no longer
    aborts the entire restore. Failed tabs are recorded and the script moves
    on to the remaining tabs and windows.
    """
    session = load_session()

    total_tabs = sum(len(tabs) for tabs in session)

    print(
        "Restoring with Explorer keyboard shortcuts. "
        "Do not use the keyboard or mouse while it runs.\n"
        "Warning: the clipboard will be overwritten.\n"
    )

    print(
        f"Session contains {total_tabs} tab(s) "
        f"in {len(session)} window(s).\n"
    )

    restored_tabs = 0
    failed_tabs = []

    for window_index, saved_tabs in enumerate(session, start=1):
        print(
            f"Restoring window {window_index}/{len(session)} "
            f"({len(saved_tabs)} tab(s))..."
        )

        try:
            hwnd = create_window()

        except Exception as error:
            print(
                f"  Could not create Explorer window {window_index}: "
                f"{error}"
            )

            for location in saved_tabs:
                failed_tabs.append(
                    (
                        window_index,
                        location,
                        f"Could not create Explorer window: {error}",
                    )
                )

            continue

        # ------------------------------------------------------------
        # First tab in the physical Explorer window
        # ------------------------------------------------------------
        first_location = saved_tabs[0]

        try:
            navigate(
                hwnd,
                first_location,
                minimum_count=1,
            )

            restored_tabs += 1

            print(
                f"  Restored tab 1/{len(saved_tabs)}: "
                f"{first_location}"
            )

        except Exception as error:
            print(
                f"  FAILED tab 1/{len(saved_tabs)}: "
                f"{first_location}"
            )
            print(f"    {error}")

            failed_tabs.append(
                (
                    window_index,
                    first_location,
                    str(error),
                )
            )

        # ------------------------------------------------------------
        # Remaining tabs
        # ------------------------------------------------------------
        for tab_index, location in enumerate(
            saved_tabs[1:],
            start=2,
        ):
            old_count = len(
                get_windows().get(hwnd, [])
            )

            old_target_count = location_count(
                hwnd,
                location,
            )

            try:
                activate(hwnd)

                # Ctrl+T: create and switch to a new tab
                send("^t", 0.4)

                wait_for_new_tab(
                    hwnd,
                    old_count,
                )

            except Exception as error:
                print(
                    f"  FAILED tab {tab_index}/{len(saved_tabs)}: "
                    f"{location}"
                )
                print(
                    f"    Could not create/switch to new tab: {error}"
                )

                failed_tabs.append(
                    (
                        window_index,
                        location,
                        f"Could not create/switch to new tab: {error}",
                    )
                )

                # Something may have gone wrong with this entire Explorer
                # window, but try the next saved tab anyway.
                continue

            try:
                # Require one additional occurrence. This also handles
                # duplicate paths in the JSON and recognizes Home
                # immediately when Home is genuinely the saved target.
                navigate(
                    hwnd,
                    location,
                    minimum_count=old_target_count + 1,
                )

                restored_tabs += 1

                print(
                    f"  Restored tab {tab_index}/{len(saved_tabs)}: "
                    f"{location}"
                )

            except Exception as error:
                print(
                    f"  FAILED tab {tab_index}/{len(saved_tabs)}: "
                    f"{location}"
                )
                print(f"    {error}")

                failed_tabs.append(
                    (
                        window_index,
                        location,
                        str(error),
                    )
                )

                # This tab was created specifically for this location.
                # If navigation failed, close the stray Home/error tab and
                # continue with the next saved location.
                close_active_tab(hwnd)

        print()

    # ----------------------------------------------------------------
    # Final summary
    # ----------------------------------------------------------------
    failed_count = len(failed_tabs)

    print("=" * 70)
    print("RESTORE FINISHED")
    print("=" * 70)

    print(
        f"Successfully restored: {restored_tabs}/{total_tabs} tab(s)"
    )

    print(
        f"Failed:                {failed_count}/{total_tabs} tab(s)"
    )

    if failed_tabs:
        print("\nFailed locations:")

        for number, (
            window_index,
            location,
            error,
        ) in enumerate(
            failed_tabs,
            start=1,
        ):
            print(
                f"\n  {number}. Window {window_index}"
            )
            print(
                f"     Location: {location}"
            )
            print(
                f"     Reason:   {error}"
            )

        print(
            "\nThe restore continued after these failures."
        )
        print(
            "Missing Temp folders or other deleted/inaccessible folders "
            "can safely appear in this list."
        )

    else:
        print(
            "\nAll saved tabs were restored successfully."
        )


def interactive_menu():
    """Prompt for one of the existing watch or restore actions."""
    print("What do you want to do?")
    print("  1. Watch and save every set amount of seconds")
    print("  2. Restore")

    choice = input(
        "Choose 1 or 2: "
    ).strip()

    if choice == "1":
        raw_interval = input(
            f"Save interval in seconds "
            f"[{DEFAULT_WATCH_INTERVAL:g}]: "
        ).strip()

        interval = DEFAULT_WATCH_INTERVAL

        if raw_interval:
            try:
                interval = float(raw_interval)
            except ValueError as error:
                raise SystemExit(
                    "Watch interval must be a number of seconds"
                ) from error

        watch_session(interval)

    elif choice == "2":
        restore_session()

    else:
        raise SystemExit(
            "Choice must be 1 or 2"
        )


def usage():
    return (
        "Usage:\n"
        "  py explorer_session_watch_interactive.py save\n"
        "  py explorer_session_watch_interactive.py restore\n"
        "  py explorer_session_watch_interactive.py "
        "watch [interval_seconds]\n"
        "  py explorer_session_watch_interactive.py menu"
    )


def main():
    if len(sys.argv) < 2:
        raise SystemExit(
            usage()
        )

    mode = sys.argv[1].lower()

    if mode == "save" and len(sys.argv) == 2:
        save_session()

    elif mode == "restore" and len(sys.argv) == 2:
        restore_session()

    elif mode == "watch" and len(sys.argv) in {2, 3}:
        interval = DEFAULT_WATCH_INTERVAL

        if len(sys.argv) == 3:
            try:
                interval = float(
                    sys.argv[2]
                )
            except ValueError as error:
                raise SystemExit(
                    "Watch interval must be a number of seconds"
                ) from error

        watch_session(interval)

    elif mode == "menu" and len(sys.argv) == 2:
        interactive_menu()

    else:
        raise SystemExit(
            usage()
        )


if __name__ == "__main__":
    main()
