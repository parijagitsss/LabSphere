import asyncio
import json
import socket
import websockets



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