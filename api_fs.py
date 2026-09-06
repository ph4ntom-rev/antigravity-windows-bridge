import os
import winreg
import ctypes
from server import router, APIError

@router.post(r"/api/fs/read_registry", capability="registry")
def read_registry(req, **kwargs):
    hive_name = req.get("hive")
    sub_key = req.get("sub_key")
    value_name = req.get("value_name")
    
    hives = {
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKU": winreg.HKEY_USERS,
        "HKCC": winreg.HKEY_CURRENT_CONFIG
    }
    
    if hive_name not in hives:
        raise APIError(f"Invalid hive. Choose from {list(hives.keys())}")
        
    try:
        with winreg.OpenKey(hives[hive_name], sub_key) as key:
            value, reg_type = winreg.QueryValueEx(key, value_name)
            return {"value": value, "type": reg_type}
    except Exception as e:
        raise APIError(str(e))

@router.post(r"/api/fs/write_registry", capability="registry_write")
def write_registry(req, **kwargs):
    hive_name = req.get("hive")
    sub_key = req.get("sub_key")
    value_name = req.get("value_name")
    value = req.get("value")
    
    hives = {
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKU": winreg.HKEY_USERS,
        "HKCC": winreg.HKEY_CURRENT_CONFIG
    }
    
    if hive_name not in hives:
        raise APIError(f"Invalid hive. Choose from {list(hives.keys())}")
        
    try:
        with winreg.OpenKey(hives[hive_name], sub_key, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, str(value))
            return {"success": True}
    except Exception as e:
        raise APIError(str(e))

@router.post(r"/api/system/exec", capability="exec")
def exec_script(req, **kwargs):
    from script_runner import execute_script
    return execute_script(req.get("script", ""))
