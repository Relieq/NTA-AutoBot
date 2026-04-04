import multiprocessing as mp
import queue
import sys
import os
import json
from datetime import datetime

from core.gui_bridge import run_bot_worker

try:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtGui import QColor, QIntValidator, QPainter, QPen
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QToolTip,
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

        self._build_ui()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_queues)
        self.poll_timer.start(200)

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        ctrl_box = QGroupBox("Dieu khien Bot")
        ctrl_layout = QHBoxLayout(ctrl_box)
        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_stop = QPushButton("Stop")
        self.btn_clear = QPushButton("Clear Log")

        self.btn_start.clicked.connect(self.start_bot)
        self.btn_pause.clicked.connect(self.pause_bot)
        self.btn_resume.clicked.connect(self.resume_bot)
        self.btn_stop.clicked.connect(self.stop_bot)
        self.btn_clear.clicked.connect(self.clear_log)

        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_pause)
        ctrl_layout.addWidget(self.btn_resume)
        ctrl_layout.addWidget(self.btn_stop)
        ctrl_layout.addWidget(self.btn_clear)
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
        self.input_map_x.setPlaceholderText("X")
        self.input_map_y.setPlaceholderText("Y")
        self.input_map_x.setMaximumWidth(80)
        self.input_map_y.setMaximumWidth(80)
        self.input_map_x.setValidator(QIntValidator(0, 600, self))
        self.input_map_y.setValidator(QIntValidator(0, 600, self))
        self.input_map_x.setText("300")
        self.input_map_y.setText("300")

        map_layout.addWidget(self.radio_use_existing_map)
        map_layout.addWidget(self.radio_create_new_map)
        map_layout.addWidget(QLabel("X:"))
        map_layout.addWidget(self.input_map_x)
        map_layout.addWidget(QLabel("Y:"))
        map_layout.addWidget(self.input_map_y)
        layout.addWidget(map_box)
        self._update_map_input_enabled()

        hard_box = QGroupBox("Hard-Dig Planner")
        hard_layout = QVBoxLayout(hard_box)

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
        self.lbl_zoom = QLabel("Zoom: 20")
        self.btn_zoom_out.clicked.connect(lambda: self._zoom_canvas(-2))
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_canvas(2))
        zoom_row.addWidget(self.btn_zoom_out)
        zoom_row.addWidget(self.btn_zoom_in)
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

        layout.addWidget(hard_box)

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

        log_box = QGroupBox("Live Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_box)

        self._set_buttons_for_stopped()

        self._load_hard_dig_plan_into_canvas()
        self._reload_hard_dig_overlay(show_feedback=False)

    def _set_buttons_for_running(self):
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_resume.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.radio_use_existing_map.setEnabled(False)
        self.radio_create_new_map.setEnabled(False)
        self.input_map_x.setEnabled(False)
        self.input_map_y.setEnabled(False)

    def _set_buttons_for_stopped(self):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.radio_use_existing_map.setEnabled(True)
        self.radio_create_new_map.setEnabled(True)
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

    def _append_log(self, line):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{now}] {line}")

    def start_bot(self):
        if self.proc is not None and self.proc.is_alive():
            QMessageBox.information(self, "Thong bao", "Bot dang chay.")
            return

        map_prefer_existing = self.radio_use_existing_map.isChecked()
        map_new_city_xy = None
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
            ),
            daemon=True,
        )
        self.proc.start()
        self.lbl_engine.setText("RUNNING")
        init_mode = "DUNG_MAP_CU" if map_prefer_existing else "TAO_MAP_MOI"
        self._append_log(f"[GUI] Lua chon khoi tao map: {init_mode}")
        if map_new_city_xy is not None:
            self._append_log(f"[GUI] Toa do map moi: X={map_new_city_xy[0]}, Y={map_new_city_xy[1]}")
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
        if self.stop_event is not None:
            self.stop_event.set()

        self.proc.join(timeout=8)
        if self.proc.is_alive():
            self._append_log("[GUI] Bot chua dung mem, terminate process.")
            self.proc.terminate()
            self.proc.join(timeout=3)

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
        super().closeEvent(event)


def main():
    mp.freeze_support()
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

