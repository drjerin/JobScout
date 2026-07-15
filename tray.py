"""System-tray icon for Job Scout.

Optional. Launched only when ``app.py`` is started with ``--tray``. Requires
``pystray`` and ``Pillow`` — both listed as extras in ``pyproject.toml``.

The tray icon exposes four actions:

* Open Dashboard  — opens ``http://host:port`` in the default browser
* Run Now         — fires a one-off scout run (same as the UI's "Run now")
* Pause / Resume  — flips the in-process scheduler on and off
* Quit            — cleanly stops the tray icon and returns control to
                     ``app.py``, which shuts down the Flask thread

The tray runs on the process's main thread (pystray requires this on Windows
and macOS), so ``app.py`` starts Flask in a background thread when ``--tray``
is used.
"""
from __future__ import annotations

import webbrowser
from typing import Callable

import logs

_log = logs.get("scout.tray")


def _make_image():
    """Return a simple procedural PIL Image for the tray icon.

    Avoids shipping a binary asset in the repo. Rendered as a rounded blue
    square with a white ``JS`` monogram — legible at 16x16.
    """
    from PIL import Image, ImageDraw, ImageFont

    size = 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, size - 4, size - 4), radius=24, fill=(37, 99, 235))
    try:
        font = ImageFont.truetype("Arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "JS", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1] - 4),
              "JS", fill="white", font=font)
    return img


def run(
    host: str,
    port: int,
    on_run_now: Callable[[], None],
    on_toggle_pause: Callable[[], bool],
    on_quit: Callable[[], None],
) -> None:
    """Run the tray icon on the calling thread (blocks until Quit).

    ``on_toggle_pause`` should return ``True`` when the scheduler is now
    paused, ``False`` when it's running.
    """
    try:
        import pystray
        from pystray import MenuItem as Item
    except ImportError:
        _log.warning("pystray/Pillow not installed; skipping tray icon. "
                     "Install with `pip install pystray Pillow`.")
        return

    url = f"http://{host}:{port}"

    def _open(_icon, _item):
        webbrowser.open(url)

    def _run_now(_icon, _item):
        try:
            on_run_now()
        except Exception as e:  # noqa: BLE001
            _log.warning("tray run-now failed: %s", e)

    def _toggle(icon, _item):
        try:
            paused = on_toggle_pause()
            icon.notify("Scheduler paused" if paused else "Scheduler resumed",
                        "Job Scout")
        except Exception as e:  # noqa: BLE001
            _log.warning("tray toggle failed: %s", e)

    def _quit(icon, _item):
        try:
            on_quit()
        finally:
            icon.stop()

    menu = pystray.Menu(
        Item(f"Open Dashboard  ({url})", _open, default=True),
        Item("Run now", _run_now),
        Item("Pause / Resume schedule", _toggle),
        pystray.Menu.SEPARATOR,
        Item("Quit", _quit),
    )
    icon = pystray.Icon("jobscout", _make_image(), "Job Scout", menu)
    _log.info("tray icon running (host=%s port=%d)", host, port)
    icon.run()
