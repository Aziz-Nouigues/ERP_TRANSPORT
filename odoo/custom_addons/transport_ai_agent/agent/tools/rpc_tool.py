import ast
import os
import logging
import xmlrpc.client
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()
_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONNEXION ODOO
# ---------------------------------------------------------------------------

class _NoneTransport(xmlrpc.client.Transport):
    """Transport XML-RPC qui accepte None dans les réponses Odoo."""
    def parse_response(self, response):
        try:
            return super().parse_response(response)
        except TypeError as e:
            if "cannot marshal None" in str(e) or "NoneType" in str(e):
                return None
            raise


def get_odoo_connection():
    url  = os.getenv("ODOO_URL")
    db   = os.getenv("ODOO_DB")
    user = os.getenv("ODOO_USER")
    pwd  = os.getenv("ODOO_PASSWORD")

    common = xmlrpc.client.ServerProxy(
        f"{url}/xmlrpc/2/common",
        transport=_NoneTransport(),
        allow_none=True,
    )
    uid = common.authenticate(db, user, pwd, {})
    if not uid:
        raise ConnectionError("Authentification Odoo échouée — vérifiez ODOO_USER et ODOO_PASSWORD dans .env")
    models = xmlrpc.client.ServerProxy(
        f"{url}/xmlrpc/2/object",
        transport=_NoneTransport(),
        allow_none=True,
    )
    return db, uid, pwd, models


# ---------------------------------------------------------------------------
# MÉTHODES AUTORISÉES ET DESCRIPTIONS
# ---------------------------------------------------------------------------

METHODES_LECTURE = {"search_read", "search_count", "read", "fields_get"}

METHODES_ECRITURE = {
    "create",
    "write",
    # Tournée — noms EXACTS du code exploitation_tournee.py
    "action_planifier",        # brouillon → planifie
    "action_demarrer",         # planifie  → en_cours
    "action_terminer",         # en_cours  → realise
    "action_annuler",          # → annule
    "action_remettre_brouillon",
    # Assurance bus — noms EXACTS du code assurance_bus.py
    "action_activer",          # brouillon → active
    "action_resilier",         # active    → résiliée
    "action_renouveler",
    # Assurance sinistre — noms EXACTS du code assurance_sinistre.py
    "action_declarer",         # brouillon → declare
    "action_instruire",        # declare   → instruction
    "action_cloturer",         # → cloture
    "action_rejeter",          # → rejete
    # Bon carburant — noms EXACTS fuel_voucher.py
    "action_confirm",          # draft     → confirmed
    "action_validate",         # confirmed → done
    "action_cancel",           # → cancelled
    "action_cancel_done",
    "action_reset_draft",
    # Facture énergie — noms EXACTS facture_energie.py
    "action_payer",            # → payee
    # BOC courrier arrivée — noms EXACTS boc_arrivee.py
    "action_enregistrer",      # brouillon → enregistre
    "action_diffuser",         # enregistre → diffuse
    "action_traiter",          # → traite
    "action_classer",          # → classe
    "action_reset",
    # Patrimoine — noms EXACTS patrimoine_immobilisation.py
    "action_mettre_en_service",
    "action_mettre_hors_service",
    "action_reset_en_service",
    # Cession patrimoine — noms EXACTS patrimoine_cession.py
    "action_confirmer",        # brouillon → confirme
    "action_comptabiliser",    # confirme  → comptabilise
}

# Méthodes bouton (appellées avec liste d'IDs uniquement)
METHODES_BOUTON = METHODES_ECRITURE - {"create", "write"}

# Modèles autorisés en écriture (liste blanche de sécurité)
MODELES_ECRITURE_AUTORISES = {
    "transport.exploitation.tournee",
    "transport.assurance.bus",
    "transport.assurance.chauffeur",
    "transport.assurance.sinistre",
    "transport.fuel.voucher",
    "transport.facture.energie",
    "fleet.vehicle",
    "fleet.vehicle.state",
    "boc.courrier.arrivee",
    "boc.courrier.depart",
    "patrimoine.immobilisation",
    "patrimoine.cession",
}


# ---------------------------------------------------------------------------
# FORMATAGE DE LA RÉPONSE
# ---------------------------------------------------------------------------

def _formater_resultat_lecture(resultats: list) -> str:
    """Formate une liste d'enregistrements Odoo en texte lisible."""
    if not resultats:
        return "Aucun enregistrement trouvé."
    lignes = []
    for r in resultats:
        rec_id = r.get("id", "?")
        parties = []
        for k, v in r.items():
            if k == "id":
                continue
            # Many2one → afficher le libellé, pas le tuple complet
            if isinstance(v, (list, tuple)) and len(v) == 2:
                v = v[1]
            parties.append(f"{k}: {v}")
        lignes.append(f"[{rec_id}] " + " | ".join(parties))
    return "\n".join(lignes)


def _formater_resultat_ecriture(methode: str, modele: str, resultat) -> str:
    """
    Formate le retour d'une opération d'écriture.
    Note: beaucoup de méthodes Odoo retournent None — c'est normal,
    l'action s'est bien exécutée. allow_none=True est requis sur ServerProxy.
    """
    labels = {
        "create":                    f"Enregistrement créé avec succès (ID={resultat}).",
        "write":                     "Modification enregistrée avec succès.",
        # Tournée
        "action_planifier":          "Tournée planifiée avec succès.",
        "action_demarrer":           "Tournée démarrée — en cours.",
        "action_terminer":           "Tournée terminée et réalisée.",
        "action_annuler":            "Tournée annulée.",
        "action_remettre_brouillon": "Tournée remise en brouillon.",
        # Assurance
        "action_activer":            "Police activée avec succès.",
        "action_resilier":           "Police résiliée.",
        "action_renouveler":         "Renouvellement effectué.",
        # Sinistre
        "action_declarer":           "Sinistre déclaré.",
        "action_instruire":          "Sinistre en instruction.",
        "action_cloturer":           "Sinistre clôturé.",
        "action_rejeter":            "Sinistre rejeté.",
        # Carburant
        "action_confirm":            "Bon confirmé.",
        "action_validate":           "Bon validé.",
        "action_cancel":             "Bon annulé.",
        "action_reset_draft":        "Remis en brouillon.",
        # Facture énergie
        "action_payer":              "Facture marquée payée.",
        "action_annuler":            "Annulation effectuée.",
        # BOC
        "action_enregistrer":        "Courrier enregistré.",
        "action_diffuser":           "Courrier diffusé.",
        "action_traiter":            "Courrier traité.",
        "action_classer":            "Courrier classé.",
        # Patrimoine
        "action_mettre_en_service":  "Immobilisation mise en service.",
        "action_mettre_hors_service":"Immobilisation hors service.",
        "action_confirmer":          "Cession confirmée.",
        "action_comptabiliser":      "Cession comptabilisée.",
    }
    msg = labels.get(methode, f"Action '{methode}' exécutée avec succès.")
    _logger.info(f"RPC OK — modèle={modele} méthode={methode} résultat={resultat}")
    return msg


# ---------------------------------------------------------------------------
# OUTIL PRINCIPAL
# ---------------------------------------------------------------------------

@tool
def rpc_tool(action: str) -> str:
    """
    Effectue des actions de lecture ET d'écriture dans Odoo via XML-RPC.

    FORMAT : 'modele|methode|param1|param2'

    ── LECTURE ──────────────────────────────────────────────────────────────
    search_read  → 'modele|search_read|domaine_json|champs_json'
        Ex: 'transport.exploitation.tournee|search_read|[["state","=","planifie"]]|["name","date","vehicle_id"]'

    search_count → 'modele|search_count|domaine_json'
        Ex: 'fleet.vehicle|search_count|[]'

    read         → 'modele|read|ids_json|champs_json'
        Ex: 'fleet.vehicle|read|[42,43]|["name","license_plate","state_id"]'

    ── CRÉATION ─────────────────────────────────────────────────────────────
    create       → 'modele|create|valeurs_json'
        Ex: 'transport.exploitation.tournee|create|{"name":"T-TEST","date":"2026-05-20","vehicle_id":5}'

    ── MODIFICATION ─────────────────────────────────────────────────────────
    write        → 'modele|write|ids_json|valeurs_json'
        Ex: 'fleet.vehicle|write|[42]|{"state_id":3}'

    ── BOUTONS WORKFLOW ─────────────────────────────────────────────────────
    action_*     → 'modele|action_confirm|ids_json'
        Ex: 'transport.exploitation.tournee|action_confirm|[15]'
        Ex: 'transport.exploitation.tournee|action_cancel|[15,16]'
        Ex: 'transport.assurance.bus|action_validate|[7]'
    """
    try:
        db, uid, pwd, models = get_odoo_connection()

        parties = [p.strip() for p in action.split("|")]
        if len(parties) < 2:
            return "Erreur RPC : format invalide. Utilise 'modele|methode|...' "

        modele  = parties[0]
        methode = parties[1]

        # ── Vérification liste blanche écriture ──────────────────────────
        if methode in METHODES_ECRITURE:
            if modele not in MODELES_ECRITURE_AUTORISES:
                return (
                    f"Erreur RPC : le modèle '{modele}' n'est pas autorisé en écriture. "
                    f"Modèles autorisés : {', '.join(sorted(MODELES_ECRITURE_AUTORISES))}"
                )

        # ================================================================
        # LECTURE — search_read
        # ================================================================
        if methode == "search_read":
            domaine = ast.literal_eval(parties[2]) if len(parties) > 2 and parties[2] else []
            champs  = ast.literal_eval(parties[3]) if len(parties) > 3 and parties[3] else []
            resultats = models.execute_kw(
                db, uid, pwd, modele, "search_read",
                [domaine], {"fields": champs, "limit": 20}
            )
            return _formater_resultat_lecture(resultats)

        # ================================================================
        # LECTURE — search_count
        # ================================================================
        elif methode == "search_count":
            domaine = ast.literal_eval(parties[2]) if len(parties) > 2 and parties[2] else []
            count   = models.execute_kw(db, uid, pwd, modele, "search_count", [domaine])
            return f"Nombre d'enregistrements : {count}"

        # ================================================================
        # LECTURE — read (par IDs)
        # ================================================================
        elif methode == "read":
            ids    = ast.literal_eval(parties[2]) if len(parties) > 2 else []
            champs = ast.literal_eval(parties[3]) if len(parties) > 3 else []
            resultats = models.execute_kw(
                db, uid, pwd, modele, "read", [ids], {"fields": champs}
            )
            return _formater_resultat_lecture(resultats)

        # ================================================================
        # CRÉATION — create
        # ================================================================
        elif methode == "create":
            valeurs = ast.literal_eval(parties[2]) if len(parties) > 2 else {}
            if not isinstance(valeurs, dict) or not valeurs:
                return "Erreur RPC : les valeurs de création doivent être un dict non vide."
            new_id = models.execute_kw(db, uid, pwd, modele, "create", [valeurs])
            return _formater_resultat_ecriture("create", modele, new_id)

        # ================================================================
        # MODIFICATION — write
        # ================================================================
        elif methode == "write":
            ids     = ast.literal_eval(parties[2]) if len(parties) > 2 else []
            valeurs = ast.literal_eval(parties[3]) if len(parties) > 3 else {}
            if not ids:
                return "Erreur RPC : liste d'IDs vide pour write."
            if not isinstance(valeurs, dict) or not valeurs:
                return "Erreur RPC : les valeurs de modification doivent être un dict non vide."
            resultat = models.execute_kw(db, uid, pwd, modele, "write", [ids, valeurs])
            # write retourne True si succès, False si échec, None parfois
            if resultat is False:
                return "Erreur RPC : la modification a échoué (Odoo a retourné False)."
            return _formater_resultat_ecriture("write", modele, resultat)

        # ================================================================
        # BOUTONS WORKFLOW — action_confirm, action_cancel, etc.
        # ================================================================
        elif methode in METHODES_BOUTON:
            ids = ast.literal_eval(parties[2]) if len(parties) > 2 else []
            if not ids:
                return f"Erreur RPC : IDs manquants pour '{methode}'."
            # Note: beaucoup de méthodes Odoo retournent None — c'est normal
            # allow_none=True sur ServerProxy évite le crash XML-RPC
            try:
                models.execute_kw(db, uid, pwd, modele, methode, [ids])
            except TypeError as e_type:
                if "cannot marshal None" in str(e_type):
                    pass  # None retourné par Odoo — action réussie
                else:
                    raise
            return _formater_resultat_ecriture(methode, modele, None)

        else:
            return (
                f"Méthode '{methode}' non supportée.\n"
                f"Lecture : {sorted(METHODES_LECTURE)}\n"
                f"Écriture : {sorted(METHODES_ECRITURE)}"
            )

    except (ValueError, SyntaxError) as e:
        return f"Erreur RPC : paramètre JSON invalide — {e}"
    except ConnectionError as e:
        return f"Erreur RPC : {e}"
    except xmlrpc.client.Fault as e:
        # Fault 2 = erreur metier Odoo (validation, precondition)
        # Fault 1 = erreur serveur (traceback Python)
        if e.faultCode == 2:
            # Extraire le message lisible (avant le traceback)
            msg = e.faultString.strip()
            # Supprimer le traceback si present
            if "\nTraceback" in msg:
                msg = msg.split("\nTraceback")[0].strip()
            elif "Traceback" in msg:
                # Prendre la derniere ligne significative
                lignes = [l.strip() for l in msg.split("\n") if l.strip()]
                msg = lignes[-1] if lignes else msg
            return f"Action impossible : {msg}"
        else:
            # Fault 1 = erreur serveur — extraire le message de la derniere ligne
            msg = e.faultString.strip()
            lignes_err = [l.strip() for l in msg.split("\n") if l.strip()
                         and not l.strip().startswith("File ")
                         and not l.strip().startswith("Traceback")
                         and "^^^" not in l]
            msg_court = lignes_err[-1] if lignes_err else str(e.faultString)[:200]
            return f"Erreur Odoo : {msg_court}"
    except TypeError as e:
        if "cannot marshal None" in str(e):
            # Odoo retourne None pour les methodes de workflow — action reussie
            _logger.info(f"rpc_tool: None recu d Odoo (normal pour workflow)")
            return _formater_resultat_ecriture(methode, modele, None)
        _logger.error(f"rpc_tool TypeError: {e}")
        return f"Erreur RPC : {str(e)}"
    except Exception as e:
        _logger.error(f"rpc_tool exception: {e}")
        return f"Erreur RPC : {str(e)}"