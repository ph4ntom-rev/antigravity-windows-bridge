"""Fail-closed policy shared by REST and stdio MCP."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import tempfile
from urllib.parse import urlsplit


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


CAPABILITIES = frozenset({"read", "registry", "registry_write", "memory_read",
    "memory_write", "terminate", "input", "ui", "screen", "browser", "wmi", "exec"})


def registry_path(value):
    parts = value.strip().replace("/", "\\").rstrip("\\").split("\\")
    if len(parts) < 2 or parts[0].upper() not in {"HKLM", "HKCU", "HKCR", "HKU", "HKCC"} or any(p in {"", ".", ".."} or "\x00" in p for p in parts):
        raise APIError("Registry root must contain a hive and valid subkey")
    return "\\".join(parts).casefold()


@dataclass(frozen=True)
class Policy:
    capabilities: frozenset = field(default_factory=lambda: frozenset({"read"}))
    pids: frozenset = field(default_factory=frozenset)
    registry_roots: tuple = ()
    origins: frozenset = field(default_factory=frozenset)

    @classmethod
    def from_env(cls):
        capabilities = frozenset({"read"} | {x.strip() for x in os.getenv("WIN_BRIDGE_CAPABILITIES", "").split(",") if x.strip()})
        if capabilities - CAPABILITIES:
            raise ValueError("Unknown WIN_BRIDGE_CAPABILITIES entry")
        pids = frozenset(int(x.strip()) for x in os.getenv("WIN_BRIDGE_ALLOWED_PIDS", "").split(",") if x.strip())
        if any(pid <= 0 for pid in pids):
            raise ValueError("Allowed PIDs must be positive")
        roots = tuple(registry_path(x) for x in os.getenv("WIN_BRIDGE_REGISTRY_ROOTS", "").split(";") if x.strip())
        origins = frozenset(x.strip() for x in os.getenv("WIN_BRIDGE_ALLOWED_ORIGINS", "").split(",") if x.strip())
        for origin in origins:
            value = urlsplit(origin)
            local = value.scheme in {"http", "https"} and value.hostname in {"localhost", "127.0.0.1", "::1"}
            extension = value.scheme == "chrome-extension" and value.hostname and len(value.hostname) == 32 and set(value.hostname) <= set("abcdefghijklmnop")
            if not (local or extension) or value.username or value.password or value.path or value.query or value.fragment:
                raise ValueError("Origins must be exact loopback or Chrome extension origins")
        return cls(capabilities, pids, roots, origins)

    def authorize(self, capability, data):
        if capability not in self.capabilities:
            raise APIError(f"Capability '{capability}' is disabled", 403)
        if capability in {"memory_read", "memory_write", "terminate"}:
            try:
                pid = int(data.get("pid", 0))
            except (ValueError, TypeError):
                raise APIError("Invalid PID") from None
            if isinstance(data.get("pid"), bool) or pid not in self.pids:
                raise APIError("PID is not explicitly allowed", 403)
        if capability in {"registry", "registry_write"}:
            target = registry_path(str(data.get("hive", "")) + "\\" + str(data.get("sub_key", "")))
            if not any(target == root or target.startswith(root + "\\") for root in self.registry_roots):
                raise APIError("Registry path is not explicitly allowed", 403)


def state_directory():
    return Path(os.getenv("WIN_BRIDGE_STATE_DIR", str(Path.home() / ".antigravity_windows_bridge"))).expanduser()


def write_session_token(path, token=None):
    """Restrict a temporary file before writing secret bytes, then replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = token or secrets.token_hex(32)
    fd, temporary = tempfile.mkstemp(prefix=".token-", dir=path.parent)
    try:
        if os.name == "nt":
            import win32api
            import win32con
            import win32security
            import ntsecuritycon
            handle = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
            try:
                sid = win32security.GetTokenInformation(handle, win32security.TokenUser)[0]
            finally:
                handle.Close()
            acl = win32security.ACL()
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, sid)
            win32security.SetNamedSecurityInfo(temporary, win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, acl, None)
        else:
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            fd = None
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return token
    finally:
        if fd is not None:
            os.close(fd)
        if os.path.exists(temporary):
            os.unlink(temporary)
