import ctypes
from server import router, APIError
import time

# Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t))

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t))

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort))

class INPUT_I(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT))

class INPUT(ctypes.Structure):
    _fields_ = (("type", ctypes.c_ulong),
                ("ii", INPUT_I))

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = ctypes.c_uint
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = ctypes.c_int

@router.post(r"/api/input/keyboard", capability="input")
def synthesize_keyboard(req, **kwargs):
    vk_code = req.get("vk_code")
    action = req.get("action", "press") # press, down, up
    
    if not vk_code:
        raise APIError("vk_code is required")
        
    vk_code = int(str(vk_code), 16) if isinstance(vk_code, str) and vk_code.startswith("0x") else int(vk_code)
    if not 1 <= vk_code <= 254 or action not in {"press", "down", "up"}:
        raise APIError("Invalid key code or action")
    
    def send_key(vk, is_up):
        ii_ = INPUT_I()
        ii_.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if is_up else 0, 0, 0)
        x = INPUT(INPUT_KEYBOARD, ii_)
        if user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x)) != 1:
            raise APIError("SendInput failed; target integrity level may forbid input")

    if action in ["down", "press"]:
        send_key(vk_code, False)
    if action == "press":
        time.sleep(0.05)
    if action in ["up", "press"]:
        send_key(vk_code, True)
        
    return {"success": True, "action": action, "vk_code": vk_code}

@router.post(r"/api/input/mouse_move", capability="input")
def move_mouse(req, **kwargs):
    x = req.get("x")
    y = req.get("y")
    if x is None or y is None:
        raise APIError("x and y are required")
        
    if not user32.SetCursorPos(int(x), int(y)):
        raise APIError("SetCursorPos failed")
    return {"success": True, "x": x, "y": y}
