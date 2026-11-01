import asyncio
import ctypes
import json
import threading
import time

import websockets
from PySide6.QtCore import QObject, Signal, Qt, QTimer, QRect
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QHBoxLayout, QLabel
BACKEND_URL = "ws://127.0.0.1:8000/ws/teacher-overlay"
COLORS = [
    ("Red", "#ff3333"),
    ("Blue", "#3399ff"),
    ("Green", "#22cc77"),
    ("Yellow", "#ffcc00"),
    ("White", "#ffffff"),
]

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Windows API signatures (64-bit safe)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p)
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, ctypes.c_uint]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.c_bool
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetAncestor.restype = ctypes.c_void_p
user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.MonitorFromWindow.restype = ctypes.c_void_p
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowRect.restype = ctypes.c_bool
user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetClientRect.restype = ctypes.c_bool
user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.ClientToScreen.restype = ctypes.c_bool

# Force the ink window to be click-through at the Windows level as well as Qt level.
_get_window_long_ptr = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_set_window_long_ptr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_get_window_long_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int]
_get_window_long_ptr.restype = ctypes.c_ssize_t
_set_window_long_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
_set_window_long_ptr.restype = ctypes.c_ssize_t

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
HC_ACTION = 0
GA_ROOT = 2

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = ctypes.c_void_p

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = ctypes.c_bool

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT), ("mouseData", ctypes.c_ulong), ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)
    ]

class BridgeSignals(QObject):
    message_received = Signal(dict)
    connected = Signal()
    disconnected = Signal()

class BridgeClient:
    def __init__(self):
        self.loop = None
        self.websocket = None
        self.signals = BridgeSignals()
        threading.Thread(target=self._thread_main, daemon=True).start()

    def _thread_main(self):
        asyncio.run(self._connect())

    async def _connect(self):
        try:
            async with websockets.connect(BACKEND_URL, ping_interval=20, ping_timeout=20) as websocket:
                self.loop = asyncio.get_running_loop()
                self.websocket = websocket
                await websocket.send(json.dumps({"role": "overlay"}))
                self.signals.connected.emit()
                async for raw_message in websocket:
                    try:
                        self.signals.message_received.emit(json.loads(raw_message))
                    except json.JSONDecodeError:
                        print("Invalid message received from backend")
        except Exception as error:
            print("Overlay bridge connection error:", error)
        finally:
            self.websocket = None
            self.signals.disconnected.emit()

    def send(self, message):
        if not self.websocket or not self.loop or not self.loop.is_running():
            print(
                f"[Overlay Bridge] WebSocket not ready. "
                f"Could not send: {message.get('type')}"
            )
            return

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.websocket.send(json.dumps(message)),
                self.loop
            )

            def check_result(f):
                try:
                    f.result()
                    print(
                        f"[Overlay Bridge] Sent successfully: "
                        f"{message.get('type')} | "
                        f"{message.get('action', '')}"
                    )
                except Exception as error:
                    print(f"[Overlay Bridge] Send failed: {error}")

            future.add_done_callback(check_result)

        except Exception as error:
            print(f"[Overlay Bridge] Error: {error}")

class DesktopInkOverlay(QWidget):
    """Transparent, click-through ink layer positioned over the selected app window."""
    def __init__(self):
        super().__init__()
        self.lines = []
        self.current_points = []
        self.current_color = COLORS[0][1]
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.hide()

    def enable_native_click_through(self):
        hwnd = ctypes.c_void_p(int(self.winId()))
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        current = _get_window_long_ptr(hwnd, GWL_EXSTYLE)
        updated = current | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        _set_window_long_ptr(hwnd, GWL_EXSTYLE, updated)

    def add_point(self, action, x, y, color):
        self.current_color = color
        point = (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))
        if action == "start":
            self.current_points = [point]
        elif action == "move" and self.current_points:
            self.current_points.append(point)
        elif action == "end" and self.current_points:
            self.current_points.append(point)
            if len(self.current_points) > 1:
                self.lines.append((self.current_color, self.current_points[:]))
            self.current_points = []
        self.update()

    def clear(self):
        self.lines.clear()
        self.current_points = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for color, points in self.lines:
            self._paint_points(painter, color, points)
        if self.current_points:
            self._paint_points(painter, self.current_color, self.current_points)

    def _paint_points(self, painter, color, points):
        if len(points) < 2:
            return
        pen = QPen(QColor(color), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        path_points = [
            (round(x * self.width()), round(y * self.height())) for x, y in points
        ]
        for first, second in zip(path_points, path_points[1:]):
            from PySide6.QtCore import QLine
            painter.drawLine(QLine(first[0], first[1], second[0], second[1]))

class GlobalMouseHook:
    def __init__(self, toolbar, bridge, ink_overlay):
        self.toolbar = toolbar
        self.bridge = bridge
        self.ink_overlay = ink_overlay
        self.drawing = False
        self.pen_enabled = False
        self.selecting_target = False
        self.color = COLORS[0][1]
        self.target_hwnd = None
        self.target_content_hwnd = None
        self.target_rect = None
        self.capture_rect = None
        self.capture_surface = "window"
        self.last_move_time = 0
        self.callback = HOOKPROC(self._mouse_callback)
        self.hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self.callback, kernel32.GetModuleHandleW(None), 0)
        if not self.hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def _window_at(self, x, y):
        """Return both the child under the pointer and its top-level window."""
        child = user32.WindowFromPoint(POINT(x, y))
        if not child:
            return None, None
        root = user32.GetAncestor(child, GA_ROOT)
        return child, (root or child)

    def _get_rect(self, hwnd):
        rect = RECT()
        if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            if rect.right > rect.left and rect.bottom > rect.top:
                return (rect.left, rect.top, rect.right, rect.bottom)
        return None

    def _get_client_rect(self, hwnd):
        rect = RECT()

        if not hwnd:
            return None

        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None

        top_left = POINT(rect.left, rect.top)
        bottom_right = POINT(rect.right, rect.bottom)

        if not user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
            return None

        if not user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
            return None

        if bottom_right.x <= top_left.x or bottom_right.y <= top_left.y:
            return None

        return (
            top_left.x,
            top_left.y,
            bottom_right.x,
            bottom_right.y
        )

    def _send_point(self, action, x, y):
        if not self.target_rect or not self.capture_rect:
            return

        # Local ink is positioned over the selected application window.
        tl, tt, tr, tb = self.target_rect
        tw, th = tr - tl, tb - tt
        if tw <= 0 or th <= 0:
            return
        local_x = max(0.0, min(1.0, (x - tl) / tw))
        local_y = max(0.0, min(1.0, (y - tt) / th))

        # Broadcast coordinates must be relative to the actual captured source.
        # For monitor capture this is the monitor, not the app window. For a
        # browser-tab capture it is the browser's page-rendering child window.
        cl, ct, cr, cb = self.capture_rect
        cw, ch = cr - cl, cb - ct
        if cw <= 0 or ch <= 0:
            return
        frame_x = max(0.0, min(1.0, (x - cl) / cw))
        frame_y = max(0.0, min(1.0, (y - ct) / ch))

        self.bridge.send({
            "type": "DRAW_EVENT", "action": action,
            "x": frame_x, "y": frame_y, "color": self.color
        })
        self.ink_overlay.add_point(action, local_x, local_y, self.color)

    def _get_monitor_rect(self, hwnd):
        if not hwnd:
            return None
        monitor = user32.MonitorFromWindow(hwnd, 2)  # nearest monitor
        if not monitor:
            return None
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        r = info.rcMonitor
        return (r.left, r.top, r.right, r.bottom)

    def _refresh_capture_rect(self):
        if not self.target_hwnd:
            self.capture_rect = None
            return
        root_rect = self._get_rect(self.target_hwnd) or self.target_rect
        if self.capture_surface == "monitor":
            # The captured frame is the whole monitor, but local ink still
            # remains restricted to the selected application window.
            self.target_rect = root_rect
            self.capture_rect = self._get_monitor_rect(self.target_hwnd) or root_rect
        elif self.capture_surface == "browser":
            # Chromium tab capture excludes browser chrome. Use the renderer
            # child window clicked by the teacher, falling back to client area.
            child_rect = self._get_rect(self.target_content_hwnd) if self.target_content_hwnd else None
            self.target_rect = child_rect or self._get_client_rect(self.target_hwnd) or root_rect
            self.capture_rect = self.target_rect
        else:
            self.target_rect = root_rect
            self.capture_rect = root_rect

    def _consume_mouse_event(self):
        # Returning 1 from WH_MOUSE_LL prevents the click from reaching the
        # application underneath. This is intentionally limited to the active
        # stroke so normal mouse use resumes immediately when the pen is off.
        return 1

    def _is_over_toolbar(self, x, y):
        toolbar_hwnd = int(self.toolbar.winId())
        rect = self._get_rect(toolbar_hwnd)

        if not rect:
            return False

        left, top, right, bottom = rect

        return left <= x <= right and top <= y <= bottom

    def _mouse_callback(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            data = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = data.pt.x, data.pt.y
            # Never intercept clicks on the floating toolbar.
            # This keeps Pen, Color, Clear and Exit functional.
            if not self.drawing and self._is_over_toolbar(x, y):
                return user32.CallNextHookEx(
                    self.hook,
                    n_code,
                    w_param,
                    l_param
                )
            if self.selecting_target and w_param == WM_LBUTTONDOWN:
                child_hwnd, hwnd = self._window_at(x, y)
                toolbar_hwnd = int(self.toolbar.winId())
                if hwnd and int(hwnd) != toolbar_hwnd:
                    rect = self._get_rect(hwnd)
                    if rect:
                        self.target_hwnd = hwnd
                        self.target_content_hwnd = child_hwnd
                        self.target_rect = rect
                        self._refresh_capture_rect()
                        self.selecting_target = False
                        self.toolbar.target_selected.emit(rect)
                return user32.CallNextHookEx(self.hook, n_code, w_param, l_param)

            if self.pen_enabled and self.target_rect:
                left, top, right, bottom = self.target_rect
                inside = left <= x <= right and top <= y <= bottom

                if w_param == WM_LBUTTONDOWN and inside:
                    self.drawing = True
                    self._send_point("start", x, y)
                    return self._consume_mouse_event()

                elif w_param == WM_MOUSEMOVE and self.drawing:
                    now = time.monotonic()

                    if now - self.last_move_time >= 0.01:
                        self.last_move_time = now
                        self._send_point("move", x, y)

                    # Allow mouse movement to reach Windows and the application.
                    # The initial mouse-down was intercepted, so this should not
                    # trigger normal dragging or text selection.
                    return user32.CallNextHookEx(
                        self.hook,
                        n_code,
                        w_param,
                        l_param
                    )

                elif w_param == WM_LBUTTONUP and self.drawing:
                    self._send_point("end", x, y)
                    self.drawing = False
                    return self._consume_mouse_event()
        return user32.CallNextHookEx(self.hook, n_code, w_param, l_param)

    def stop(self):
        self.drawing = False
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None

class TeacherToolbar(QWidget):
    target_selected = Signal(tuple)

    def __init__(self):
        super().__init__()
        self.bridge = BridgeClient()
        self.color_index = 0
        self.color_buttons = []
        self.pen_enabled = False
        self.broadcasting = False
        self.ink_overlay = DesktopInkOverlay()
        self.setWindowTitle("LabSphere Teacher Tools")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setStyleSheet("""
            QWidget {
                background-color: #24213d;
                color: #f8f6ff;
                border: 1px solid #6252c4;
                border-radius: 14px;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }
            QLabel {
                color: #c9c2f0;
                padding: 5px 9px;
                border: none;
                font-size: 9pt;
                font-weight: 600;
            }
            QPushButton {
                background-color: #353052;
                color: #f8f6ff;
                border: 1px solid #514879;
                padding: 9px 13px;
                border-radius: 9px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #49416f;
                border-color: #a99bf0;
            }
            QPushButton:pressed { background-color: #6252c4; }
            QPushButton:checked {
                background-color: #7767d9;
                color: white;
                border: 1px solid #b7a9f5;
            }
        """)
        self.status_label = QLabel("Connecting...")
        self.target_button = QPushButton("Set Target")
        self.pen_button = QPushButton("Pen OFF")

        self.color_buttons = []

        for index, (name, color) in enumerate(COLORS):
            button = QPushButton()
            button.setFixedSize(24, 24)
            button.setCheckable(True)
            button.setToolTip(f"{name} pen")

            button.clicked.connect(
                lambda checked=False, i=index: self.select_color(i)
            )

            self.color_buttons.append(button)

        self.clear_button = QPushButton("Clear")
        self.exit_button = QPushButton("Exit")
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(7)
        for widget in (self.status_label, self.target_button, self.pen_button):
            layout.addWidget(widget)

        for button in self.color_buttons:
            layout.addWidget(button)

        for widget in (self.clear_button, self.exit_button):
            layout.addWidget(widget)
        self.setLayout(layout)
        self.target_button.clicked.connect(self.begin_target_selection)
        self.pen_button.clicked.connect(self.toggle_pen)
        self.clear_button.clicked.connect(self.clear_annotations)
        self.exit_button.clicked.connect(self.close)
        self.mouse_hook = GlobalMouseHook(self, self.bridge, self.ink_overlay)
        self.target_selected.connect(self.apply_target)
        self.bridge.signals.connected.connect(lambda: self.status_label.setText("Connected"))
        self.bridge.signals.disconnected.connect(lambda: self.status_label.setText("Disconnected"))
        self.bridge.signals.message_received.connect(self.handle_dashboard_message)
        self.resize(700, 66)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width() - self.width()) // 2, screen.y() + screen.height() - self.height() - 45)
        self.hide()

        self.position_timer = QTimer(self)
        self.position_timer.timeout.connect(self.refresh_target_position)
        self.position_timer.start(250)

    def begin_target_selection(self):
        self.mouse_hook.selecting_target = True
        self.status_label.setText("Click the shared app window")
        self.target_button.setText("Waiting...")

    def _set_ink_overlay_geometry(self, rect):
        # WH_MOUSE_LL and Win32 window rectangles use physical screen pixels.
        # Qt widget geometry uses device-independent pixels on scaled displays.
        # Convert before positioning the transparent ink window; the stroke
        # itself remains normalized, so student-frame coordinates are unchanged.
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        left, top, right, bottom = rect
        self.ink_overlay.setGeometry(QRect(
            round(left / dpr),
            round(top / dpr),
            round((right - left) / dpr),
            round((bottom - top) / dpr),
        ))

    def apply_target(self, rect):
        self._set_ink_overlay_geometry(rect)
        self.ink_overlay.show()
        self.ink_overlay.enable_native_click_through()
        self.ink_overlay.raise_()
        self.target_button.setText("Target Set")
        self.status_label.setText("Target window ready")
        self.mouse_hook.pen_enabled = self.pen_enabled
        self.bridge.send({"type": "TARGET_WINDOW_SET", "width": rect[2] - rect[0], "height": rect[3] - rect[1]})

    def refresh_target_position(self):
        hwnd = self.mouse_hook.target_hwnd
        if not hwnd:
            return
        rect = self.mouse_hook._get_rect(hwnd)
        if not rect:
            self.ink_overlay.hide()
            self.mouse_hook.target_rect = None
            self.mouse_hook.capture_rect = None
            self.mouse_hook.target_hwnd = None
            self.mouse_hook.target_content_hwnd = None
            self.status_label.setText("Target window closed")
            return
        self.mouse_hook.target_rect = rect
        self._set_ink_overlay_geometry(rect)
        if not self.ink_overlay.isVisible():
            self.ink_overlay.show()
            self.ink_overlay.enable_native_click_through()

    def toggle_pen(self):
        self.pen_enabled = not self.pen_enabled
        self.mouse_hook.pen_enabled = self.pen_enabled
        if not self.pen_enabled:
            self.mouse_hook.drawing = False
        self.pen_button.setText("Pen ON" if self.pen_enabled else "Pen OFF")
        self.bridge.send({"type": "PEN_STATE", "enabled": self.pen_enabled})

    def select_color(self, index):
        self.color_index = index

        color_name, color_value = COLORS[index]

        self.mouse_hook.color = color_value
        self.ink_overlay.current_color = color_value

        self.update_color_buttons()

        self.bridge.send({
            "type": "PEN_COLOR",
            "color": color_value
        })


    def update_color_buttons(self):
        for index, button in enumerate(self.color_buttons):
            name, color = COLORS[index]
            selected = index == self.color_index

            button.setChecked(selected)

            border = "#b7a9f5" if selected else "#81799f"
            border_width = "3px" if selected else "1px"

            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: {border_width} solid {border};
                    border-radius: 11px;
                    padding: 0px;
                }}

                QPushButton:hover {{
                    border: 3px solid #b7a9f5;
                }}

                QPushButton:checked {{
                    border: 3px solid #b7a9f5;
                }}
            """)

    def clear_annotations(self):
        self.ink_overlay.clear()
        self.bridge.send({"type": "CLEAR_ANNOTATIONS"})

    def handle_dashboard_message(self, message):
        kind = message.get("type")

        if kind == "BROADCAST_STATE":
            self.broadcasting = bool(message.get("broadcasting"))
            surface = message.get("displaySurface") or "window"
            self.mouse_hook.capture_surface = surface if surface in ("browser", "window", "monitor") else "window"
            self.refresh_target_position()

            if self.broadcasting:
                self.show()
                self.raise_()
                self.status_label.setText("Ready to annotate")
            else:
                self.pen_enabled = False
                self.mouse_hook.pen_enabled = False
                self.mouse_hook.drawing = False
                self.pen_button.setText("Pen OFF")
                self.ink_overlay.clear()
                self.ink_overlay.hide()
                self.hide()

        elif kind == "CLEAR_ANNOTATIONS":
            self.ink_overlay.clear()
            
    def closeEvent(self, event):
        self.position_timer.stop()
        self.mouse_hook.stop()
        self.ink_overlay.close()
        self.bridge.send({"type": "OVERLAY_CLOSED"})
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    toolbar = TeacherToolbar()
    app.exec()
