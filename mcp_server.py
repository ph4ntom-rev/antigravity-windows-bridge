"""Local stdio MCP adapter. All operations use the REST route policy."""
from mcp.server.mcpserver import MCPServer
from security import Policy
from runtime import load_endpoints
from server import router

mcp = MCPServer("Antigravity Windows Bridge")
policy = Policy.from_env()


def _call(method, path, data):
    load_endpoints()
    return router.dispatch(method, path, data, policy)


@mcp.tool()
def get_system_info() -> dict:
    """Get hardware and OS information."""
    return _call("GET", "/api/system/info", {})


@mcp.tool()
def get_processes() -> dict:
    """List processes."""
    return _call("GET", "/api/system/processes", {})


@mcp.tool()
def terminate_process(pid: int) -> dict:
    """Terminate an explicitly allowed PID; requires terminate capability."""
    return _call("POST", "/api/system/terminate", {"pid": pid})


@mcp.tool()
def execute_wmi_query(query: str) -> dict:
    """Run a WMI read query; requires wmi capability."""
    return _call("GET", "/api/system/wmi_query", {"query": [query]})


@mcp.tool()
def read_registry(hive: str, sub_key: str, value_name: str) -> dict:
    """Read an explicitly allowed registry subtree."""
    return _call("POST", "/api/fs/read_registry", {"hive": hive, "sub_key": sub_key, "value_name": value_name})


@mcp.tool()
def write_registry(hive: str, sub_key: str, value_name: str, value: str) -> dict:
    """Write a string in an explicitly allowed registry subtree."""
    return _call("POST", "/api/fs/write_registry", {"hive": hive, "sub_key": sub_key, "value_name": value_name, "value": value})


@mcp.tool()
def execute_python_script(script: str) -> dict:
    """Execute trusted Python in a bounded child process; requires exec capability. This is not a sandbox."""
    return _call("POST", "/api/system/exec", {"script": script})


@mcp.tool()
def take_screenshot() -> dict:
    """Capture the desktop; requires screen capability."""
    return _call("GET", "/api/ui/screenshot", {})


@mcp.tool()
def get_windows() -> dict:
    """List visible windows."""
    return _call("GET", "/api/ui/windows", {})


@mcp.tool()
def focus_window(hwnd: int) -> dict:
    """Focus a window; requires ui capability."""
    return _call("POST", "/api/ui/window/focus", {"hwnd": hwnd})


@mcp.tool()
def show_messagebox(title: str, message: str) -> dict:
    """Display a message; requires ui capability."""
    return _call("POST", "/api/ui/messagebox", {"title": title, "message": message})


@mcp.tool()
def get_chrome_tabs() -> dict:
    """List Chrome tabs; requires browser capability."""
    return _call("GET", "/api/chrome/tabs", {})


@mcp.tool()
def evaluate_chrome_js(tab_id: str, js_code: str = "document.title") -> dict:
    """Execute JavaScript in a tab; requires browser capability."""
    return _call("POST", "/api/chrome/evaluate", {"tab_id": tab_id, "js_code": js_code})


@mcp.tool()
def read_memory(pid: int, address: str, size: int = 4) -> dict:
    """Read bounded memory from an allowed PID."""
    return _call("POST", "/api/memory/read", {"pid": pid, "address": address, "size": size})


@mcp.tool()
def write_memory(pid: int, address: str, data_hex: str) -> dict:
    """Write bounded memory to an allowed PID."""
    return _call("POST", "/api/memory/write", {"pid": pid, "address": address, "data_hex": data_hex})


if __name__ == "__main__":
    mcp.run(transport="stdio")
