from backend.app.database import client

try:
    client.admin.command("ping")
    print("LabSphere database connection successful!")
except Exception as error:
    print("Connection error:", error)
finally:
    client.close()