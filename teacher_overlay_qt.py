
import sys
import ctypes

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QColorDialog,
    QHBoxLayout, QVBoxLayout, QLabel
)


class DrawingOverlay(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LabSphere Drawing Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.pen_color = QColor("#ff3333")
        self.pen_width = 5
        self.drawing_enabled = False
        self.last_point = None
        self.lines = []

        self.setGeometry(QApplication.primaryScreen().geometry())
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self.show()
        self.set_click_through(True)

        # Emergency exit: Ctrl + Alt + F12
        self.emergency_exit = QShortcut(
            QKeySequence("Ctrl+Alt+F12"), self
        )
        self.emergency_exit.activated.connect(
            QApplication.quit
        )

    def set_click_through(self, enabled):
    # Temporary diagnostic: do not modify Windows click-through styles.
        print("Click-through temporarily disabled for testing")

    def set_drawing_enabled(self, enabled):
        self.drawing_enabled = enabled

        self.set_click_through(not enabled)

        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.show()
            self.raise_()
            print("DRAWING MODE ON")
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setMouseTracking(True)
            print("DRAWING MODE OFF")

    def mousePressEvent(self, event):
        print("MOUSE PRESSED:", event.position().toPoint())

        if not self.drawing_enabled:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.last_point = event.position().toPoint()

    def mouseMoveEvent(self, event):
        print("MOUSE MOVED:", event.position().toPoint())
        if not self.drawing_enabled or self.last_point is None:
            return

        current_point = event.position().toPoint()

        self.lines.append((
            QPoint(self.last_point),
            QPoint(current_point),
            QColor(self.pen_color),
            self.pen_width
        ))

        self.last_point = current_point
        self.update()

    def mouseReleaseEvent(self, event):
        self.last_point = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for start, end, color, width in self.lines:
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

            painter.setPen(pen)
            painter.drawLine(start, end)


class AnnotationToolbar(QWidget):
    def __init__(self, overlay):
        super().__init__()

        self.overlay = overlay

        self.setWindowTitle("LabSphere Toolbar")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setStyleSheet("""
            QWidget {
                background-color: #202938;
                color: white;
            }
            QPushButton {
                background-color: #34445c;
                color: white;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #4c6383;
            }
        """)

        self.setGeometry(100, 100, 470, 65)

        layout = QHBoxLayout(self)

        self.toggle_button = QPushButton("Enable Pen")
        self.toggle_button.clicked.connect(self.toggle_pen)
        layout.addWidget(self.toggle_button)

        color_button = QPushButton("Color")
        color_button.clicked.connect(self.choose_color)
        layout.addWidget(color_button)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear_annotations)
        layout.addWidget(clear_button)

        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(QApplication.quit)
        layout.addWidget(exit_button)

        self.show()

    def toggle_pen(self):
        enabled = not self.overlay.drawing_enabled

        self.overlay.set_drawing_enabled(enabled)

        self.toggle_button.setText(
            "Disable Pen" if enabled else "Enable Pen"
        )

    def choose_color(self):
        color = QColorDialog.getColor(
            self.overlay.pen_color,
            self
        )

        if color.isValid():
            self.overlay.pen_color = color

    def clear_annotations(self):
        self.overlay.lines.clear()
        self.overlay.update()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    overlay = DrawingOverlay()
    toolbar = AnnotationToolbar(overlay)

    sys.exit(app.exec())
