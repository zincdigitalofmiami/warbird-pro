#!/usr/bin/env python3
"""
Legacy loopback redirect for the retired standalone Optuna dashboard port.

The old 8080 service used a shared mixed-study SQLite database. Canonical Optuna
state now lives in per-workspace DBs and the operator entrypoint is the hub on
8090. Keep 8080 alive as a local compatibility alias so old bookmarks and VS
Code links still land on the live hub instead of failing.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class RedirectServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        target_host: str,
        target_port: int,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.target_host = target_host
        self.target_port = target_port


class RedirectHandler(BaseHTTPRequestHandler):
    server_version = "WarbirdOptunaCompat/1.0"

    def _location(self) -> str:
        parsed = urlsplit(self.path)
        path = parsed.path or "/"
        if path in {"", "/dashboard", "/dashboard/"} or path.startswith("/dashboard/"):
            path = "/"
        target = f"http://{self.server.target_host}:{self.server.target_port}{path}"
        if parsed.query:
            target += f"?{parsed.query}"
        return target

    def _redirect(self, include_body: bool = True) -> None:
        location = self._location()
        self.send_response(307)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(f"Redirecting to {location}\n".encode("utf-8"))

    def do_GET(self) -> None:
        self._redirect()

    def do_HEAD(self) -> None:
        self._redirect(include_body = False)

    def do_POST(self) -> None:
        self._redirect()

    def do_PUT(self) -> None:
        self._redirect()

    def do_PATCH(self) -> None:
        self._redirect()

    def do_DELETE(self) -> None:
        self._redirect()

    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description = "Warbird legacy Optuna port redirect")
    parser.add_argument("--listen-host", default = "localhost")
    parser.add_argument("--listen-port", type = int, default = 8080)
    parser.add_argument("--target-host", default = "localhost")
    parser.add_argument("--target-port", type = int, default = 8090)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = RedirectServer(
        (args.listen_host, args.listen_port),
        RedirectHandler,
        target_host = args.target_host,
        target_port = args.target_port,
    )
    print(
        "Warbird Optuna 8080 compatibility alias -> "
        f"http://{args.target_host}:{args.target_port}"
    )
    try:
        server.serve_forever(poll_interval = 0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
