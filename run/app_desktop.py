"""The (r, Q) solver as a desktop application.

    python app_desktop.py

Opens one window holding the solver. The HTTP layer that serves the page and
runs the model (``webapp.py``, next to this file) lives inside this process on
a loopback port the operating system picks, so there is nothing to start, stop
or remember to restart: every launch runs the code as it is on disk right now.

    python app_desktop.py --browser     open a browser tab instead of a window
    python app_desktop.py --port 8501   pin the port (otherwise a free one is chosen)

The window needs pywebview:  pip install -r requirements.txt
Without it the launcher says so and falls back to the browser.

The older Tkinter interface, which needs no install at all, is
``../extras/app_tk.py``.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser

from webapp import serve_in_background

TITLE = "The (r, Q) model — iterative solver"
MIN_SIZE = (1040, 680)
SIZE = (1440, 940)


def open_window(url: str, title: str = TITLE) -> bool:
    """Show the page in a native window. False when pywebview is unavailable."""
    try:
        import webview
    except ImportError:
        return False

    webview.create_window(title, url, width=SIZE[0], height=SIZE[1],
                          min_size=MIN_SIZE, text_select=True)
    try:
        webview.start()
    except Exception as exc:                 # no WebView2 runtime, no display…
        print(f"The window could not open ({exc}).", file=sys.stderr)
        return False
    return True


def launch(port: int = 0, prefer_window: bool = True,
           window=open_window, browser=webbrowser.open, wait=None) -> int:
    """Serve on loopback, show the page, and tear the server down afterwards.

    ``window``, ``browser`` and ``wait`` are injectable so the launcher can be
    tested without a display. ``wait`` is what holds the process open in the
    browser fallback, where there is no window close to wait for.
    """
    httpd, thread, url = serve_in_background("127.0.0.1", port)
    print(f"(r, Q) solver on {url}", flush=True)
    try:
        if prefer_window and window(url):
            return 0
        if prefer_window:
            print("pywebview is not installed, so the page is opening in your "
                  "browser instead.\n"
                  "  pip install -r requirements.txt",
                  file=sys.stderr, flush=True)
        browser(url)
        print("Press Ctrl+C to stop.", flush=True)
        try:
            (wait or thread.join)()
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
        return 0
    finally:
        httpd.shutdown()
        httpd.server_close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--browser", action="store_true",
                        help="open a browser tab instead of a window")
    parser.add_argument("--port", type=int, default=0,
                        help="pin the loopback port (default: any free one)")
    args = parser.parse_args(argv)
    return launch(port=args.port, prefer_window=not args.browser)


if __name__ == "__main__":
    sys.exit(main())
