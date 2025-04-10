from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from fastapi.responses import FileResponse
import csv

from db_utils import (
    init_db,
    get_all_students,
    get_expired_students,
    update_expiry,
    update_status,
    replace_student,
    daily_check,
    get_left_students,
)

from notifier import send_push_notification

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()  # 🧠 Initializes the database on startup

class StatusUpdateRequest(BaseModel):
    seat_no: int
    new_status: str

class UpdateExpiryRequest(BaseModel):
    seat_no: int
    name: str
    new_expiry: str

class ReplaceStudentRequest(BaseModel):
    seat_no: int
    name: str
    day_type: str
    charge: int
    start_date: str
    phone: Optional[str] = ""
    status: str

WHATSAPP_LINK_FILE = "group_link.txt"

@app.get("/whatsapp-link")
def get_whatsapp_link():
    if os.path.exists(WHATSAPP_LINK_FILE):
        with open(WHATSAPP_LINK_FILE, "r") as file:
            return {"link": file.read().strip()}
    return {"link": ""}

@app.post("/whatsapp-link")
def set_whatsapp_link(data: dict):
    link = data.get("link", "")
    with open(WHATSAPP_LINK_FILE, "w") as file:
        file.write(link)
    return {"message": "Link updated successfully."}

@app.get("/students")
def get_students():
    return get_all_students()

@app.get("/expired-students")
def get_expired_students():
    return get_expired_students()

@app.post("/update-expiry")
def update_expiry_handler(req: UpdateExpiryRequest):
    success = update_expiry(req.seat_no, req.new_expiry)
    if not success:
        raise HTTPException(status_code=404, detail="Student not found")
    send_push_notification(f"📆 Expiry updated for {req.name} (Seat {req.seat_no}) to {req.new_expiry}.")
    return {"message": "Expiry updated successfully."}

@app.post("/replace-student")
def replace_student_handler(req: ReplaceStudentRequest):
    result = replace_student(req)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to replace student")

    if req.name.lower() == "vacant":
        send_push_notification(f"🪑 Seat {req.seat_no} has been vacated.")
    else:
        send_push_notification(f"👤 {req.name} has been assigned to Seat {req.seat_no}.")
    return {"message": "Student replaced successfully."}

@app.post("/update-status")
def update_status_handler(req: StatusUpdateRequest):
    success = update_status(req.seat_no, req.new_status)
    if not success:
        raise HTTPException(status_code=404, detail="Seat not found")
    send_push_notification(f"💰 Seat {req.seat_no} status updated to {req.new_status}")
    return {"message": "Status updated successfully."}

@app.get("/")
def root():
    return {"message": "Backend running ✅"}

@app.get("/left-students")
def view_left():
    return get_left_students()

@app.get("/daily-check")
def daily_checker():
    result = daily_check()
    if result["count"] > 0:
        send_push_notification(f"🚨 {result['count']} student(s) expired. Daily check complete.")
    else:
        send_push_notification("✅ Daily check complete. No expired students today.")
    return result



@app.get("/download-left-students")
def download_left_students():
    from db_utils import get_left_students  # import your fetch logic
    filename = "Left_Students_Log.csv"
    headers = ["Seat No", "Name", "Phone", "Start Date", "Left On", "Status", "Reason"]
    data = get_left_students()

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for student in data:
            writer.writerow(student)

    return FileResponse(path=filename, filename=filename, media_type='text/csv')



from fastapi.responses import FileResponse

@app.get("/download-db")
def download_db():
    db_path = "students.db"
    if os.path.exists(db_path):
        return FileResponse(path=db_path, filename="students.db", media_type="application/octet-stream")
    raise HTTPException(status_code=404, detail="Database file not found")

