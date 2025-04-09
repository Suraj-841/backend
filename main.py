from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from excel_utils import update_expiry_date, read_students, replace_student_data
from notifier import send_push_notification

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExpiryUpdate(BaseModel):
    seat_no: int
    name: str
    new_expiry: str

class Replacement(BaseModel):
    seat_no: int
    name: str
    day_type: str
    charge: int
    start_date: str
    expiry_date: str
    status: str

@app.get("/students")
def get_students():
    return read_students()

@app.post("/update-expiry")
def update_expiry(data: ExpiryUpdate):
    success = update_expiry_date(data.seat_no, data.new_expiry)
    if success:
        send_push_notification(f"✅ Expiry updated: {data.name} (Seat {data.seat_no}) -> {data.new_expiry}")
        return {"status": "updated", "seat_no": data.seat_no}
    raise HTTPException(status_code=404, detail="Seat not found")

@app.post("/replace-student")
def replace_student(data: Replacement):
    success = replace_student_data(data)
    if success:
        if data.name.lower() == "vacant":
            send_push_notification(f"🚫 Seat {data.seat_no} vacated")
        else:
            send_push_notification(f"➕ New student added: {data.name} to Seat {data.seat_no}")
        return {"status": "student replaced", "seat_no": data.seat_no}
    raise HTTPException(status_code=404, detail="Seat not found")