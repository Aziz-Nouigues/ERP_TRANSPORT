import os
import logging
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import json
from pathlib import Path

from agent.agent_core import (
    create_agent, ask_agent,
    charger_historique, effacer_historique,
    TEMPLATES_RAPPORTS, generer_rapport,
)
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
CHAT_TIMEOUT   = int(os.getenv("CHAT_TIMEOUT", "120"))
RAPPORTS_DIR   = Path(__file__).parent.parent / "rapports"
RAPPORTS_DIR.mkdir(exist_ok=True)


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
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Modèles ──────────────────────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    question: str
    session_id: str = "default"
    user_id: int = 1
    user_name: str = "Utilisateur"
    allowed_tables: list = []
    is_admin: bool = False
    mode_rapport: bool = False


class ReponseModel(BaseModel):
    reponse: str
    session_id: str
    statut: str


# ── Routes de base ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Agent IA Transport", "statut": "opérationnel", "version": "2.0.0"}


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
        loop   = asyncio.get_event_loop()
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        reponse = await asyncio.wait_for(
            loop.run_in_executor(
                executor,
                lambda: ask_agent(
                    question=request.question,
                    llm=agent_executor,
                    allowed_tables=request.allowed_tables,
                    is_admin=request.is_admin,
                    session_id=request.session_id,
                    mode_rapport=request.mode_rapport
                )
            ),
            timeout=CHAT_TIMEOUT
        )

    except asyncio.TimeoutError:
        logger.error(f"[{request.user_name}] TIMEOUT ({CHAT_TIMEOUT}s)")
        return UTF8JSONResponse(content={
            "reponse": f"La requête a pris trop de temps (>{CHAT_TIMEOUT}s). Reformulez votre question.",
            "session_id": request.session_id,
            "statut": "timeout"
        })
    except (ConnectionResetError, ConnectionError, BrokenPipeError) as e:
        logger.warning(f"[{request.user_name}] Connexion interrompue: {e}")
        return UTF8JSONResponse(content={
            "reponse": "La connexion a été interrompue. Veuillez réessayer.",
            "session_id": request.session_id,
            "statut": "error"
        })
    except Exception as e:
        logger.error(f"[{request.user_name}] Erreur inattendue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"[{request.user_name}] Réponse : {reponse[:100]}")

    # Détecter si la réponse contient un lien PDF (format PDF_URL:http://...)
    pdf_url = None
    type_rapport = None
    import re as _re

    if "PDF_URL:" in reponse:
        # Format : "✅ Rapport prêt...\nPDF_URL:http://..."
        # Robuste : \S+ peut rater sur Windows à cause de \r — on extrait jusqu'à fin de ligne
        m = _re.search(r'PDF_URL:(https?://[^\s\r\n]+)', reponse)
        if m:
            pdf_url = m.group(1).strip().rstrip("\r")
            print(f"  [DEBUG main.py] pdf_url extrait = {pdf_url!r}")
            # Type rapport prédéfini ou None pour rapport libre
            m2 = _re.search(r'/rapport/([^/]+)/pdf', pdf_url)
            type_rapport = m2.group(1) if m2 else None
        # Nettoyer la réponse (retirer la ligne PDF_URL:)
        reponse_propre = _re.sub(r'\nPDF_URL:https?://[^\r\n]+', '', reponse).strip()
    else:
        # Fallback : ancien format markdown
        m = _re.search(r'http://localhost:8000/rapport/([^/]+)/pdf', reponse)
        if m:
            pdf_url = m.group(0)
            type_rapport = m.group(1)
            reponse_propre = _re.sub(
                r'\n---\n📄 \*\*\[Télécharger.*?\]\(.*?\)\*\*',
                '', reponse
            ).strip()
        else:
            reponse_propre = reponse

    return UTF8JSONResponse(content={
        "reponse":      reponse_propre,
        "session_id":   request.session_id,
        "statut":       "ok",
        "pdf_url":      pdf_url,
        "type_rapport": type_rapport,
    })


# ── NIVEAU 3 — Endpoints Rapports PDF ────────────────────────────────────────

@app.get("/rapports")
def liste_rapports():
    """Liste tous les rapports disponibles."""
    rapports = []
    for type_id, template in TEMPLATES_RAPPORTS.items():
        rapports.append({
            "id":     type_id,
            "label":  template["label"],
            "url":    f"/rapport/{type_id}/pdf",
        })
    return UTF8JSONResponse(content={"rapports": rapports})


@app.get("/rapport/{type_rapport}/pdf")
async def telecharger_rapport_pdf(type_rapport: str):
    """
    Génère et retourne un rapport PDF à la demande.
    Utilisé par le bouton de téléchargement dans l'interface chatbot.
    """
    if type_rapport not in TEMPLATES_RAPPORTS:
        raise HTTPException(
            status_code=404,
            detail=f"Rapport '{type_rapport}' inconnu. "
                   f"Disponibles : {list(TEMPLATES_RAPPORTS.keys())}"
        )

    if not agent_executor:
        raise HTTPException(status_code=503, detail="Agent non initialisé.")

    logger.info(f"Génération PDF demandée : {type_rapport}")

    from datetime import date
    import concurrent.futures

    try:
        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

        def _generer():
            from agent.agent_core import _executer_requetes_rapport, TEMPLATES_RAPPORTS
            from rapport_pdf import generer_pdf_rapport

            # Collecter les données via les requêtes SQL du template
            template = TEMPLATES_RAPPORTS[type_rapport]
            data = _executer_requetes_rapport(template["requetes"])

            # Chemin du fichier
            nom = f"{type_rapport}_{date.today().strftime('%Y%m%d_%H%M')}.pdf"
            chemin = RAPPORTS_DIR / nom
            generer_pdf_rapport(type_rapport, template["label"], data, chemin)
            return str(chemin)

        chemin_pdf = await asyncio.wait_for(
            loop.run_in_executor(executor, _generer),
            timeout=60
        )

        nom_fichier = Path(chemin_pdf).name
        return FileResponse(
            path=chemin_pdf,
            filename=nom_fichier,
            media_type="application/pdf",
            headers={
                # inline = s'ouvre dans le navigateur
                # attachment = force le téléchargement
                "Content-Disposition": f'inline; filename="{nom_fichier}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
                "Access-Control-Allow-Origin": "*",
            }
        )

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Génération du rapport trop longue.")
    except Exception as e:
        logger.error(f"Erreur génération PDF {type_rapport}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _collecter_donnees_rapport(type_rapport: str) -> dict:
    """
    Collecte les données pour un rapport spécifique (non-hebdomadaire).
    Exécute les requêtes SQL du template correspondant.
    """
    from agent.agent_core import _executer_requetes_rapport
    template = TEMPLATES_RAPPORTS[type_rapport]
    return _executer_requetes_rapport(template["requetes"])


@app.get("/rapports/fichiers")
def liste_fichiers_pdf():
    """Liste les rapports PDF déjà générés."""
    fichiers = []
    for f in sorted(RAPPORTS_DIR.glob("*.pdf"), reverse=True):
        fichiers.append({
            "nom":    f.name,
            "taille": f"{f.stat().st_size / 1024:.1f} Ko",
            "date":   f.stat().st_mtime,
            "url":    f"/rapports/fichiers/{f.name}",
        })
    return UTF8JSONResponse(content={"fichiers": fichiers[:20]})


@app.get("/rapports/fichiers/{nom_fichier}")
async def telecharger_fichier_existant(
    nom_fichier: str,
    dl: bool = False   # ?dl=true → téléchargement, ?dl=false → affichage inline
):
    """Ouvre ou télécharge un rapport PDF déjà généré."""
    chemin = RAPPORTS_DIR / nom_fichier
    if not chemin.exists() or not chemin.suffix == ".pdf":
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")
    disposition = "attachment" if dl else "inline"
    return FileResponse(
        path=str(chemin),
        filename=nom_fichier,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{nom_fichier}"',
            "Access-Control-Allow-Origin": "*",
        }
    )


# ── Endpoints existants ───────────────────────────────────────────────────────

@app.get("/historique/{session_id}")
def get_historique(session_id: str, limite: int = 10):
    try:
        messages = charger_historique(session_id, limite)
        return UTF8JSONResponse(content={
            "session_id": session_id,
            "messages": messages,
            "total": len(messages)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/historique/{session_id}")
def delete_historique(session_id: str):
    try:
        effacer_historique(session_id)
        return {"statut": "ok", "message": f"Historique de '{session_id}' effacé."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/test-sql")
def test_sql():
    from agent.tools.sql_tool import sql_tool
    result = sql_tool.invoke("SELECT COUNT(*) FROM transport_exploitation_tournee")
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
        raw = os.getenv("CHROMA_PATH", "./chroma_db")
        p = Path(raw)
        chroma_path = str(p) if p.is_absolute() else str(
            (Path(__file__).parent.parent / p).resolve()
        )
        client = chroma.PersistentClient(path=chroma_path)
        collection = client.get_or_create_collection(name="transport_procedures")
        doc_id = f"{request.model.replace('.', '_')}_{request.record_id}"
        if request.operation == "delete":
            try:
                collection.delete(ids=[doc_id])
            except Exception:
                pass
        else:
            collection.upsert(documents=[request.document], ids=[doc_id])
        return {"statut": "ok", "doc_id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))