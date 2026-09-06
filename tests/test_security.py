import ctypes
import http.client
import json
import os
import threading
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security import APIError, Policy, registry_path, write_session_token
from server import APIRouter, BridgeServer, router


@pytest.fixture
def live_server():
    server = BridgeServer(("127.0.0.1", 0), policy=Policy(), token="a" * 64, extension_token="b" * 64)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(server, method="GET", path="/api/status", *, headers=None, body=None, token="a" * 64):
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    supplied = {"Authorization": "Bearer " + token}
    supplied.update(headers or {})
    try:
        client.request(method, path, body, supplied)
        response = client.getresponse()
        return response.status, dict(response.getheaders()), json.loads(response.read())
    finally:
        client.close()


def test_auth_host_origin_and_token_scope(live_server):
    assert request(live_server)[0] == 200
    assert request(live_server, token="wrong")[0] == 401
    assert request(live_server, token="b" * 64)[0] == 401
    assert request(live_server, headers={"Host": "attacker.example"})[0] == 403
    status, headers, _ = request(live_server, headers={"Origin": "https://attacker.example"})
    assert status == 403
    assert "Access-Control-Allow-Origin" not in headers
    assert request(live_server, method="OPTIONS", headers={"Origin": "null"})[0] == 403


def test_explicit_origin_is_exact(live_server):
    live_server.policy = Policy(origins=frozenset({"http://localhost:3000"}))
    status, headers, _ = request(live_server, headers={"Origin": "http://localhost:3000"})
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert request(live_server, headers={"Origin": "http://localhost:3000.evil"})[0] == 403


@pytest.mark.parametrize("body", [b'[]', b'null', b'{"x":NaN}', b'{"x":1,"x":2}', b'\xff', b'{'])
def test_invalid_json_is_rejected(live_server, body):
    assert request(live_server, "POST", "/api/system/exec", headers={"Content-Type": "application/json"}, body=body)[0] == 400


def test_body_and_transfer_limits(live_server):
    for headers, expected in [({"Content-Length": "-1"}, 400), ({"Content-Length": "bad"}, 400),
        ({"Content-Length": "1048577"}, 413), ({"Transfer-Encoding": "chunked"}, 400),
        ({"Content-Type": "text/plain"}, 415)]:
        assert request(live_server, "POST", "/api/system/exec", headers=headers, body=b'{}')[0] == expected


def test_duplicate_headers_are_rejected(live_server):
    client = http.client.HTTPConnection("127.0.0.1", live_server.server_port, timeout=3)
    try:
        client.putrequest("GET", "/api/status")
        client.putheader("Authorization", "Bearer " + "a" * 64)
        client.putheader("Authorization", "Bearer " + "a" * 64)
        client.endheaders()
        assert client.getresponse().status == 401
    finally:
        client.close()


def test_policy_enforced_before_handler():
    routes = APIRouter()
    called = []

    @routes.post("/exec", capability="exec")
    def execute(data):
        called.append(True)
        return {}

    with pytest.raises(APIError, match="disabled"):
        routes.dispatch("POST", "/exec", {}, Policy())
    assert not called
    routes.dispatch("POST", "/exec", {}, Policy(frozenset({"exec"})))
    assert called


def test_target_allowlists_are_deny_by_default():
    policy = Policy(frozenset({"memory_read", "registry_write"}), frozenset({123}), (registry_path(r"HKCU\Software\BridgeTests"),))
    policy.authorize("memory_read", {"pid": 123})
    with pytest.raises(APIError):
        policy.authorize("memory_read", {"pid": 124})
    policy.authorize("registry_write", {"hive": "HKCU", "sub_key": r"Software\BridgeTests\Child"})
    for path in [r"Software\BridgeTestsElsewhere", r"Software\BridgeTests\..\Other", "Software"]:
        with pytest.raises(APIError):
            policy.authorize("registry_write", {"hive": "HKCU", "sub_key": path})


def test_bad_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("WIN_BRIDGE_CAPABILITIES", "everything")
    with pytest.raises(ValueError):
        Policy.from_env()
    monkeypatch.setenv("WIN_BRIDGE_CAPABILITIES", "")
    monkeypatch.setenv("WIN_BRIDGE_ALLOWED_ORIGINS", "*")
    with pytest.raises(ValueError):
        Policy.from_env()


def test_tokens_rotate_and_have_private_permissions(tmp_path):
    path = tmp_path / "token"
    first = write_session_token(path)
    second = write_session_token(path)
    assert first != second and len(second) == 64
    assert path.read_text() == second
    if os.name == "nt":
        import win32security
        descriptor = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
        assert descriptor.GetSecurityDescriptorDacl().GetAceCount() == 1
    else:
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "nt", reason="Windows API integration")
def test_rest_and_mcp_share_read_only_policy(live_server, monkeypatch):
    import mcp_server
    from runtime import load_endpoints
    load_endpoints()
    monkeypatch.setattr(mcp_server, "policy", Policy())
    assert request(live_server, "POST", "/api/system/exec", headers={"Content-Type": "application/json"}, body=b'{"script":"raise RuntimeError()"}')[0] == 403
    with pytest.raises(APIError, match="disabled"):
        mcp_server.execute_python_script("raise RuntimeError()")
    with pytest.raises(APIError, match="disabled"):
        mcp_server.terminate_process(os.getpid())


@pytest.mark.skipif(os.name != "nt", reason="Windows API integration")
def test_memory_roundtrip_uses_owned_buffer():
    import api_memory
    pid = os.getpid()
    data = ctypes.create_string_buffer(b"abcd")
    policy = Policy(frozenset({"memory_read", "memory_write"}), frozenset({pid}))
    args = {"pid": pid, "address": hex(ctypes.addressof(data)), "size": 4}
    assert router.dispatch("POST", "/api/memory/read", args, policy)["data_hex"] == "61626364"
    router.dispatch("POST", "/api/memory/write", {**args, "data_hex": "65666768"}, policy)
    assert data.raw[:4] == b"efgh"
    for size in [-1, 0, api_memory.MAX_TRANSFER + 1]:
        with pytest.raises(APIError):
            api_memory.checked_address(args["address"], size)


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
def test_script_result_timeout_and_output_limit():
    from script_runner import execute_script
    result = execute_script("print('hello'); result['value'] = 42")
    assert result["stdout"] == "hello\n" and result["result"] == {"value": 42}
    with pytest.raises(APIError, match="time limit"):
        execute_script("import time; time.sleep(30)", timeout=0.2)
    with pytest.raises(APIError, match="output limit"):
        execute_script("print('x' * 400000)")


def test_expired_extension_results_are_not_retained():
    from api_chrome_ext import ExtensionBridge
    ext = ExtensionBridge()
    with pytest.raises(APIError, match="expired"):
        ext.resolve("unknown", {"result": "late"})
    assert ext._results == {}
    with pytest.raises(APIError, match="timed out"):
        ext.submit("navigate", timeout=0.001, url="about:blank")
    assert ext.poll() is None
    assert not ext._events and not ext._results
