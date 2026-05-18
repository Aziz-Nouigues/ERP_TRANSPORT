"""
lire_schema_complet.py
Lit le vrai schéma de toutes les tables custom du projet depuis PostgreSQL.
Lancer : python3 lire_schema_complet.py > schema_reel.txt
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

# Récupérer toutes les tables custom
cur.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_type = 'BASE TABLE'
      AND (
          table_name LIKE 'transport_%'
       OR table_name LIKE 'fleet_vehicle%'
       OR table_name LIKE 'hr_employee%'
       OR table_name LIKE 'boc_%'
       OR table_name LIKE 'patrimoine_%'
      )
    ORDER BY table_name
""")
tables = [r[0] for r in cur.fetchall()]

print("=" * 70)
print("SCHÉMA COMPLET — ERP TRANSPORT TERRESTRE")
print("=" * 70)
print(f"Nombre de tables trouvées : {len(tables)}")
print()

for table in tables:
    print(f"\nTABLE {table} :")

    # Colonnes
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table,))
    cols = cur.fetchall()

    for col_name, dtype, nullable, default in cols:
        null_str = "NULL" if nullable == "YES" else "NOT NULL"
        print(f"  {col_name:<40} {dtype:<30} {null_str}")

    # Compter les lignes
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  -- {count} ligne(s) en base")
    except Exception as e:
        conn.rollback()
        print(f"  -- Impossible de compter : {e}")

    # Exemple 1 ligne
    try:
        cur.execute(f"SELECT * FROM {table} LIMIT 1")
        row = cur.fetchone()
        if row:
            col_names = [d[0] for d in cur.description]
            print(f"  -- Exemple :")
            for c, v in zip(col_names, row):
                if v is not None and str(v).strip():
                    print(f"       {c} = {str(v)[:80]}")
    except Exception as e:
        conn.rollback()
        print(f"  -- Exemple impossible : {e}")

cur.close()
conn.close()
print("\n" + "=" * 70)
print("FIN")
print("=" * 70)