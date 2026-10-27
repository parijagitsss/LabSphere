
from datetime import datetime

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.computers = {}
        self.sessions = {}
        self.student_list = {}
        self.assignments = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        for pc_id, info in list(self.computers.items()):
            if info["websocket"] == websocket:
                info["status"] = "Offline"
                print(f"Student disconnected: {pc_id}")

    async def send_to_computer(self, pc_id: str, message: dict):
        if pc_id in self.computers:
            info = self.computers[pc_id]

            if info["status"] != "Online":
                return False

            websocket = info["websocket"]

            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                print(f"Failed to send to {pc_id}: {e}")
                info["status"] = "Offline"
                return False

        return False

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"Broadcast failed: {e}")

    def register_computer(
        self,
        hostname: str,
        ip_address: str,
        websocket: WebSocket,
        device_id: str
    ):
        # Reuse the existing PC ID when a known device reconnects.
        for pc_id, info in self.computers.items():
            if info.get("device_id") == device_id:
                info["hostname"] = hostname
                info["ip_address"] = ip_address
                info["websocket"] = websocket
                info["status"] = "Online"
                info["last_seen"] = datetime.now().isoformat()

                print(f"Existing computer reconnected: {pc_id}")
                return pc_id

        # Assign the next unused PC ID to a new device.
        pc_number = 1

        while f"PC-{pc_number:02d}" in self.computers:
            pc_number += 1

        pc_id = f"PC-{pc_number:02d}"

        self.computers[pc_id] = {
            "pc_id": pc_id,
            "device_id": device_id,
            "hostname": hostname,
            "ip_address": ip_address,
            "websocket": websocket,
            "student_name": None,
            "status": "Online",
            "activity": None,
            "last_seen": datetime.now().isoformat()
        }

        print(f"New computer registered: {pc_id}")
        return pc_id

    def get_computers(self):
        return list(self.computers.keys())
