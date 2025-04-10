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


from datetime import datetime
from dateutil import parser

def get_expired_students():
    today = datetime.today().date()
    current_year = today.year

    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()

    expired = []

    for row in rows:
        expiry_raw = row[5]  # This is the expiry_date column

        if not expiry_raw or str(expiry_raw).strip() == "":
            continue  # Skip blanks or empty strings

        try:
            expiry_str = str(expiry_raw).strip()

            # If year is missing (like "01 April"), add current year
            if not any(char.isdigit() for char in expiry_str[-4:]):
                expiry_str += f" {current_year}"

            expiry_date = parser.parse(expiry_str).date()

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
        except Exception as e:
            print(f"❌ Error parsing expiry '{expiry_raw}' for Seat {row[0]}: {e}")
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

    # If vacating, fetch the current student info before overwriting
    if req.name.lower() == "vacant":
        cursor.execute("SELECT * FROM students WHERE seat_no = ?", (req.seat_no,))
        current = cursor.fetchone()
        if current:
            log_left_students({
                "seat_no": current[0],
                "name": current[1],
                "day_type": current[2],
                "charge": current[3],
                "start_date": current[4],
                "expiry_date": current[5],
                "status": current[6],
                "phone": current[7]
            })

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
        send_push_notification(f"🪑 Seat {req.seat_no} has been vacated.")
    else:
        send_push_notification(f"👤 {req.name} assigned to Seat {req.seat_no}.")

    return True

def log_left_students(student):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO left_students (seat_no, name, phone, start_date, left_on, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        student['seat_no'],
        student['name'],
        student['phone'],
        student['start_date'],
        datetime.today().strftime("%d %B %Y"),
        student['status'],
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
