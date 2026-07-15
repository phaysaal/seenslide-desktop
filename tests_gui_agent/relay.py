"""Tiny HTTP relay: the sandbox app talks to http://127.0.0.1:<port>, we
forward verbatim to the real cloud. Killing the relay IS the network
outage — the app sees connection-refused instantly, exactly like a dead
uplink — and restarting it restores service, letting scenarios exercise
the upload outbox end to end without touching the host network stack.
(identity.py allows plain http for localhost only, so no TLS needed here.)
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te",
              "trailers", "upgrade", "proxy-authenticate",
              "proxy-authorization", "content-length", "host"}


def make_handler(target: str):
    class Relay(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self):
            body = None
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                body = self.rfile.read(length)
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in HOP_BY_HOP}
            try:
                resp = requests.request(
                    self.command, target + self.path, headers=headers,
                    data=body, timeout=60, allow_redirects=False)
            except Exception as e:
                self.send_error(502, f"relay upstream error: {e}")
                return
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                # content-encoding must go too: requests already decoded the
                # body, so forwarding the header would make the app try to
                # zstd/gzip-decode plain JSON
                if k.lower() not in HOP_BY_HOP | {"content-encoding"}:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _forward

        def log_message(self, fmt, *args):
            pass  # quiet; the runner log is the record

    return Relay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--target", default="https://seenslide.com")
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port),
                              make_handler(args.target.rstrip("/")))
    print(f"relay 127.0.0.1:{args.port} -> {args.target}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
