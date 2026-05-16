import chromadb
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()


def get_chroma_collection():
    client = chromadb.PersistentClient(path=os.getenv("CHROMA_PATH"))
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