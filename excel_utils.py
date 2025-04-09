import pandas as pd

file_path = "Student_Seat_Assignment.xlsx"

def read_students():
    df = pd.read_excel(file_path)
    return df.fillna("").to_dict(orient="records")

def update_expiry_date(seat_no, new_expiry):
    df = pd.read_excel(file_path)
    idx = df[df["Seat No"] == seat_no].index
    if not idx.empty:
        df.loc[idx[0], "Expiry Date"] = new_expiry
        df.to_excel(file_path, index=False)
        return True
    return False

def replace_student_data(data):
    df = pd.read_excel(file_path)
    idx = df[df["Seat No"] == data.seat_no].index
    if not idx.empty:
        if data.name.strip().lower() == "vacant":
            df.loc[idx[0], ["Name", "Day Type", "Charge", "Start Date", "Expiry Date", "Status"]] = ""
            df.loc[idx[0], "Name"] = "Vacant"
        else:
            df.loc[idx[0], "Name"] = data.name
            df.loc[idx[0], "Day Type"] = data.day_type
            df.loc[idx[0], "Charge"] = data.charge
            df.loc[idx[0], "Start Date"] = data.start_date
            df.loc[idx[0], "Expiry Date"] = data.expiry_date
            df.loc[idx[0], "Status"] = data.status
        df.to_excel(file_path, index=False)
        return True
    return False



from pushbullet import Pushbullet

API_KEY = "o.2WygSBf3nAwSfMbAG4x9whsVOWVxNpuC"
pb = Pushbullet(API_KEY)

def send_push_notification(message):
    try:
        pb.push_note("Student App Update", message)
    except Exception as e:
        print("Pushbullet error:", e)



