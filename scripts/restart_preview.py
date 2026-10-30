#!/usr/bin/env python3
"""Export atlas (optional rebuild) and restart the local static preview server.

Usage (from repo root):
  python scripts/restart_preview.py
  python scripts/restart_preview.py --rebuild
  python scripts/restart_preview.py --port 8080 --year 672 --lang ja
  python scripts/restart_preview.py --no-export --no-open

Opens the system browser (not Cursor Simple Browser). Ctrl+C stops the server.
"""

from __future__ import annotations

import argparse
import gzip
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

# Compress these types when the client accepts gzip.
GZIP_TYPES = {
    ".html",
    ".js",
    ".css",
    ".json",
    ".svg",
    ".mjs",
    ".map",
}


def run_py(script: Path) -> None:
    print(f">> python {script.relative_to(ROOT)}")
    subprocess.check_call([sys.executable, str(script)], cwd=ROOT)


def pids_on_port(port: int) -> list[int]:
    """Best-effort: find PIDs listening on TCP port (Windows + Unix)."""
    pids: set[int] = set()
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                text=True,
                errors="ignore",
            )
        except (OSError, subprocess.CalledProcessError):
            return []
        needle = f":{port} "
        for line in out.splitlines():
            if needle not in line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                continue
    else:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"],
                text=True,
                errors="ignore",
            )
            for tok in out.split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    continue
        except (OSError, subprocess.CalledProcessError):
            pass
    # Never kill ourselves
    me = os.getpid()
    return [p for p in sorted(pids) if p != me and p > 0]


def kill_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.check_call(
                    ["taskkill", "/PID", str(pid), "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            print(f">> stopped pid {pid}")
        except (OSError, subprocess.CalledProcessError):
            print(f">> could not stop pid {pid} (may already be gone)")


def free_port(port: int) -> None:
    pids = pids_on_port(port)
    if not pids:
        return
    print(f">> port {port} in use by {pids}; stopping…")
    kill_pids(pids)
    time.sleep(0.4)


def serve(port: int, open_url: str | None = None) -> None:
    os.chdir(WEB)

    class GzipHandler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def do_GET(self) -> None:
            path = Path(self.translate_path(self.path))
            if (
                path.is_file()
                and path.suffix.lower() in GZIP_TYPES
                and "gzip" in (self.headers.get("Accept-Encoding") or "")
            ):
                try:
                    raw = path.read_bytes()
                except OSError:
                    self.send_error(404, "File not found")
                    return
                payload = gzip.compress(raw, compresslevel=6)
                ctype = self.guess_type(str(path))
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Vary", "Accept-Encoding")
                self.end_headers()
                self.wfile.write(payload)
                return
            super().do_GET()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), GzipHandler)
    print(f">> serving {WEB} (gzip on)", flush=True)
    print(f">> http://127.0.0.1:{port}/  (Ctrl+C to stop)", flush=True)
    if open_url:
        # Open after bind; never block the server thread on the browser.
        def _open() -> None:
            time.sleep(0.3)
            print(f">> open {open_url}", flush=True)
            try:
                webbrowser.open(open_url)
            except Exception as exc:  # noqa: BLE001
                print(f">> browser open failed: {exc}", flush=True)

        threading.Thread(target=_open, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n>> stopped", flush=True)
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export + restart local web preview")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--rebuild", action="store_true", help="run build_db.py before export")
    parser.add_argument("--no-export", action="store_true", help="skip export_web_data.py")
    parser.add_argument("--no-open", action="store_true", help="do not open system browser")
    parser.add_argument("--year", type=int, default=None, help="optional ?year=")
    parser.add_argument("--lang", choices=("zh", "ja", "en"), default=None)
    args = parser.parse_args()

    # Unbuffered-ish logs when piped by the agent terminal.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    if args.rebuild:
        run_py(ROOT / "db" / "build_db.py")
    if not args.no_export:
        run_py(ROOT / "db" / "export_web_data.py")

    free_port(args.port)

    q = []
    if args.year is not None:
        q.append(f"year={args.year}")
    if args.lang:
        q.append(f"lang={args.lang}")
    url = f"http://127.0.0.1:{args.port}/"
    if q:
        url += "?" + "&".join(q)

    serve(args.port, open_url=None if args.no_open else url)


if __name__ == "__main__":
    main()
