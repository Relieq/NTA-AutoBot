import io
import queue
import sys
import traceback


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


def run_bot_worker(
    event_queue,
    state_queue,
    stop_event,
    pause_event,
    map_prefer_existing=None,
    map_new_city_xy=None,
    command_queue=None,
):
    from main import run_bot_loop

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = QueueTextIO(event_queue, stream_name="stdout")
    sys.stderr = QueueTextIO(event_queue, stream_name="stderr")

    def on_state(state):
        _safe_put(state_queue, state)

    try:
        _safe_put(event_queue, {"type": "engine", "status": "STARTING"})
        run_bot_loop(
            stop_event=stop_event,
            pause_event=pause_event,
            state_callback=on_state,
            map_prefer_existing=map_prefer_existing,
            map_new_city_xy=map_new_city_xy,
            command_queue=command_queue,
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
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        sys.stdout = old_stdout
        sys.stderr = old_stderr

