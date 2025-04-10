import psycopg2
import os
from datetime import datetime, timedelta
from notifier import send_push_notification
from dateutil import parser
from dotenv import load_dotenv

load_dotenv()

def connect():
    return psycopg2.connect(("postgresql://neondb_owner:npg_J6gaj8onvXkH@ep-fragrant-silence-a51qqre0-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"))

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
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS left_students (
            id SERIAL PRIMARY KEY,
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
    cursor.execute("SELECT * FROM students ORDER BY seat_no ASC")  # ✅ Sorted to maintain consistent card order
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
    current_year = today.year

    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()

    expired = []

    for row in rows:
        expiry_raw = row[5]
        if not expiry_raw or str(expiry_raw).strip() == "":
            continue

        try:
            expiry_str = str(expiry_raw).strip()
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
    cursor.execute("UPDATE students SET expiry_date = %s WHERE seat_no = %s", (new_expiry, seat_no))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    if success:
        send_push_notification(f"📆 Expiry updated for Seat {seat_no} to {new_expiry}.")
    return success

def update_status(seat_no: int, new_status: str):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET status = %s WHERE seat_no = %s", (new_status, seat_no))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    if success:
        send_push_notification(f"💰 Seat {seat_no} status updated to {new_status}")
    return success

def replace_student(req):
    conn = connect()
    cursor = conn.cursor()

    if req.name.lower() == "vacant":
        cursor.execute("SELECT * FROM students WHERE seat_no = %s", (req.seat_no,))
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
        INSERT INTO students (seat_no, name, day_type, charge, start_date, expiry_date, status, phone)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (seat_no)
        DO UPDATE SET
            name = EXCLUDED.name,
            day_type = EXCLUDED.day_type,
            charge = EXCLUDED.charge,
            start_date = EXCLUDED.start_date,
            expiry_date = EXCLUDED.expiry_date,
            status = EXCLUDED.status,
            phone = EXCLUDED.phone
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
        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
            cursor.execute("UPDATE students SET status = %s WHERE seat_no = %s", ("Pending", student['Seat No']))
            count += 1
    conn.commit()
    conn.close()
    return {"expired_students": expired_students, "count": count}

def update_day_type(seat_no: int, new_day_type: str):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET day_type = %s WHERE seat_no = %s", (new_day_type, seat_no))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    if updated:
        send_push_notification(f"🔄 Seat {seat_no} switched to {new_day_type}")
    return updated

def set_setting(key: str, value: str, notify: bool = False):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    ''', (key, value))
    conn.commit()
    conn.close()
    if notify:
        send_push_notification(f"⚙️ Setting '{key}' updated.")

def get_setting(key: str) -> str:
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = %s', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else ""

