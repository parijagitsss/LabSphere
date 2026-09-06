import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.app.websocket.manager import ConnectionManager


app = FastAPI()

manager = ConnectionManager()
class SessionCreate(BaseModel):
    subject: str
    batch: str
    title: str

class StudentCreate(BaseModel):
    student_id: str
    name: str

class AssignmentCreate(BaseModel):
    session_id: str
    student_id: str
    pc_id: str

@app.post("/students")
def create_student(student: StudentCreate):
    manager.student_list[student.student_id] = {
        "student_id": student.student_id,
        "name": student.name
    }

    return manager.student_list[student.student_id]

@app.get("/students")
def get_students():
    return manager.student_list

@app.post("/assignments")
def assign_student(assignment: AssignmentCreate):

    for existing_assignment in manager.assignments.values():
        if existing_assignment["session_id"] == assignment.session_id:
            if existing_assignment["pc_id"] == assignment.pc_id:
                return {
                    "status": "computer_already_assigned",
                    "pc_id": assignment.pc_id
                }

            if existing_assignment["student_id"] == assignment.student_id:
                return {
                    "status": "student_already_assigned",
                    "student_id": assignment.student_id
                }

    if assignment.session_id not in manager.sessions:
        return {
            "status": "session_not_found",
            "session_id": assignment.session_id
        }
    if assignment.pc_id not in manager.computers:
        return {
            "status": "computer_not_found",
            "pc_id": assignment.pc_id
        }

    assignment_id = f"ASSIGN-{len(manager.assignments) + 1:03d}"

    manager.assignments[assignment_id] = {
        "assignment_id": assignment_id,
        "session_id": assignment.session_id,
        "student_id": assignment.student_id,
        "student_name": manager.student_list[assignment.student_id]["name"],
        "pc_id": assignment.pc_id
    }

    manager.computers[assignment.pc_id]["student_name"] = \
        manager.student_list[assignment.student_id]["name"]

    return {
        "status": "assigned",
        "assignment": manager.assignments[assignment_id]
    }

@app.delete("/assignments/{assignment_id}")
def unassign_student(assignment_id: str):
    if assignment_id not in manager.assignments:
        return {
            "status": "assignment_not_found",
            "assignment_id": assignment_id
        }

    assignment = manager.assignments[assignment_id]
    pc_id = assignment["pc_id"]

    if pc_id in manager.computers:
        manager.computers[pc_id]["student_name"] = None

    del manager.assignments[assignment_id]

    return {
        "status": "unassigned",
        "assignment_id": assignment_id,
        "pc_id": pc_id
    }

@app.get("/sessions/{session_id}/assignments")
def get_session_assignments(session_id: str):
    if session_id not in manager.sessions:
        return {
            "status": "session_not_found",
            "session_id": session_id
        }

    assignments = []

    for assignment in manager.assignments.values():
        if assignment["session_id"] == session_id:
            assignments.append(assignment)

    return {
        "session_id": session_id,
        "assignments": assignments
    }

@app.post("/sessions")
def create_session(session: SessionCreate):
        for existing_session in manager.sessions.values():
            if existing_session["status"] == "Active":
                return {
                    "status": "active_session_exists",
                    "session_id": existing_session["session_id"]
                }
        session_number = len(manager.sessions) + 1
        session_id = f"SESSION-{len(manager.sessions) + 1:03d}"

        manager.sessions[session_id] = {
        "session_id": session_id,
        "subject": session.subject,
        "batch": session.batch,
        "title": session.title,
        "status": "Active",
        "created_at": datetime.now().isoformat()
    }

        return manager.sessions[session_id]

@app.get("/sessions")
def get_sessions():
    return manager.sessions

@app.get("/sessions/active")
def get_active_session():
    for session in manager.sessions.values():
        if session["status"] == "Active":
            return session

    return {
        "status": "no_active_session"
    }

@app.post("/sessions/{session_id}/end")
def end_session(session_id: str):
    if session_id not in manager.sessions:
        return {
            "status": "session_not_found",
            "session_id": session_id
        }

    manager.sessions[session_id]["status"] = "Ended"
    manager.sessions[session_id]["ended_at"] = datetime.now().isoformat()

    ended_assignments = []

    for assignment_id, assignment in list(manager.assignments.items()):
        if assignment["session_id"] == session_id:
            pc_id = assignment["pc_id"]

            if pc_id in manager.computers:
                manager.computers[pc_id]["student_name"] = None

            ended_assignments.append(assignment_id)
            del manager.assignments[assignment_id]

    return {
        "status": "session_ended",
        "session": manager.sessions[session_id],
        "cleared_assignments": ended_assignments
    }

@app.get("/health")
def health_check():
    return {"status": "online"}


@app.get("/computers")
def get_computers():
    computers = {}

    for pc_id, info in manager.computers.items():
        computers[pc_id] = {
            "pc_id": info["pc_id"],
            "hostname": info["hostname"],
            "ip_address": info["ip_address"],
            "student_name": info["student_name"],
            "status": info["status"],
            "last_seen": info["last_seen"]
        }

    return computers

@app.get("/computers/{pc_id}")
def get_computer(pc_id: str):
    if pc_id not in manager.computers:
        return {
            "status": "computer_not_found",
            "pc_id": pc_id
        }

    info = manager.computers[pc_id]

    return {
        "pc_id": info["pc_id"],
        "hostname": info["hostname"],
        "ip_address": info["ip_address"],
        "student_name": info["student_name"],
        "status": info["status"],
        "last_seen": info["last_seen"]
    }

@app.post("/computers/{pc_id}/message")
async def send_computer_message(pc_id: str):
    success = await manager.send_to_computer(
        pc_id,
        {
            "type": "COMMAND",
            "command": "SHOW_MESSAGE",
            "data": {
                "message": "Hello from LabSphere Teacher!"
            }
        }
    )

    if success:
        return {
            "status": "sent",
            "pc_id": pc_id
        }

    return {
        "status": "computer_not_found",
        "pc_id": pc_id
    }


@app.post("/computers/{pc_id}/ping")
async def ping_computer(pc_id: str):
    success = await manager.send_to_computer(
        pc_id,
        {
            "type": "COMMAND",
            "command": "PING",
            "data": {}
        }
    )

    if success:
        return {
            "status": "ping_sent",
            "pc_id": pc_id
        }

    return {
        "status": "computer_not_found",
        "pc_id": pc_id
    }

class ComputerCommand(BaseModel):
    command: str
    data: dict = {}

@app.post("/computers/{pc_id}/command")
async def send_computer_command(
    pc_id: str,
    command: ComputerCommand
):
    if pc_id not in manager.computers:
        return {
            "status": "computer_not_found",
            "pc_id": pc_id
        }

    success = await manager.send_to_computer(
        pc_id,
        {
            "type": "COMMAND",
            "command": command.command,
            "data": command.data
        }
    )

    if success:
        return {
            "status": "command_sent",
            "pc_id": pc_id,
            "command": command.command
        }

    return {
        "status": "computer_offline",
        "pc_id": pc_id
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            message = await websocket.receive_text()

            data = json.loads(message)

            if data.get("type") == "REGISTER":
                pc_id = data.get("pc_id")
                hostname = data.get("hostname")
                ip_address = data.get("ip_address")

                if pc_id and hostname and ip_address:
                    manager.register_computer(
                        pc_id,
                        hostname,
                        ip_address,
                        websocket
                    )

                    await websocket.send_json({
                        "type": "REGISTER_SUCCESS",
                        "message": f"Computer {pc_id} registered successfully"
                    })

                    print(
                        f"Computer connected: {pc_id} | Hostname: {hostname} | IP: {ip_address}"
                    )

            elif data.get("type") == "RESPONSE":
                command = data.get("command")
                status = data.get("status")

                if command == "PING":
                    for pc_id, info in manager.computers.items():
                        if info["websocket"] == websocket:
                            manager.computers[pc_id]["last_seen"] = datetime.now().isoformat()

                            print(
                                f"PING response from {pc_id}: {status}"
                            )

                            break

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Computer disconnected")


async def check_computer_status():
    while True:
        await asyncio.sleep(10)

        now = datetime.now()

        for pc_id, info in manager.computers.items():
            last_seen = datetime.fromisoformat(info["last_seen"])

            elapsed = (now - last_seen).total_seconds()

            if elapsed > 30:
                info["status"] = "Offline"
                print(f"Computer offline: {pc_id}")
            else:
                info["status"] = "Online"


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_computer_status())