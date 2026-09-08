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

        for student_id, info in list(self.computers.items()):
            if info["websocket"] == websocket:
                info["status"] = "Offline"
                print(f"Student disconnected: {student_id}")

    async def send_to_computer(self, pc_id: str, message: dict):
     if pc_id in self.computers:
        websocket = self.computers[pc_id]["websocket"]
        await websocket.send_json(message)
        return True

     return False

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    def register_computer(
        self,
        hostname: str,
        ip_address: str,
        websocket: WebSocket
    ):
        pc_number = 1

        while f"PC-{pc_number:02d}" in self.computers:
            pc_number += 1

        pc_id = f"PC-{pc_number:02d}"

        self.computers[pc_id] = {
            "pc_id": pc_id,
            "hostname": hostname,
            "ip_address": ip_address,
            "websocket": websocket,
            "student_name": None,
            "status": "Online",
            "activity": None,
            "last_seen": datetime.now().isoformat()
        }

        return pc_id

    def get_computers(self):
        return list(self.computers.keys())