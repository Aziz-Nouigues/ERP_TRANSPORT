# test_sql_assurance.py v2
import sys, os
sys.path.insert(0, '.')
os.chdir('.')
from dotenv import load_dotenv
load_dotenv()

from agent.agent_core import generer_sql
from langchain_ollama import OllamaLLM
import psycopg2

llm = OllamaLLM(
    model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
)

def run_sql(sql):
    try:
        conn = psycopg2.connect(
            host=os.getenv("PG_HOST","localhost"),
            port=int(os.getenv("PG_PORT",5432)),
            dbname=os.getenv("PG_DB","erp_db2"),
            user=os.getenv("PG_USER","erp_user2"),
            password=os.getenv("PG_PASSWORD",""),
            client_encoding='utf8'
        )
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return f"ERREUR: {e}"

questions = [
    "Quelle est l assurance du bus Tesla",
    "Liste les polices assurance actives",
    "Quelles polices expirent bientot",
    "Quel est l etat de la police POL-BUS/2026/0006",
    "Liste les sinistres",
]

print("=" * 65)
for q in questions:
    print(f"\nQuestion : {q}")
    sql = generer_sql(q, llm, None, True)
    print(f"SQL      : {sql}")
    result = run_sql(sql)
    if isinstance(result, str):
        print(f"ECHEC    : {result}")
    else:
        print(f"Resultat : {result[:2] if result else 'VIDE'}")
    print("-" * 65)