from pushbullet import Pushbullet

API_KEY = "o.2WygSBf3nAwSfMbAG4x9whsVOWVxNpuC"
pb = Pushbullet(API_KEY)

def send_push_notification(message):
    try:
        pb.push_note("Student App Update", message)
    except Exception as e:
        print("Pushbullet error:", e)