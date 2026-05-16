import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    dbname=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD")
)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM transport_exploitation_tournee")
print(f"PostgreSQL OK — tournées : {cur.fetchone()[0]}")
conn.close()