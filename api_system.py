import psutil
import platform
import wmi
import win32api
import win32con
from server import router, APIError


@router.get(r"/api/system/info", capability="read")
def get_sys_info(req, **kwargs):
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total": psutil.virtual_memory().total,
        "memory_available": psutil.virtual_memory().available,
        "disk_usage": {
            part.mountpoint: psutil.disk_usage(part.mountpoint).percent
            for part in psutil.disk_partitions() if 'cdrom' not in part.opts
        }
    }

@router.get(r"/api/system/processes", capability="read")
def list_processes(req, **kwargs):
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_info']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {"processes": processes, "count": len(processes)}

@router.post(r"/api/system/terminate", capability="terminate")
def terminate_process(req, **kwargs):
    pid = req.get("pid")
    if not pid:
        raise APIError("PID required")
    try:
        p = psutil.Process(int(pid))
        p.terminate()
        return {"success": True, "message": f"Terminated {pid}"}
    except Exception as e:
        raise APIError(str(e))

@router.get(r"/api/system/wmi_query", capability="wmi")
def wmi_query(req, **kwargs):
    query = req.get("query", [""])[0]
    if not query:
        raise APIError("Query string required")
    import pythoncom
    pythoncom.CoInitialize()
    try:
        results = []
        for item in wmi.WMI().query(query):
            properties = {}
            for prop in item.properties:
                properties[prop] = getattr(item, prop)
            results.append(properties)
        return {"results": results}
    except Exception as e:
        raise APIError(str(e))
    finally:
        pythoncom.CoUninitialize()
