from mcp.server.fastmcp import FastMCP
import platform
import psutil
import wmi
import winreg
import ctypes
import io
import sys
import traceback
import win32gui
import win32con
from PIL import ImageGrab
import base64
import time

mcp = FastMCP("Antigravity Windows Bridge")
c_wmi = wmi.WMI()
kernel32 = ctypes.windll.kernel32

# --- SYSTEM TOOLS ---

@mcp.tool()
def get_system_info() -> dict:
    """Get basic system hardware and OS information."""
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total": psutil.virtual_memory().total,
        "memory_available": psutil.virtual_memory().available
    }

@mcp.tool()
def get_processes() -> list:
    """Get a list of currently running processes with their CPU and memory usage."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'username']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes

@mcp.tool()
def terminate_process(pid: int) -> str:
    """Terminate a process by its PID."""
    try:
        psutil.Process(pid).terminate()
        return f"Terminated {pid}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def execute_wmi_query(query: str) -> list:
    """Execute a raw WMI query. Example: SELECT * FROM Win32_VideoController"""
    try:
        results = []
        for item in c_wmi.query(query):
            properties = {}
            for prop in item.properties:
                properties[prop] = str(getattr(item, prop))
            results.append(properties)
        return results
    except Exception as e:
        return [f"Error: {e}"]

# --- FILE SYSTEM & REGISTRY ---

@mcp.tool()
def read_registry(hive: str, sub_key: str, value_name: str) -> dict:
    """Read a registry key. Hive must be HKLM, HKCU, HKCR, HKU, or HKCC."""
    hives = {"HKCR": winreg.HKEY_CLASSES_ROOT, "HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE, "HKU": winreg.HKEY_USERS, "HKCC": winreg.HKEY_CURRENT_CONFIG}
    if hive not in hives: return {"error": "Invalid hive"}
    try:
        with winreg.OpenKey(hives[hive], sub_key) as key:
            value, reg_type = winreg.QueryValueEx(key, value_name)
            return {"value": value, "type": reg_type}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def execute_python_script(script: str) -> dict:
    """DANGEROUS: Execute arbitrary Python code in the bridge host process. Returns stdout/stderr."""
    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    env = {"result": {}}
    success, err_msg = True, ""
    try:
        exec(script, globals(), env)
    except Exception:
        success, err_msg = False, traceback.format_exc()
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return {"success": success, "stdout": out.getvalue(), "stderr": err.getvalue(), "error": err_msg, "result": str(env.get("result", {}))}

# --- UI AUTOMATION ---

@mcp.tool()
def take_screenshot() -> str:
    """Take a screenshot and return as base64 JPEG."""
    try:
        img = ImageGrab.grab()
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def get_windows() -> list:
    """List all visible windows with their HWNDs and titles."""
    windows = []
    def enum_cb(hwnd, results):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            results.append({"hwnd": hwnd, "title": win32gui.GetWindowText(hwnd), "class_name": win32gui.GetClassName(hwnd)})
    win32gui.EnumWindows(enum_cb, windows)
    return windows

@mcp.tool()
def focus_window(hwnd: int) -> str:
    """Bring a window to the foreground by its HWND."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return "Success"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def show_messagebox(title: str, message: str) -> str:
    """Show a native Windows message box."""
    ctypes.windll.user32.MessageBoxW(0, message, title, 0)
    return "Success"

# --- CHROME AUTOMATION ---

@mcp.tool()
def get_chrome_tabs() -> dict:
    """Retrieve all open Chrome tabs via CDP. Chrome must be launched with --remote-debugging-port=9222"""
    import urllib.request, urllib.error, json
    try:
        req_obj = urllib.request.Request("http://127.0.0.1:9222/json")
        with urllib.request.urlopen(req_obj, timeout=2) as response:
            tabs = json.loads(response.read().decode())
            return {"tabs": tabs, "count": len(tabs)}
    except urllib.error.URLError:
        return {"error": "Cannot connect to Chrome. Is it running with --remote-debugging-port=9222 ?"}

@mcp.tool()
def evaluate_chrome_js(tab_id: str, js_code: str = "document.body.innerText") -> dict:
    """Evaluate JS in a specific tab and return the text/result."""
    import urllib.request, urllib.error, json
    try:
        import websocket
    except ImportError:
        return {"error": "websocket-client library is not installed."}
        
    try:
        req_obj = urllib.request.Request("http://127.0.0.1:9222/json")
        with urllib.request.urlopen(req_obj, timeout=2) as response:
            tabs = json.loads(response.read().decode())
    except urllib.error.URLError:
        return {"error": "Cannot connect to Chrome debug port."}
        
    ws_url = next((t.get("webSocketDebuggerUrl") for t in tabs if t.get("id") == tab_id), None)
    if not ws_url:
        return {"error": f"Tab {tab_id} not found."}
        
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
        cmd = {"id": 1, "method": "Runtime.evaluate", "params": {"expression": js_code, "returnByValue": True}}
        ws.send(json.dumps(cmd))
        result = json.loads(ws.recv())
        ws.close()
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run()
