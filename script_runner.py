"""Opt-in trusted script execution. Process isolation is not a sandbox."""
import json
import subprocess
import sys
import threading
from security import APIError

MAX_SCRIPT = 64 * 1024
MAX_OUTPUT = 256 * 1024
TIMEOUT = 10
HARNESS = '''
import contextlib, io, json, sys, traceback
script = json.loads(sys.stdin.readline())
out, err = io.StringIO(), io.StringIO()
env = {"result": {}}
success, error = True, ""
try:
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        exec(compile(script, "<bridge-script>", "exec"), env, env)
except BaseException:
    success, error = False, traceback.format_exc()
print(json.dumps({"success": success, "stdout": out.getvalue(), "stderr": err.getvalue(),
    "error": error, "result": env.get("result", {})}, default=str))
'''


def execute_script(script, timeout=TIMEOUT):
    if not isinstance(script, str) or not script.strip() or len(script.encode("utf-8")) > MAX_SCRIPT:
        raise APIError("Script must contain 1 to 65536 UTF-8 bytes")
    # The harness waits for input until the Job Object has been attached.
    process = subprocess.Popen([sys.executable, "-I", "-u", "-c", HARNESS],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    job = None
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    exceeded = threading.Event()
    lock = threading.Lock()

    def drain(stream, name):
        while True:
            block = stream.read(4096)
            if not block:
                break
            with lock:
                if sum(map(len, chunks.values())) + len(block) > MAX_OUTPUT:
                    exceeded.set()
                    process.kill()
                    break
                chunks[name].extend(block)

    readers = []
    try:
        if sys.platform == "win32":
            import win32api
            import win32job
            job = win32job.CreateJobObject(None, "")
            limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
            limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            limits["ProcessMemoryLimit"] = 256 * 1024 * 1024
            win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
            win32job.AssignProcessToJobObject(job, int(process._handle))
        for name in chunks:
            reader = threading.Thread(target=drain, args=(getattr(process, name), name), daemon=True)
            reader.start()
            readers.append(reader)
        process.stdin.write((json.dumps(script) + "\n").encode("utf-8"))
        process.stdin.close()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise APIError("Script exceeded its time limit; execution was terminated", 408) from None
        if job is not None:
            win32api.CloseHandle(job)
            job = None
        for reader in readers:
            reader.join(timeout=2)
        if exceeded.is_set():
            raise APIError("Script exceeded its output limit", 413)
        try:
            result = json.loads(chunks["stdout"])
        except (ValueError, UnicodeError):
            raise APIError("Script worker failed or returned invalid output", 500) from None
        if not isinstance(result, dict):
            raise APIError("Invalid script result", 500)
        return result
    finally:
        if process.poll() is None:
            process.kill()
        if job is not None:
            win32api.CloseHandle(job)
        process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()
