import subprocess
import time
import os
import signal

def test_kill():
    started = time.monotonic()
    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    
    process = subprocess.Popen(
        ["sh", "-c", "sleep 10 & sleep 10"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs
    )
    
    try:
        process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
        print(f"Killed after {time.monotonic() - started:.2f}s")
        out, err = process.communicate()
        print("Done")

test_kill()
