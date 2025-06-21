import psycopg2
import os
from datetime import datetime, timedelta
from notifier import send_push_notification
from dateutil import parser
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import uuid

load_dotenv()

INVOICE_DIR = "invoices"
os.makedirs(INVOICE_DIR, exist_ok=True)

def connect():
    return psycopg2.connect(("postgresql://neondb_owner:npg_J6gaj8onvXkH@ep-fragrant-silence-a51qqre0-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"))

def init_db():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            seat_no TEXT PRIMARY KEY,
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
            seat_no TEXT,
            name TEXT,
            phone TEXT,
            start_date TEXT,
            left_on TEXT,
            status TEXT,
            reason TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            seat_no TEXT,
            name TEXT,
            amount INTEGER,
            payment_date DATE,
            payment_method TEXT,
            remarks TEXT,
            invoice_id TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            date DATE,
            category TEXT,
            amount INTEGER,
            description TEXT
        )
    ''')
    cursor.execute('''
        ALTER TABLE students ADD COLUMN IF NOT EXISTS due_amount INTEGER DEFAULT 0
    ''')
    conn.commit()
    conn.close()


def get_all_students():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM students 
        ORDER BY 
            CAST(regexp_replace(seat_no, '[^0-9]', '', 'g') AS INTEGER),
            seat_no ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "Seat No": str(row[0]),
            "Name": row[1],
            "Day Type": row[2],
            "Charge": row[3],
            "Start Date": row[4],
            "Expiry Date": row[5],
            "Status": row[6],
            "Phone": row[7],
            "Due": row[8] if len(row) > 8 else 0
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
                    "Seat No": str(row[0]),  # <-- explicitly cast to string
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

def update_expiry(seat_no: str, new_expiry: str):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET expiry_date = %s WHERE seat_no = %s", (new_expiry, seat_no))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    if success:
        send_push_notification(f"📆 Expiry updated for Seat {seat_no} to {new_expiry}.")
    return success

def update_status(seat_no: str, new_status: str):
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

    seat_no = str(req.seat_no)  # ENSURE it's always treated as a string

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

    # When replacing a student, set expiry_date to the start_date provided and status to Pending
    expiry_date = req.start_date
    status = "Pending"

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
        status,
        req.phone
    ))

    conn.commit()
    conn.close()

    if req.name.lower() == "vacant":
        send_push_notification(f"🪑 Seat {req.seat_no} has been vacated.")
    else:
        send_push_notification(f"👤 {req.name} assigned to Seat {req.seat_no} (Pending, expiry set to {expiry_date}).")

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
                        "Seat No": str(row[0]),  # <-- explicitly cast to string
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
            # Fetch the latest charge from the database for this seat
            cursor.execute("SELECT charge FROM students WHERE seat_no = %s", (student['Seat No'],))
            charge_row = cursor.fetchone()
            latest_charge = charge_row[0] if charge_row and charge_row[0] is not None else 0
            # Set status to Pending
            cursor.execute("UPDATE students SET status = %s WHERE seat_no = %s", ("Pending", student['Seat No']))
            # Set due_amount to latest charge
            cursor.execute("UPDATE students SET due_amount = %s WHERE seat_no = %s", (latest_charge, student['Seat No']))
            count += 1
    conn.commit()
    conn.close()
    return {"expired_students": expired_students, "count": count}

def update_day_type(seat_no: str, new_day_type: str):
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



def add_student_card(data):
    conn = connect()
    cursor = conn.cursor()

    # Optional: Prevent duplicates
    cursor.execute("SELECT * FROM students WHERE seat_no = %s", (data["seat_no"],))
    if cursor.fetchone():
        conn.close()
        return False, "Seat already exists"

    # Calculate expiry if start date is valid
    expiry_date = ""
    try:
        start_dt = datetime.strptime(data["start_date"], "%d %B")
        start_dt = start_dt.replace(year=datetime.now().year)
        expiry = start_dt + timedelta(days=30)
        expiry_date = expiry.strftime("%d %B %Y")
    except:
        pass

    cursor.execute("""
        INSERT INTO students (seat_no, name, day_type, charge, start_date, expiry_date, status, phone)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data["seat_no"],
        data["name"],
        data["day_type"],
        data["charge"],
        data["start_date"],
        expiry_date,
        data["status"],
        data["phone"]
    ))

    conn.commit()
    conn.close()
    send_push_notification(f"📥 Seat {data['seat_no']} added for {data['name']}")
    return True, "Added"


def remove_student_card(seat_no: str):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE seat_no = %s", (seat_no,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    if deleted:
        send_push_notification(f"🗑️ Seat {seat_no} removed.")
    return deleted

def update_charge(seat_no: str, new_charge: int):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET charge = %s WHERE seat_no = %s", (new_charge, seat_no))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    if updated:
        send_push_notification(f"💸 Charge updated for Seat {seat_no} to {new_charge}")
    return updated

def record_payment(data):
    from datetime import date
    conn = connect()
    cursor = conn.cursor()
    invoice_id = str(uuid.uuid4())[:8]
    # Fetch current due
    cursor.execute('SELECT due_amount FROM students WHERE seat_no = %s', (data["seat_no"],))
    row = cursor.fetchone()
    current_due = row[0] if row and row[0] is not None else 0
    payment_amount = data["amount"]
    new_due = max(current_due - payment_amount, 0)
    # Insert payment
    cursor.execute('''
        INSERT INTO payments (seat_no, name, amount, payment_date, payment_method, remarks, invoice_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (
        data["seat_no"],
        data["name"],
        payment_amount,
        date.today(),
        data.get("payment_method", "Cash"),
        data.get("remarks", ""),
        invoice_id
    ))
    # Update due amount
    cursor.execute('UPDATE students SET due_amount = %s WHERE seat_no = %s', (new_due, data["seat_no"]))
    # Optionally update status
    if new_due == 0:
        cursor.execute('UPDATE students SET status = %s WHERE seat_no = %s', ("Done", data["seat_no"]))
    else:
        cursor.execute('UPDATE students SET status = %s WHERE seat_no = %s', ("Pending", data["seat_no"]))
    conn.commit()
    conn.close()
    return invoice_id

def get_payments(month: int = None, year: int = None):
    conn = connect()
    cursor = conn.cursor()
    if month and year:
        cursor.execute('''SELECT * FROM payments WHERE EXTRACT(MONTH FROM payment_date) = %s AND EXTRACT(YEAR FROM payment_date) = %s''', (month, year))
    elif year:
        cursor.execute('''SELECT * FROM payments WHERE EXTRACT(YEAR FROM payment_date) = %s''', (year,))
    else:
        cursor.execute('SELECT * FROM payments')
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "ID": row[0],
            "Seat No": row[1],
            "Name": row[2],
            "Amount": row[3],
            "Date": str(row[4]),
            "Payment Method": row[5],
            "Remarks": row[6],
            "Invoice": f"/invoice/invoice_{row[7]}.pdf" if row[7] and row[7] != '-' else "-",
            "Invoice URL": f"/invoice/invoice_{row[7]}.pdf" if row[7] and row[7] != '-' else None
        } for row in rows
    ]

def get_total_collected(month: int, year: int):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('''SELECT SUM(amount) FROM payments WHERE EXTRACT(MONTH FROM payment_date) = %s AND EXTRACT(YEAR FROM payment_date) = %s''', (month, year))
    total = cursor.fetchone()[0] or 0
    conn.close()
    return total

def generate_invoice_pdf(payment_data):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Table, TableStyle, Paragraph
    import num2words
    invoice_id = payment_data.get("invoice_id") or str(uuid.uuid4())[:8]
    filename = f"invoice_{invoice_id}.pdf"
    filepath = os.path.join(INVOICE_DIR, filename)
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter

    # --- Header ---
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 30, height-90, width=60, height=60, preserveAspectRatio=True, mask='auto')
    c.setFont("Helvetica-Bold", 18)
    c.drawString(110, height-50, "Swayam Shiksha")
    c.setFont("Helvetica", 10)
    c.drawString(110, height-65, "Plot No 122, Sector No 9 Extension, Near RUB, Hanumangarh Junction")
    c.drawString(110, height-78, "Phone no.: 9694440915 Email: swayamshiksha.hmh@gmail.com")
    c.setStrokeColor(colors.HexColor('#2563eb'))
    c.setLineWidth(2)
    c.line(30, height-95, width-30, height-95)

    # --- Sale Order Title ---
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor('#2563eb'))
    c.drawString(35, height-120, "Sale Order")
    c.setFillColor(colors.black)

    # --- Order From/Details ---
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35, height-140, "Order From")
    c.drawString(width-200, height-140, "Order Details")
    c.setFont("Helvetica", 10)
    c.drawString(35, height-155, "Suraj Kataria")  # Hardcoded name
    c.drawString(35, height-170, payment_data.get("address", "Hanumangarh"))
    c.drawString(35, height-185, f"Contact No. : {payment_data.get('phone', '6377235145')}")
    c.drawString(width-200, height-155, f"Order No. : {payment_data.get('seat_no', '')}")
    c.drawString(width-200, height-170, f"Date : {payment_data.get('payment_date', '')}")
    c.drawString(width-200, height-185, f"Due Date : {payment_data.get('due_date', payment_data.get('payment_date', ''))}")

    # --- Table ---
    data = [
        ["#", "Item name", "Quantity", "Unit", "Price/ Unit", "Discount", "Amount"],
        [
            "1",
            "Library Seat",
            "1",
            "Seat",
            f"INR {payment_data.get('charge', payment_data.get('amount', 0)):.2f}",
            f"INR {float(payment_data.get('charge', payment_data.get('amount', 0))) - float(payment_data.get('amount', 0)):.2f}" if payment_data.get('charge') else "INR 0.00",
            f"INR {payment_data.get('amount', 0):.2f}"
        ]
    ]
    table = Table(data, colWidths=[20, 100, 50, 40, 70, 60, 60])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BACKGROUND', (0,1), (-1,-1), colors.white),  # Data rows white
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),   # Data rows black text
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),  # Set all cells to Helvetica
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    table.wrapOn(c, width, height)
    table.drawOn(c, 35, height-250)

    # --- Totals ---
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor('#2563eb'))
    c.drawString(35, height-270, "Order Amount In Words")
    c.drawString(width-200, height-270, "Amounts")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    # --- Amount in Words (INR, singular/plural, no cents/paise) ---
    try:
        amount = float(payment_data.get('amount', 0))
        int_amount = int(amount)
        words = num2words.num2words(int_amount, lang='en_IN').replace('euro', 'Rupees').replace('rupees', 'rupee' if int_amount == 1 else 'rupees')
        amount_words = words.capitalize() + " only"
    except Exception:
        amount_words = f"{amount:.2f} only"
    c.drawString(35, height-285, amount_words)

    # --- Amounts Section ---
    # Fetch due_amount from students table using seat_no (row[8])
    seat_no = payment_data.get('seat_no')
    total_amount = 0
    if seat_no:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute('SELECT due_amount FROM students WHERE seat_no = %s', (seat_no,))
        row = cursor.fetchone()
        if row and len(row) > 0 and row[0] is not None:
            total_amount = float(row[0])  # row[8] in SELECT * is due_amount
        conn.close()
    paid_amount = float(payment_data.get('amount', 0))
    due_payment = total_amount
    total_amount=total_amount+paid_amount

    c.setFont("Helvetica", 10)
    c.drawString(width-200, height-285, f"Total Amount   INR {total_amount:.2f}")
    c.drawString(width-200, height-300, f"Paid Amount    INR {paid_amount:.2f}")
    if due_payment > 0:
        c.drawString(width-200, height-315, f"Due           INR {due_payment:.2f}")
    else:
        c.drawString(width-200, height-315, "NULL")

    # --- Terms and Conditions ---
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor('#2563eb'))
    c.drawString(35, height-360, "Terms and Conditions")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(35, height-375, "Thanks for doing business with us!")

    # --- QR Code (placeholder) ---
    qr_path = os.path.join(os.path.dirname(__file__), "upi_qr.png")
    if os.path.exists(qr_path):
        c.drawImage(qr_path, 35, height-500, width=100, height=100, preserveAspectRatio=True, mask='auto')
        c.setFont("Helvetica", 8)
        c.drawString(35, height-510, "SCAN TO PAY")

    # --- Signature (placeholder) ---
    sign_path = os.path.join(os.path.dirname(__file__), "signature.png")
    if os.path.exists(sign_path):
        c.drawImage(sign_path, width-150, height-500, width=80, height=40, preserveAspectRatio=True, mask='auto')
        c.setFont("Helvetica", 10)
        c.drawString(width-150, height-520, "For : Swayam Shiksha")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(width-150, height-535, "Authorized Signatory")
    else:
        c.setFont("Helvetica", 10)
        c.drawString(width-150, height-520, "For : Swayam Shiksha")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(width-150, height-535, "Authorized Signatory")

    c.save()
    return filename

def update_due_amount(seat_no: str, amount: int):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET due_amount = %s WHERE seat_no = %s", (amount, seat_no))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

# --- Expense Management ---
def record_expense(data):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO expenses (date, category, amount, description)
        VALUES (%s, %s, %s, %s)
    ''', (
        data.get("date"),
        data.get("category"),
        data.get("amount"),
        data.get("description", "")
    ))
    conn.commit()
    conn.close()
    return True

def get_expenses(month: int = None, year: int = None):
    conn = connect()
    cursor = conn.cursor()
    if month and year:
        cursor.execute('''SELECT * FROM expenses WHERE EXTRACT(MONTH FROM date) = %s AND EXTRACT(YEAR FROM date) = %s''', (month, year))
    elif year:
        cursor.execute('''SELECT * FROM expenses WHERE EXTRACT(YEAR FROM date) = %s''', (year,))
    else:
        cursor.execute('SELECT * FROM expenses')
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "ID": row[0],
            "Date": str(row[1]),
            "Category": row[2],
            "Amount": row[3],
            "Description": row[4]
        } for row in rows
    ]

def get_total_expenses(month: int = None, year: int = None):
    conn = connect()
    cursor = conn.cursor()
    if month and year:
        cursor.execute('''SELECT SUM(amount) FROM expenses WHERE EXTRACT(MONTH FROM date) = %s AND EXTRACT(YEAR FROM date) = %s''', (month, year))
        total = cursor.fetchone()[0] or 0
    else:
        cursor.execute('SELECT SUM(amount) FROM expenses')
        total = cursor.fetchone()[0] or 0
    conn.close()
    return total

def get_net_profit(month: int = None, year: int = None):
    total_collected = get_total_collected(month, year) if month and year else get_total_collected(None, None)
    total_expenses = get_total_expenses(month, year) if month and year else get_total_expenses(None, None)
    return total_collected - total_expenses

def get_students_with_dues():
    conn = connect()
    cursor = conn.cursor()
    # Natural sort: order by numeric part of seat_no
    cursor.execute("SELECT * FROM students WHERE due_amount > 0 ORDER BY (regexp_replace(seat_no, '\\D', '', 'g'))::int ASC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "Seat No": str(row[0]),
            "Name": row[1],
            "Day Type": row[2],
            "Charge": row[3],
            "Start Date": row[4],
            "Expiry Date": row[5],
            "Status": row[6],
            "Phone": row[7],
            "Due": row[8] if len(row) > 8 else 0
        } for row in rows
    ]
