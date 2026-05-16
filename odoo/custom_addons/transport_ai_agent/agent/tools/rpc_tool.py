import xmlrpc.client
import os
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()


def get_odoo_connection():
    url  = os.getenv("ODOO_URL")
    db   = os.getenv("ODOO_DB")
    user = os.getenv("ODOO_USER")
    pwd  = os.getenv("ODOO_PASSWORD")

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid    = common.authenticate(db, user, pwd, {})
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    return db, uid, pwd, models


@tool
def rpc_tool(action: str) -> str:
    """
    Effectue des actions dans Odoo via XML-RPC.
    Utilise cet outil pour :
    - Lire des enregistrements Odoo avec leurs champs complets
    - Obtenir les détails d'une tournée, d'un bus, d'une police d'assurance
    - Vérifier le statut d'un enregistrement en temps réel
    Format de l'action : 'modele|methode|domaine|champs'
    Exemple : 'transport.exploitation.tournee|search_read|[["state","=","planifie"]]|["name","date","vehicle_id"]'
    """
    try:
        db, uid, pwd, models = get_odoo_connection()

        parties = action.split("|")
        if len(parties) < 2:
            return "Erreur : format invalide. Utilise 'modele|methode|domaine|champs'"

        modele  = parties[0].strip()
        methode = parties[1].strip()

        import ast

        if methode == "search_read":
            domaine = ast.literal_eval(parties[2]) if len(parties) > 2 else []
            champs  = ast.literal_eval(parties[3]) if len(parties) > 3 else []

            resultats = models.execute_kw(
                db, uid, pwd,
                modele, "search_read",
                [domaine],
                {"fields": champs, "limit": 20}
            )

            if not resultats:
                return "Aucun enregistrement trouvé."

            lignes = []
            for r in resultats:
                ligne = " | ".join(
                    f"{k}: {v}" for k, v in r.items() if k != "id"
                )
                lignes.append(f"[{r.get('id', '?')}] {ligne}")

            return "\n".join(lignes)

        elif methode == "search_count":
            domaine = ast.literal_eval(parties[2]) if len(parties) > 2 else []
            count   = models.execute_kw(db, uid, pwd, modele, "search_count", [domaine])
            return f"Nombre d'enregistrements : {count}"

        else:
            return f"Méthode '{methode}' non supportée. Utilise search_read ou search_count."

    except Exception as e:
        return f"Erreur RPC : {str(e)}"