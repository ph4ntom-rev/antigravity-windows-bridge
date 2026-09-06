"""Authenticated loopback transport with bounded requests and shared policy."""
import json
import logging
import re
import secrets
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs
from security import APIError, Policy, state_directory, write_session_token

HOST, PORT = "127.0.0.1", 13371
MAX_BODY_SIZE, REQUEST_TIMEOUT = 1024 * 1024, 5
audit = logging.getLogger("windows_bridge.audit")


class APIRouter:
    def __init__(self):
        self.routes = {"GET": [], "POST": []}

    def _route(self, method, path, capability):
        def decorate(func):
            self.routes[method].append((re.compile(f"^{path}$"), func, capability))
            return func
        return decorate

    def get(self, path, capability="read"):
        return self._route("GET", path, capability)

    def post(self, path, capability):
        return self._route("POST", path, capability)

    def dispatch(self, method, path, req_data, policy):
        if not isinstance(req_data, dict):
            raise APIError("Request must be a JSON object")
        for pattern, handler, capability in self.routes.get(method.upper(), []):
            match = pattern.fullmatch(path)
            if match:
                try:
                    policy.authorize(capability, req_data)
                    result = handler(req_data, **match.groupdict())
                except Exception:
                    audit.warning("operation=%s capability=%s outcome=failed", handler.__name__, capability)
                    raise
                audit.info("operation=%s capability=%s outcome=completed", handler.__name__, capability)
                return result
        raise APIError("Endpoint not found", 404)


router = APIRouter()


class BridgeServer(ThreadingHTTPServer):
    daemon_threads, allow_reuse_address = True, False

    def __init__(self, address, *, policy, token, extension_token=""):
        if address[0] != HOST:
            raise ValueError("Only 127.0.0.1 is supported")
        if len(token) < 32 or (extension_token and (len(extension_token) < 32 or extension_token == token)):
            raise ValueError("Independent tokens of at least 32 characters are required")
        self.policy, self.token, self.extension_token = policy, token, extension_token
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, BridgeHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("Non-finite JSON number")


class BridgeHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT)

    def log_message(self, format, *args):
        pass

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin in self.server.policy.origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _send_response(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.close_connection = True
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            pass

    def _boundary(self, authenticate=True):
        hosts = self.headers.get_all("Host", [])
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if len(hosts) != 1 or hosts[0] not in allowed:
            raise APIError("Invalid Host", 403)
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] not in self.server.policy.origins):
            raise APIError("Origin is not allowed", 403)
        if not authenticate:
            return
        auth = self.headers.get_all("Authorization", [])
        if len(auth) != 1:
            raise APIError("Bearer authentication required", 401)
        if secrets.compare_digest(auth[0].encode(), ("Bearer " + self.server.token).encode()):
            return
        if self.server.extension_token and secrets.compare_digest(auth[0].encode(), ("Bearer " + self.server.extension_token).encode()):
            if (self.command, self.path) in {("GET", "/api/ext/poll"), ("GET", "/api/ext/status"), ("POST", "/api/ext/result")}:
                return
        raise APIError("Invalid bearer token or token scope", 401)

    def handle_request(self, method):
        try:
            self._boundary()
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise APIError("Invalid request target")
            path = parsed.path.rstrip("/")
            req_data = parse_qs(parsed.query, max_num_fields=100) if method == "GET" else {}
            if self.headers.get("Transfer-Encoding"):
                raise APIError("Transfer-Encoding is not supported")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1:
                raise APIError("Duplicate Content-Length")
            content_length = int(lengths[0]) if lengths else 0
            if content_length < 0:
                raise APIError("Invalid Content-Length")
            if content_length > MAX_BODY_SIZE:
                raise APIError("Payload too large", 413)
            if method == "POST":
                if self.headers.get_content_type() != "application/json":
                    raise APIError("Content-Type must be application/json", 415)
                raw = self.rfile.read(content_length)
                if len(raw) != content_length:
                    raise APIError("Incomplete request body")
                req_data = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object, parse_constant=invalid_constant)
                if not isinstance(req_data, dict):
                    raise APIError("Request must be a JSON object")
            if method == "GET" and path == "/api/status":
                result = {"status": "ok", "auth_enabled": True, "capabilities": sorted(self.server.policy.capabilities)}
            else:
                result = router.dispatch(method, path, req_data, self.server.policy)
            self._send_response(result)
        except APIError as exc:
            self._send_response({"error": exc.message}, exc.status)
        except (ValueError, TypeError, UnicodeError):
            self._send_response({"error": "Invalid request data"}, 400)
        except TimeoutError:
            self._send_response({"error": "Request timed out"}, 408)
        except Exception:
            self._send_response({"error": "Internal server error"}, 500)

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_OPTIONS(self):
        try:
            self._boundary(authenticate=False)
            if self.headers.get("Origin") not in self.server.policy.origins:
                raise APIError("Origin is not allowed", 403)
            self._send_response({}, 200)
        except APIError as exc:
            self._send_response({"error": exc.message}, exc.status)


def start_server():
    policy = Policy.from_env()
    directory = state_directory()
    token = secrets.token_hex(32)
    extension_token = secrets.token_hex(32) if "browser" in policy.capabilities else ""
    with BridgeServer((HOST, PORT), policy=policy, token=token, extension_token=extension_token) as server:
        # A second instance must fail to bind before it can rotate live tokens.
        write_session_token(directory / "token", token)
        if extension_token:
            write_session_token(directory / "extension-token", extension_token)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
        print(f"[Windows Bridge] http://{HOST}:{PORT}; token file: {directory / 'token'}", flush=True)
        server.serve_forever()
