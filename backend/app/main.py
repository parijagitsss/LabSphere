import asyncio
import json
from datetime import datetime
import os
import subprocess
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.websocket.manager import ConnectionManager
from backend.app.database import (
    sessions_collection,
    activity_collection
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()
# Latest screen frame for each monitored computer
screen_frames = {}
teacher_screen_frame = None 

# Desktop annotation communication bridge
teacher_overlay_clients = set()
teacher_dashboard_clients = set()
# Teacher desktop toolbar process
teacher_overlay_process = None

def start_teacher_overlay():
    global teacher_overlay_process

    if teacher_overlay_process and teacher_overlay_process.poll() is None:
        print("Teacher toolbar is already running.")
        return

    project_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    overlay_script = os.path.join(project_dir, "teacher_overlay.py")

    if not os.path.exists(overlay_script):
        print(f"Teacher toolbar script not found: {overlay_script}")
        return

    teacher_overlay_process = subprocess.Popen(
        [sys.executable, overlay_script],
        cwd=project_dir
    )

    print("Teacher toolbar launched automatically.")


async def forward_overlay_message(clients, message):
    """Forward a message to all connected clients in a group."""
    disconnected = []

    for client in list(clients):
        try:
            await client.send_json(message)
        except Exception as error:
            print(f"Overlay bridge send failed: {error}")
            disconnected.append(client)

    for client in disconnected:
        clients.discard(client)
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

    # Check MongoDB for an existing active session
    existing_session = sessions_collection.find_one(
        {"status": "Active"},
        {"_id": 0}
    )

    if existing_session:

        # Restore the active session in backend memory
        created_at = existing_session.get("created_at")

        if isinstance(created_at, datetime):
            existing_session["created_at"] = created_at.isoformat()

        manager.sessions[existing_session["session_id"]] = existing_session

        return {
            "status": "active_session_exists",
            "session_id": existing_session["session_id"]
        }

    session_id = f"SESSION-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    created_at = datetime.now()

    session_data = {
        "session_id": session_id,
        "subject": session.subject,
        "batch": session.batch,
        "title": session.title,
        "status": "Active",
        "created_at": created_at.isoformat()
    }

    # Store in memory
    manager.sessions[session_id] = session_data

    # Store permanently in MongoDB
    mongo_session = {
        **session_data,
        "created_at": created_at
    }

    sessions_collection.insert_one(mongo_session)

    return session_data

@app.get("/sessions")
def get_sessions():
    sessions = list(sessions_collection.find({}, {"_id": 0}))

    return sessions
@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):

    session = sessions_collection.find_one({
        "session_id": session_id
    })

    if not session:
        return {
            "status": "session_not_found",
            "session_id": session_id
        }

    if session["status"] == "Active":
        return {
            "status": "active_session_cannot_be_deleted",
            "message": "Please end the session before deleting it."
        }

    # Delete associated activity records
    activity_result = activity_collection.delete_many({
        "session_id": session_id
    })

    # Delete the session itself
    sessions_collection.delete_one({
        "session_id": session_id
    })

    # Remove from backend memory
    manager.sessions.pop(session_id, None)

    return {
        "status": "session_deleted",
        "session_id": session_id,
        "deleted_activity_records": activity_result.deleted_count
    }


@app.get("/sessions/{session_id}/activity")
def get_session_activity(session_id: str):

    # Check whether the session exists in MongoDB
    session = sessions_collection.find_one(
        {"session_id": session_id}
    )

    if not session:
        return {
            "status": "session_not_found",
            "session_id": session_id
        }

    # Retrieve all activity records for this session
    activities = list(
        activity_collection.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", 1)
    )

    return {
        "session_id": session_id,
        "total_records": len(activities),
        "activities": activities
    }

@app.get("/sessions/active")
def get_active_session():

    session = sessions_collection.find_one(
        {"status": "Active"},
        {"_id": 0}
    )

    if not session:
        return {
            "status": "no_active_session"
        }

    # Restore session into memory
    created_at = session.get("created_at")

    if isinstance(created_at, datetime):
        session["created_at"] = created_at.isoformat()

    manager.sessions[session["session_id"]] = session

    return session


@app.post("/sessions/{session_id}/end")
def end_session(session_id: str):

    # Find session in MongoDB
    session = sessions_collection.find_one({
        "session_id": session_id
    })

    if not session:
        return {
            "status": "session_not_found",
            "session_id": session_id
        }

    if session["status"] == "Ended":
        return {
            "status": "session_already_ended",
            "session_id": session_id
        }

    ended_at = datetime.now()

    # Update MongoDB
    sessions_collection.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": "Ended",
                "ended_at": ended_at
            }
        }
    )

    # Update in-memory session if it exists
    if session_id in manager.sessions:
        manager.sessions[session_id]["status"] = "Ended"
        manager.sessions[session_id]["ended_at"] = ended_at.isoformat()

    # Clear associated assignments
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
        "session_id": session_id,
        "cleared_assignments": ended_assignments
    }


@app.get("/health")
def health_check():
    return {"status": "online"}



@app.post("/teacher/broadcast/frame")
async def receive_teacher_broadcast_frame(payload: dict):
    global teacher_screen_frame

    frame = payload.get("frame")

    if frame is None:
        teacher_screen_frame = None
        return {"status": "broadcast_stopped"}

    if not frame:
        return {"status": "missing_frame"}

    teacher_screen_frame = frame
    sent_to = []

    for pc_id, computer in list(manager.computers.items()):
        websocket = computer.get("websocket")

        if not websocket:
            continue

        try:
            await websocket.send_json({
                "type": "TEACHER_SCREEN_FRAME",
                "frame": frame
            })
            sent_to.append(pc_id)

        except Exception as error:
            print(
                f"Teacher broadcast failed for {pc_id}: {error}"
            )

    return {
        "status": "frame_sent",
        "sent_to": sent_to
    }


@app.get("/teacher/broadcast/frame")
def get_teacher_broadcast_frame():
    if not teacher_screen_frame:
        return {"status": "no_frame"}

    return {
        "status": "ok",
        "frame": teacher_screen_frame
    }

@app.get("/computers/{pc_id}/screen")
def get_computer_screen(pc_id: str):
    if pc_id not in manager.computers:
        return {
            "status": "computer_not_found",
            "pc_id": pc_id
        }

    frame = screen_frames.get(pc_id)

    if not frame:
        return {
            "status": "no_screen_frame",
            "pc_id": pc_id
        }

    return {
        "status": "ok",
        "pc_id": pc_id,
        "frame": frame
    }

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

@app.get("/computers/{pc_id}/activity")
def get_computer_activity(pc_id: str):
    if pc_id not in manager.computers:
        return {
            "status": "computer_not_found",
            "pc_id": pc_id
        }

    info = manager.computers[pc_id]

    return {
        "pc_id": pc_id,
        "student_name": info["student_name"],
        "status": info["status"],
        "activity": info.get("activity")
    }

class MessageCommand(BaseModel):
    message: str


@app.post("/computers/{pc_id}/message")
async def send_message(
    pc_id: str,
    message_command: MessageCommand
):
    if pc_id not in manager.computers:
        return {
            "status": "computer_not_found",
            "pc_id": pc_id
        }

    info = manager.computers[pc_id]
    websocket = info.get("websocket")

    if not websocket or info["status"] != "Online":
        return {
            "status": "computer_offline",
            "pc_id": pc_id
        }

    
    message = {
        "type": "COMMAND",
        "command": "SHOW_MESSAGE",
        "data": {
            "message": message_command.message
        }
    }

    try:
        await websocket.send_json(message)

        return {
            "status": "message_sent",
            "pc_id": pc_id,
            "message": message_command.message
        }

    except Exception as e:
        return {
            "status": "message_failed",
            "pc_id": pc_id,
            "error": str(e)
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

class BroadcastCommand(BaseModel):
    command: str
    data: dict = {}


@app.post("/computers/broadcast")
async def broadcast_command(command: BroadcastCommand):
    message = {
        "type": "COMMAND",
        "command": command.command,
        "data": command.data
    }

    sent_to = []
    failed = []

    for pc_id, info in manager.computers.items():
        websocket = info.get("websocket")

        if websocket and info["status"] == "Online":
            try:
                await websocket.send_json(message)
                sent_to.append(pc_id)
            except Exception:
                failed.append(pc_id)
        else:
            failed.append(pc_id)

    return {
        "status": "broadcast_complete",
        "command": command.command,
        "sent_to": sent_to,
        "failed": failed
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            message = await websocket.receive_text()

            data = json.loads(message)

            if data.get("type") == "REGISTER":
                hostname = data.get("hostname")
                ip_address = data.get("ip_address")
                device_id = data.get("device_id")

                if hostname and ip_address and device_id:
                    pc_id = manager.register_computer(
                        hostname,
                        ip_address,
                        websocket,
                        device_id
                    )

                    await websocket.send_json({
                        "type": "REGISTER_SUCCESS",
                        "pc_id": pc_id,
                        "message": f"Computer {pc_id} registered successfully"
                    })

                    print(
                        f"Computer connected: {pc_id} | "
                        f"Hostname: {hostname} | IP: {ip_address}"
                    )

                else:
                    await websocket.send_json({
                        "type": "REGISTER_ERROR",
                        "message": "Missing hostname, IP address, or device ID"
                    })

            elif data.get("type") == "SCREEN_FRAME":
                pc_id = data.get("pc_id")
                frame = data.get("frame")

                print(
                    f"SCREEN_FRAME received | PC: {pc_id} | "
                    f"Frame present: {bool(frame)} | "
                    f"Frame length: {len(frame) if frame else 0}"
                )

                if pc_id in manager.computers and frame:
                    screen_frames[pc_id] = frame
                    print(f"Screen frame stored for {pc_id}")
                else:
                    print(f"Screen frame NOT stored. Known PCs: {list(manager.computers.keys())}")

            elif data.get("type") == "ACTIVITY":
                pc_id = data.get("pc_id")

                if pc_id in manager.computers:
                    manager.computers[pc_id]["activity"] = {
                        "active_window": data.get("active_window"),
                        "cpu_percent": data.get("cpu_percent"),
                        "memory_percent": data.get("memory_percent"),
                        "idle_seconds": data.get("idle_seconds"),
                        "timestamp": data.get("timestamp")
                    }

                    manager.computers[pc_id]["last_seen"] = datetime.now().isoformat()

                    # Save activity if a lab session is active
                    for session in manager.sessions.values():
                        if session["status"] == "Active":

                            activity_record = {
                                "session_id": session["session_id"],
                                "pc_id": pc_id,
                                "active_window": data.get("active_window"),
                                "cpu_percent": data.get("cpu_percent"),
                                "memory_percent": data.get("memory_percent"),
                                "idle_seconds": data.get("idle_seconds"),
                                "timestamp": datetime.now()
                            }

                            activity_collection.insert_one(activity_record)
                            break

                    print(
                        f"Activity from {pc_id} | "
                        f"Window: {data.get('active_window')} | "
                        f"CPU: {data.get('cpu_percent')}% | "
                        f"RAM: {data.get('memory_percent')}%"
                )
                else:
                    print(f"Activity received from unknown computer: {pc_id}")

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

# ==========================================
# TEACHER DESKTOP ANNOTATION WEBSOCKET
# ==========================================

@app.websocket("/ws/teacher-overlay")
async def teacher_overlay_websocket(websocket: WebSocket):
    await websocket.accept()

    client_role = None

    try:
        # First message identifies the connecting application
        registration = await websocket.receive_json()
        client_role = registration.get("role")

        if client_role == "overlay":
            teacher_overlay_clients.add(websocket)
            print("Teacher desktop overlay connected")

        elif client_role == "dashboard":
            teacher_dashboard_clients.add(websocket)
            print("Teacher dashboard annotation bridge connected")

        else:
            await websocket.close(code=1008)
            return

        # Receive and forward messages
        while True:
                message = await websocket.receive_json()

                print(
                    f"[Annotation Bridge] Received from {client_role}: "
                    f"{message.get('type')} | "
                    f"Action: {message.get('action', '')}"
                )

                if client_role == "overlay":
                    print(
                        f"[Annotation Bridge] Forwarding to "
                        f"{len(teacher_dashboard_clients)} dashboard client(s)"
                    )

                    await forward_overlay_message(
                        teacher_dashboard_clients,
                        message
                    )

                elif client_role == "dashboard":

                    if (
                        message.get("type") == "BROADCAST_STATE"
                        and message.get("broadcasting") is True
                    ):
                        start_teacher_overlay()

                        # Wait for the toolbar to connect to the backend.
                        for attempt in range(20):
                            if teacher_overlay_clients:
                                break
                            await asyncio.sleep(0.25)

                        if not teacher_overlay_clients:
                            print("Teacher toolbar failed to connect.")
                            continue

                    # Forward ALL dashboard commands to the desktop toolbar.
                    await forward_overlay_message(
                        teacher_overlay_clients,
                        message
                    )

    except WebSocketDisconnect:
        print(f"Teacher {client_role} disconnected")

    except Exception as error:
        print(f"Teacher overlay bridge error: {error}")

    finally:
        if client_role == "overlay":
            teacher_overlay_clients.discard(websocket)

        elif client_role == "dashboard":
            teacher_dashboard_clients.discard(websocket)