import os
from dotenv import load_dotenv
from pushbullet import Pushbullet

load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("PUSHBULLET_API_KEY")
pb = Pushbullet(API_KEY)

def send_push_notification(message):
    try:
        pb.push_note("Student App Update", message)
    except Exception as e:
        print("Pushbullet Error:", e)