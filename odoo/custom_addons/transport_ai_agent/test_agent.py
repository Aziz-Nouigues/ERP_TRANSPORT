"""
verifier_boc.py
Vérifie les données réelles dans boc_courrier_arrivee
Lancer : python3 verifier_boc.py
"""
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

conn = psycopg2.connect(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", 5432)),
    dbname=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
)
cur = conn.cursor()

print("=" * 60)
print("VÉRIFICATION DONNÉES BOC")
print("=" * 60)

# 1. Total courriers
cur.execute("SELECT COUNT(*) FROM boc_courrier_arrivee")
print(f"\nTotal courriers arrivée : {cur.fetchone()[0]}")

# 2. Répartition par state
cur.execute("SELECT state, COUNT(*) FROM boc_courrier_arrivee GROUP BY state ORDER BY COUNT(*) DESC")
rows = cur.fetchall()
print("\nRépartition par état :")
for state, nb in rows:
    print(f"  {state} : {nb}")

# 3. Dates des courriers
cur.execute("SELECT MIN(date_arrivee), MAX(date_arrivee) FROM boc_courrier_arrivee")
row = cur.fetchone()
print(f"\nDate min arrivée : {row[0]}")
print(f"Date max arrivée : {row[1]}")

# 4. Courriers ce mois
cur.execute("""
    SELECT COUNT(*) FROM boc_courrier_arrivee
    WHERE EXTRACT(MONTH FROM date_arrivee) = EXTRACT(MONTH FROM CURRENT_DATE)
    AND EXTRACT(YEAR FROM date_arrivee) = EXTRACT(YEAR FROM CURRENT_DATE)
""")
print(f"\nCourriers ce mois : {cur.fetchone()[0]}")

# 5. Courriers en attente (enregistre ou diffuse)
cur.execute("""
    SELECT COUNT(*) FROM boc_courrier_arrivee
    WHERE state IN ('enregistre', 'diffuse')
""")
print(f"Courriers en attente (enregistre/diffuse) : {cur.fetchone()[0]}")

# 6. Courriers en attente ce mois
cur.execute("""
    SELECT COUNT(*) FROM boc_courrier_arrivee
    WHERE state IN ('enregistre', 'diffuse')
    AND EXTRACT(MONTH FROM date_arrivee) = EXTRACT(MONTH FROM CURRENT_DATE)
    AND EXTRACT(YEAR FROM date_arrivee) = EXTRACT(YEAR FROM CURRENT_DATE)
""")
print(f"Courriers en attente CE MOIS : {cur.fetchone()[0]}")

# 7. Exemple de données
cur.execute("""
    SELECT name, sujet, state, date_arrivee::date
    FROM boc_courrier_arrivee
    ORDER BY date_arrivee DESC
    LIMIT 5
""")
rows = cur.fetchall()
print(f"\nDerniers courriers :")
for r in rows:
    print(f"  {r[0]} | {r[1][:30]} | {r[2]} | {r[3]}")

cur.close()
conn.close()
print("\n" + "=" * 60)