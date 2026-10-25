"""Serve the generic demonstration on loopback. No persistence or collection API."""

import argparse
import functools
import http.server
import os
import threading
import webbrowser
from pathlib import Path


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open the local page in your browser")
    parser.add_argument("--port", type=int, default=int(os.environ.get("JOB_VIEWER_PORT", "8766")))
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent / "demo"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    url = f"http://127.0.0.1:{args.port}/"
    with Server(("127.0.0.1", args.port), handler) as server:
        print(url + " — Ctrl-C to stop", flush=True)
        if args.open:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
