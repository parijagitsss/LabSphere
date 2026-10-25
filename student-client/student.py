import asyncio
import json
import socket
import websockets
import ctypes
import psutil
import win32gui
import base64
import io
import mss
from PIL import Image


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
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "timestamp": asyncio.get_running_loop().time(),
                "active_window": get_active_window(),
                "idle_seconds": get_idle_time(),
            }

            await websocket.send(json.dumps(activity))

            print(
                f"Activity sent | CPU: {activity['cpu_percent']}% | "
                f"RAM: {activity['memory_percent']}%"
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
    uri = "ws://127.0.0.1:8000/ws"

    async with websockets.connect(uri) as websocket:
        print("Connected to LabSphere server!")

        pc_name = socket.gethostname()
        pc_ip = socket.gethostbyname(pc_name)

        pc_id = None

        registration = {
            "type": "REGISTER",
            "hostname": pc_name,
            "ip_address": pc_ip
        }

        await websocket.send(json.dumps(registration))

        response = await websocket.recv()
        print("Server:", response)

        registration_response = json.loads(response)

        if registration_response.get("type") == "REGISTER_SUCCESS":
            pc_id = registration_response.get("pc_id")
            print(f"Assigned computer ID: {pc_id}")

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

            if command.get("type") == "COMMAND":
                command_name = command.get("command")
                data = command.get("data", {})

                if command_name == "START_MONITORING":
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