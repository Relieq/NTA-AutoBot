import io
import logging
import os
import sys


class _NullTextIO(io.TextIOBase):
    def write(self, s):
        return len(s or "")

    def flush(self):
        return None


def _ensure_stdio():
    # Windowed frozen app may run with stdout/stderr = None in child process.
    if sys.stdout is None or not hasattr(sys.stdout, "write"):
        sys.stdout = _NullTextIO()
    if sys.stderr is None or not hasattr(sys.stderr, "write"):
        sys.stderr = _NullTextIO()


def _repair_logging_streams():
    try:
        targets = [logging.getLogger()]
        for obj in logging.Logger.manager.loggerDict.values():
            if isinstance(obj, logging.Logger):
                targets.append(obj)

        for lg in targets:
            for handler in getattr(lg, "handlers", []):
                if not isinstance(handler, logging.StreamHandler):
                    continue
                stream = getattr(handler, "stream", None)
                if stream is None or not hasattr(stream, "write"):
                    handler.setStream(sys.stderr)
    except Exception:
        pass


def _append_dll_paths():
    candidates = []
    if getattr(sys, "frozen", False):
        exe_root = os.path.dirname(sys.executable)
        candidates.extend([
            os.path.join(exe_root, "_internal"),
            os.path.join(exe_root, "_internal", "paddle", "libs"),
            os.path.join(exe_root, "_internal", "paddle", "base"),
        ])

    seen = set()
    valid = []
    for path in candidates:
        ap = os.path.abspath(path)
        if ap in seen or not os.path.isdir(ap):
            continue
        seen.add(ap)
        valid.append(ap)

    if not valid:
        return

    for path in valid:
        try:
            os.add_dll_directory(path)
        except Exception:
            pass

    current_path = os.environ.get("PATH", "")
    prepend = os.pathsep.join(valid)
    if current_path:
        os.environ["PATH"] = prepend + os.pathsep + current_path
    else:
        os.environ["PATH"] = prepend


_ensure_stdio()
_repair_logging_streams()
_append_dll_paths()

# Avoid noisy internal logging exceptions from third-party libs in frozen mode.
logging.raiseExceptions = False

