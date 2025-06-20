from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import os
import csv
from io import StringIO
import pandas as pd
from datetime import date, datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

from db_utils import add_student_card, remove_student_card
from db_utils import record_payment, generate_invoice_pdf

from db_utils import (
    init_db,
    get_all_students,
    get_expired_students as fetch_expired_students,
    update_expiry,
    update_status,
    replace_student,
    daily_check,
    get_left_students,
    update_day_type,
    get_payments,
    get_total_collected,
    record_expense,
    get_expenses,
    get_total_expenses,
    get_net_profit,
    update_charge
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

init_db()

# === Models ===

class StatusUpdateRequest(BaseModel):
    seat_no: str   
    new_status: str

class UpdateExpiryRequest(BaseModel):
    seat_no: str   
    name: str
    new_expiry: str

class ReplaceStudentRequest(BaseModel):
    seat_no: str   
    name: str
    day_type: str
    charge: int
    start_date: str
    phone: Optional[str] = ""
    status: str

class DayTypeUpdateRequest(BaseModel):
    seat_no: str   
    new_day_type: str

class AddStudentCardRequest(BaseModel):
    seat_no: str
    name: str
    day_type: str
    charge: int
    start_date: str
    phone: Optional[str] = ""
    status: str

class UpdateChargeRequest(BaseModel):
    seat_no: str
    new_charge: int

class RecordPaymentRequest(BaseModel):
    seat_no: str
    name: str
    amount: int
    payment_method: Optional[str] = "Cash"
    remarks: Optional[str] = ""

class RecordExpenseRequest(BaseModel):
    date: str
    category: str
    amount: int
    description: Optional[str] = ""




# === WhatsApp Group Link ===



from db_utils import get_setting, set_setting

@app.get("/whatsapp-link")
def get_whatsapp_link():
    link = get_setting("whatsapp_link")
    return {"link": link}

@app.post("/whatsapp-link")
def set_whatsapp_link(data: dict):
    link = data.get("link", "")
    set_setting("whatsapp_link", link, notify=True)
    return {"message": "WhatsApp link updated ✅"}



# === Core APIs ===

@app.get("/")
def root():
    return {"message": "Backend running ✅"}

@app.get("/students")
def get_students():
    return get_all_students()

@app.get("/expired-students")
def expired_students_route():
    return fetch_expired_students()

@app.get("/left-students")
def view_left():
    return get_left_students()

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

@app.post("/update-day-type")
def change_day_type(req: DayTypeUpdateRequest):
    updated = update_day_type(req.seat_no, req.new_day_type)
    if not updated:
        raise HTTPException(status_code=404, detail="Seat not found")
    return {"message": "Day type updated successfully."}

@app.get("/daily-check")
def daily_checker():
    result = daily_check()
    if result["count"] > 0:
        send_push_notification(f"🚨 {result['count']} student(s) expired. Daily check complete.")
    else:
        send_push_notification("✅ Daily check complete. No expired students today.")
    return result

# === CSV / DB File Download ===

@app.get("/download-left-students")
def download_left_students():
    filename = "Left_Students_Log.csv"
    headers = ["Seat No", "Name", "Phone", "Start Date", "Left On", "Status", "Reason"]
    data = get_left_students()

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for student in data:
            writer.writerow(student)

    return FileResponse(path=filename, filename=filename, media_type='text/csv')



@app.post("/add-student-card")
def add_student_card_handler(data: AddStudentCardRequest):
    success, msg = add_student_card(data.dict())
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": "Student card added successfully."}

@app.delete("/remove-student-card/{seat_no}")
def remove_student_card_handler(seat_no: str):
    if not remove_student_card(seat_no):
        raise HTTPException(status_code=404, detail="Seat not found.")
    return {"message": f"Seat {seat_no} removed."}

@app.post("/update-charge")
def update_charge_handler(req: UpdateChargeRequest):
    success = update_charge(req.seat_no, req.new_charge)
    if not success:
        raise HTTPException(status_code=404, detail="Student not found")
    send_push_notification(f"💸 Charge updated for Seat {req.seat_no} to {req.new_charge}")
    return {"message": "Charge updated successfully."}

class UpdatePhoneRequest(BaseModel):
    seat_no: str
    new_phone: str

@app.post("/update-phone")
def update_phone_handler(req: UpdatePhoneRequest):
    conn = None
    try:
        conn = update_phone_handler.__globals__["update_charge"].__globals__["connect"]()
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET phone = %s WHERE seat_no = %s", (req.new_phone, req.seat_no))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        send_push_notification(f"📞 Phone updated for Seat {req.seat_no} to {req.new_phone}")
        return {"message": "Phone number updated successfully."}
    finally:
        if conn:
            conn.close()

@app.post("/record-payment")
def record_payment_handler(req: RecordPaymentRequest):
    invoice_id = record_payment(req.dict())
    payment_data = req.dict()
    payment_data["invoice_id"] = invoice_id
    payment_data["payment_date"] = str(date.today())
    send_push_notification(f"💵 Payment recorded: {payment_data['name']} (Seat {payment_data['seat_no']}) paid ₹{payment_data['amount']} on {payment_data['payment_date']}")
    invoice_filename = generate_invoice_pdf(payment_data)
    invoice_path = os.path.join("invoices", invoice_filename)
    if not os.path.exists(invoice_path):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return FileResponse(invoice_path, filename=invoice_filename, media_type="application/pdf")

@app.get("/payments")
def list_payments(month: int = None, year: int = None):
    return get_payments(month, year)

@app.get("/total-collected")
def total_collected(month: int, year: int):
    return {"total": get_total_collected(month, year)}

@app.get("/invoice/{invoice_filename}")
def get_invoice(invoice_filename: str):
    invoice_path = os.path.join("invoices", invoice_filename)
    if not os.path.exists(invoice_path):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return FileResponse(invoice_path, filename=invoice_filename, media_type="application/pdf")

@app.post("/send-invoice-link")
def send_invoice_link(data: dict):
    from notifier import send_push_notification
    link = data.get("link", "")
    seat_no = data.get("seat_no", "")
    name = data.get("name", "")
    if not link:
        raise HTTPException(status_code=400, detail="Invoice link required")
    send_push_notification(f"🧾 Invoice for {name} (Seat {seat_no}): {link}")
    return {"message": "Invoice link sent via notification ✅"}

@app.post("/generate-whatsapp-invoice-link")
def generate_whatsapp_invoice_link(data: dict):
    phone = data.get("phone", "")
    name = data.get("name", "")
    seat_no = data.get("seat_no", "")
    invoice_url = data.get("invoice_url", "")
    if not phone or not invoice_url:
        raise HTTPException(status_code=400, detail="Phone and invoice URL required")
    import urllib.parse
    message = f"🧾 Invoice for {name} (Seat {seat_no}): {invoice_url}"
    encoded_message = urllib.parse.quote(message)
    wa_link = f"https://wa.me/{phone}?text={encoded_message}"
    return {"whatsapp_link": wa_link}

@app.post("/record-expense")
def record_expense_handler(req: RecordExpenseRequest):
    success = record_expense(req.dict())
    if not success:
        raise HTTPException(status_code=400, detail="Failed to record expense")
    send_push_notification(f"💸 Expense recorded: {req.category} - ₹{req.amount} on {req.date}")
    return {"message": "Expense recorded successfully."}

@app.get("/expenses")
def list_expenses(month: int = None, year: int = None):
    return get_expenses(month, year)

@app.get("/total-expenses")
def total_expenses(month: int = None, year: int = None):
    return {"total": get_total_expenses(month, year)}

@app.get("/net-profit")
def net_profit(month: int = None, year: int = None):
    return {"net_profit": get_net_profit(month, year)}

@app.get("/students-with-dues")
def students_with_dues():
    from db_utils import get_students_with_dues
    return get_students_with_dues()

# === Financial Reports ===

@app.get("/report/financial-csv")
def financial_report_csv(month: int = None, year: int = None, start_date: str = None, end_date: str = None):
    # Get payments
    payments = get_payments(month, year)
    expenses = get_expenses(month, year)
    # If custom date range, filter in Python
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        payments = [p for p in payments if start <= datetime.strptime(p["payment_date"], "%Y-%m-%d") <= end]
        expenses = [e for e in expenses if start <= datetime.strptime(e["date"], "%Y-%m-%d") <= end]
    # Prepare DataFrames
    df_payments = pd.DataFrame(payments)
    df_expenses = pd.DataFrame(expenses)
    # Write to CSV in memory
    output = StringIO()
    output.write("Payments\n")
    df_payments.to_csv(output, index=False)
    output.write("\nExpenses\n")
    df_expenses.to_csv(output, index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=financial_report.csv"})

@app.get("/report/financial-pdf")
def financial_report_pdf(month: int = None, year: int = None, start_date: str = None, end_date: str = None):
    payments = get_payments(month, year)
    expenses = get_expenses(month, year)
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        payments = [p for p in payments if start <= datetime.strptime(p["payment_date"], "%Y-%m-%d") <= end]
        expenses = [e for e in expenses if start <= datetime.strptime(e["date"], "%Y-%m-%d") <= end]
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "Financial Report")
    c.setFont("Helvetica", 12)
    y = 730
    c.drawString(50, y, "Payments:")
    y -= 20
    for p in payments:
        c.drawString(50, y, f"{p['payment_date']} | {p['name']} | ₹{p['amount']} | {p['payment_method']}")
        y -= 15
        if y < 100:
            c.showPage()
            y = 750
    y -= 10
    c.drawString(50, y, "Expenses:")
    y -= 20
    for e in expenses:
        c.drawString(50, y, f"{e['date']} | {e['category']} | ₹{e['amount']} | {e['description']}")
        y -= 15
        if y < 100:
            c.showPage()
            y = 750
    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=financial_report.pdf"})

@app.get("/payments/by-date")
def payments_by_date(date: str):
    """Fetch all payments for a specific date (YYYY-MM-DD)."""
    from db_utils import get_payments
    from datetime import datetime
    all_payments = get_payments()
    filtered = [p for p in all_payments if p.get("Date") == date]
    return filtered

@app.get("/expenses/by-date")
def expenses_by_date(date: str):
    """Fetch all expenses for a specific date (YYYY-MM-DD)."""
    from db_utils import get_expenses
    all_expenses = get_expenses()
    filtered = [e for e in all_expenses if e.get("Date") == date]
    return filtered

@app.get("/payments/by-year")
def payments_by_year(year: int):
    """Fetch all payments for a specific year."""
    from db_utils import get_payments
    return get_payments(year=year)

@app.get("/expenses/by-year")
def expenses_by_year(year: int):
    """Fetch all expenses for a specific year."""
    from db_utils import get_expenses
    return get_expenses(year=year)

@app.get("/invoice/latest/{seat_no}")
def get_latest_invoice_for_seat(seat_no: str, request: Request):
    """Return the latest invoice URL for a given seat_no, or 404 if not found."""
    from db_utils import get_payments
    payments = get_payments()
    filtered = [p for p in payments if str(p.get("Seat No")) == str(seat_no) and p.get("Invoice URL")]
    if not filtered:
        raise HTTPException(status_code=404, detail="No invoice found for this student.")
    filtered.sort(key=lambda x: x.get("Date", ""), reverse=True)
    rel_url = filtered[0]["Invoice URL"]
    # Build absolute URL
    base_url = str(request.base_url).rstrip('/')
    abs_url = f"{base_url}{rel_url}"
    return {"invoice_url": abs_url}

@app.post("/expenses")
def add_expense(req: RecordExpenseRequest):
    success = record_expense(req.dict())
    if not success:
        raise HTTPException(status_code=400, detail="Failed to record expense")
    return {"message": "Expense recorded successfully."}

class UpdateNameRequest(BaseModel):
    seat_no: str
    new_name: str

@app.post("/update-name")
def update_name_handler(req: UpdateNameRequest):
    conn = None
    try:
        from db_utils import connect
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET name = %s WHERE seat_no = %s", (req.new_name, req.seat_no))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        send_push_notification(f"📝 Name updated for Seat {req.seat_no} to {req.new_name}")
        return {"message": "Name updated successfully."}
    finally:
        if conn:
            conn.close()

@app.get("/dashboard-totals")
def dashboard_totals(month: int = None, year: int = None):
    total_collected = get_total_collected(month, year)
    total_expenses = get_total_expenses(month, year)
    return {
        "total_collected": total_collected,
        "total_expenses": total_expenses
    }

