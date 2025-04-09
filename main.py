# === main.py (FastAPI Backend with Expiry + Pushbullet + Phone) ===

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from excel_utils import (
    load_excel,
    save_excel,
    run_daily_check,
    get_all_students,
    get_expired_students_data,
    update_expiry_in_excel,
    replace_student_in_excel
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/students")
def get_students():
    return get_all_students()

@app.get("/expired-students")
def get_expired_students():
    return get_expired_students_data()

@app.post("/update-expiry")
def update_expiry(req: UpdateExpiryRequest):
    return update_expiry_in_excel(req)

@app.post("/replace-student")
def replace_student(req: ReplaceStudentRequest):
    return replace_student_in_excel(req)

@app.get("/")
def root():
    return {"message": "Backend running ✅"}

@app.get("/daily-check")
def daily_check():
    return run_daily_check()
