import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from project root
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "atlas-credentials.env")

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI not found in .env file")

client = MongoClient(MONGODB_URI)

# Connect to LabSphere database
db = client["LabSphere"]

# Collections
sessions_collection = db["lab_sessions"]
activity_collection = db["session_activity_logs"]

# Verify connection
try:
    client.admin.command("ping")
    print("MongoDB Atlas connected successfully!")
except Exception as error:
    print("MongoDB connection failed:", error)