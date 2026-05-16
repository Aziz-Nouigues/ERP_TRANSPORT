import os
import logging
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import json

from agent.agent_core import create_agent, ask_agent
from langchain_ollama import OllamaLLM


class UTF8JSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":")
        ).encode("utf-8")


load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/agent.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

agent_executor = None
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "120"))  # secondes


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_executor
    logger.info("Initialisation de l'agent IA transport...")
    agent_executor = create_agent()
    logger.info("Agent prêt.")
    yield
    logger.info("Arrêt de l'API.")


app = FastAPI(
    title="Agent IA — ERP Transport Terrestre",
    description="API REST pour l'agent IA intégré dans Odoo 19",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8070", "http://127.0.0.1:8070"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str
    session_id: str = "default"
    user_id: int = 1
    user_name: str = "Utilisateur"
    allowed_tables: list = []
    is_admin: bool = False


class ReponseModel(BaseModel):
    reponse: str
    session_id: str
    statut: str


@app.get("/")
def root():
    return {
        "service": "Agent IA Transport",
        "statut": "opérationnel",
        "version": "1.0.0"
    }


@app.get("/health")
def health():
    return {
        "statut": "ok",
        "agent": "prêt" if agent_executor else "non initialisé",
        "modele": os.getenv("OLLAMA_MODEL"),
        "base": os.getenv("ODOO_DB"),
        "timeout_chat": f"{CHAT_TIMEOUT}s"
    }


@app.post("/chat")
async def chat(request: QuestionRequest):
    if not agent_executor:
        raise HTTPException(status_code=503, detail="Agent non initialisé.")

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question vide.")

    logger.info(
        f"[{request.user_name}] Question : {request.question} "
        f"| Tables autorisées : {request.allowed_tables}"
    )

    try:
        # Exécuter ask_agent dans un thread (car c'est synchrone)
        # avec un timeout configurable
        loop = asyncio.get_event_loop()
        reponse = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: ask_agent(
                    question=request.question,
                    llm=agent_executor,
                    allowed_tables=request.allowed_tables,
                    is_admin=request.is_admin,
                    session_id=request.session_id
                )
            ),
            timeout=CHAT_TIMEOUT
        )

    except asyncio.TimeoutError:
        logger.error(
            f"[{request.user_name}] TIMEOUT ({CHAT_TIMEOUT}s) "
            f"pour: {request.question}"
        )
        return UTF8JSONResponse(content={
            "reponse": (
                f"La requête a pris trop de temps (>{CHAT_TIMEOUT}s). "
                "Essayez de reformuler votre question de manière plus précise."
            ),
            "session_id": request.session_id,
            "statut": "timeout"
        })

    except Exception as e:
        logger.error(f"[{request.user_name}] Erreur inattendue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"[{request.user_name}] Réponse : {reponse[:100]}")

    return UTF8JSONResponse(content={
        "reponse": reponse,
        "session_id": request.session_id,
        "statut": "ok"
    })


@app.get("/test-sql")
def test_sql():
    from agent.tools.sql_tool import sql_tool
    result = sql_tool.invoke(
        "SELECT COUNT(*) FROM transport_exploitation_tournee"
    )
    return {"resultat": result}


@app.get("/test-rag")
def test_rag():
    from agent.tools.rag_tool import rag_tool
    result = rag_tool.invoke("qu est ce qu un BGI")
    return {"resultat": result}


class SyncRequest(BaseModel):
    model: str
    record_id: int
    operation: str
    document: str = ""


@app.post("/sync")
def sync_chroma(request: SyncRequest):
    try:
        import chromadb as chroma
        client = chroma.PersistentClient(
            path=os.getenv("CHROMA_PATH")
        )
        collection = client.get_or_create_collection(
            name="transport_procedures"
        )

        doc_id = f"{request.model.replace('.', '_')}_{request.record_id}"

        if request.operation == 'delete':
            try:
                collection.delete(ids=[doc_id])
            except Exception:
                pass
            logger.info(f"ChromaDB delete: {doc_id}")
        else:
            collection.upsert(
                documents=[request.document],
                ids=[doc_id]
            )
            logger.info(f"ChromaDB upsert: {doc_id}")

        return {"statut": "ok", "doc_id": doc_id}

    except Exception as e:
        logger.error(f"Erreur sync ChromaDB: {e}")
        raise HTTPException(status_code=500, detail=str(e))