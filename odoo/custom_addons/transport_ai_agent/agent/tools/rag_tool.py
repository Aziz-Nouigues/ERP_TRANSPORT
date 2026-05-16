import chromadb
import os
from pathlib import Path
os.environ["ANONYMIZED_TELEMETRY"] = "False"
from dotenv import load_dotenv
from langchain.tools import tool

# Chargement du .env depuis la racine du module (FIX 2)
load_dotenv(Path(__file__).parent.parent.parent / ".env")


def _resolve_chroma_path() -> str:
    """
    FIX 2 — Résout CHROMA_PATH de façon portable.
    - Si le chemin est absolu (ancien comportement Windows), on le garde.
    - Si le chemin est relatif (ex: ./chroma_db), on le résout depuis
      la racine du module transport_ai_agent.
    """
    raw = os.getenv("CHROMA_PATH", "./chroma_db")
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    # Chemin relatif → ancré sur la racine du module
    module_root = Path(__file__).parent.parent.parent
    return str((module_root / p).resolve())


def get_chroma_collection():
    path = _resolve_chroma_path()
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(name="transport_procedures")


@tool
def rag_tool(question: str) -> str:
    """
    Recherche dans la base de connaissances locale (ChromaDB) les procédures,
    règles métier et informations documentaires de l'ERP transport.
    Utilise cet outil pour répondre aux questions sur :
    - Les procédures internes (comment faire une action dans l'ERP)
    - Les règles métier (conditions de blocage, workflow, validations)
    - Les définitions (qu'est-ce qu'un BGI, une feuille de route, etc.)
    """
    try:
        collection = get_chroma_collection()

        if collection.count() == 0:
            return "La base de connaissances est vide. Aucun document indexé."

        resultats = collection.query(
            query_texts=[question],
            n_results=min(3, collection.count())
        )

        documents = resultats.get("documents", [[]])[0]
        distances = resultats.get("distances", [[]])[0]

        if not documents:
            return "Aucune information trouvée dans la base de connaissances."

        reponse = "Informations trouvées dans la base de connaissances :\n\n"
        for i, (doc, dist) in enumerate(zip(documents, distances), 1):
            pertinence = round((1 - dist) * 100, 1)
            reponse += f"{i}. {doc}\n"
            reponse += f"   (pertinence : {pertinence}%)\n\n"

        return reponse

    except Exception as e:
        return f"Erreur RAG : {str(e)}"