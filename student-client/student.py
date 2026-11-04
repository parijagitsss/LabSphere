import asyncio
import json
import socket
from click import command
import websockets
import ctypes
import win32gui
import base64
import io
import mss
from PIL import Image, ImageTk, ImageOps
import uuid
from pathlib import Path
import tkinter as tk
from PIL import ImageTk
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class TeacherBroadcastViewer:
    def __init__(self):
        self.root = None
        self.label = None
        self.photo = None

    def show_frame(self, frame_bytes):
        try:
            image = Image.open(io.BytesIO(frame_bytes)).convert("RGB")

            if self.root is None or not self.root.winfo_exists():
                self.root = tk.Tk()
                self.root.title("LabSphere - Teacher Broadcast")

                # Make the broadcast occupy the entire student monitor.
                self.root.configure(bg="black")
                self.root.attributes("-fullscreen", True)
                self.root.attributes("-topmost", True)
                # Testing shortcut: ESC closes the fullscreen viewer.
                self.root.bind("<Escape>", self.close)

                # Prevent closing the broadcast through the window controls.
                self.root.protocol("WM_DELETE_WINDOW", lambda: None)

                self.label = tk.Label(
                    self.root,
                    bg="black",
                    borderwidth=0
                )
                self.label.pack(expand=True, fill="both")

                self.root.update_idletasks()

            # Get the actual student monitor dimensions.
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()

            # Fit the teacher's screen without stretching it.
            image = ImageOps.contain(
                image,
                (screen_width, screen_height)
            )

            self.photo = ImageTk.PhotoImage(image)
            self.label.configure(image=self.photo)

            self.root.update_idletasks()
            self.root.update()

        except Exception as error:
            print("Teacher broadcast display error:", error)

    def close(self, event=None):
        if self.root is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

            self.root = None
            self.label = None
            self.photo = None

# ==========================================
# BROWSER ACTIVITY RECEIVER
# ==========================================

latest_browser_activity = {}
browser_activity_lock = threading.Lock()


class BrowserActivityHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):

        if self.path != "/activity":
            self.send_error(404)
            return

        try:
            content_length = int(
                self.headers.get("Content-Length", 0)
            )

            if content_length > 10000:
                self.send_error(413)
                return

            data = json.loads(
                self.rfile.read(content_length)
            )

            required_fields = ["browser", "title", "url"]

            if not all(data.get(field) for field in required_fields):
                self.send_error(400)
                return

            with browser_activity_lock:
                global latest_browser_activity

                latest_browser_activity = {
                    "browser": data["browser"],
                    "title": data["title"],
                    "url": data["url"],
                    "domain": data.get("domain", "")
                }

            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"Activity received")

            print(
                f"Browser activity received: "
                f"{data['browser']} | {data['domain']}"
            )

        except Exception as error:
            print("Browser activity error:", error)
            self.send_error(400)

    def log_message(self, format, *args):
        pass


def start_browser_receiver():

    server = HTTPServer(
        ("127.0.0.1", 8765),
        BrowserActivityHandler
    )

    print("Browser activity receiver running on port 8765")

    server.serve_forever()

async def send_browser_activity(websocket, pc_id):

    last_sent = None

    while True:
        with browser_activity_lock:
            activity = latest_browser_activity.copy()

        if activity and activity != last_sent:

            message = {
                "type": "BROWSER_ACTIVITY",
                "pc_id": pc_id,
                "browser": activity.get("browser"),
                "title": activity.get("title"),
                "domain": activity.get("domain"),
                "timestamp": asyncio.get_running_loop().time()
            }

            await websocket.send(json.dumps(message))
            print(f"Browser activity sent to server: {activity.get('domain')}")

            last_sent = activity.copy()

        await asyncio.sleep(1)  

def get_device_id():
    config_path = Path(__file__).with_name("device_config.json")

    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as file:
                config = json.load(file)

            device_id = config.get("device_id")
            if device_id:
                return device_id
        except (json.JSONDecodeError, OSError):
            print("Could not read device_config.json. Creating a new device ID.")

    device_id = str(uuid.uuid4())

    with config_path.open("w", encoding="utf-8") as file:
        json.dump({"device_id": device_id}, file, indent=4)

    print(f"Created persistent device ID: {device_id}")
    return device_id

def get_active_window():
    try:
        window = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(window)

        if title:
            return title

        return "Unknown"

    except Exception:
        return "Unknown"

def get_idle_time():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("dwTime", ctypes.c_uint)
        ]

    last_input = LASTINPUTINFO()
    last_input.cbSize = ctypes.sizeof(LASTINPUTINFO)

    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input)):
        current_tick = ctypes.windll.kernel32.GetTickCount()
        idle_ms = current_tick - last_input.dwTime
        return round(idle_ms / 1000, 1)

    return 0

async def send_activity(websocket, pc_id):
    while True:
        try:
            activity = {
                "type": "ACTIVITY",
                "pc_id": pc_id,
                "timestamp": asyncio.get_running_loop().time(),
                "active_window": get_active_window()
            }

            await websocket.send(json.dumps(activity))

            print(
                f"Activity sent | Window: {activity['active_window']}"
            )

        except Exception as e:
            print("Activity error:", e)

        await asyncio.sleep(10)

def capture_screen_frame():
    with mss.mss() as screen_capture:
        screenshot = screen_capture.grab(screen_capture.monitors[1])
        image = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        image.thumbnail((1280, 720))

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=60)

        return base64.b64encode(buffer.getvalue()).decode("ascii")


async def stream_screen(websocket, pc_id, stop_event):
    loop = asyncio.get_running_loop()

    while not stop_event.is_set():
        try:
            frame = await loop.run_in_executor(
                None, capture_screen_frame
            )

            await websocket.send(json.dumps({
                "type": "SCREEN_FRAME",
                "pc_id": pc_id,
                "frame": frame
            }))

            await asyncio.sleep(1)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("Screen streaming error:", e)
            await asyncio.sleep(2)


async def student_client():
    threading.Thread(
    target=start_browser_receiver,
    daemon=True
).start()
    uri = "ws://127.0.0.1:8000/ws"

    async with websockets.connect(uri) as websocket:
        print("Connected to LabSphere server!")

        pc_name = socket.gethostname()
        pc_ip = socket.gethostbyname(pc_name)

        pc_id = None

        
        device_id = get_device_id()

        registration = {
            "type": "REGISTER",
            "hostname": pc_name,
            "ip_address": pc_ip,
            "device_id": device_id
        }

        await websocket.send(json.dumps(registration))

        response = await websocket.recv()
        print("Server:", response)

        registration_response = json.loads(response)

        if registration_response.get("type") != "REGISTER_SUCCESS":
            print("Registration failed. Student client will stop.")
            return

        pc_id = registration_response.get("pc_id")
        broadcast_viewer = TeacherBroadcastViewer()
        print(f"Assigned computer ID: {pc_id}")

        browser_task = asyncio.create_task(
            send_browser_activity(websocket, pc_id)
        )

        asyncio.create_task(send_heartbeat(websocket))
        asyncio.create_task(send_activity(websocket, pc_id))

        screen_stop_event = asyncio.Event()
        screen_task = asyncio.create_task(
            stream_screen(websocket, pc_id, screen_stop_event)
        )
        print("Continuous screen monitoring started")

    
        while True:
            message = await websocket.recv()
            print("Received:", message)

            command = json.loads(message)

            if command.get("type") == "TEACHER_SCREEN_FRAME":
                frame_data = command.get("frame")

                if frame_data:
                    try:
                        frame_bytes = base64.b64decode(frame_data)
                        broadcast_viewer.show_frame(frame_bytes)
                    except Exception as error:
                        print("Invalid teacher screen frame:", error)

                continue

            if command.get("type") != "COMMAND":
                continue

            command_name = command.get("command")
            data = command.get("data", {})

            if command_name == "START_TEACHER_BROADCAST":
                print("Teacher screen broadcast is starting")

            elif command_name == "STOP_TEACHER_BROADCAST":
                print("Teacher screen broadcast has stopped")
                broadcast_viewer.close()

            elif command_name == "START_MONITORING":
                if screen_task is None or screen_task.done():
                    screen_stop_event.clear()
                    screen_task = asyncio.create_task(
                        stream_screen(websocket, pc_id, screen_stop_event)
                    )
                    print("Screen monitoring started")

            elif command_name == "STOP_MONITORING":
                if screen_task and not screen_task.done():
                    screen_stop_event.set()
                    screen_task.cancel()
                    screen_task = None
                    print("Screen monitoring stopped")

            elif command_name == "SHOW_MESSAGE":
                teacher_message = data.get("message", "")
                print("TEACHER MESSAGE:", teacher_message)

                ctypes.windll.user32.MessageBoxW(
                    0,
                    teacher_message,
                    "Message from Teacher",
                    0x40
                )

            elif command_name == "PING":
                response = {
                    "type": "RESPONSE",
                    "command": "PING",
                    "status": "OK"
                }
                await websocket.send(json.dumps(response))
                print("PING response sent")

            elif command_name == "LOCK":
                print("LOCK command received")
                ctypes.windll.user32.LockWorkStation()

            elif command_name == "UNLOCK":
                print("UNLOCK command received")
                print("Windows unlock requires user authentication")

            else:
                print("TEACHER COMMAND:", command_name)
                print("COMMAND DATA:", data)

        
    
async def send_heartbeat(websocket):
    while True:
        await asyncio.sleep(10)

        ping_message = {
            "type": "RESPONSE",
            "command": "PING",
            "status": "OK"
        }

        await websocket.send(json.dumps(ping_message))
        print("Heartbeat sent")

asyncio.run(student_client())