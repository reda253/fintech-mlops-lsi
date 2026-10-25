"""Disposable proxy contract fixture; never a replacement for the real Gateway."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time


class GatewayStub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/notifications/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"event: ping\ndata: frontend-ci\n\n")
            self.wfile.flush()
            # The first event must reach the client before this connection closes.
            time.sleep(4)
            return
        self.respond()

    def do_POST(self):
        self.respond()

    def respond(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
        denied = self.path == "/api/v1/denied"
        missing = not self.path.startswith("/api/v1/")
        status = 401 if denied else 404 if missing else 200
        payload = json.dumps({
            "status": status, "path": self.path, "method": self.command,
            "authorization": self.headers.get("Authorization"),
            "correlationId": self.headers.get("X-Correlation-Id"), "body": body,
        }).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if denied:
            self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), GatewayStub).serve_forever()
