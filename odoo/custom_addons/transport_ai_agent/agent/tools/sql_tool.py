import psycopg2
import os
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        dbname=os.getenv("PG_DB"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD")
    )


REQUETES_AUTORISEES = [
    "SELECT", "WITH", "select", "with"
]

# Filet de sécurité : noms de tables que le LLM génère parfois avec des accents
TABLE_NAME_FIXES = {
    "transport_exploitation_tourn\u00e9e": "transport_exploitation_tournee",
    "transport_exploitation_tourn\u00e9es": "transport_exploitation_tournee",
    "transport_exploitation_lign\u00e9": "transport_exploitation_ligne",
    "transport_fuel_cuv\u00e9": "transport_fuel_cuve",
}


def normaliser_noms_tables(sql: str) -> str:
    """Corrige les noms de tables accentués générés par le LLM."""
    for wrong, correct in TABLE_NAME_FIXES.items():
        sql = sql.replace(wrong, correct)
    return sql


@tool
def sql_tool(question_sql: str) -> str:
    """
    Exécute une requête SQL SELECT sur la base PostgreSQL Odoo.
    Utilise cet outil pour répondre aux questions analytiques sur les tournées,
    bus, assurances, carburant, patrimoine et courrier BOC.
    La requête doit être un SELECT valide en PostgreSQL.
    """
    question_sql = normaliser_noms_tables(question_sql.strip())

    if not any(question_sql.startswith(k) for k in REQUETES_AUTORISEES):
        return "Erreur : seules les requêtes SELECT sont autorisées."

    if any(mot in question_sql.upper() for mot in
           ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER"]):
        return "Erreur : requête non autorisée pour des raisons de sécurité."

    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(question_sql)

        colonnes = [desc[0] for desc in cur.description]
        lignes = cur.fetchmany(50)
        conn.close()

        if not lignes:
            return "Aucun résultat trouvé pour cette requête."

        resultat = " | ".join(colonnes) + "\n"
        resultat += "-" * 60 + "\n"
        for ligne in lignes:
            resultat += " | ".join(str(v) if v is not None else "—" for v in ligne) + "\n"

        if len(lignes) == 50:
            resultat += "\n(résultats limités à 50 lignes)"

        return resultat

    except Exception as e:
        return f"Erreur SQL : {str(e)}"