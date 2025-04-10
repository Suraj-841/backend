import pandas as pd
import psycopg2

# Load Excel
df = pd.read_excel("Student_Seat_Assignment.xlsx").fillna("")

# Setup DB connection
conn = psycopg2.connect(
    dbname="neondb",
    user="neondb_owner",
    password="npg_J6gaj8onvXkH",
    host="ep-fragrant-silence-a51qqre0.us-east-2.aws.neon.tech",
    port="5432",
    sslmode="require"
)
cursor = conn.cursor()

# Iterate and insert with proper type handling
for _, row in df.iterrows():
    # Convert empty strings in numeric fields to None
    seat_no = int(row["Seat No"]) if str(row["Seat No"]).strip().isdigit() else None
    charge = int(row["Charge"]) if str(row["Charge"]).strip().isdigit() else None

    cursor.execute("""
        INSERT INTO students (seat_no, name, day_type, charge, start_date, expiry_date, status, phone)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (seat_no) DO NOTHING
    """, (
        seat_no,
        row["Name"] or None,
        row["Day Type"] or None,
        charge,
        row["Start Date"] or None,
        row["Expiry Date"] or None,
        row["Status"] or None,
        str(row["Phone"]) if pd.notna(row["Phone"]) else None
    ))

conn.commit()
cursor.close()
conn.close()

print("🎉 Excel data imported successfully!")
