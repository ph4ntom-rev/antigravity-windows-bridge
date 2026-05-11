import json
import threading
import traceback
import re
import os
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = 13371  # Different from IDA bridge
MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status

class APIRouter:
    def __init__(self):
        self.routes = {'GET': [], 'POST': []}

    def get(self, path):
        def decorator(func):
            self.routes['GET'].append((re.compile(f"^{path}$"), func))
            return func
        return decorator

    def post(self, path):
        def decorator(func):
            self.routes['POST'].append((re.compile(f"^{path}$"), func))
            return func
        return decorator

    def dispatch(self, method: str, path: str, req_data: dict):
        for pattern, handler in self.routes.get(method.upper(), []):
            match = pattern.match(path)
            if match:
                return handler(req_data, **match.groupdict())
        raise APIError(f"Endpoint not found: {path}", 404)

router = APIRouter()

class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_response(self, data, status=200):
        try:
            payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            pass

    def handle_request(self, method):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        req_data = parse_qs(parsed.query) if method == "GET" else {}
        
        if method == "POST":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_BODY_SIZE:
                return self._send_response({"error": "Payload Too Large"}, 413)
            if content_length > 0:
                try:
                    req_data = json.loads(self.rfile.read(content_length).decode("utf-8"))
                except json.JSONDecodeError:
                    return self._send_response({"error": "Invalid JSON"}, 400)

        try:
            result = router.dispatch(method, path, req_data)
            self._send_response(result, 200)
        except APIError as api_err:
            self._send_response({"error": api_err.message}, api_err.status)
        except Exception as e:
            self._send_response({"error": "Internal Server Error", "details": str(e), "trace": traceback.format_exc()}, 500)

    def do_GET(self): self.handle_request("GET")
    def do_POST(self): self.handle_request("POST")

def start_server():
    server = ThreadingHTTPServer((HOST, PORT), BridgeHandler)
    print(f"[Windows Bridge] Server ONLINE on http://{HOST}:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    # Import endpoints before starting
    import api_system
    import api_fs
    import api_ui
    start_server()
