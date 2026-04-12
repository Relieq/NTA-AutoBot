import io
import logging
import queue
import sys
import traceback
import os


def _safe_put(q, item):
    try:
        q.put_nowait(item)
    except queue.Full:
        # Drop messages when queue is full to keep engine responsive.
        pass
    except Exception:
        pass


class QueueTextIO(io.TextIOBase):
    def __init__(self, event_queue, stream_name="stdout"):
        super().__init__()
        self.event_queue = event_queue
        self.stream_name = stream_name
        self._buffer = ""

    def write(self, s):
        if not s:
            return 0
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                _safe_put(
                    self.event_queue,
                    {
                        "type": "log",
                        "stream": self.stream_name,
                        "message": line,
                    },
                )
        return len(s)

    def flush(self):
        if self._buffer.strip():
            _safe_put(
                self.event_queue,
                {
                    "type": "log",
                    "stream": self.stream_name,
                    "message": self._buffer.strip(),
                },
            )
        self._buffer = ""


def _repair_logging_streams(fallback_stream):
    """Fix StreamHandler instances that reference invalid streams (common in windowed frozen child process)."""
    try:
        loggers = [logging.getLogger()]
        for logger_obj in logging.Logger.manager.loggerDict.values():
            if isinstance(logger_obj, logging.Logger):
                loggers.append(logger_obj)

        for lg in loggers:
            for handler in getattr(lg, "handlers", []):
                if not isinstance(handler, logging.StreamHandler):
                    continue
                stream = getattr(handler, "stream", None)
                if stream is None or not hasattr(stream, "write"):
                    handler.setStream(fallback_stream)
    except Exception:
        pass


def run_bot_worker(
    event_queue,
    state_queue,
    stop_event,
    pause_event,
    map_prefer_existing=None,
    map_new_city_xy=None,
    command_queue=None,
    adb_port=5555,
):
    # Đảm bảo cwd luôn là thư mục app root để các đường dẫn tương đối (config/assets/third_party)
    # hoạt động đúng cả khi chạy source và khi chạy bản đóng gói.
    if getattr(sys, "frozen", False):
        app_root = os.path.dirname(sys.executable)
    else:
        app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    try:
        os.chdir(app_root)
    except Exception:
        pass

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = QueueTextIO(event_queue, stream_name="stdout")
    sys.stderr = QueueTextIO(event_queue, stream_name="stderr")
    _repair_logging_streams(sys.stderr)

    from main import run_bot_loop

    def on_state(state):
        _safe_put(state_queue, state)

    def on_runtime_event(event):
        if not isinstance(event, dict):
            return
        payload = dict(event)
        payload.setdefault("type", "runtime_event")
        _safe_put(event_queue, payload)

    try:
        _safe_put(event_queue, {"type": "engine", "status": "STARTING"})
        run_bot_loop(
            stop_event=stop_event,
            pause_event=pause_event,
            state_callback=on_state,
            event_callback=on_runtime_event,
            map_prefer_existing=map_prefer_existing,
            map_new_city_xy=map_new_city_xy,
            command_queue=command_queue,
            adb_port=adb_port,
        )
        _safe_put(event_queue, {"type": "engine", "status": "STOPPED"})
    except Exception:
        _safe_put(
            event_queue,
            {
                "type": "log",
                "stream": "stderr",
                "message": traceback.format_exc(),
            },
        )
        _safe_put(event_queue, {"type": "engine", "status": "CRASHED"})
    finally:
        try:
            from core.device import DeviceManager
            DeviceManager.stop_adb_server_global()
        except Exception:
            pass
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        sys.stdout = old_stdout
        sys.stderr = old_stderr

