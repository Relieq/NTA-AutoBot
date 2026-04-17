import multiprocessing as mp
import queue
import sys
import os
import json
import time
from datetime import datetime

from core.gui_bridge import run_bot_worker
from core.device import DeviceManager
from config.build_order import BUILD_SEQUENCE

try:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtGui import QColor, QIntValidator, QPainter, QPen
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QSpinBox,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QToolTip,
        QStackedWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover
    print("PySide6 chua duoc cai hoac import loi:", exc)
    print("Hay chay: pip install PySide6")
    sys.exit(1)


class HardDigGridCanvas(QWidget):
    selection_changed = Signal(int, int, int)

    OVERLAY_STATE_COLORS = {
        "OWNED": (80, 170, 255, 90),
        "RESOURCE": (70, 210, 120, 85),
        "ENEMY": (255, 90, 90, 95),
        "OBSTACLE": (140, 140, 140, 80),
    }
    MAIN_CITY_COLOR = (255, 215, 70, 140)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = 601
        self.rows = 601
        self.cell_size = 20
        self.min_cell_size = 6
        self.max_cell_size = 60
        self.axis_left = 0
        self.axis_top = 0
        self.painted = set()
        self.start_cell = None
        self.mode = "PAINT"  # PAINT | ERASE | START
        self._dragging = False
        self._last_drag_cell = None
        self._hover_cell = None
        self.overlay_tiles = {}
        self.city_tiles = set()
        self.setMouseTracking(True)
        self._sync_size()

    def _sync_size(self):
        total_w = self.axis_left + self.cols * self.cell_size
        total_h = self.axis_top + self.rows * self.cell_size
        self.setMinimumSize(total_w, total_h)
        self.resize(total_w, total_h)
        self.update()

    def _grid_origin(self):
        return self.axis_left, self.axis_top

    def _display_row_to_game_y(self, display_row):
        return (self.rows - 1) - int(display_row)

    def _game_y_to_display_row(self, game_y):
        return (self.rows - 1) - int(game_y)

    def _label_step(self):
        # Giữ khoảng cách nhãn trục đủ thoáng, tự co giãn theo mức zoom.
        candidates = [1, 2, 5, 10, 20, 25, 50, 100]
        for step in candidates:
            if step * self.cell_size >= 56:
                return step
        return 100

    def set_mode(self, mode):
        self.mode = str(mode).upper()

    def zoom(self, delta):
        old_size = self.cell_size
        self.cell_size = max(self.min_cell_size, min(self.max_cell_size, self.cell_size + int(delta)))
        if self.cell_size != old_size:
            self._sync_size()

    def clear_all(self):
        self.painted.clear()
        self.start_cell = None
        self.update()
        self.selection_changed.emit(0, -1, -1)

    def set_overlay_data(self, main_city, tile_info_map):
        self.overlay_tiles = tile_info_map if isinstance(tile_info_map, dict) else {}
        self.city_tiles = set()

        if isinstance(main_city, (list, tuple)) and len(main_city) == 2:
            try:
                cx, cy = int(main_city[0]), int(main_city[1])
                for dx in (0, 1):
                    for dy in (0, 1):
                        tx, ty = cx + dx, cy + dy
                        if 0 <= tx <= 600 and 0 <= ty <= 600:
                            self.city_tiles.add((tx, ty))
            except Exception:
                pass

        self.update()

    def _overlay_state_for_cell(self, cell):
        info = self.overlay_tiles.get(cell)
        if isinstance(info, dict):
            return str(info.get("state", "")).upper(), info
        if isinstance(info, str):
            return str(info).upper(), {}
        return "", {}

    def set_plan(self, targets, start_tile=None):
        self.painted = set()
        for item in targets or []:
            try:
                x, y = int(item[0]), int(item[1])
            except Exception:
                continue
            if 0 <= x <= 600 and 0 <= y <= 600:
                self.painted.add((x, y))

        self.start_cell = None
        if isinstance(start_tile, (list, tuple)) and len(start_tile) == 2:
            try:
                sx, sy = int(start_tile[0]), int(start_tile[1])
                if (sx, sy) in self.painted:
                    self.start_cell = (sx, sy)
            except Exception:
                pass

        self.update()
        if self.start_cell:
            self.selection_changed.emit(len(self.painted), self.start_cell[0], self.start_cell[1])
        else:
            self.selection_changed.emit(len(self.painted), -1, -1)

    def _cell_at(self, pos):
        ox, oy = self._grid_origin()
        gx = pos.x() - ox
        gy = pos.y() - oy
        if gx < 0 or gy < 0:
            return None
        x = int(gx // self.cell_size)
        display_row = int(gy // self.cell_size)
        if 0 <= x < self.cols and 0 <= display_row < self.rows:
            y = self._display_row_to_game_y(display_row)
            return x, y
        return None

    def _apply_mode_on_cell(self, cell):
        if cell is None:
            return

        changed = False
        if self.mode == "PAINT":
            if cell not in self.painted:
                self.painted.add(cell)
                changed = True
        elif self.mode == "ERASE":
            if cell in self.painted:
                self.painted.remove(cell)
                changed = True
            if self.start_cell == cell:
                self.start_cell = None
                changed = True
        elif self.mode == "START":
            if cell in self.painted and self.start_cell != cell:
                self.start_cell = cell
                changed = True

        if changed:
            self.update()
            if self.start_cell:
                self.selection_changed.emit(len(self.painted), self.start_cell[0], self.start_cell[1])
            else:
                self.selection_changed.emit(len(self.painted), -1, -1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            cell = self._cell_at(event.position().toPoint())
            self._last_drag_cell = cell
            self._apply_mode_on_cell(cell)

    def mouseMoveEvent(self, event):
        cell = self._cell_at(event.position().toPoint())
        if cell != self._hover_cell:
            self._hover_cell = cell
            self.update()

        if cell is not None:
            state, info = self._overlay_state_for_cell(cell)
            tip = f"({cell[0]}, {cell[1]})"
            if cell in self.city_tiles:
                tip += " | MAIN_CITY"
            elif state:
                tip += f" | {state}"
                difficulty = str(info.get("difficulty_label", "") or info.get("difficulty", "")).strip()
                if difficulty:
                    tip += f" | {difficulty}"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()

        if self._dragging:
            if cell is None or cell == self._last_drag_cell:
                return
            self._last_drag_cell = cell
            self._apply_mode_on_cell(cell)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._last_drag_cell = None

    def leaveEvent(self, event):
        self._hover_cell = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(245, 245, 245))

        ox, oy = self._grid_origin()

        x0 = max(0, (event.rect().left() - ox) // self.cell_size)
        x1 = min(self.cols - 1, (event.rect().right() - ox) // self.cell_size)
        display_row0 = max(0, (event.rect().top() - oy) // self.cell_size)
        display_row1 = min(self.rows - 1, (event.rect().bottom() - oy) // self.cell_size)

        painted_color = QColor(70, 180, 90)
        start_color = QColor(255, 160, 40)
        hover_color = QColor(80, 130, 255)

        for display_row in range(display_row0, display_row1 + 1):
            y = self._display_row_to_game_y(display_row)
            for x in range(x0, x1 + 1):
                px = ox + x * self.cell_size
                py = oy + display_row * self.cell_size

                if (x, y) in self.city_tiles:
                    r, g, b, a = self.MAIN_CITY_COLOR
                    painter.fillRect(px, py, self.cell_size, self.cell_size, QColor(r, g, b, a))
                else:
                    state, _ = self._overlay_state_for_cell((x, y))
                    if state in self.OVERLAY_STATE_COLORS:
                        r, g, b, a = self.OVERLAY_STATE_COLORS[state]
                        painter.fillRect(px, py, self.cell_size, self.cell_size, QColor(r, g, b, a))

                if (x, y) == self.start_cell:
                    painter.fillRect(px, py, self.cell_size, self.cell_size, start_color)
                elif (x, y) in self.painted:
                    painter.fillRect(px, py, self.cell_size, self.cell_size, painted_color)

        if self._hover_cell is not None:
            hx, hy = self._hover_cell
            if 0 <= hx < self.cols and 0 <= hy < self.rows:
                hover_row = self._game_y_to_display_row(hy)
                px = ox + hx * self.cell_size
                py = oy + hover_row * self.cell_size
                hover_pen = QPen(hover_color)
                hover_pen.setWidth(2)
                painter.setPen(hover_pen)
                painter.drawRect(px + 1, py + 1, self.cell_size - 2, self.cell_size - 2)

        pen = QPen(QColor(170, 170, 170))
        pen.setWidth(1)
        painter.setPen(pen)

        for x in range(x0, x1 + 2):
            gx = ox + x * self.cell_size
            painter.drawLine(gx, oy + display_row0 * self.cell_size, gx, oy + (display_row1 + 1) * self.cell_size)
        for display_row in range(display_row0, display_row1 + 2):
            gy = oy + display_row * self.cell_size
            painter.drawLine(ox + x0 * self.cell_size, gy, ox + (x1 + 1) * self.cell_size, gy)


class HorizontalAxisRuler(QWidget):
    def __init__(self, canvas, scroll_area, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.scroll_area = scroll_area
        self.setMinimumHeight(26)
        self.setMaximumHeight(26)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(232, 232, 232))

        if self.canvas.cell_size <= 0:
            return

        x_offset = self.scroll_area.horizontalScrollBar().value()
        view_w = self.scroll_area.viewport().width()
        cell = self.canvas.cell_size

        start_col = max(0, x_offset // cell)
        end_col = min(self.canvas.cols - 1, (x_offset + view_w) // cell + 1)
        step = self.canvas._label_step()

        line_pen = QPen(QColor(150, 150, 150))
        txt_pen = QPen(QColor(80, 80, 80))

        for col in range(start_col, end_col + 1):
            if col % step != 0:
                continue
            px = col * cell - x_offset
            painter.setPen(line_pen)
            painter.drawLine(px, 0, px, self.height())
            painter.setPen(txt_pen)
            painter.drawText(px + 3, self.height() - 6, str(col))


class VerticalAxisRuler(QWidget):
    def __init__(self, canvas, scroll_area, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.scroll_area = scroll_area
        self.setMinimumWidth(46)
        self.setMaximumWidth(46)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(232, 232, 232))

        if self.canvas.cell_size <= 0:
            return

        y_offset = self.scroll_area.verticalScrollBar().value()
        view_h = self.scroll_area.viewport().height()
        cell = self.canvas.cell_size

        start_display_row = max(0, y_offset // cell)
        end_display_row = min(self.canvas.rows - 1, (y_offset + view_h) // cell + 1)
        step = self.canvas._label_step()

        line_pen = QPen(QColor(150, 150, 150))
        txt_pen = QPen(QColor(80, 80, 80))

        for display_row in range(start_display_row, end_display_row + 1):
            game_y = self.canvas._display_row_to_game_y(display_row)
            if game_y % step != 0:
                continue
            py = display_row * cell - y_offset
            painter.setPen(line_pen)
            painter.drawLine(0, py, self.width(), py)
            painter.setPen(txt_pen)
            painter.drawText(4, py + min(cell - 2, 14), str(game_y))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NTA-AutoBot - Phase 1")
        self.resize(1100, 700)

        self.ctx = mp.get_context("spawn")
        self.proc = None
        self.stop_event = None
        self.pause_event = None
        self.command_queue = None
        self.event_queue = None
        self.state_queue = None
        self.hard_planner_window = None
        self.config_editor_window = None
        self._config_editor_loading = False
        self._config_dirty = False
        self._config_current_path = None
        self._config_data_cache = {}
        self._config_tiers = ["de", "nhap_mon", "thuong", "tang_bac", "kho", "dia_nguc"]
        self._build_order_buttons = []
        self._build_order_initial_setup_done = False
        self._build_order_setup_prompt_shown = False
        self._hard_main_city = None
        self._config_runtime_dir = self._resolve_runtime_config_dir()
        self._config_bundle_dir = self._resolve_bundled_config_dir()
        self.config_file_options = {
            "runtime.json": os.path.join(self._config_runtime_dir, "runtime.json"),
            "build_order_runtime.json": os.path.join(self._config_runtime_dir, "build_order_runtime.json"),
            "template_profiles.json": os.path.join(self._config_runtime_dir, "template_profiles.json"),
            "combat_timing.json": os.path.join(self._config_runtime_dir, "combat_timing.json"),
            "combat_difficulty_blacklist.json": os.path.join(self._config_runtime_dir, "combat_difficulty_blacklist.json"),
            "combat_first_dispatch_status.json": os.path.join(self._config_runtime_dir, "combat_first_dispatch_status.json"),
            "hard_dig_plan.json": os.path.join(self._config_runtime_dir, "hard_dig_plan.json"),
        }
        self._ensure_runtime_config_files()

        self._build_ui()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_queues)
        self.poll_timer.start(200)

    def _resolve_runtime_config_dir(self):
        return os.path.abspath(os.path.join(os.getcwd(), "config"))

    def _resolve_bundled_config_dir(self):
        candidates = [
            os.path.abspath(os.path.join(os.getcwd(), "_internal", "config")),
            os.path.abspath(os.path.join(os.getcwd(), "config")),
        ]
        if getattr(sys, "frozen", False):
            exe_root = os.path.dirname(sys.executable)
            candidates.insert(0, os.path.abspath(os.path.join(exe_root, "_internal", "config")))
            candidates.insert(1, os.path.abspath(os.path.join(exe_root, "config")))
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.insert(0, os.path.abspath(os.path.join(meipass, "config")))

        for path in candidates:
            if os.path.isdir(path):
                return path
        return ""

    def _default_config_object(self, key):
        if key == "runtime.json":
            return {
                "terminal_auto_clear_enabled": True,
                "terminal_auto_clear_interval_seconds": 900,
                "debug_auto_cleanup_enabled": True,
                "debug_auto_cleanup_interval_seconds": 900,
                "debug_auto_cleanup_keep_hours": 12,
                "config_backup_enabled": True,
                "config_backup_keep_count": 10,
                "config_backup_keep_days": 30,
            }
        if key == "build_order_runtime.json":
            return {"start_index": 0, "initial_setup_done": False}
        if key == "template_profiles.json":
            return {}
        if key == "combat_timing.json":
            return {
                "default_battle_duration_seconds": 150,
                "max_scout_targets_per_cycle": 10,
                "battle_duration_seconds": {
                    "de": 20,
                    "nhap_mon": 80,
                    "thuong": 150,
                    "tang_bac": 240,
                    "kho": 420,
                    "dia_nguc": 480,
                },
            }
        if key == "combat_difficulty_blacklist.json":
            return {
                "enabled": True,
                "tiers": {
                    "de": {"default": False, "levels": {}},
                    "nhap_mon": {"default": False, "levels": {}},
                    "thuong": {"default": False, "levels": {}},
                    "tang_bac": {"default": False, "levels": {"2": True, "3": True}},
                    "kho": {"default": False, "levels": {"1": True, "2": True, "3": True}},
                    "dia_nguc": {"default": True, "levels": {}},
                },
            }
        if key == "combat_first_dispatch_status.json":
            return {
                "enabled": True,
                "tiers": {
                    "de": False,
                    "nhap_mon": False,
                    "thuong": False,
                    "tang_bac": False,
                    "kho": False,
                    "dia_nguc": False,
                },
            }
        if key == "hard_dig_plan.json":
            return {
                "enabled": False,
                "auto_start_on_boot": False,
                "activate_hotkey": "h",
                "start_tile": [300, 300],
                "targets": [],
            }
        return {}

    def _ensure_runtime_config_files(self):
        os.makedirs(self._config_runtime_dir, exist_ok=True)

        for key, target_path in self.config_file_options.items():
            if os.path.exists(target_path):
                continue

            copied = False
            if self._config_bundle_dir:
                src_path = os.path.join(self._config_bundle_dir, key)
                if os.path.exists(src_path):
                    try:
                        content = self._read_text_file(src_path)
                        with open(target_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        copied = True
                        self._append_log(f"[GUI] Da seed config tu bundle: {key}") if hasattr(self, "log_view") else None
                    except Exception:
                        copied = False

            if not copied:
                obj = self._default_config_object(key)
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False, indent=2)
                    f.write("\n")

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        top_help_row = QHBoxLayout()
        self.btn_help_main = QPushButton("?")
        self.btn_help_main.setFixedWidth(28)
        self.btn_help_main.clicked.connect(self._show_help_main)
        top_help_row.addStretch(1)
        top_help_row.addWidget(self.btn_help_main)
        layout.addLayout(top_help_row)

        ctrl_box = QGroupBox("Dieu khien Bot")
        ctrl_layout = QHBoxLayout(ctrl_box)
        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_stop = QPushButton("Stop")
        self.btn_clear = QPushButton("Clear Log")
        self.btn_open_hard = QPushButton("Open Hard-Dig Planner")
        self.btn_open_config = QPushButton("Open Config Editor")

        self.btn_start.clicked.connect(self.start_bot)
        self.btn_pause.clicked.connect(self.pause_bot)
        self.btn_resume.clicked.connect(self.resume_bot)
        self.btn_stop.clicked.connect(self.stop_bot)
        self.btn_clear.clicked.connect(self.clear_log)
        self.btn_open_hard.clicked.connect(self._open_hard_planner_window)
        self.btn_open_config.clicked.connect(self._open_config_editor_window)

        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_pause)
        ctrl_layout.addWidget(self.btn_resume)
        ctrl_layout.addWidget(self.btn_stop)
        ctrl_layout.addWidget(self.btn_clear)
        ctrl_layout.addWidget(self.btn_open_hard)
        ctrl_layout.addWidget(self.btn_open_config)
        layout.addWidget(ctrl_box)

        map_box = QGroupBox("Khoi tao map")
        map_layout = QHBoxLayout(map_box)
        self.radio_use_existing_map = QRadioButton("Dung map cu")
        self.radio_create_new_map = QRadioButton("Tao map moi")
        self.radio_use_existing_map.setChecked(True)

        self.map_choice_group = QButtonGroup(self)
        self.map_choice_group.addButton(self.radio_use_existing_map)
        self.map_choice_group.addButton(self.radio_create_new_map)
        self.radio_use_existing_map.toggled.connect(self._update_map_input_enabled)

        self.input_map_x = QLineEdit()
        self.input_map_y = QLineEdit()
        self.input_adb_port = QLineEdit()
        self.input_map_x.setPlaceholderText("X")
        self.input_map_y.setPlaceholderText("Y")
        self.input_adb_port.setPlaceholderText("ADB Port")
        self.input_map_x.setMaximumWidth(80)
        self.input_map_y.setMaximumWidth(80)
        self.input_adb_port.setMaximumWidth(100)
        self.input_map_x.setValidator(QIntValidator(0, 600, self))
        self.input_map_y.setValidator(QIntValidator(0, 600, self))
        self.input_adb_port.setValidator(QIntValidator(1, 65535, self))
        self.input_map_x.setText("300")
        self.input_map_y.setText("300")
        self.input_adb_port.setText("5555")

        map_layout.addWidget(self.radio_use_existing_map)
        map_layout.addWidget(self.radio_create_new_map)
        map_layout.addWidget(QLabel("X:"))
        map_layout.addWidget(self.input_map_x)
        map_layout.addWidget(QLabel("Y:"))
        map_layout.addWidget(self.input_map_y)
        map_layout.addWidget(QLabel("ADB Port:"))
        map_layout.addWidget(self.input_adb_port)
        layout.addWidget(map_box)
        self._update_map_input_enabled()

        self.hard_box = QGroupBox("Hard-Dig Planner")
        hard_layout = QVBoxLayout(self.hard_box)

        mode_row = QHBoxLayout()
        self.radio_mode_paint = QRadioButton("To mau")
        self.radio_mode_erase = QRadioButton("Xoa")
        self.radio_mode_start = QRadioButton("Chon o bat dau")
        self.radio_mode_paint.setChecked(True)
        self.radio_mode_paint.toggled.connect(self._update_hard_dig_mode)
        self.radio_mode_erase.toggled.connect(self._update_hard_dig_mode)
        self.radio_mode_start.toggled.connect(self._update_hard_dig_mode)
        mode_row.addWidget(self.radio_mode_paint)
        mode_row.addWidget(self.radio_mode_erase)
        mode_row.addWidget(self.radio_mode_start)
        hard_layout.addLayout(mode_row)

        zoom_row = QHBoxLayout()
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_in = QPushButton("+")
        self.btn_center_city = QPushButton("Ve thanh chinh")
        self.lbl_zoom = QLabel("Zoom: 20")
        self.btn_zoom_out.clicked.connect(lambda: self._zoom_canvas(-2))
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_canvas(2))
        self.btn_center_city.clicked.connect(self._scroll_hard_to_main_city)
        zoom_row.addWidget(self.btn_zoom_out)
        zoom_row.addWidget(self.btn_zoom_in)
        zoom_row.addWidget(self.btn_center_city)
        zoom_row.addWidget(self.lbl_zoom)
        hard_layout.addLayout(zoom_row)

        self.hard_canvas = HardDigGridCanvas()
        self.hard_canvas.selection_changed.connect(self._on_canvas_selection_changed)
        self.hard_scroll = QScrollArea()
        self.hard_scroll.setWidgetResizable(False)
        self.hard_scroll.setWidget(self.hard_canvas)
        self.hard_scroll.setMinimumHeight(300)

        self.hard_axis_top = HorizontalAxisRuler(self.hard_canvas, self.hard_scroll)
        self.hard_axis_left = VerticalAxisRuler(self.hard_canvas, self.hard_scroll)
        axis_corner = QWidget()
        axis_corner.setMinimumSize(46, 26)
        axis_corner.setMaximumSize(46, 26)
        axis_corner.setStyleSheet("background-color: rgb(232,232,232);")

        self.hard_scroll.horizontalScrollBar().valueChanged.connect(self.hard_axis_top.update)
        self.hard_scroll.verticalScrollBar().valueChanged.connect(self.hard_axis_left.update)

        canvas_frame = QWidget()
        canvas_grid = QGridLayout(canvas_frame)
        canvas_grid.setContentsMargins(0, 0, 0, 0)
        canvas_grid.setSpacing(0)
        canvas_grid.addWidget(axis_corner, 0, 0)
        canvas_grid.addWidget(self.hard_axis_top, 0, 1)
        canvas_grid.addWidget(self.hard_axis_left, 1, 0)
        canvas_grid.addWidget(self.hard_scroll, 1, 1)

        hard_layout.addWidget(canvas_frame)

        plan_row = QHBoxLayout()
        self.btn_hard_clear = QPushButton("Xoa toan bo")
        self.btn_hard_send_plan = QPushButton("Luu plan Hard-Dig")
        self.btn_hard_activate = QPushButton("Kich hoat Hard-Dig")
        self.btn_hard_reload_overlay = QPushButton("Reload map_data")
        self.btn_hard_clear.clicked.connect(self._hard_clear)
        self.btn_hard_send_plan.clicked.connect(self._hard_save_plan)
        self.btn_hard_activate.clicked.connect(self._hard_activate)
        self.btn_hard_reload_overlay.clicked.connect(lambda: self._reload_hard_dig_overlay(show_feedback=True))
        plan_row.addWidget(self.btn_hard_clear)
        plan_row.addWidget(self.btn_hard_send_plan)
        plan_row.addWidget(self.btn_hard_activate)
        plan_row.addWidget(self.btn_hard_reload_overlay)
        hard_layout.addLayout(plan_row)

        self.lbl_hard_stats = QLabel("Painted: 0 | Start: (chua chon)")
        hard_layout.addWidget(self.lbl_hard_stats)

        self.lbl_hard_legend = QLabel(
            "Legend: MAIN_CITY=vang | OWNED=xanh duong | RESOURCE=xanh la | ENEMY=do | "
            "OBSTACLE=xam | Painted=xanh dam | Start=cam"
        )
        hard_layout.addWidget(self.lbl_hard_legend)

        # Hard-Dig planner sẽ hiển thị ở cửa sổ riêng.

        state_box = QGroupBox("Trang thai Runtime")
        state_grid = QGridLayout(state_box)
        self.lbl_engine = QLabel("STOPPED")
        self.lbl_combat_mode = QLabel("-")
        self.lbl_combat_status = QLabel("-")
        self.lbl_build_idx = QLabel("-")
        self.lbl_hard_dig = QLabel("-")
        self.lbl_updated = QLabel("-")

        state_grid.addWidget(QLabel("Engine:"), 0, 0)
        state_grid.addWidget(self.lbl_engine, 0, 1)
        state_grid.addWidget(QLabel("Combat Mode:"), 1, 0)
        state_grid.addWidget(self.lbl_combat_mode, 1, 1)
        state_grid.addWidget(QLabel("Combat Status:"), 2, 0)
        state_grid.addWidget(self.lbl_combat_status, 2, 1)
        state_grid.addWidget(QLabel("Build Index:"), 3, 0)
        state_grid.addWidget(self.lbl_build_idx, 3, 1)
        state_grid.addWidget(QLabel("Hard-Dig State:"), 4, 0)
        state_grid.addWidget(self.lbl_hard_dig, 4, 1)
        state_grid.addWidget(QLabel("Cap nhat cuoi:"), 5, 0)
        state_grid.addWidget(self.lbl_updated, 5, 1)
        layout.addWidget(state_box)

        self.config_box = QGroupBox("Config Editor")
        config_layout = QVBoxLayout(self.config_box)

        config_top = QHBoxLayout()
        self.combo_config_file = QComboBox()
        self.combo_config_file.addItems(list(self.config_file_options.keys()))
        self.btn_config_load = QPushButton("Load")
        self.btn_config_save = QPushButton("Save")
        self.btn_config_format = QPushButton("Format JSON")
        self.btn_config_toggle_advanced = QPushButton("Toggle Advanced JSON")

        self.btn_config_load.clicked.connect(self._load_selected_config)
        self.btn_config_save.clicked.connect(self._save_selected_config)
        self.btn_config_format.clicked.connect(self._format_selected_json)
        self.btn_config_toggle_advanced.clicked.connect(self._toggle_advanced_editor)
        self.combo_config_file.currentIndexChanged.connect(self._on_config_selection_changed)

        config_top.addWidget(self.combo_config_file)
        config_top.addWidget(self.btn_config_load)
        config_top.addWidget(self.btn_config_save)
        config_top.addWidget(self.btn_config_format)
        config_top.addWidget(self.btn_config_toggle_advanced)
        config_layout.addLayout(config_top)

        self.lbl_config_mode = QLabel("Mode: friendly")
        config_layout.addWidget(self.lbl_config_mode)

        self.config_stack = QStackedWidget()
        self.config_layout_runtime = {}
        self.config_layout_build_order = {}
        self.config_layout_combat_timing = {}
        self.config_layout_blacklist = {}
        self.config_layout_first_dispatch = {}
        self.config_layout_hard_dig = {}

        runtime_page = QWidget()
        runtime_form = QFormLayout(runtime_page)
        self.config_layout_runtime["terminal_auto_clear_enabled"] = QCheckBox()
        self.config_layout_runtime["terminal_auto_clear_interval_seconds"] = QSpinBox()
        self.config_layout_runtime["terminal_auto_clear_interval_seconds"].setRange(1, 86400)
        self.config_layout_runtime["debug_auto_cleanup_enabled"] = QCheckBox()
        self.config_layout_runtime["debug_auto_cleanup_interval_seconds"] = QSpinBox()
        self.config_layout_runtime["debug_auto_cleanup_interval_seconds"].setRange(1, 86400)
        self.config_layout_runtime["debug_auto_cleanup_keep_hours"] = QSpinBox()
        self.config_layout_runtime["debug_auto_cleanup_keep_hours"].setRange(1, 24 * 365)
        self.config_layout_runtime["config_backup_enabled"] = QCheckBox()
        self.config_layout_runtime["config_backup_keep_count"] = QSpinBox()
        self.config_layout_runtime["config_backup_keep_count"].setRange(1, 200)
        self.config_layout_runtime["config_backup_keep_days"] = QSpinBox()
        self.config_layout_runtime["config_backup_keep_days"].setRange(1, 3650)
        runtime_form.addRow("terminal_auto_clear_enabled", self.config_layout_runtime["terminal_auto_clear_enabled"])
        runtime_form.addRow("terminal_auto_clear_interval_seconds", self.config_layout_runtime["terminal_auto_clear_interval_seconds"])
        runtime_form.addRow("debug_auto_cleanup_enabled", self.config_layout_runtime["debug_auto_cleanup_enabled"])
        runtime_form.addRow("debug_auto_cleanup_interval_seconds", self.config_layout_runtime["debug_auto_cleanup_interval_seconds"])
        runtime_form.addRow("debug_auto_cleanup_keep_hours", self.config_layout_runtime["debug_auto_cleanup_keep_hours"])
        runtime_form.addRow("config_backup_enabled", self.config_layout_runtime["config_backup_enabled"])
        runtime_form.addRow("config_backup_keep_count", self.config_layout_runtime["config_backup_keep_count"])
        runtime_form.addRow("config_backup_keep_days", self.config_layout_runtime["config_backup_keep_days"])

        build_order_page = QWidget()
        build_order_layout = QVBoxLayout(build_order_page)
        build_order_form = QFormLayout()
        self.config_layout_build_order["start_index"] = QSpinBox()
        self.config_layout_build_order["start_index"].setRange(0, max(0, len(BUILD_SEQUENCE)))
        self.config_layout_build_order["start_index"].valueChanged.connect(self._on_build_order_start_index_changed)
        build_order_form.addRow("start_index", self.config_layout_build_order["start_index"])
        build_order_layout.addLayout(build_order_form)

        self.lbl_build_order_pick = QLabel("Step picker: chon mot buoc de dat diem bat dau")
        build_order_layout.addWidget(self.lbl_build_order_pick)

        self.lbl_build_order_preview = QLabel("Preview: -")
        build_order_layout.addWidget(self.lbl_build_order_preview)

        self.build_order_scroll = QScrollArea()
        self.build_order_scroll.setWidgetResizable(True)
        self.build_order_list_widget = QWidget()
        self.build_order_list_layout = QVBoxLayout(self.build_order_list_widget)
        self.build_order_list_layout.setContentsMargins(4, 4, 4, 4)
        self.build_order_list_layout.setSpacing(6)
        self.build_order_scroll.setWidget(self.build_order_list_widget)
        build_order_layout.addWidget(self.build_order_scroll)
        self._build_build_order_buttons()

        timing_page = QWidget()
        timing_form = QFormLayout(timing_page)
        self.config_layout_combat_timing["default_battle_duration_seconds"] = QSpinBox()
        self.config_layout_combat_timing["default_battle_duration_seconds"].setRange(1, 36000)
        self.config_layout_combat_timing["max_scout_targets_per_cycle"] = QSpinBox()
        self.config_layout_combat_timing["max_scout_targets_per_cycle"].setRange(1, 200)
        timing_form.addRow("default_battle_duration_seconds", self.config_layout_combat_timing["default_battle_duration_seconds"])
        timing_form.addRow("max_scout_targets_per_cycle", self.config_layout_combat_timing["max_scout_targets_per_cycle"])
        for tier in self._config_tiers:
            sb = QSpinBox()
            sb.setRange(1, 36000)
            self.config_layout_combat_timing[f"battle_{tier}"] = sb
            timing_form.addRow(f"battle_duration_seconds.{tier}", sb)

        blacklist_page = QWidget()
        blacklist_form = QFormLayout(blacklist_page)
        self.config_layout_blacklist["enabled"] = QCheckBox()
        blacklist_form.addRow("enabled", self.config_layout_blacklist["enabled"])
        for tier in self._config_tiers:
            default_cb = QCheckBox()
            levels_le = QLineEdit()
            levels_le.setPlaceholderText("vd: 1,2,3")
            self.config_layout_blacklist[f"{tier}_default"] = default_cb
            self.config_layout_blacklist[f"{tier}_levels"] = levels_le
            blacklist_form.addRow(f"tiers.{tier}.default", default_cb)
            blacklist_form.addRow(f"tiers.{tier}.levels", levels_le)

        first_dispatch_page = QWidget()
        first_dispatch_form = QFormLayout(first_dispatch_page)
        self.config_layout_first_dispatch["enabled"] = QCheckBox()
        first_dispatch_form.addRow("enabled", self.config_layout_first_dispatch["enabled"])
        for tier in self._config_tiers:
            cb = QCheckBox()
            self.config_layout_first_dispatch[f"tier_{tier}"] = cb
            first_dispatch_form.addRow(f"tiers.{tier}", cb)

        hard_dig_page = QWidget()
        hard_dig_form = QFormLayout(hard_dig_page)
        self.config_layout_hard_dig["enabled"] = QCheckBox()
        self.config_layout_hard_dig["auto_start_on_boot"] = QCheckBox()
        self.config_layout_hard_dig["activate_hotkey"] = QLineEdit()
        self.config_layout_hard_dig["start_x"] = QSpinBox()
        self.config_layout_hard_dig["start_x"].setRange(0, 600)
        self.config_layout_hard_dig["start_y"] = QSpinBox()
        self.config_layout_hard_dig["start_y"].setRange(0, 600)
        hard_dig_form.addRow("enabled", self.config_layout_hard_dig["enabled"])
        hard_dig_form.addRow("auto_start_on_boot", self.config_layout_hard_dig["auto_start_on_boot"])
        hard_dig_form.addRow("activate_hotkey", self.config_layout_hard_dig["activate_hotkey"])
        hard_dig_form.addRow("start_tile.x", self.config_layout_hard_dig["start_x"])
        hard_dig_form.addRow("start_tile.y", self.config_layout_hard_dig["start_y"])

        self.editor_config = QTextEdit()
        self.editor_config.setMinimumHeight(180)
        self.editor_config.textChanged.connect(self._on_config_text_changed)

        self.config_stack.addWidget(runtime_page)
        self.config_stack.addWidget(build_order_page)
        self.config_stack.addWidget(timing_page)
        self.config_stack.addWidget(blacklist_page)
        self.config_stack.addWidget(first_dispatch_page)
        self.config_stack.addWidget(hard_dig_page)
        self.config_stack.addWidget(self.editor_config)
        self._advanced_page_index = self.config_stack.count() - 1
        config_layout.addWidget(self.config_stack)

        self.lbl_config_status = QLabel("Status: idle")
        config_layout.addWidget(self.lbl_config_status)

        for widget in (
            *self.config_layout_runtime.values(),
            *self.config_layout_build_order.values(),
            *self.config_layout_combat_timing.values(),
            *self.config_layout_blacklist.values(),
            *self.config_layout_first_dispatch.values(),
            *self.config_layout_hard_dig.values(),
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._on_config_text_changed)
            elif hasattr(widget, "stateChanged"):
                widget.stateChanged.connect(self._on_config_text_changed)
            elif hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._on_config_text_changed)

        # Config editor sẽ hiển thị ở cửa sổ riêng.

        log_box = QGroupBox("Live Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_box)

        self._set_buttons_for_stopped()

        self._load_hard_dig_plan_into_canvas()
        self._reload_hard_dig_overlay(show_feedback=False)
        self._load_selected_config()
        self._sync_build_order_start_gate(show_popup=True)

    def _show_help_main(self):
        text = (
            "--- HƯỚNG DẪN ĐIỀU KHIỂN BOT ---\n\n"
            "1) Start: Bắt đầu chạy bot. Bot sẽ tự động thực hiện các vòng lặp nhiệm vụ (Builder, Combat, Daily) dựa trên cấu hình.\n\n"
            "2) Pause/Resume: Tạm dừng bot ngay lập tức mà không làm mất trạng thái. Bấm Resume để bot tiếp tục từ đúng điểm đang dừng.\n\n"
            "3) Stop: Dừng hoàn toàn tiến trình. Nếu bấm Start lại, bot sẽ khởi động lại từ đầu.\n\n"
            "4) Khởi tạo Map: Thiết lập Bản đồ số. Bạn có thể tải lại dữ liệu map đã quét (map_data.json) hoặc tạo map mới bằng cách nhập tọa độ X, Y của Thành Chính.\n\n"
            "5) Open Hard-Dig Planner: Mở công cụ lập kế hoạch đánh chiếm thủ công. Dùng khi bạn muốn bot ưu tiên đánh các ô đất cụ thể thay vì tự động loang lỗ.\n\n"
            "6) Open Config Editor: Mở cửa sổ quản lý cấu hình. Cho phép thay đổi thông số, chuỗi xây dựng hoặc trạng thái bot trực tiếp mà không cần sửa code.\n\n"
            "7) Live Log: Bảng theo dõi trực tiếp các hành động bot đang làm, trạng thái lỗi (nếu có) và tiến độ thời gian thực."
        )
        QMessageBox.information(self, "Hướng dẫn - Giao diện chính", text)

    def _show_help_hard(self):
        parent = self.hard_planner_window if self.hard_planner_window is not None else self
        text = (
            "--- HƯỚNG DẪN HARD-DIG PLANNER ---\n\n"
            "1) Tô màu (Draw): Nhấp hoặc kéo chuột trên lưới bản đồ để chọn các ô đất bạn muốn bot ưu tiên tấn công.\n\n"
            "2) Xóa (Erase): Chế độ tẩy, dùng để loại bỏ các ô đất đã chọn nhầm khỏi kế hoạch.\n\n"
            "3) Chọn ô bắt đầu: Chỉ định ô đất đầu tiên mà bot sẽ tiến hành đánh trong chuỗi kế hoạch này.\n\n"
            "4) Zoom +/-: Phóng to hoặc thu nhỏ lưới bản đồ để quan sát bao quát hơn.\n\n"
            "5) Lưu plan Hard-Dig: Ghi nhớ danh sách các ô đã chọn vào file 'config/hard_dig_plan.json' để bot có thể đọc và thực thi.\n\n"
            "6) Kích hoạt Hard-Dig: Phát tín hiệu ưu tiên cho bot. Sau khi hoàn thành hành động hiện tại, bot sẽ tạm ngưng auto tự do và chuyển sang đánh theo kế hoạch này.\n\n"
            "7) Reload map_data: Cập nhật lại màu sắc và trạng thái các ô đất (Đất mình, Tài nguyên, Địch...) mới nhất từ file data/map_data.json."
        )
        QMessageBox.information(parent, "Hướng dẫn - Hard-Dig Planner", text)

    def _show_help_config(self):
        parent = self.config_editor_window if self.config_editor_window is not None else self
        text = (
            "--- HƯỚNG DẪN CONFIG EDITOR ---\n\n"
            "1) Load Config: Chọn file cấu hình từ danh sách (Combobox) và bấm 'Load' để hiển thị nội dung.\n\n"
            "2) Friendly Mode: Chế độ giao diện trực quan, giúp bạn sửa nhanh các thông số cơ bản bằng ô nhập liệu mà không sợ sai cú pháp.\n\n"
            "3) Toggle Advanced JSON: Chuyển sang chế độ chỉnh sửa trực tiếp mã nguồn JSON dành cho người dùng nắm rõ cấu trúc file.\n\n"
            "4) Save: Lưu lại các thay đổi. Hệ thống sẽ tự động tạo một file sao lưu (.bak kèm timestamp) để phòng hờ trường hợp cần khôi phục.\n\n"
            "5) Quản lý build_order: Khi chọn file 'build_order_runtime.json', bạn có thể theo dõi và can thiệp vào tiến độ xây dựng của Builder.\n\n"
            "6) Step Picker (Build Order): Nhấp vào một bước bất kỳ trong danh sách công trình để ép bot bắt đầu xây từ bước đó ở lần chạy kế tiếp."
        )
        QMessageBox.information(parent, "Hướng dẫn - Config Editor", text)

    def _open_hard_planner_window(self):
        if self.hard_planner_window is None:
            self.hard_planner_window = QWidget()
            self.hard_planner_window.setWindowTitle("NTA-AutoBot - Hard-Dig Planner")
            self.hard_planner_window.resize(1080, 760)
            layout = QVBoxLayout(self.hard_planner_window)
            layout.setContentsMargins(8, 8, 8, 8)

            top_row = QHBoxLayout()
            top_row.addStretch(1)
            self.btn_help_hard_window = QPushButton("?")
            self.btn_help_hard_window.setFixedWidth(28)
            self.btn_help_hard_window.clicked.connect(self._show_help_hard)
            top_row.addWidget(self.btn_help_hard_window)
            layout.addLayout(top_row)

            layout.addWidget(self.hard_box)

        self.hard_planner_window.show()
        self.hard_planner_window.raise_()
        self.hard_planner_window.activateWindow()

    def _open_config_editor_window(self):
        if self.config_editor_window is None:
            self.config_editor_window = QWidget()
            self.config_editor_window.setWindowTitle("NTA-AutoBot - Config Editor")
            self.config_editor_window.resize(980, 700)
            layout = QVBoxLayout(self.config_editor_window)
            layout.setContentsMargins(8, 8, 8, 8)

            top_row = QHBoxLayout()
            top_row.addStretch(1)
            self.btn_help_config_window = QPushButton("?")
            self.btn_help_config_window.setFixedWidth(28)
            self.btn_help_config_window.clicked.connect(self._show_help_config)
            top_row.addWidget(self.btn_help_config_window)
            layout.addLayout(top_row)

            layout.addWidget(self.config_box)

        self.config_editor_window.show()
        self.config_editor_window.raise_()
        self.config_editor_window.activateWindow()

    def _selected_config_path(self):
        key = self.combo_config_file.currentText().strip()
        return self.config_file_options.get(key)

    def _selected_config_key(self):
        return self.combo_config_file.currentText().strip()

    def _read_build_order_runtime_config(self):
        path = self.config_file_options.get("build_order_runtime.json", "")
        if not path or not os.path.exists(path):
            return {}
        try:
            content = self._read_text_file(path)
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _sync_build_order_start_gate(self, show_popup=False):
        data = self._read_build_order_runtime_config()
        self._build_order_initial_setup_done = bool(data.get("initial_setup_done", False))

        if self.proc is None:
            self.btn_start.setEnabled(self._build_order_initial_setup_done)

        if self._build_order_initial_setup_done:
            return

        if show_popup and (not self._build_order_setup_prompt_shown):
            self._build_order_setup_prompt_shown = True
            QMessageBox.information(
                self,
                "Thiet lap ban dau bat buoc",
                "Ban can cau hinh build_order_runtime truoc khi Start bot.\n"
                "Hay chon buoc khoi dau Builder trong Config Editor va bam Save.",
            )
            self._open_build_order_config_for_setup()

    def _open_build_order_config_for_setup(self):
        key = "build_order_runtime.json"
        target_index = self.combo_config_file.findText(key)
        if target_index >= 0:
            self.combo_config_file.blockSignals(True)
            self.combo_config_file.setCurrentIndex(target_index)
            self.combo_config_file.blockSignals(False)
        self._load_selected_config()
        self.config_stack.setCurrentIndex(self._friendly_page_index(key))
        self.lbl_config_mode.setText("Mode: friendly")
        self._open_config_editor_window()

    def _friendly_page_index(self, key):
        mapping = {
            "runtime.json": 0,
            "build_order_runtime.json": 1,
            "combat_timing.json": 2,
            "combat_difficulty_blacklist.json": 3,
            "combat_first_dispatch_status.json": 4,
            "hard_dig_plan.json": 5,
        }
        return mapping.get(key, self._advanced_page_index)

    def _build_build_order_buttons(self):
        # Xoa danh sach cu (neu co) de dam bao idempotent khi khoi tao lai UI.
        while self.build_order_list_layout.count() > 0:
            item = self.build_order_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._build_order_buttons = []
        for idx, task in enumerate(BUILD_SEQUENCE):
            type_name = str(task.get("type_name", task.get("name", "Unknown")))
            target_lv = int(task.get("target_lv", 0))
            btn = QPushButton(f"Buoc {idx + 1}: {type_name} +Lv{target_lv}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, i=idx: self._on_build_order_step_clicked(i))
            self.build_order_list_layout.addWidget(btn)
            self._build_order_buttons.append(btn)

        self.build_order_list_layout.addStretch(1)
        self._update_build_order_preview()

    def _on_build_order_step_clicked(self, index):
        self.config_layout_build_order["start_index"].setValue(int(index))

    def _on_build_order_start_index_changed(self, _value):
        self._update_build_order_preview()

    def _update_build_order_preview(self):
        spin = self.config_layout_build_order.get("start_index")
        if spin is None:
            return

        idx = int(spin.value())
        total = len(BUILD_SEQUENCE)

        for i, btn in enumerate(self._build_order_buttons):
            btn.setChecked(i == idx)

        if total == 0:
            self.lbl_build_order_preview.setText("Preview: BUILD_SEQUENCE rong")
            return

        if idx >= total:
            self.lbl_build_order_preview.setText(f"Preview: start_index={idx} (da het danh sach)")
            return

        task = BUILD_SEQUENCE[idx]
        type_name = str(task.get("type_name", task.get("name", "Unknown")))
        target_lv = int(task.get("target_lv", 0))
        self.lbl_build_order_preview.setText(
            f"Preview: start_index={idx} -> Buoc {idx + 1}: {type_name} +Lv{target_lv}"
        )

    def _toggle_advanced_editor(self):
        current = self.config_stack.currentIndex()
        key = self._selected_config_key()
        friendly_idx = self._friendly_page_index(key)
        if current == self._advanced_page_index:
            self.config_stack.setCurrentIndex(friendly_idx)
            self.lbl_config_mode.setText("Mode: friendly")
        else:
            self.config_stack.setCurrentIndex(self._advanced_page_index)
            self.lbl_config_mode.setText("Mode: advanced json")

    def _populate_friendly_editor(self, key, data):
        self._config_editor_loading = True
        try:
            if key == "runtime.json":
                self.config_layout_runtime["terminal_auto_clear_enabled"].setChecked(bool(data.get("terminal_auto_clear_enabled", True)))
                self.config_layout_runtime["terminal_auto_clear_interval_seconds"].setValue(int(data.get("terminal_auto_clear_interval_seconds", 900)))
                self.config_layout_runtime["debug_auto_cleanup_enabled"].setChecked(bool(data.get("debug_auto_cleanup_enabled", True)))
                self.config_layout_runtime["debug_auto_cleanup_interval_seconds"].setValue(int(data.get("debug_auto_cleanup_interval_seconds", 900)))
                self.config_layout_runtime["debug_auto_cleanup_keep_hours"].setValue(int(data.get("debug_auto_cleanup_keep_hours", 12)))
                self.config_layout_runtime["config_backup_enabled"].setChecked(bool(data.get("config_backup_enabled", True)))
                self.config_layout_runtime["config_backup_keep_count"].setValue(int(data.get("config_backup_keep_count", 10)))
                self.config_layout_runtime["config_backup_keep_days"].setValue(int(data.get("config_backup_keep_days", 30)))
            elif key == "build_order_runtime.json":
                self.config_layout_build_order["start_index"].setValue(int(data.get("start_index", 0)))
                self._update_build_order_preview()
            elif key == "combat_timing.json":
                self.config_layout_combat_timing["default_battle_duration_seconds"].setValue(int(data.get("default_battle_duration_seconds", 150)))
                self.config_layout_combat_timing["max_scout_targets_per_cycle"].setValue(int(data.get("max_scout_targets_per_cycle", 10)))
                battle = data.get("battle_duration_seconds", {}) if isinstance(data.get("battle_duration_seconds", {}), dict) else {}
                for tier in self._config_tiers:
                    self.config_layout_combat_timing[f"battle_{tier}"].setValue(int(battle.get(tier, 150)))
            elif key == "combat_difficulty_blacklist.json":
                self.config_layout_blacklist["enabled"].setChecked(bool(data.get("enabled", True)))
                tiers = data.get("tiers", {}) if isinstance(data.get("tiers", {}), dict) else {}
                for tier in self._config_tiers:
                    cfg = tiers.get(tier, {}) if isinstance(tiers.get(tier, {}), dict) else {}
                    self.config_layout_blacklist[f"{tier}_default"].setChecked(bool(cfg.get("default", False)))
                    levels = cfg.get("levels", {}) if isinstance(cfg.get("levels", {}), dict) else {}
                    blocked = sorted([str(k) for k, v in levels.items() if bool(v)], key=lambda s: int(s) if s.isdigit() else s)
                    self.config_layout_blacklist[f"{tier}_levels"].setText(",".join(blocked))
            elif key == "combat_first_dispatch_status.json":
                self.config_layout_first_dispatch["enabled"].setChecked(bool(data.get("enabled", True)))
                tiers = data.get("tiers", {}) if isinstance(data.get("tiers", {}), dict) else {}
                for tier in self._config_tiers:
                    self.config_layout_first_dispatch[f"tier_{tier}"].setChecked(bool(tiers.get(tier, False)))
            elif key == "hard_dig_plan.json":
                self.config_layout_hard_dig["enabled"].setChecked(bool(data.get("enabled", False)))
                self.config_layout_hard_dig["auto_start_on_boot"].setChecked(bool(data.get("auto_start_on_boot", False)))
                self.config_layout_hard_dig["activate_hotkey"].setText(str(data.get("activate_hotkey", "h")))
                st = data.get("start_tile", [300, 300])
                sx = int(st[0]) if isinstance(st, (list, tuple)) and len(st) >= 2 else 300
                sy = int(st[1]) if isinstance(st, (list, tuple)) and len(st) >= 2 else 300
                self.config_layout_hard_dig["start_x"].setValue(sx)
                self.config_layout_hard_dig["start_y"].setValue(sy)
        finally:
            self._config_editor_loading = False

    def _collect_friendly_editor(self, key, base_obj):
        obj = dict(base_obj) if isinstance(base_obj, dict) else {}

        if key == "runtime.json":
            obj["terminal_auto_clear_enabled"] = self.config_layout_runtime["terminal_auto_clear_enabled"].isChecked()
            obj["terminal_auto_clear_interval_seconds"] = int(self.config_layout_runtime["terminal_auto_clear_interval_seconds"].value())
            obj["debug_auto_cleanup_enabled"] = self.config_layout_runtime["debug_auto_cleanup_enabled"].isChecked()
            obj["debug_auto_cleanup_interval_seconds"] = int(self.config_layout_runtime["debug_auto_cleanup_interval_seconds"].value())
            obj["debug_auto_cleanup_keep_hours"] = int(self.config_layout_runtime["debug_auto_cleanup_keep_hours"].value())
            obj["config_backup_enabled"] = self.config_layout_runtime["config_backup_enabled"].isChecked()
            obj["config_backup_keep_count"] = int(self.config_layout_runtime["config_backup_keep_count"].value())
            obj["config_backup_keep_days"] = int(self.config_layout_runtime["config_backup_keep_days"].value())
            return obj

        if key == "build_order_runtime.json":
            obj["start_index"] = int(self.config_layout_build_order["start_index"].value())
            # Save qua Config Editor duoc xem la da hoan tat setup ban dau.
            obj["initial_setup_done"] = True
            return obj

        if key == "combat_timing.json":
            obj["default_battle_duration_seconds"] = int(self.config_layout_combat_timing["default_battle_duration_seconds"].value())
            obj["max_scout_targets_per_cycle"] = int(self.config_layout_combat_timing["max_scout_targets_per_cycle"].value())
            battle = obj.get("battle_duration_seconds", {}) if isinstance(obj.get("battle_duration_seconds", {}), dict) else {}
            for tier in self._config_tiers:
                battle[tier] = int(self.config_layout_combat_timing[f"battle_{tier}"].value())
            obj["battle_duration_seconds"] = battle
            return obj

        if key == "combat_difficulty_blacklist.json":
            obj["enabled"] = self.config_layout_blacklist["enabled"].isChecked()
            tiers = obj.get("tiers", {}) if isinstance(obj.get("tiers", {}), dict) else {}
            for tier in self._config_tiers:
                tier_cfg = tiers.get(tier, {}) if isinstance(tiers.get(tier, {}), dict) else {}
                tier_cfg["default"] = self.config_layout_blacklist[f"{tier}_default"].isChecked()
                raw = self.config_layout_blacklist[f"{tier}_levels"].text().strip()
                levels = {}
                if raw:
                    for token in raw.split(","):
                        t = token.strip()
                        if t.isdigit():
                            levels[t] = True
                tier_cfg["levels"] = levels
                tiers[tier] = tier_cfg
            obj["tiers"] = tiers
            return obj

        if key == "combat_first_dispatch_status.json":
            obj["enabled"] = self.config_layout_first_dispatch["enabled"].isChecked()
            tiers = obj.get("tiers", {}) if isinstance(obj.get("tiers", {}), dict) else {}
            for tier in self._config_tiers:
                tiers[tier] = self.config_layout_first_dispatch[f"tier_{tier}"].isChecked()
            obj["tiers"] = tiers
            return obj

        if key == "hard_dig_plan.json":
            obj["enabled"] = self.config_layout_hard_dig["enabled"].isChecked()
            obj["auto_start_on_boot"] = self.config_layout_hard_dig["auto_start_on_boot"].isChecked()
            hotkey = self.config_layout_hard_dig["activate_hotkey"].text().strip().lower()
            obj["activate_hotkey"] = hotkey[:1] if hotkey else "h"
            obj["start_tile"] = [
                int(self.config_layout_hard_dig["start_x"].value()),
                int(self.config_layout_hard_dig["start_y"].value()),
            ]
            return obj

        return obj

    def _read_text_file(self, path):
        for enc in ("utf-8-sig", "utf-8"):
            try:
                with open(path, "r", encoding=enc) as f:
                    return f.read()
            except Exception:
                continue
        raise RuntimeError(f"Khong doc duoc file: {path}")

    def _write_text_file_safe(self, path, content):
        backup_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.bak_{backup_ts}"
        tmp_path = f"{path}.tmp"

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as src, open(backup_path, "w", encoding="utf-8") as bak:
                    bak.write(src.read())
            except Exception:
                # Backup lỗi không chặn save chính.
                pass

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)

        runtime_override = None
        if os.path.basename(path).lower() == "runtime.json":
            try:
                loaded = json.loads(content)
                if isinstance(loaded, dict):
                    runtime_override = loaded
            except Exception:
                runtime_override = None

        policy = self._load_backup_policy(runtime_override)
        deleted = self._prune_backup_files(path, policy)
        if deleted > 0:
            self._append_log(f"[GUI] Da don dep {deleted} file .bak cua {os.path.basename(path)}")

    def _load_backup_policy(self, runtime_override=None):
        policy = {
            "enabled": True,
            "keep_count": 10,
            "keep_days": 30,
        }

        data = None
        if isinstance(runtime_override, dict):
            data = runtime_override
        else:
            runtime_path = self.config_file_options.get("runtime.json", os.path.join(self._config_runtime_dir, "runtime.json"))
            if os.path.exists(runtime_path):
                for enc in ("utf-8-sig", "utf-8"):
                    try:
                        with open(runtime_path, "r", encoding=enc) as f:
                            loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                            break
                    except Exception:
                        continue

        if isinstance(data, dict):
            policy["enabled"] = bool(data.get("config_backup_enabled", True))
            try:
                policy["keep_count"] = max(1, int(data.get("config_backup_keep_count", 10)))
            except Exception:
                policy["keep_count"] = 10
            try:
                policy["keep_days"] = max(1, int(data.get("config_backup_keep_days", 10)))
            except Exception:
                policy["keep_days"] = 10

        return policy

    def _prune_backup_files(self, path, policy):
        if not bool(policy.get("enabled", True)):
            return 0

        folder = os.path.dirname(path)
        base = os.path.basename(path)
        prefix = f"{base}.bak_"
        if not os.path.isdir(folder):
            return 0

        backups = []
        for name in os.listdir(folder):
            if not name.startswith(prefix):
                continue
            full_path = os.path.join(folder, name)
            if os.path.isfile(full_path):
                backups.append(full_path)

        if not backups:
            return 0

        keep_count = max(1, int(policy.get("keep_count", 10)))
        keep_days = max(1, int(policy.get("keep_days", 30)))
        cutoff = time.time() - (keep_days * 86400)

        backups.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        keep_set = set(backups[:keep_count])

        deleted = 0
        for bak in backups:
            # keep_count là giới hạn cứng số bản backup tối đa.
            # keep_days là điều kiện bổ sung để dọn bản backup cũ theo thời gian.
            if bak in keep_set:
                continue
            try:
                mtime = os.path.getmtime(bak)
            except Exception:
                mtime = 0
            try:
                os.remove(bak)
                deleted += 1
            except Exception:
                pass

        # Dọn thêm theo tuổi file (kể cả khi số lượng backup hiện tại <= keep_count).
        for bak in list(keep_set):
            if not os.path.exists(bak):
                continue
            try:
                mtime = os.path.getmtime(bak)
            except Exception:
                mtime = 0
            if mtime >= cutoff:
                continue
            try:
                os.remove(bak)
                deleted += 1
            except Exception:
                pass

        return deleted

    def _on_config_text_changed(self):
        if self._config_editor_loading:
            return
        self._config_dirty = True
        self.lbl_config_status.setText("Status: modified")

    def _on_config_selection_changed(self):
        if self._config_dirty:
            reply = QMessageBox.question(
                self,
                "Thong bao",
                "Ban co thay doi chua luu. Co tai file config moi khong?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._load_selected_config()

    def _load_selected_config(self):
        path = self._selected_config_path()
        key = self._selected_config_key()
        if not path:
            return

        if not os.path.exists(path):
            self._config_editor_loading = True
            self.editor_config.setPlainText("{}\n")
            self._config_editor_loading = False
            self._config_dirty = False
            self._config_current_path = path
            self._config_data_cache = {}
            self.config_stack.setCurrentIndex(self._friendly_page_index(key))
            self._populate_friendly_editor(key, {})
            self.lbl_config_mode.setText("Mode: friendly")
            self.lbl_config_status.setText("Status: new file template loaded")
            return

        try:
            content = self._read_text_file(path)
            parsed = {}
            if path.lower().endswith(".json"):
                try:
                    parsed = json.loads(content)
                except Exception:
                    parsed = {}
            self._config_editor_loading = True
            self.editor_config.setPlainText(content)
            self._config_editor_loading = False
            self._config_data_cache = parsed if isinstance(parsed, dict) else {}
            self.config_stack.setCurrentIndex(self._friendly_page_index(key))
            self._populate_friendly_editor(key, self._config_data_cache)
            self.lbl_config_mode.setText("Mode: friendly")
            self._config_dirty = False
            self._config_current_path = path
            self.lbl_config_status.setText(f"Status: loaded {os.path.basename(path)}")
        except Exception as exc:
            self._config_editor_loading = False
            QMessageBox.warning(self, "Thong bao", str(exc))

    def _format_selected_json(self):
        path = self._selected_config_path() or ""
        if self.config_stack.currentIndex() != self._advanced_page_index:
            QMessageBox.information(self, "Thong bao", "Dang o che do friendly. Bat Advanced JSON de format.")
            return
        if not path.lower().endswith(".json"):
            QMessageBox.information(self, "Thong bao", "Format JSON chi ap dung cho file .json")
            return

        raw = self.editor_config.toPlainText()
        try:
            obj = json.loads(raw)
        except Exception as exc:
            QMessageBox.warning(self, "Thong bao", f"JSON khong hop le: {exc}")
            return

        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        self._config_editor_loading = True
        self.editor_config.setPlainText(pretty + "\n")
        self._config_editor_loading = False
        self._config_dirty = True
        self.lbl_config_status.setText("Status: formatted (unsaved)")

    def _save_selected_config(self):
        path = self._selected_config_path()
        key = self._selected_config_key()
        if not path:
            return

        if self.config_stack.currentIndex() == self._advanced_page_index:
            content = self.editor_config.toPlainText()
            if path.lower().endswith(".json"):
                try:
                    obj = json.loads(content)
                    if key == "build_order_runtime.json" and isinstance(obj, dict):
                        obj["initial_setup_done"] = True
                    content = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
                except Exception as exc:
                    QMessageBox.warning(self, "Thong bao", f"JSON khong hop le, khong the save: {exc}")
                    return
        else:
            base = self._config_data_cache if isinstance(self._config_data_cache, dict) else {}
            obj = self._collect_friendly_editor(key, base)
            content = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._write_text_file_safe(path, content)
            self._config_dirty = False
            self._config_current_path = path
            self.lbl_config_status.setText(f"Status: saved {os.path.basename(path)}")
            self._append_log(f"[GUI] Saved config: {path}")
            try:
                self._config_data_cache = json.loads(content)
            except Exception:
                self._config_data_cache = {}

            if os.path.basename(path) == "build_order_runtime.json":
                self._sync_build_order_start_gate(show_popup=False)
                if self._build_order_initial_setup_done:
                    self._append_log("[GUI] Build order setup da hoan tat. Ban co the Start bot.")

            # Auto refresh overlay nếu user sửa map_data-related config ảnh hưởng trực quan.
            if os.path.basename(path) == "hard_dig_plan.json":
                self._load_hard_dig_plan_into_canvas()
        except Exception as exc:
            QMessageBox.warning(self, "Thong bao", f"Khong save duoc config: {exc}")

    def _set_buttons_for_running(self):
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_resume.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.radio_use_existing_map.setEnabled(False)
        self.radio_create_new_map.setEnabled(False)
        self.input_map_x.setEnabled(False)
        self.input_map_y.setEnabled(False)
        self.input_adb_port.setEnabled(False)

    def _set_buttons_for_stopped(self):
        self.btn_start.setEnabled(bool(self._build_order_initial_setup_done))
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.radio_use_existing_map.setEnabled(True)
        self.radio_create_new_map.setEnabled(True)
        self.input_adb_port.setEnabled(True)
        self._update_map_input_enabled()

    def _update_hard_dig_mode(self):
        if self.radio_mode_erase.isChecked():
            self.hard_canvas.set_mode("ERASE")
        elif self.radio_mode_start.isChecked():
            self.hard_canvas.set_mode("START")
        else:
            self.hard_canvas.set_mode("PAINT")

    def _zoom_canvas(self, delta):
        self.hard_canvas.zoom(delta)
        self.lbl_zoom.setText(f"Zoom: {self.hard_canvas.cell_size}")
        self.hard_axis_top.update()
        self.hard_axis_left.update()

    def _scroll_hard_to_main_city(self):
        city = self._hard_main_city
        if not (isinstance(city, (list, tuple)) and len(city) == 2):
            QMessageBox.information(self, "Thong bao", "Chua co thong tin thanh chinh trong map_data.")
            return

        try:
            city_x = int(city[0])
            city_y = int(city[1])
        except Exception:
            QMessageBox.information(self, "Thong bao", "Toa do thanh chinh khong hop le.")
            return

        display_row = self.hard_canvas._game_y_to_display_row(city_y)
        cell = self.hard_canvas.cell_size
        target_px_x = int((city_x + 0.5) * cell)
        target_px_y = int((display_row + 0.5) * cell)

        hbar = self.hard_scroll.horizontalScrollBar()
        vbar = self.hard_scroll.verticalScrollBar()
        view_w = self.hard_scroll.viewport().width()
        view_h = self.hard_scroll.viewport().height()

        hbar.setValue(max(hbar.minimum(), min(hbar.maximum(), target_px_x - view_w // 2)))
        vbar.setValue(max(vbar.minimum(), min(vbar.maximum(), target_px_y - view_h // 2)))

    def _on_canvas_selection_changed(self, count, sx, sy):
        if sx >= 0 and sy >= 0:
            self.lbl_hard_stats.setText(f"Painted: {count} | Start: ({sx},{sy})")
        else:
            self.lbl_hard_stats.setText(f"Painted: {count} | Start: (chua chon)")

    def _hard_clear(self):
        self.hard_canvas.clear_all()

    def _collect_hard_plan(self):
        painted = sorted(list(self.hard_canvas.painted), key=lambda p: (p[1], p[0]))
        start = self.hard_canvas.start_cell
        if not painted:
            QMessageBox.warning(self, "Thong bao", "Ban chua to o nao cho Hard-Dig.")
            return None
        if start is None:
            QMessageBox.warning(self, "Thong bao", "Ban chua chon o bat dau cho Hard-Dig.")
            return None
        if start not in self.hard_canvas.painted:
            QMessageBox.warning(self, "Thong bao", "O bat dau phai nam trong tap o da to.")
            return None
        targets = [[int(x), int(y)] for x, y in painted]
        return {
            "start_tile": [int(start[0]), int(start[1])],
            "targets": targets,
        }

    def _hard_plan_file_path(self):
        return os.path.abspath(os.path.join(os.getcwd(), "config", "hard_dig_plan.json"))

    def _map_data_file_path(self):
        return os.path.abspath(os.path.join(os.getcwd(), "data", "map_data.json"))

    def _reload_hard_dig_overlay(self, show_feedback=False):
        path = self._map_data_file_path()
        if not os.path.exists(path):
            self.hard_canvas.set_overlay_data(main_city=None, tile_info_map={})
            if show_feedback:
                self._append_log("[GUI] Chua co data/map_data.json de overlay.")
            return

        payload = None
        for enc in ("utf-8-sig", "utf-8"):
            try:
                with open(path, "r", encoding=enc) as f:
                    payload = json.load(f)
                break
            except Exception:
                continue

        if not isinstance(payload, dict):
            self.hard_canvas.set_overlay_data(main_city=None, tile_info_map={})
            if show_feedback:
                self._append_log("[GUI] map_data.json khong hop le, bo qua overlay.")
            return

        main_city = payload.get("main_city", [300, 300])
        if isinstance(main_city, (list, tuple)) and len(main_city) >= 2:
            try:
                self._hard_main_city = (int(main_city[0]), int(main_city[1]))
            except Exception:
                self._hard_main_city = None
        else:
            self._hard_main_city = None
        raw_grid = payload.get("grid", {})
        tile_info_map = {}

        if isinstance(raw_grid, dict):
            for key, info in raw_grid.items():
                if not isinstance(key, str):
                    continue
                try:
                    x_str, y_str = key.split(",", 1)
                    x = int(x_str)
                    y = int(y_str)
                except Exception:
                    continue
                if not (0 <= x <= 600 and 0 <= y <= 600):
                    continue
                tile_info_map[(x, y)] = info if isinstance(info, dict) else {"state": str(info)}

        self.hard_canvas.set_overlay_data(main_city=main_city, tile_info_map=tile_info_map)
        if show_feedback:
            self._append_log(f"[GUI] Da reload overlay map_data ({len(tile_info_map)} o).")

    def _save_hard_plan_file(self, start_tile, targets):
        path = self._hard_plan_file_path()
        data = {}
        if os.path.exists(path):
            for enc in ("utf-8-sig", "utf-8"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
                        break
                except Exception:
                    pass

        if not isinstance(data, dict):
            data = {}
        runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}

        data["enabled"] = True
        data.setdefault("activate_hotkey", "h")
        data.setdefault("auto_start_on_boot", False)
        data["start_tile"] = [int(start_tile[0]), int(start_tile[1])]
        data["targets"] = [[int(t[0]), int(t[1])] for t in targets]
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        data["runtime"] = runtime

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_hard_dig_plan_into_canvas(self):
        path = self._hard_plan_file_path()
        if not os.path.exists(path):
            return

        plan = None
        for enc in ("utf-8-sig", "utf-8"):
            try:
                with open(path, "r", encoding=enc) as f:
                    plan = json.load(f)
                break
            except Exception:
                continue

        if not isinstance(plan, dict):
            return
        self.hard_canvas.set_plan(plan.get("targets", []), plan.get("start_tile", [300, 300]))

    def _hard_save_plan(self):
        plan = self._collect_hard_plan()
        if not plan:
            return False

        try:
            self._save_hard_plan_file(plan["start_tile"], plan["targets"])
        except Exception as exc:
            QMessageBox.warning(self, "Thong bao", f"Khong luu duoc hard_dig_plan.json: {exc}")
            return False

        self._append_log(
            f"[GUI] Da luu hard-dig plan: {len(plan['targets'])} o, start={tuple(plan['start_tile'])}"
        )

        if self.command_queue is not None:
            try:
                self.command_queue.put_nowait(
                    {
                        "type": "UPDATE_HARD_DIG_PLAN",
                        "start_tile": plan["start_tile"],
                        "targets": plan["targets"],
                    }
                )
                self._append_log("[GUI] Da gui UPDATE_HARD_DIG_PLAN den bot runtime.")
            except Exception:
                self._append_log("[GUI] Khong gui duoc command UPDATE_HARD_DIG_PLAN (queue full?).")

        return True

    def _hard_activate(self):
        if not self._hard_save_plan():
            return
        if self.command_queue is not None:
            try:
                self.command_queue.put_nowait({"type": "ACTIVATE_HARD_DIG"})
                self._append_log("[GUI] Da gui lenh ACTIVATE_HARD_DIG.")
                return
            except Exception:
                self._append_log("[GUI] Khong gui duoc ACTIVATE_HARD_DIG (queue full?).")

        # Bot chua chay: mark activation in file de lan start sau pick up duoc.
        try:
            path = self._hard_plan_file_path()
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
            runtime["activation_requested"] = True
            runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
            data["runtime"] = runtime
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._append_log("[GUI] Bot dang dung, da set activation_requested=true trong file plan.")
        except Exception as exc:
            QMessageBox.warning(self, "Thong bao", f"Khong kich hoat duoc hard-dig: {exc}")

    def _update_map_input_enabled(self):
        allow_edit = self.radio_create_new_map.isChecked() and (self.proc is None)
        self.input_map_x.setEnabled(allow_edit)
        self.input_map_y.setEnabled(allow_edit)
        self.input_adb_port.setEnabled(self.proc is None)

    def _append_log(self, line):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{now}] {line}")

    def start_bot(self):
        if self.proc is not None and self.proc.is_alive():
            QMessageBox.information(self, "Thong bao", "Bot dang chay.")
            return

        if not self._build_order_initial_setup_done:
            self._sync_build_order_start_gate(show_popup=True)
            QMessageBox.warning(
                self,
                "Thong bao",
                "Chua hoan tat setup build_order_runtime. Vui long cau hinh va Save truoc khi Start.",
            )
            return

        map_prefer_existing = self.radio_use_existing_map.isChecked()
        map_new_city_xy = None
        adb_port = 5555

        adb_port_text = self.input_adb_port.text().strip()
        if adb_port_text:
            try:
                adb_port = int(adb_port_text)
            except ValueError:
                QMessageBox.warning(self, "Thong bao", "ADB Port phai la so nguyen.")
                return
            if not (1 <= adb_port <= 65535):
                QMessageBox.warning(self, "Thong bao", "ADB Port phai trong khoang 1..65535.")
                return

        if not map_prefer_existing:
            x_text = self.input_map_x.text().strip()
            y_text = self.input_map_y.text().strip()
            if not x_text or not y_text:
                QMessageBox.warning(self, "Thong bao", "Vui long nhap day du toa do X/Y.")
                return
            try:
                x_val = int(x_text)
                y_val = int(y_text)
            except ValueError:
                QMessageBox.warning(self, "Thong bao", "Toa do X/Y phai la so nguyen.")
                return

            if not (0 <= x_val <= 600 and 0 <= y_val <= 600):
                QMessageBox.warning(self, "Thong bao", "Toa do X/Y phai trong khoang 0..600.")
                return
            map_new_city_xy = (x_val, y_val)

        self.stop_event = self.ctx.Event()
        self.pause_event = self.ctx.Event()
        self.command_queue = self.ctx.Queue(maxsize=200)
        self.event_queue = self.ctx.Queue(maxsize=5000)
        self.state_queue = self.ctx.Queue(maxsize=1000)

        self.proc = self.ctx.Process(
            target=run_bot_worker,
            args=(
                self.event_queue,
                self.state_queue,
                self.stop_event,
                self.pause_event,
                map_prefer_existing,
                map_new_city_xy,
                self.command_queue,
                adb_port,
            ),
            daemon=True,
        )
        self.proc.start()
        self.lbl_engine.setText("RUNNING")
        init_mode = "DUNG_MAP_CU" if map_prefer_existing else "TAO_MAP_MOI"
        self._append_log(f"[GUI] Lua chon khoi tao map: {init_mode}")
        if map_new_city_xy is not None:
            self._append_log(f"[GUI] Toa do map moi: X={map_new_city_xy[0]}, Y={map_new_city_xy[1]}")
        self._append_log(f"[GUI] ADB Port: {adb_port}")
        self._append_log("[GUI] Da start bot process.")
        self._set_buttons_for_running()

    def pause_bot(self):
        if self.pause_event is None:
            return
        self.pause_event.set()
        self._append_log("[GUI] Da gui lenh pause.")

    def resume_bot(self):
        if self.pause_event is None:
            return
        self.pause_event.clear()
        self._append_log("[GUI] Da gui lenh resume.")

    def stop_bot(self):
        if self.proc is None:
            return
        forced_terminate = False
        if self.stop_event is not None:
            self.stop_event.set()

        self.proc.join(timeout=8)
        if self.proc.is_alive():
            self._append_log("[GUI] Bot chua dung mem, terminate process.")
            self.proc.terminate()
            self.proc.join(timeout=3)
            forced_terminate = True

        # Nếu worker bị terminate cứng thì finally của worker có thể không chạy,
        # nên parent process cleanup ADB thêm một lần để tránh lock adb.exe.
        if forced_terminate:
            try:
                DeviceManager.stop_adb_server_global()
            except Exception:
                pass

        self.lbl_engine.setText("STOPPED")
        self._append_log("[GUI] Bot da dung.")
        self.proc = None
        self.stop_event = None
        self.pause_event = None
        self.command_queue = None
        self.event_queue = None
        self.state_queue = None
        self._set_buttons_for_stopped()

    def clear_log(self):
        self.log_view.clear()

    def _poll_queues(self):
        if self.proc is not None and not self.proc.is_alive() and self.lbl_engine.text() != "STOPPED":
            self.lbl_engine.setText("STOPPED")
            self._append_log("[GUI] Bot process da thoat.")
            self._set_buttons_for_stopped()

        if self.event_queue is not None:
            drained = 0
            while drained < 300:
                try:
                    event = self.event_queue.get_nowait()
                except queue.Empty:
                    break
                drained += 1

                if isinstance(event, dict) and event.get("type") == "log":
                    stream = event.get("stream", "stdout")
                    msg = event.get("message", "")
                    self._append_log(f"[{stream}] {msg}")
                elif isinstance(event, dict) and event.get("type") == "engine":
                    self._append_log(f"[ENGINE] {event.get('status', '')}")
                elif isinstance(event, dict) and event.get("type") == "GUI_CLEAR_LOG":
                    self.log_view.clear()
                    self._append_log("[GUI] Live Log da duoc xoa boi terminal auto-clear.")

        if self.state_queue is not None:
            latest = None
            while True:
                try:
                    latest = self.state_queue.get_nowait()
                except queue.Empty:
                    break

            if isinstance(latest, dict):
                self._render_state(latest)

    def _render_state(self, state):
        self.lbl_combat_mode.setText(str(state.get("combat_mode", "-")))
        self.lbl_combat_status.setText(str(state.get("combat_status", "-")))
        self.lbl_build_idx.setText(str(state.get("build_index", "-")))

        hd = []
        if state.get("hard_dig_pending_activation"):
            hd.append("PENDING")
        if state.get("hard_dig_waiting_final_retreat"):
            hd.append("WAIT_FINAL_RETREAT")
        if state.get("hard_dig_inflight_target"):
            hd.append(f"INFLIGHT={state.get('hard_dig_inflight_target')}")
        self.lbl_hard_dig.setText(" | ".join(hd) if hd else "IDLE")

        ts = state.get("ts")
        if ts:
            self.lbl_updated.setText(datetime.fromtimestamp(ts).strftime("%H:%M:%S"))

        if state.get("engine_paused"):
            self.lbl_engine.setText("PAUSED")
        elif self.proc is not None and self.proc.is_alive():
            self.lbl_engine.setText("RUNNING")

    def closeEvent(self, event):
        try:
            self.stop_bot()
        except Exception:
            pass
        try:
            if self.hard_planner_window is not None:
                self.hard_planner_window.close()
            if self.config_editor_window is not None:
                self.config_editor_window.close()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    # Chuẩn hóa cwd để các module dùng os.getcwd() tìm đúng config/assets/third_party.
    if getattr(sys, "frozen", False):
        app_root = os.path.dirname(sys.executable)
    else:
        app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    try:
        os.chdir(app_root)
    except Exception:
        pass

    mp.freeze_support()
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

