import psycopg2

conn = psycopg2.connect('postgresql://neondb_owner:npg_J6gaj8onvXkH@ep-fragrant-silence-a51qqre0-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require')
cur = conn.cursor()
cur.execute("""
    UPDATE students
    SET due_amount = CASE WHEN status = 'Pending' THEN charge ELSE 0 END;
""")
conn.commit()
cur.close()
conn.close()
print('Due amounts updated.')
