import ctypes
from PIL import ImageGrab
import io
import base64
from server import router, APIError
import win32gui
import win32con

@router.get(r"/api/ui/screenshot")
def get_screenshot(req, **kwargs):
    try:
        img = ImageGrab.grab()
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return {"screenshot_base64": img_str, "format": "jpeg"}
    except Exception as e:
        raise APIError(str(e))

@router.get(r"/api/ui/windows")
def get_windows(req, **kwargs):
    windows = []
    def enum_cb(hwnd, results):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            results.append({
                "hwnd": hwnd,
                "title": win32gui.GetWindowText(hwnd),
                "class_name": win32gui.GetClassName(hwnd),
                "rect": {
                    "left": rect[0],
                    "top": rect[1],
                    "right": rect[2],
                    "bottom": rect[3]
                }
            })
    win32gui.EnumWindows(enum_cb, windows)
    return {"windows": windows, "count": len(windows)}

@router.post(r"/api/ui/window/focus")
def focus_window(req, **kwargs):
    hwnd = req.get("hwnd")
    if not hwnd:
        raise APIError("hwnd required")
    try:
        win32gui.ShowWindow(int(hwnd), win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(int(hwnd))
        return {"success": True}
    except Exception as e:
        raise APIError(str(e))

@router.post(r"/api/ui/messagebox")
def show_messagebox(req, **kwargs):
    title = req.get("title", "Antigravity Bridge")
    message = req.get("message", "")
    ctypes.windll.user32.MessageBoxW(0, message, title, 0)
    return {"success": True}
