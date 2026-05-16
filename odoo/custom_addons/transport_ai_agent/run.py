"""
Lancement de l'API Agent IA Transport.
Utilise ce script à la place de 'uvicorn api.main:app' directement
pour bénéficier des paramètres anti-timeout optimisés.
"""
import uvicorn
import os
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        # Évite ConnectionResetError (erreur 10054) sur Windows
        timeout_keep_alive=75,      # keep-alive HTTP étendu (défaut: 5s)
        timeout_graceful_shutdown=30,
        # Logs
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True,
    )