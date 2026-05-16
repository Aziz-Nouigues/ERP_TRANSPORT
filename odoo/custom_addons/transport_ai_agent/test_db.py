import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(
    host=os.getenv('PG_HOST'),
    port=os.getenv('PG_PORT'),
    dbname=os.getenv('PG_DB'),
    user=os.getenv('PG_USER'),
    password=os.getenv('PG_PASSWORD')
)
cur = conn.cursor()

cur.execute("""
    SELECT DISTINCT
        l.code,
        l.type_ligne,
        COALESCE(l.name->>'fr_FR', l.name->>'en_US') as nom
    FROM transport_exploitation_tournee t
    JOIN transport_exploitation_ligne l ON t.ligne_id = l.id
    ORDER BY l.code
""")
print("Types de lignes dans les tournees :")
for row in cur.fetchall():
    print(f"  {row[0]} | {row[1]} | {row[2]}")

conn.close()