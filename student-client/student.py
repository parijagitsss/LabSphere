import asyncio
import json
import socket
import websockets
import ctypes
import psutil
import win32gui


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

async def student_client():
    uri = "ws://192.168.100.4:8000/ws"

    async with websockets.connect(uri) as websocket:
        print("Connected to LabSphere server!")

        pc_name = socket.gethostname()
        pc_ip = socket.gethostbyname(pc_name)

        with open("student-client/config.json", "r") as file:
            config = json.load(file)

        pc_id = config["pc_id"]

        registration = {
            "type": "REGISTER",
            "pc_id": pc_id,
            "hostname": pc_name,
            "ip_address": pc_ip
        }

        await websocket.send(json.dumps(registration))

        response = await websocket.recv()
        print("Server:", response)

        asyncio.create_task(send_heartbeat(websocket))
        asyncio.create_task(send_activity(websocket, pc_id))

        while True:
            message = await websocket.recv()
            print("Received:", message)

            command = json.loads(message)

            if command.get("type") == "COMMAND":
                command_name = command.get("command")
                data = command.get("data", {})

                if command_name == "SHOW_MESSAGE":
                    print("TEACHER MESSAGE:", data.get("message"))

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