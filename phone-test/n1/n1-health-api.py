#!/usr/bin/env python3
"""N1 Health Status API - Lightweight HTTP server on port 8090."""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

HEALTH_STATUS_FILE = "/var/run/n1-health-status.json"
HEALTH_API_PORT = 8090
ALLOWED_PREFIX = "192.168.5."


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/health":
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())
            return

        client_ip = self.client_address[0]
        if not client_ip.startswith(ALLOWED_PREFIX) and client_ip != "127.0.0.1":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "access denied"}).encode())
            return

        if not os.path.exists(HEALTH_STATUS_FILE):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "unknown", "error": "health data not available"}).encode())
            return

        try:
            with open(HEALTH_STATUS_FILE, "r") as f:
                data = f.read().strip()
            json.loads(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data.encode())
        except (json.JSONDecodeError, IOError):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "unknown", "error": "health data corrupt"}).encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", HEALTH_API_PORT), HealthHandler)
    server.serve_forever()