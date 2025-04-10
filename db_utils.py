import sqlite3
from datetime import datetime, timedelta
from typing import List
from fastapi import HTTPException
from notifier import send_push_notification
from dateutil import parser

DB_NAME = "students.db"

def connect():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            seat_no INTEGER PRIMARY KEY,
            name TEXT,
            day_type TEXT,
            charge INTEGER,
            start_date TEXT,
            expiry_date TEXT,
            status TEXT,
            phone TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS left_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seat_no INTEGER,
            name TEXT,
            phone TEXT,
            start_date TEXT,
            left_on TEXT,
            status TEXT,
            reason TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_all_students():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "Seat No": row[0],
            "Name": row[1],
            "Day Type": row[2],
            "Charge": row[3],
            "Start Date": row[4],
            "Expiry Date": row[5],
            "Status": row[6],
            "Phone": row[7]
        } for row in rows
    ]

def get_expired_students():
    today = datetime.today().date()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()

    expired = []
    for row in rows:
        expiry = row[5]
        try:
            expiry_date = parser.parse(expiry).date()
            if expiry_date < today:
                expired.append({
                    "Seat No": row[0],
                    "Name": row[1],
                    "Day Type": row[2],
                    "Charge": row[3],
                    "Start Date": row[4],
                    "Expiry Date": row[5],
                    "Status": row[6],
                    "Phone": row[7]
                })
        except:
            continue
    return expired

def update_expiry(seat_no: int, new_expiry: str):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET expiry_date = ? WHERE seat_no = ?", (new_expiry, seat_no))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    if success:
        send_push_notification(f"📆 Expiry updated for Seat {seat_no} to {new_expiry}.")
    return success

def update_status(seat_no: int, new_status: str):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET status = ? WHERE seat_no = ?", (new_status, seat_no))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    if success:
        send_push_notification(f"💰 Seat {seat_no} status updated to {new_status}")
    return success

def replace_student(req):
    conn = connect()
    cursor = conn.cursor()
    expiry_date = ""
    try:
        start_dt = datetime.strptime(req.start_date, "%d %B")
        start_dt = start_dt.replace(year=datetime.now().year)
        expiry = start_dt + timedelta(days=30)
        expiry_date = expiry.strftime("%d %B %Y")
    except:
        pass

    cursor.execute("""
        INSERT OR REPLACE INTO students (seat_no, name, day_type, charge, start_date, expiry_date, status, phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.seat_no,
        req.name,
        req.day_type,
        req.charge,
        req.start_date,
        expiry_date,
        req.status,
        req.phone
    ))

    conn.commit()
    conn.close()

    if req.name.lower() == "vacant":
        log_left_students(req)
        send_push_notification(f"🪑 Seat {req.seat_no} has been vacated.")
    else:
        send_push_notification(f"👤 {req.name} assigned to Seat {req.seat_no}.")

    return True

def log_left_students(req):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO left_students (seat_no, name, phone, start_date, left_on, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        req.seat_no,
        req.name,
        req.phone,
        req.start_date,
        datetime.today().strftime("%d %B %Y"),
        req.status,
        "Vacated"
    ))
    conn.commit()
    conn.close()

def get_left_students():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM left_students")
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "Seat No": row[1],
            "Name": row[2],
            "Phone": row[3],
            "Start Date": row[4],
            "Left On": row[5],
            "Status": row[6],
            "Reason": row[7]
        } for row in rows
    ]

def daily_check():
    expired_students = get_expired_students()
    conn = connect()
    cursor = conn.cursor()
    count = 0
    for student in expired_students:
        if student['Status'].lower() != "pending":
            cursor.execute("UPDATE students SET status = ? WHERE seat_no = ?", ("Pending", student['Seat No']))
            count += 1
    conn.commit()
    conn.close()
    return {"expired_students": expired_students, "count": count}
