# Antigravity Windows Bridge

Local Windows tooling for MCP agents and authenticated HTTP clients. System
information and process/window listings are enabled by default. Registry,
memory, desktop capture, browser control, input and code execution require
explicit capabilities. REST and MCP use the same policy and handlers.

## Install and verify

Windows and Python 3.10+ are required. Start as an ordinary user.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_bridge.py
```

In another terminal:

```powershell
.\.venv\Scripts\python.exe bridge_client.py
.\.venv\Scripts\python.exe bridge_client.py /api/system/info
```

The HTTP server binds to `127.0.0.1:13371`. Every request requires a session
bearer token. The CLI reads it from `~/.antigravity_windows_bridge/token` on
each invocation. The server prints the path, never the token. A restart rotates
tokens. Old unauthenticated HTTP clients must migrate to the CLI or supply
`Authorization: Bearer <token>` themselves.

## Capabilities

Set environment variables **before** starting the bridge or its MCP process.
Settings apply to both transports. Unknown capabilities fail startup.

| Capability | Operations | Additional restriction |
|---|---|---|
| `read` | System, processes, connections, visible windows | Always enabled |
| `registry` | Read registry values | `WIN_BRIDGE_REGISTRY_ROOTS` |
| `registry_write` | Write registry string values | `WIN_BRIDGE_REGISTRY_ROOTS` |
| `memory_read` | Read process memory, max 1 MiB | `WIN_BRIDGE_ALLOWED_PIDS` |
| `memory_write` | Write process memory, max 1 MiB | `WIN_BRIDGE_ALLOWED_PIDS` |
| `terminate` | Terminate a process | `WIN_BRIDGE_ALLOWED_PIDS` |
| `screen` | Capture desktop | Explicit opt-in |
| `input` | Keyboard/mouse control | Explicit opt-in |
| `ui` | Focus windows, show message boxes | Explicit opt-in |
| `browser` | CDP and paired extension control | Explicit opt-in |
| `wmi` | WMI queries | Explicit opt-in |
| `exec` | Trusted Python scripts | Explicit opt-in; full user authority |

For example, allow registry reads under one dedicated subtree:

```powershell
$env:WIN_BRIDGE_CAPABILITIES = 'registry'
$env:WIN_BRIDGE_REGISTRY_ROOTS = 'HKCU\Software\BridgeExample'
.\.venv\Scripts\python.exe run_bridge.py
```

PID lists use commas; registry roots use semicolons. A missing target allowlist
permits no targets. Settings in `.env.example` are documentation; they must be
supplied as process environment variables and are not automatically loaded.

## MCP

Configure a local stdio server with absolute paths:

```json
{
  "mcpServers": {
    "windows_bridge": {
      "command": "C:/path/to/bridge/.venv/Scripts/python.exe",
      "args": ["C:/path/to/bridge/mcp_server.py"]
    }
  }
}
```

MCP runs in its own process and does not need the HTTP server. Configure its
capability environment explicitly in your MCP client. This release uses the
MCP Python SDK v2. Tool responses are consistently JSON objects; older MCP
integrations that expected lists or bare strings must adapt to the REST-style
response envelopes. Disabled operations return errors even if their tools are
listed by the client.

## Chrome extension pairing

1. Load `chrome_extension/` as an unpacked extension and copy its extension ID.
2. Set `WIN_BRIDGE_CAPABILITIES=browser` and set
   `WIN_BRIDGE_ALLOWED_ORIGINS=chrome-extension://<extension-id>`.
3. Start the HTTP bridge. Open the extension popup and paste the contents of
   `~/.antigravity_windows_bridge/extension-token` into the pairing field.
4. Pair again after restarting the bridge. Never paste the normal API token.

The extension token is restricted to its command/result channel. The browser
channel and the standalone Chrome Bridge both default to port 13371; run one
at a time. A timed-out mutation may have executed: inspect state before retrying.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```

CI checks Python 3.10 and 3.12 on Windows. Tests use an ephemeral loopback port,
private temporary tokens and memory owned by the test process. They do not
capture your screen, terminate existing processes or modify existing registry
keys. See [SECURITY.md](SECURITY.md) for trust boundaries and operational limits.

## License

MIT; see [LICENSE](LICENSE).
