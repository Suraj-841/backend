import sqlite3
import openpyxl

EXCEL_FILE = "Student_Seat_Assignment.xlsx"
DB_FILE = "students.db"

def migrate_data():
    # Load Excel
    wb = openpyxl.load_workbook(EXCEL_FILE)
    sheet = wb.active

    # Connect to SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    migrated = 0

    for row in range(2, sheet.max_row + 1):  # skip header row
        seat_no = sheet[f"A{row}"].value
        name = sheet[f"B{row}"].value
        day_type = sheet[f"C{row}"].value
        charge = sheet[f"D{row}"].value
        start_date = sheet[f"E{row}"].value
        expiry_date = sheet[f"F{row}"].value
        status = sheet[f"G{row}"].value
        phone = sheet[f"H{row}"].value

        # Insert into DB
        cursor.execute('''
            INSERT OR REPLACE INTO students (
                seat_no, name, day_type, charge, start_date, expiry_date, status, phone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            seat_no, name, day_type, charge, start_date, expiry_date, status, phone
        ))

        migrated += 1

    conn.commit()
    conn.close()
    print(f"✅ Migrated {migrated} students from Excel to DB.")

if __name__ == "__main__":
    migrate_data()
