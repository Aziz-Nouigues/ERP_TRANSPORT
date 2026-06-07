import os
import re
import ast
import json
import logging
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from langchain_ollama import OllamaLLM

from agent.tools.sql_tool import sql_tool, get_pg_connection
from agent.tools.rpc_tool import rpc_tool
from agent.tools.rag_tool import rag_tool
from agent.prompts import SYSTEM_PROMPT
from agent.language_detector import (
    detecter_langue, msg, get_system_prompt,
    TABLES_METIER_EN, TABLES_METIER_AR,
    LABELS_COLONNES, STATUTS_TRADUITS, GABARITS_COUNT,
)

# Chercher .env dans plusieurs emplacements (robuste Windows/Linux, uvicorn/direct)
def _find_and_load_dotenv():
    candidates = [
        Path(__file__).parent.parent / ".env",   # agent_core.py → transport_ai_agent/.env
        Path(__file__).parent / ".env",           # agent/.env
        Path.cwd() / ".env",                       # répertoire courant (uvicorn)
        Path.cwd().parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=True)
            break
    # Toujours aussi charger sans argument (répertoire courant uvicorn)
    load_dotenv(override=False)

_find_and_load_dotenv()

# URL FastAPI — hardcodé, pas de dépendance au .env
_AGENT_URL = "http://localhost:8000"

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIX 3 — Historique persistant dans SQLite (remplace dict en RAM)
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).parent.parent / "historique.db"

# Cache RAM des contextes par session — synchrone et immédiat
_SESSION_CONTEXT: dict = {}  # session_id → {"ref": str, "modele": str, "erreur": str}
_db_lock = threading.Lock()


def _init_db():
    """Crée la table historique si elle n'existe pas."""
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historique (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                session   TEXT    NOT NULL,
                role      TEXT    NOT NULL,
                contenu   TEXT    NOT NULL,
                ts        TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON historique(session)")
        conn.commit()


_init_db()


def charger_historique(session_id: str, limite: int = 10) -> list:
    """Retourne les N derniers échanges pour la session."""
    with _db_lock, sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute("""
            SELECT role, contenu FROM historique
            WHERE session = ?
            ORDER BY id DESC LIMIT ?
        """, (session_id, limite * 2)).fetchall()
    rows.reverse()
    return [{"role": r, "contenu": c} for r, c in rows]


def sauvegarder_historique(session_id: str, question: str, reponse: str):
    """Persiste une paire question/réponse."""
    with _db_lock, sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO historique (session, role, contenu) VALUES (?,?,?)",
            (session_id, "user", question)
        )
        conn.execute(
            "INSERT INTO historique (session, role, contenu) VALUES (?,?,?)",
            (session_id, "assistant", reponse)
        )
        # Garde max 20 tours par session pour éviter la croissance infinie
        conn.execute("""
            DELETE FROM historique WHERE session = ? AND id NOT IN (
                SELECT id FROM historique WHERE session = ?
                ORDER BY id DESC LIMIT 40
            )
        """, (session_id, session_id))
        conn.commit()


def effacer_historique(session_id: str):
    """Efface l'historique d'une session (ex : logout utilisateur)."""
    with _db_lock, sqlite3.connect(_DB_PATH) as conn:
        conn.execute("DELETE FROM historique WHERE session = ?", (session_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# MAPPING METIER — mots-clés -> tables réelles PostgreSQL
# ---------------------------------------------------------------------------

TABLES_METIER = {
    "bus":             ["fleet_vehicle", "transport_assurance_bus"],
    "vehicule":        ["fleet_vehicle"],
    "véhicule":        ["fleet_vehicle"],
    "immatriculation": ["fleet_vehicle"],
    "parc":            ["fleet_vehicle"],
    "etat":            ["fleet_vehicle", "fleet_vehicle_state"],
    "état":            ["fleet_vehicle", "fleet_vehicle_state"],
    "actuel":          ["fleet_vehicle", "fleet_vehicle_state"],
    "historique":      ["fleet_vehicle", "fleet_vehicle_state"],
    "odometer":        ["fleet_vehicle_odometer", "fleet_vehicle"],
    "odometre":        ["fleet_vehicle_odometer", "fleet_vehicle"],
    "contrat":         ["fleet_vehicle_log_contract", "fleet_vehicle"],
    "assurance":       ["transport_assurance_bus", "fleet_vehicle"],
    "police":          ["transport_assurance_bus", "fleet_vehicle"],
    "sinistre":        ["transport_assurance_sinistre", "fleet_vehicle"],
    "accident":        ["transport_assurance_sinistre"],
    "tournee":         ["transport_exploitation_tournee"],
    "tournée":         ["transport_exploitation_tournee"],
    "realise":         ["transport_exploitation_tournee"],
    "réalisé":         ["transport_exploitation_tournee"],
    "planifie":        ["transport_exploitation_tournee"],
    "planifié":        ["transport_exploitation_tournee"],
    "ligne":           ["transport_exploitation_ligne"],
    "chauffeur":       ["hr_employee", "transport_assurance_chauffeur"],
    "conducteur":      ["hr_employee"],
    "employe":         ["hr_employee"],
    "employé":         ["hr_employee"],
    "carburant":       ["transport_fuel_voucher", "transport_fuel_station"],
    "bgi":             ["transport_fuel_voucher"],
    "bge":             ["transport_fuel_voucher", "transport_fuel_station"],
    "cuve":            ["transport_fuel_cuve"],
    "station":         ["transport_exploitation_station", "transport_fuel_station"],
    "stations":        ["transport_exploitation_station"],
    "lubrifiant":      ["transport_bon_lubrifiant", "transport_stock_lubrifiant"],
    "stock":           ["transport_stock_lubrifiant", "transport_fuel_cuve"],
    "km":              ["transport_exploitation_tournee"],
    "kilometre":       ["transport_exploitation_tournee", "fleet_vehicle_odometer"],
    "kilomètre":       ["transport_exploitation_tournee", "fleet_vehicle_odometer"],
    "kilometres":      ["transport_exploitation_tournee", "fleet_vehicle_odometer"],
    "kilomètres":      ["transport_exploitation_tournee", "fleet_vehicle_odometer"],
    "kilometrage":     ["transport_exploitation_tournee"],
    "kilométrage":     ["transport_exploitation_tournee"],
    "patrimoine":      ["patrimoine_immobilisation", "patrimoine_categorie"],
    "immobilisation":  ["patrimoine_immobilisation", "patrimoine_categorie"],
    "amortissement":   ["patrimoine_immobilisation"],
    "cession":         ["patrimoine_cession", "patrimoine_immobilisation"],
    "inventaire":      ["patrimoine_inventaire", "patrimoine_immobilisation"],
    "affectation":     ["patrimoine_affectation", "patrimoine_immobilisation"],
    "depreciation":    ["patrimoine_depreciation", "patrimoine_immobilisation"],
    "courrier":        ["boc_courrier_arrivee", "boc_courrier_depart"],
    "boc":             ["boc_courrier_arrivee", "boc_courrier_depart"],
    "arrivee":         ["boc_courrier_arrivee"],
    "arrivée":         ["boc_courrier_arrivee"],
    "depart":          ["boc_courrier_depart"],
    "départ":          ["boc_courrier_depart"],
    "centre":          ["transport_exploitation_centre"],
    "agence":          ["transport_exploitation_agence"],
    "facture":         ["transport_facture_energie"],
    "factures":        ["transport_facture_energie"],
    "facturation":     ["transport_facture_energie"],
    "steg":            ["transport_facture_energie"],
    "sonede":          ["transport_facture_energie"],
    "topnet":          ["transport_facture_energie"],
    "electricite":     ["transport_facture_energie"],
    "électricité":     ["transport_facture_energie"],
    "eau":             ["transport_facture_energie"],
    "kwh":             ["transport_facture_energie"],
    "compteur":        ["transport_facture_energie"],
    "energie":         ["transport_facture_energie"],
    "paiement":        ["account_move", "res_partner"],
    "fournisseur":     ["account_move", "res_partner"],
    "client":          ["account_move", "res_partner"],
}

TABLES_PRINCIPALES = [
    "fleet_vehicle", "hr_employee",
    "transport_exploitation_tournee", "transport_exploitation_ligne",
    "transport_assurance_bus", "transport_assurance_chauffeur",
    "transport_assurance_sinistre",
    "transport_fuel_voucher", "transport_fuel_cuve", "transport_fuel_station",
    "transport_facture_energie",
    "boc_courrier_arrivee", "boc_courrier_depart",
    "patrimoine_immobilisation", "patrimoine_categorie",
    "fleet_vehicle_state", "fleet_vehicle_odometer",
    "transport_exploitation_centre", "transport_exploitation_agence",
    "transport_exploitation_station",
]

# ---------------------------------------------------------------------------
# DÉTECTION DES TABLES PERTINENTES
# ---------------------------------------------------------------------------

CATALOGUE_TABLES = """
fleet_vehicle: parc de bus, véhicules, immatriculations, liste des bus, plaques
fleet_vehicle_state: états des bus (en service, hors service, réformé)
fleet_vehicle_odometer: kilométrage/odomètre des bus
fleet_vehicle_log_contract: contrats des véhicules
transport_exploitation_tournee: tournées, trajets réalisés/planifiés, km, kilométrage mensuel des bus
transport_exploitation_ligne: lignes de transport, itinéraires
transport_exploitation_station: stations d'arrêt, gares, terminus, points d'arrêt, haltes (54 stations)
transport_exploitation_centre: centres d'exploitation
transport_exploitation_agence: agences de transport
transport_assurance_bus: assurances des bus, polices, dates
transport_assurance_chauffeur: assurances des chauffeurs
transport_assurance_sinistre: sinistres, accidents
transport_fuel_voucher: bons de carburant, BGI (interne), BGE (externe)
transport_fuel_cuve: cuves de carburant, stock
transport_fuel_station: stations carburant (pas les stations d'arrêt)
transport_facture_energie: factures STEG, SONEDE, électricité, eau, énergie
transport_bon_lubrifiant: bons lubrifiants
transport_stock_lubrifiant: stock lubrifiants
patrimoine_immobilisation: immobilisations, actifs, équipements
patrimoine_categorie: catégories des immobilisations
patrimoine_amortissement_ligne: lignes d'amortissement
patrimoine_cession: cessions d'immobilisations
patrimoine_inventaire: inventaires
boc_courrier_arrivee: courriers arrivée, correspondances reçues
boc_courrier_depart: courriers départ, correspondances envoyées
hr_employee: employés, chauffeurs, conducteurs, personnel
account_move: factures comptables générales (PAS énergie)
res_partner: fournisseurs, clients, partenaires
"""


def detecter_tables_pertinentes(question: str, llm=None) -> list:
    """
    Détecte les tables pertinentes via le LLM d'abord,
    puis fallback sur le mapping statique si LLM indisponible.
    """
    if llm is not None:
        try:
            prompt = (
                "You are a database expert. Given this question in French, "
                "select the 1-3 most relevant PostgreSQL table names from the list below.\n"
                "Return ONLY the table names, one per line, nothing else.\n\n"
                f"Question: {question}\n\n"
                "Available tables:\n"
                f"{CATALOGUE_TABLES}\n"
                "Selected tables (1-3 names only):"
            )
            reponse = llm.invoke(prompt).strip()
            tables_llm = []
            for line in reponse.split("\n"):
                line = line.strip().strip("-").strip("*").strip()
                if line and line in CATALOGUE_TABLES:
                    tables_llm.append(line)
                    if len(tables_llm) >= 3:
                        break
            if tables_llm:
                _logger.info(f"Tables détectées par LLM: {tables_llm}")
                return tables_llm
        except Exception as e:
            _logger.warning(f"LLM table detection failed: {e}")

    # Fallback mapping statique
    question_lower = question.lower()
    tables = set()
    for mot, tables_liees in TABLES_METIER.items():
        if mot in question_lower:
            tables.update(tables_liees)
    if not tables:
        tables = {"fleet_vehicle", "transport_exploitation_tournee",
                  "transport_assurance_bus", "hr_employee"}
    tables_list = list(tables)
    if len(tables_list) > 4:
        tables_list = tables_list[:4]
    return tables_list

# ---------------------------------------------------------------------------
# SCHÉMA DYNAMIQUE — colonnes chargées depuis PostgreSQL
# ---------------------------------------------------------------------------


def charger_schema_tables(tables: list) -> str:
    """
    Charge le schéma PostgreSQL. Filtre les colonnes inutiles mais
    conserve les types complets (jsonb visible) et un exemple de valeur
    pour que le LLM génère un SQL correct.
    """
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        schema = ""
        tables_chargees = 0
        cols_exclues = _COLS_SCHEMA_EXCLUES | {
            "create_uid", "write_uid", "create_date", "write_date",
            "message_follower_ids", "message_ids", "activity_ids",
        }
        for table in sorted(set(tables)):
            try:
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table,))
                cols = cur.fetchall()
                if not cols:
                    _logger.warning(f"Table '{table}' absente de PostgreSQL")
                    continue
                # Filtrer colonnes inutiles, garder type complet (jsonb important !)
                col_desc = [
                    f"{c[0]}({c[1][:8]})"
                    for c in cols
                    if c[0] not in cols_exclues
                ]
                # Limiter à 20 colonnes max pour ne pas saturer la RAM Ollama
                if len(col_desc) > 20:
                    col_desc = col_desc[:20]
                # Exemple sur colonnes clés seulement (pas toutes)
                COLS_SAMPLE = {
                    "state", "statut", "type_facture", "voucher_type",
                    "direction", "name", "license_plate", "active",
                }
                cur.execute(f"SELECT * FROM {table} LIMIT 1")
                sample = cur.fetchone()
                sample_str = ""
                if sample and cur.description:
                    for i, desc in enumerate(cur.description):
                        if desc[0] not in COLS_SAMPLE:
                            continue
                        val = sample[i]
                        if val is not None and str(val).strip():
                            sample_str += f"{desc[0]}={repr(str(val)[:15])} "
                schema += f"\nTABLE: {table}\n"
                schema += f"COLUMNS: {', '.join(col_desc)}\n"
                if sample_str:
                    schema += f"SAMPLE: {sample_str[:150]}\n"
                tables_chargees += 1
            except Exception as e:
                _logger.warning(f"Erreur lecture table {table}: {e}")
        conn.close()
        _logger.info(f"Schéma chargé: {tables_chargees}/{len(tables)} tables depuis PostgreSQL")
        return schema
    except Exception as e:
        _logger.error(f"Erreur chargement schéma: {e}")
        return ""


def charger_schema_detaille() -> str:
    return charger_schema_tables(TABLES_PRINCIPALES)

# ---------------------------------------------------------------------------
# VÉRIFICATION ET DIAGNOSTIC
# ---------------------------------------------------------------------------


def verifier_colonnes_sql(sql: str) -> tuple:
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        tables_trouvees = re.findall(
            r'(?:FROM|JOIN)\s+([a-z_]+)\s*(?:AS\s+)?([a-z_]*)',
            sql, re.IGNORECASE
        )
        alias_map = {}
        for table, alias in tables_trouvees:
            table = table.lower()
            alias = alias.lower() if alias else table
            alias_map[alias] = table
            alias_map[table] = table
        colonnes_reelles = {}
        for alias, table in alias_map.items():
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
            """, (table,))
            cols = {row[0] for row in cur.fetchall()}
            colonnes_reelles[alias] = (table, cols)
        conn.close()
        refs = re.findall(r'([a-z_]+)\.([a-z_]+)', sql.lower())
        for alias, col in refs:
            if alias in colonnes_reelles:
                table, cols = colonnes_reelles[alias]
                if col not in cols and col != 'id':
                    return False, f"Colonne '{col}' inexistante dans '{table}'"
        return True, ""
    except Exception as e:
        _logger.warning(f"Erreur vérification colonnes: {e}")
        return True, ""


def diagnostiquer_erreur_sql(sql_erreur: str, message_erreur: str) -> str:
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND (table_name LIKE 'transport_%' OR table_name LIKE 'fleet_%'
                 OR table_name LIKE 'patrimoine_%' OR table_name LIKE 'boc_%'
                 OR table_name = 'hr_employee' OR table_name = 'account_move')
            ORDER BY table_name
        """)
        toutes_tables = [row[0] for row in cur.fetchall()]
        diagnostic = "DIAGNOSTIC DEPUIS POSTGRESQL:\n"
        tables_sql = re.findall(r'(?:from|join)\s+([a-z_]+)', sql_erreur.lower())
        for table in set(tables_sql):
            cur.execute("""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
                AND column_name NOT IN ('create_uid','write_uid','create_date','write_date')
                ORDER BY ordinal_position
            """, (table,))
            cols = cur.fetchall()
            if cols:
                col_list = ", ".join(f"{c[0]}({c[1][:8]})" for c in cols)
                diagnostic += f"\nTABLE '{table}' existe. Colonnes: {col_list}\n"
            else:
                diagnostic += f"\nTABLE '{table}' N'EXISTE PAS.\n"
                mots = set(table.split("_"))
                suggestions = sorted(
                    toutes_tables,
                    key=lambda t: len(mots & set(t.split("_"))),
                    reverse=True
                )[:3]
                if suggestions:
                    diagnostic += "  Utiliser plutôt:\n"
                    for sug in suggestions:
                        cur.execute("""
                            SELECT column_name, data_type FROM information_schema.columns
                            WHERE table_name = %s AND table_schema = 'public'
                            AND column_name NOT IN (
                                'create_uid','write_uid','create_date','write_date'
                            )
                            ORDER BY ordinal_position
                        """, (sug,))
                        cols_sug = cur.fetchall()
                        col_list = ", ".join(f"{c[0]}({c[1][:8]})" for c in cols_sug)
                        diagnostic += f"  -> {sug}: {col_list}\n"
        conn.close()
        return diagnostic
    except Exception as e:
        return f"Erreur diagnostic: {e}"

# ---------------------------------------------------------------------------
# CONTRÔLE D'ACCÈS
# ---------------------------------------------------------------------------

MOTS_TRANSPORT_AUTORISES = [
    'cuve', 'carburant', 'bgi', 'bge', 'tournee', 'tournée',
    'bus', 'assurance', 'police', 'patrimoine', 'immobilisation',
    'boc', 'courrier', 'lubrifiant', 'ravitaillement', 'agilis',
    'ligne', 'parc', 'vehicule', 'véhicule', 'stock', 'km',
    'kilometrage', 'kilométrage', 'chauffeur', 'conducteur',
    'litre', 'pompe', 'station', 'realise', 'planifie', 'annule',
    'type', 'liste', 'detail', 'nombre', 'combien', 'etat',
    'resume', 'bilan', 'tournees', 'lignes', 'quels', 'quelle',
    'amortissement', 'amorties', 'amortie', 'cession', 'inventaire',
    'facture', 'factures', 'facturation', 'montant', 'paiement',
    'steg', 'sonede', 'fournisseur', 'client', 'partenaire',
    'electricite', 'électricité', 'eau', 'kwh', 'compteur', 'energie',
    'acquisition', 'valeur', 'nette', 'sinistre', 'accident',
    # Verbes d'action RPC — indispensable pour le contrôle d'accès
    'planifier', 'planifie', 'planifié', 'demarrer', 'démarrer',
    'terminer', 'termine', 'cloturer', 'clôturer',
    'annuler', 'annule', 'confirmer', 'confirme',
    'valider', 'valide', 'activer', 'resilier', 'résilier',
    'renouveler', 'renouvelle', 'payer', 'payé',
    'traiter', 'traité', 'classer', 'classé',
    'diffuser', 'diffuse', 'enregistrer', 'enregistre',
    'mettre', 'hors service', 'en service', 'immobiliser',
    'comptabiliser', 'declarer', 'déclarer',
]

MOTS_CLES_PROTEGES = {
    'hr': ['employe', 'employee', 'salarie', 'staff', 'personnel'],
}


def verifier_acces_question(question: str, allowed_tables: list, is_admin: bool):
    if is_admin or (allowed_tables and "ALL" in allowed_tables):
        return None
    import unicodedata
    question_lower = question.lower()
    q_norm = unicodedata.normalize('NFD', question_lower)
    q_norm = ''.join(c for c in q_norm if unicodedata.category(c) != 'Mn')
    for mot in MOTS_TRANSPORT_AUTORISES:
        if mot in question_lower or mot in q_norm:
            return None
    for domaine, mots in MOTS_CLES_PROTEGES.items():
        for mot in mots:
            if mot in question_lower:
                tables_domaine = {'hr': ['hr_employee', 'hr_department']}
                autorise = any(t in (allowed_tables or [])
                               for t in tables_domaine.get(domaine, []))
                if not autorise:
                    return msg("access_denied", langue)
    return None

# ---------------------------------------------------------------------------
# DÉTECTION RAPIDE D'OUTIL — 100% Python, 0 appel LLM
# ---------------------------------------------------------------------------

# Mots-clés qui indiquent une procédure/définition (rag)
_MOTS_RAG = {
    "comment", "procédure", "procedure", "définition", "definition",
    "qu'est-ce", "qu est ce", "c'est quoi", "c est quoi", "cest quoi",
    "expliquer", "expliquez", "comment faire", "règle", "regle",
    "workflow", "étapes", "etapes", "feuille de route", "manuel", "guide",
    "kesquoi", "koi", "ca veut dire", "ça veut dire", "signifie",
    "c'est quoi le", "c'est quoi la", "c'est quoi un", "c'est quoi une",
}

# Mots-clés qui indiquent une action Odoo (rpc)
_MOTS_RPC = {
    # Création
    "créer", "creer", "créé", "ajouter", "ajoute", "nouveau", "nouvelle",
    # Validation / confirmation
    "valider", "valide", "confirmer", "confirme",
    # Modification / mise à jour
    "modifier", "modifie", "mettre à jour", "mettre a jour",
    # Annulation / suppression
    "annuler", "annule", "supprimer", "supprime",
    # Enregistrement (BOC)
    "enregistrer", "enregistre",
    # Tournée — verbes spécifiques du code
    "planifier", "planifie", "planifié", "planifie la", "planifier la",
    "affecter", "assigner", "attribuer",
    "démarrer", "demarrer",
    "terminer", "termine", "terminé",
    "clôturer", "cloturer",
    "remettre en brouillon",
    # Bus
    "hors service", "en service", "immobiliser", "remettre en service",
    # Assurance
    "activer", "résilier", "resilier", "renouveler", "renouvelle",
    # Sinistre
    "déclarer", "declarer", "instruire",
    # Facture
    "payer", "payé",
    # BOC
    "diffuser", "diffuse", "traiter", "traité", "classer", "classé",
    # Patrimoine
    "mettre en service", "mettre hors service", "comptabiliser",
}


def detecter_outil(question: str, llm=None) -> str:
    """
    Détection de l'outil en Python pur — zéro appel LLM.
    RAG  : questions de définition/procédure
    RPC  : actions Odoo (créer, valider, modifier…)
    SQL  : tout le reste (liste, stats, détails)
    """
    import unicodedata
    q = question.lower()
    q_norm = unicodedata.normalize('NFD', q)
    q_norm = ''.join(c for c in q_norm if unicodedata.category(c) != 'Mn')

    # Préfixes RPC impératifs — détectés EN PREMIER (verbe d'action au début)
    PREFIXES_RPC = [
        "cree ", "creer ", "ajoute ", "ajouter ", "valide ", "valider ",
        "modifie ", "modifier ", "annule ", "annuler ", "supprime ", "supprimer ",
        "affecte ", "affecter ", "assigne ", "assigner ", "planifie ", "planifier ",
        "demarre ", "terminer ", "termine ", "cloture ", "cloturer ",
        "passe ", "mets ", "met ", "change ", "mettre ",
        "enregistre ", "enregistrer ", "diffuse ", "diffuser ",
        "traite ", "classer ", "classe ", "resilier ", "resilier ",
        "declare ", "declarer ", "paye ", "payer ",
    ]
    for pref in PREFIXES_RPC:
        if q_norm.startswith(pref) or q.startswith(pref):
            return "rpc"

    # Mots interrogatifs = lecture SQL
    MOTS_LECTURE = {
        "quel", "quelle", "quels", "quelles", "combien", "liste",
        "afficher", "montrer", "voir", "donner", "donne",
        "lequel", "laquelle", "qui a", "qui est",
        "meilleur", "maximum", "minimum", "grand nombre",
        "top", "rang", "statistique", "analyse", "rapport", "bilan",
        "etat actuel", "etat de", "situation", "evolution",
    }
    # RAG d'abord — questions définitionnelles prioritaires sur lecture SQL
    for mot in _MOTS_RAG:
        if mot in q or mot in q_norm:
            return "rag"

    for mot in MOTS_LECTURE:
        if mot in q or mot in q_norm:
            return "sql"
    for mot in _MOTS_RPC:
        if mot in q or mot in q_norm:
            return "rpc"
    return "sql"


# ---------------------------------------------------------------------------
# PIPELINE UNIFIÉ : 1 seul appel LLM (outil + tables + SQL en une fois)
# ---------------------------------------------------------------------------

def _tables_par_mots_cles(question: str, langue: str = "fr") -> list:
    """Détection des tables 100% Python via TABLES_METIER (multilingue)."""
    q = question.lower()
    tables = set()
    # Mots-clés français (base)
    for mot, tables_liees in TABLES_METIER.items():
        if mot in q:
            tables.update(tables_liees)
    # Mots-clés anglais
    if langue == "en":
        for mot, tables_liees in TABLES_METIER_EN.items():
            if mot in q:
                tables.update(tables_liees)
    # Mots-clés arabes
    elif langue == "ar":
        for mot, tables_liees in TABLES_METIER_AR.items():
            if mot in q:
                tables.update(tables_liees)

    # Cas spéciaux : référence de tournée → toujours charger bus + chauffeur
    if re.search(r"tourn/\d{4}/\d+", q) or (
        ("détail" in q or "detail" in q or "information" in q or "info" in q)
        and ("tournee" in q or "tournée" in q)
    ):
        tables.update(["transport_exploitation_tournee", "fleet_vehicle", "hr_employee"])

    if not tables:
        tables = {"fleet_vehicle", "transport_exploitation_tournee",
                  "transport_assurance_bus", "hr_employee"}

    # Max 3 tables pour rester dans la RAM Ollama
    tables_list = sorted(tables)
    return tables_list[:3]


# ---------------------------------------------------------------------------
# CACHE SQL — Requêtes pré-construites pour questions fréquentes (0 LLM)
# ---------------------------------------------------------------------------

_CACHE_SQL = [
    # COUNT bus
    (r"combien.*(bus|véhicul|vehicul|parc)",
     "SELECT COUNT(*) AS nombre_de_bus FROM fleet_vehicle"),
    # Liste bons carburant (name est Char, pas jsonb)
    (r"(liste|tous|référence|reference).*(bon|bgi|bge|carburant)",
     "SELECT name AS reference, voucher_type AS type_bon, state AS etat, date "
     "FROM transport_fuel_voucher ORDER BY date DESC LIMIT 20"),
    # Liste polices assurance (chercher dans transport_assurance_bus)
    (r"(liste|tous|référence|reference).*(police|assurance)",
     "SELECT name AS reference, state AS etat, date_debut, date_fin "
     "FROM transport_assurance_bus ORDER BY date_debut DESC LIMIT 20"),
    # COUNT tournées toutes
    (r"combien.*(tournee|tournée)(?!.*mois|.*semaine|.*jour|.*réalisée|.*planif)",
     "SELECT COUNT(*) AS nombre_tournees FROM transport_exploitation_tournee"),
    # COUNT tournées réalisées ce mois
    (r"combien.*(tournee|tournée).*(mois|mensuel|réalisée|realise|effectuée)",
     "SELECT COUNT(*) AS nombre_tournees FROM transport_exploitation_tournee "
     "WHERE state='realise' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) "
     "AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)"),
    # COUNT chauffeurs
    (r"combien.*(chauffeur|conducteur|employ|personnel)",
     "SELECT COUNT(*) AS nombre_employes FROM hr_employee WHERE active=true"),
    # COUNT stations
    (r"combien.*(station)",
     "SELECT COUNT(*) AS nombre_stations FROM transport_exploitation_station"),
    # COUNT sinistres
    (r"combien.*(sinistre|accident)",
     "SELECT COUNT(*) AS nombre_sinistres FROM transport_assurance_sinistre"),
    # Liste tous les bus — license_plate en premier, name brut évité
    (r"(liste|tous|toutes|quels|quelles).*(bus|véhicul|vehicul|parc)",
     "SELECT v.license_plate AS immatriculation, "
     "COALESCE(s.name->>'fr_FR',s.name->>'en_US','Inconnu') AS etat "
     "FROM fleet_vehicle v LEFT JOIN fleet_vehicle_state s ON v.state_id=s.id "
     "ORDER BY v.license_plate LIMIT 50"),

    # Assurance — états avec accents réels en base
    (r"assurance.*(tesla|bus.*2|255)",
     "SELECT a.numero_police, a.state, a.date_debut, a.date_fin, "
     "a.prime_annuelle, c.name AS compagnie "
     "FROM transport_assurance_bus a "
     "JOIN fleet_vehicle v ON a.vehicle_id = v.id "
     "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
     "WHERE v.name ILIKE '%Tesla%' LIMIT 10"),

    (r"assurance.*(audi|bus.*1|123)",
     "SELECT a.numero_police, a.state, a.date_debut, a.date_fin, "
     "c.name AS compagnie "
     "FROM transport_assurance_bus a "
     "JOIN fleet_vehicle v ON a.vehicle_id = v.id "
     "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
     "WHERE v.name ILIKE '%Audi%' LIMIT 10"),

    (r"(liste|tous).*(police|assurance).*(activ|en cours)",
     "SELECT a.numero_police, a.state, a.date_debut, a.date_fin, "
     "v.name AS bus, c.name AS compagnie "
     "FROM transport_assurance_bus a "
     "JOIN fleet_vehicle v ON a.vehicle_id = v.id "
     "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
     "WHERE a.state = 'active' ORDER BY a.date_fin LIMIT 20"),

    (r"(liste|tous).*(police|assurance)",
     "SELECT a.numero_police, a.state, a.date_debut, a.date_fin, "
     "v.name AS bus, c.name AS compagnie "
     "FROM transport_assurance_bus a "
     "JOIN fleet_vehicle v ON a.vehicle_id = v.id "
     "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
     "ORDER BY a.date_fin DESC LIMIT 20"),

    (r"(expir|bientot|prochain).*(police|assurance)",
     "SELECT a.numero_police, a.state, a.date_fin, v.name AS bus "
     "FROM transport_assurance_bus a "
     "JOIN fleet_vehicle v ON a.vehicle_id = v.id "
     "WHERE a.date_fin BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days' "
     "AND a.state = 'active' ORDER BY a.date_fin LIMIT 20"),

    (r"(sinistre|accident)",
     "SELECT s.name, s.state, s.date_sinistre, s.montant_dommage, "
     "v.name AS bus FROM transport_assurance_sinistre s "
     "LEFT JOIN fleet_vehicle v ON s.vehicle_id = v.id "
     "ORDER BY s.date_sinistre DESC LIMIT 20"),

    (r"(combien|nombre).*(police|assurance)",
     "SELECT state, COUNT(*) AS nombre FROM transport_assurance_bus GROUP BY state"),

    (r"(combien|nombre).*(sinistre)",
     "SELECT COUNT(*) AS nombre_sinistres FROM transport_assurance_sinistre"),


    # Chauffeurs
    (r"(liste|tous|disponible).*(chauffeur|conducteur)",
     "SELECT e.id, e.name AS chauffeur "
     "FROM hr_employee e "
     "WHERE e.active = true "
     "ORDER BY e.name LIMIT 20"),

    (r"(combien|nombre).*(chauffeur|conducteur)",
     "SELECT COUNT(*) AS nombre_chauffeurs "
     "FROM hr_employee "
     "WHERE active = true AND job_title ILIKE '%chauffeur%'"),

    (r"chauffeur.*(plus|tournee|effectue)",
     "SELECT e.name AS chauffeur, COUNT(t.id) AS nb_tournees "
     "FROM hr_employee e "
     "LEFT JOIN transport_exploitation_tournee t ON t.chauffeur_id = e.id "
     "WHERE t.state = 'realise' "
     "GROUP BY e.id, e.name ORDER BY nb_tournees DESC LIMIT 10"),

    (r"chauffeur.*(sinistre|accident)",
     "SELECT e.name AS chauffeur, COUNT(s.id) AS nb_sinistres "
     "FROM hr_employee e "
     "LEFT JOIN transport_assurance_sinistre s ON s.chauffeur_id = e.id "
     "GROUP BY e.id, e.name ORDER BY nb_sinistres DESC LIMIT 10"),

    # Tournées avec chauffeur et bus
    (r"(liste|tournee).*(chauffeur|conducteur|bus|vehicule)",
     "SELECT t.name AS tournee, t.state, t.date, "
     "e.name AS chauffeur, v.name AS bus, v.license_plate "
     "FROM transport_exploitation_tournee t "
     "LEFT JOIN hr_employee e ON t.chauffeur_id = e.id "
     "LEFT JOIN fleet_vehicle v ON t.vehicle_id = v.id "
     "ORDER BY t.date DESC LIMIT 20"),

    # Bus assurés et en service
    (r"(bus|vehicule).*(assure|assurance).*(service|disponible)",
     "SELECT v.name AS bus, v.license_plate, "
     "a.numero_police, a.date_fin AS expiration_assurance "
     "FROM fleet_vehicle v "
     "JOIN fleet_vehicle_state s ON v.state_id = s.id "
     "JOIN transport_assurance_bus a ON a.vehicle_id = v.id "
     "WHERE s.id = 47 AND a.state = 'active' "
     "ORDER BY v.name LIMIT 20"),

    # Ecart kilométrique
    (r"(ecart|kilometrique|km).*(suspect|eleve|important|superieur)",
     "SELECT t.name AS tournee, t.date, t.km_prevu, t.km_realise, "
     "t.ecart_km, e.name AS chauffeur, v.name AS bus "
     "FROM transport_exploitation_tournee t "
     "LEFT JOIN hr_employee e ON t.chauffeur_id = e.id "
     "LEFT JOIN fleet_vehicle v ON t.vehicle_id = v.id "
     "WHERE ABS(t.ecart_km) > 50 AND t.state = 'realise' "
     "ORDER BY ABS(t.ecart_km) DESC LIMIT 20"),


    # Chauffeurs disponibles pour une tournée (sans conflit horaire)
    (r"chauffeur.*(disponible|libre|tourné|tournee|tourn)",
     "SELECT e.id, e.name AS chauffeur "
     "FROM hr_employee e "
     "WHERE e.active = true "
     "ORDER BY e.name LIMIT 20"),

    # Chauffeurs disponibles simple
    (r"(disponible|libre).*(chauffeur|conducteur)",
     "SELECT e.id, e.name AS chauffeur "
     "FROM hr_employee e "
     "WHERE e.active = true "
     "ORDER BY e.name LIMIT 20"),

]


def _chercher_cache_sql(question: str) -> str | None:
    """
    Retourne une requête SQL pré-construite si la question correspond,
    sinon None. Zéro appel LLM.
    """
    q = question.lower()
    for pattern, sql in _CACHE_SQL:
        if re.search(pattern, q):
            _logger.info(f"Cache SQL hit: {pattern[:40]}")
            print(f"  -> Cache SQL: {sql[:60]}...")
            return sql
    return None



def _regles_metier_pour(question: str) -> str:
    """Retourne uniquement les règles SQL pertinentes pour cette question."""
    q = question.lower()
    regles = []
    if any(w in q for w in ["bus", "véhicul", "vehicul", "parc", "immatricul"]):
        regles.append("BUS: state jsonb COALESCE(s.name->>'fr_FR',s.name->>'en_US'). No type_vehicule col.")
    if any(w in q for w in ["assurance", "police", "sinistre"]):
        regles.append("ASSURANCE: colonne=numero_police (PAS name). state VALEURS EXACTES: 'active','résiliée','expirée','brouillon','alerte'. JOIN compagnie: LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id=c.id. IMPORTANT: compagnie.name=VARCHAR pas jsonb, utiliser c.name SANS ->>.")
    if any(w in q for w in ["tournee", "tournée", "tourn/"]):
        regles.append("TOURNEE state: brouillon,planifie,en_cours,realise,annule. km_realise=actual,km_prevu=planned.")
    if any(w in q for w in ["chauffeur", "conducteur", "employe", "employé"]):
        regles.append("EMPLOYES: table=hr_employee. JOIN ON t.chauffeur_id=e.id")
    if any(w in q for w in ["carburant", "bgi", "bge", "litre"]):
        regles.append("CARBURANT: voucher_type='internal'=BGI,'external'=BGE. qty=total_quantity.")
    if any(w in q for w in ["steg", "sonede", "facture", "energie", "électricité", "electricite", "eau"]):
        regles.append("ENERGIE: ONLY transport_facture_energie. type_facture='steg'|'sonede'. statut='saisie'|'payee'|'validee'. No statut filter unless asked.")
    if any(w in q for w in ["patrimoine", "immobilisation", "amortissement"]):
        regles.append("PATRIMOINE: name jsonb COALESCE(name->>'fr_FR',name->>'en_US') AS nom.")
    if any(w in q for w in ["station", "gare", "terminus"]):
        regles.append("STATION: name jsonb, ville jsonb. type_station='intermediaire'|'terminus'.")
    if any(w in q for w in ["courrier", "boc"]):
        regles.append("BOC depart.state: enregistre,classe.")
    return ("METIER:\n" + "\n".join(f"  {r}" for r in regles) + "\n") if regles else ""

def generer_sql(question: str, llm: OllamaLLM,
                allowed_tables: list = None,
                is_admin: bool = False,
                diagnostic_extra: str = "") -> str:
    """
    OPTIMISÉ — 1 seul appel LLM qui détecte les tables ET génère le SQL.
    Le schéma est chargé par mots-clés Python (sans appel LLM préalable).
    """
    # ── Étape 1 : tables par mots-clés Python (instantané) ──
    tables_pertinentes = _tables_par_mots_cles(question)
    schema = charger_schema_tables(tables_pertinentes)
    _logger.info(f"Tables injectées dans le prompt: {tables_pertinentes}")
    print(f"  -> Tables pertinentes: {tables_pertinentes}")

    # ── Étape 2 : 1 seul appel LLM — génère directement le SQL ──
    prompt = (
        "PostgreSQL expert for Odoo 19 transport ERP Tunisia.\n"
        "Output ONLY the SQL SELECT. No explanation. No markdown. No comments.\n\n"
        "SCHEMA (live from PostgreSQL):\n"
        "COLONNES IMPORTANTES:\n"
        "transport_assurance_bus: numero_police,state,vehicle_id,compagnie_id,date_debut,date_fin,prime_annuelle\n"
        "transport_assurance_compagnie: id,name\n"
        "transport_facture_energie: name,type_facture,statut(PAS state),site,montant,date_reception\n"
        "patrimoine_immobilisation: name,statut(PAS state),valeur_nette_comptable\n"
        "fleet_vehicle_state IDs: 47=En service,48=Hors service,5=En panne,6=En maintenance\n"
        f"{schema}\n"
        f"{diagnostic_extra}\n"
        "RULES:\n"
        "  [BUS] ALWAYS SELECT v.name AS bus, v.license_plate. "
        "state jsonb: LEFT JOIN fleet_vehicle_state s ON v.state_id=s.id, COALESCE(s.name->>'fr_FR',s.name->>'en_US') AS etat. "
        "NEVER add WHERE on state unless user explicitly asks for a specific state. "
        "NEVER use @> operator on state. Use state_id IN(47,48,5,6) to filter if needed. "
        "COUNT(*) FROM fleet_vehicle needs no WHERE. "
        "No cols: type_vehicule,activity_type,vehicle_type. NEVER select raw id columns.\n"
        "  [ASSURANCE] colonne ref=numero_police (jamais name). state valeurs EXACTES: 'active','resiliee','expiree','brouillon','alerte'. JOIN compagnie: LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id=c.id. CRITICAL: transport_assurance_compagnie.name est VARCHAR (pas jsonb) — utiliser c.name directement SANS ->> operator.\n"
        "  [TOURNEES] state: brouillon,planifie,en_cours,realise,annule. "
        "km_realise=actual, km_prevu=planned, ecart_km=diff.\n"
        "  [EMPLOYES] table=hr_employee. JOIN: hr_employee e ON t.chauffeur_id=e.id\n"
        "  [CARBURANT] voucher_type='internal'=BGI,'external'=BGE. qty=total_quantity.\n"
        "  [ENERGIE] ONLY transport_facture_energie for STEG/SONEDE. "
        "type_facture='steg'|'sonede'. statut='saisie'|'payee'|'validee'. "
        "Cols: name,type_facture,statut,site,numero_compteur,unite_mesure,"
        "date_debut_periode,date_fin_periode,date_reception,quantite_consommee,montant. "
        "No statut filter unless asked.\n"
        "  [PATRIMOINE] name jsonb: COALESCE(name->>'fr_FR',name->>'en_US') AS nom.\n"
        "  [STATION] name jsonb. ville jsonb.\n"
        "  [BOC] boc_courrier_depart.state: enregistre,classe.\n"
        "CRITICAL: only real columns. ->> only on jsonb. LEFT JOIN for nullable FK. "
        "ILIKE for text. LIMIT 50 for lists. No accents in table names. "
        "No bracket placeholders.\n"
        "NOT IN subquery: ALWAYS add AND vehicle_id IS NOT NULL inside NOT IN() to avoid NULL poisoning.\n"
        "INTERVAL current month: use DATE_TRUNC('month', CURRENT_DATE), not CURRENT_DATE - INTERVAL '1 month'.\n"
        "LICENSE PLATE: ALWAYS use ILIKE for license_plate search. "
        "CORRECT: WHERE v.license_plate ILIKE '%158%tu%2026%' "
        "WRONG: WHERE v.license_plate = '158 TU 2026' "
        "Split the plate into parts with % between each.\n\n"
        f"Question: {question}\n\nSQL:"
    )

    try:
        sql = llm.invoke(prompt).strip()
    except Exception as e_llm:
        msg = str(e_llm)
        if "system memory" in msg or "memory" in msg.lower():
            _logger.error(f"Mémoire insuffisante Ollama: {msg}")
            raise MemoryError("Mémoire insuffisante pour Ollama. Relancez : ollama stop && ollama serve")
        raise
    sql = re.sub(r"```sql|```", "", sql).strip()
    sql = sql.split(";")[0].strip()
    lignes = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    sql = " ".join(lignes).strip()

    TABLE_NAME_FIXES = {
        "transport_exploitation_tourné":   "transport_exploitation_tournee",
        "transport_exploitation_tournée":  "transport_exploitation_tournee",
        "transport_exploitation_tournées": "transport_exploitation_tournee",
        "transport_fuel_cuvé":             "transport_fuel_cuve",
    }
    for wrong, correct in TABLE_NAME_FIXES.items():
        sql = sql.replace(wrong, correct)

    FILTRES_INVENTES = [
        r"AND\s+(?:\w+\.)?type_vehicule\s*=\s*'[^']*'",
        r"WHERE\s+(?:\w+\.)?type_vehicule\s*=\s*'[^']*'\s*AND",
        r"WHERE\s+(?:\w+\.)?type_vehicule\s*=\s*'[^']*'",
        r"AND\s+(?:\w+\.)?activity_type\s*=\s*'[^']*'",
        r"AND\s+(?:\w+\.)?vehicle_type\s*=\s*'[^']*'",
        r"AND\s+(?:\w+\.)?type_vehicule\s*LIKE\s*'[^']*'",
    ]
    for pattern in FILTRES_INVENTES:
        sql = re.sub(pattern, '', sql, flags=re.IGNORECASE).strip()

    sql = re.sub(r'WHERE\s+AND', 'WHERE', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\s{2,}', ' ', sql).strip()

    if re.search(r'\[[a-z_]+\]', sql):
        _logger.warning("Placeholder détecté dans SQL")
        sql = "SELECT 'Placeholder detecte' as erreur"

    if not sql.upper().startswith("SELECT"):
        sql = "SELECT 'Requete non valide' as message"

    if not is_admin and allowed_tables and "ALL" not in allowed_tables:
        sql_upper = sql.upper()
        for mot in ["HR_EMPLOYEE", "HR_DEPARTMENT", "RES_USERS"]:
            if mot in sql_upper and mot not in [t.upper() for t in (allowed_tables or [])]:
                return "SELECT 'Acces refuse' as message"

    return sql

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# FIX 1 — Génération dynamique de l'action RPC (lecture + écriture)
# ---------------------------------------------------------------------------

MODELES_RPC = {
    "tournee":        ("transport.exploitation.tournee",
                       ["name", "date", "state", "vehicle_id", "chauffeur_id",
                        "ligne_id", "km_prevu", "km_realise", "ecart_km",
                        "heure_depart_prevu", "heure_arrivee_prevu"]),
    "tournée":        ("transport.exploitation.tournee",
                       ["name", "date", "state", "vehicle_id", "chauffeur_id",
                        "ligne_id", "km_prevu", "km_realise", "ecart_km"]),
    "bus":            ("fleet.vehicle",
                       ["name", "license_plate", "state_id"]),
    "vehicule":       ("fleet.vehicle",
                       ["name", "license_plate", "state_id"]),
    "véhicule":       ("fleet.vehicle",
                       ["name", "license_plate", "state_id"]),
    "assurance":      ("transport.assurance.bus",
                       ["numero_police", "vehicle_id", "state", "date_debut",
                        "date_fin", "compagnie_id", "type_id"]),
    "police":         ("transport.assurance.bus",
                       ["numero_police", "vehicle_id", "state", "date_debut", "date_fin"]),
    "sinistre":       ("transport.assurance.sinistre",
                       ["name", "vehicle_id", "date_sinistre", "state",
                        "montant_dommage"]),
    "chauffeur":      ("hr.employee",
                       ["name", "job_title", "active"]),
    "conducteur":     ("hr.employee",
                       ["name", "job_title", "active"]),
    "carburant":      ("transport.fuel.voucher",
                       ["name", "voucher_type", "total_quantity", "date", "state",
                        "vehicle_id"]),
    "bgi":            ("transport.fuel.voucher",
                       ["name", "voucher_type", "total_quantity", "date", "state"]),
    "bge":            ("transport.fuel.voucher",
                       ["name", "voucher_type", "total_quantity", "date", "state"]),
    "courrier":       ("boc.courrier.arrivee",
                       ["name", "sujet", "expediteur", "date_arrivee", "state"]),
    "facture":        ("transport.facture.energie",
                       ["name", "type_facture", "statut", "site",
                        "montant", "date_reception"]),
    "immobilisation": ("patrimoine.immobilisation",
                       ["name", "statut", "valeur_nette_comptable",
                        "date_mise_en_service", "duree_amortissement"]),
}

ETATS_RPC = {
    # Tournées
    "réalisée": "realise",  "realisee": "realise",
    "effectuée": "realise", "terminée": "realise",
    "planifiée": "planifie","planifie": "planifie",
    "prévue": "planifie",   "programmée": "planifie",
    "en cours": "en_cours", "encours": "en_cours",
    "annulée": "annule",    "annule": "annule",
    "brouillon": "brouillon",
    # Assurance — valeurs EXACTES du code (avec accents)
    "active": "active",
    "expirée": "expirée",   "expiree": "expirée",
    "résiliée": "résiliée", "resiliee": "résiliée",
    "alerte": "alerte",
    # Carburant
    "confirme": "confirmed", "confirmé": "confirmed",
    "validé": "done",        "valide": "done",
    "annulé": "cancelled",   "annule_bon": "cancelled",
    # Facture énergie
    "payée": "payee",        "validée": "validee",
    "saisie": "saisie",
    # Patrimoine (champ = statut, pas state)
    "en service": "en_service",
    "hors_service": "hors_service",
    "cédé": "cede",          "rebut": "rebut",
}

# Actions d'écriture : (mots-clés, méthode_odoo, modèle_défaut)
# IMPORTANT : noms des méthodes pris DIRECTEMENT dans le code source des modules
INTENTIONS_ECRITURE = [
    # ── Tournée ─────────────────────────────────────────────────────
    # code : action_planifier (PAS action_confirm)
    (["confirmer la tournée", "confirme la tournée", "planifier la tournée",
      "planifie la tournée", "planifie la tournee", "planifier la tournee",
      "planifie la tourn"],
     "action_planifier", "transport.exploitation.tournee"),

    # code : action_demarrer
    (["démarrer la tournée", "demarrer la tournée", "commencer la tournée",
      "demarrer la tournee", "démarrer la tournee", "demarrer la tourn"],
     "action_demarrer", "transport.exploitation.tournee"),

    # code : action_terminer (PAS action_realiser)
    (["terminer la tournée", "clôturer la tournée", "marquer réalisée",
      "marquer la tournée réalisée", "marquer terminée",
      "terminer la tournee", "cloturer la tournee", "marquer realisee"],
     "action_terminer", "transport.exploitation.tournee"),

    # code : action_annuler
    (["annuler la tournée", "annule la tournée",
      "annuler la tournee", "annule la tournee"],
     "action_annuler", "transport.exploitation.tournee"),

    # code : action_remettre_brouillon
    (["remettre en brouillon", "remettre la tournée en brouillon"],
     "action_remettre_brouillon", "transport.exploitation.tournee"),

    # create
    (["créer une tournée", "nouvelle tournée", "ajouter une tournée"],
     "create", "transport.exploitation.tournee"),

    # Affecter chauffeur ou bus → write sur la tournée
    (["affecter", "affecter le chauffeur", "assigner le chauffeur",
      "affecter le bus", "assigner le bus"],
     "write", "transport.exploitation.tournee"),

    # ── Bus ──────────────────────────────────────────────────────────
    # code : action_changer_etat → ouvre wizard (géré en write simplifié)
    (["mettre le bus en service", "remettre en service", "remettre le bus", "remet en service", "remets en service", "remet le bus", "remets le bus",
      "mets le bus en service", "mets bus", "met le bus en service"],
     "write", "fleet.vehicle"),
    (["mettre le bus hors service", "immobiliser le bus", "hors service",
      "mets le bus hors service", "mets hors service"],
     "write", "fleet.vehicle"),
    (["mettre le bus en maintenance", "en maintenance", "mets en maintenance",
      "mets le bus en maintenance", "met en maintenance", "maintenance"],
     "write", "fleet.vehicle"),
    (["mettre le bus en panne", "en panne", "mets en panne",
      "mets le bus en panne", "met en panne"],
     "write", "fleet.vehicle"),

    # ── Assurance bus ────────────────────────────────────────────────
    # code : action_activer (PAS action_validate)
    (["valider la police", "valider l'assurance", "activer la police",
      "activer l'assurance"],
     "action_activer", "transport.assurance.bus"),

    # code : action_resilier
    (["résilier la police", "resilier la police", "résilier l'assurance"],
     "action_resilier", "transport.assurance.bus"),

    # renouvellement → via wizard (on crée un enregistrement brouillon)
    (["renouveler la police", "renouveler l'assurance", "renouvellement"],
     "create", "transport.assurance.bus"),

    # ── Sinistre ─────────────────────────────────────────────────────
    (["déclarer le sinistre", "declarer le sinistre"],
     "action_declarer", "transport.assurance.sinistre"),
    (["clôturer le sinistre", "cloture sinistre"],
     "action_cloturer", "transport.assurance.sinistre"),

    # ── Bon carburant ────────────────────────────────────────────────
    # Workflow OBLIGATOIRE : draft → action_confirm → action_validate
    (["confirmer le bon", "confirmer le bgi", "confirmer le bge"],
     "action_confirm", "transport.fuel.voucher"),
    (["valider le bon", "valider le bgi", "valider le bge"],
     "action_validate", "transport.fuel.voucher"),
    (["annuler le bon", "annuler le bgi", "annuler le bge"],
     "action_cancel", "transport.fuel.voucher"),

    # ── Facture énergie ──────────────────────────────────────────────
    # code : action_payer (PAS write statut directement)
    (["payer la facture", "marquer payée", "facture payée"],
     "action_payer", "transport.facture.energie"),
    (["annuler la facture", "annule la facture énergie"],
     "action_annuler", "transport.facture.energie"),

    # ── BOC courrier arrivée ─────────────────────────────────────────
    (["enregistrer le courrier", "enregistre le courrier"],
     "action_enregistrer", "boc.courrier.arrivee"),
    (["diffuser le courrier", "diffuse le courrier"],
     "action_diffuser", "boc.courrier.arrivee"),
    (["traiter le courrier", "marquer traité"],
     "action_traiter", "boc.courrier.arrivee"),
    (["classer le courrier", "classe le courrier"],
     "action_classer", "boc.courrier.arrivee"),

    # ── Patrimoine ───────────────────────────────────────────────────
    # code : action_mettre_en_service / action_mettre_hors_service
    (["mettre en service l'immobilisation", "mettre l'immobilisation en service"],
     "action_mettre_en_service", "patrimoine.immobilisation"),
    (["mettre hors service l'immobilisation", "hors service l'immobilisation"],
     "action_mettre_hors_service", "patrimoine.immobilisation"),

    # Cession
    (["confirmer la cession", "confirme la cession"],
     "action_confirmer", "patrimoine.cession"),
    (["comptabiliser la cession"],
     "action_comptabiliser", "patrimoine.cession"),
]


def _extraire_ref_tournee(question: str) -> str:
    """Extrait une référence Odoo du style TOURN/2026/00042."""
    import re as _re
    m = _re.search(r'[A-Z][A-Z0-9\-]*/\d{4}/\d+', question, _re.IGNORECASE)
    return m.group(0).upper() if m else ""


def _extraire_ids_rpc(q: str) -> list:
    """Extrait les IDs numériques bruts mentionnés dans la question."""
    import re as _re
    matches = _re.findall(r'(?:id[:\s#]+)(\d+)', q)
    return [int(x) for x in matches] if matches else []


def _construire_valeurs_creation(q: str, modele: str, llm) -> dict:
    """Construit un dict de valeurs pour create() via LLM + défauts."""
    import datetime, re as _re
    defaults = {
        "transport.exploitation.tournee": {
            "date": str(datetime.date.today()),
            "state": "brouillon",
        },
        "transport.assurance.bus": {"state": "brouillon"},
        "transport.fuel.voucher":  {"state": "draft", "voucher_type": "internal"},
    }
    if llm is None:
        return defaults.get(modele, {})
    try:
        champs_dispo = ", ".join(
            MODELES_RPC.get(modele.split(".")[-1], ("", []))[1]
        ) or "name, date, state"
        prompt = (
            f"Odoo 19 expert. Modèle: '{modele}'. "
            f"Champs: {champs_dispo}.\n"
            f"Question: {q}\n"
            "Retourne UNIQUEMENT un dict Python valide avec les valeurs extraites. "
            "Exemple: {\"date\": \"2026-05-20\", \"state\": \"brouillon\"}\n"
            "Dict:"
        )
        rep = llm.invoke(prompt).strip()
        rep = _re.sub(r"```.*?```", "", rep, flags=_re.DOTALL).strip()
        parsed = ast.literal_eval(rep)
        if isinstance(parsed, dict) and parsed:
            base = defaults.get(modele, {})
            base.update(parsed)
            return base
    except Exception as e_llm:
        _logger.warning(f"LLM create values failed: {e_llm}")
    return defaults.get(modele, {})


def generer_action_rpc(question: str, llm: OllamaLLM) -> str:
    """
    Génère dynamiquement une action RPC à partir de la question.
    Couvre lecture ET écriture.
    Retourne une chaîne au format: modele|methode|param1|param2
    """
    q = question.lower()

    # ── 1. Détecter l'intention d'écriture ──────────────────────────────────
    for mots_cles, methode_odoo, modele_defaut in INTENTIONS_ECRITURE:
        if any(mot in q for mot in mots_cles):
            _logger.info(f"Intention écriture: {methode_odoo} sur {modele_defaut}")
            ids = _extraire_ids_rpc(q)
            ref = _extraire_ref_tournee(question)

            # CREATE
            if methode_odoo == "create":
                valeurs = _construire_valeurs_creation(q, modele_defaut, llm)
                return f"{modele_defaut}|create|{json.dumps(valeurs, ensure_ascii=False)}"

            # WRITE bus état
            if methode_odoo == "write" and modele_defaut == "fleet.vehicle":
                # IDs reels fleet.vehicle.state
                if any(w in q for w in ["hors service", "immobiliser"]):
                    etat_id = 48
                elif any(w in q for w in ["en panne", "panne"]):
                    etat_id = 5
                elif any(w in q for w in ["maintenance", "en maintenance"]):
                    etat_id = 6
                elif any(w in q for w in ["en service", "remettre en service"]):
                    etat_id = 47
                else:
                    etat_id = 47
                if ids:
                    return f"{modele_defaut}|write|{json.dumps(ids)}|{{\"state_id\":{etat_id}}}"
                # Pas d'IDs → lister les bus pour que l'utilisateur choisisse
                return f"{modele_defaut}|search_read|[]|[\"id\",\"name\",\"license_plate\",\"state_id\"]"

            # WRITE facture payée
            if methode_odoo == "write" and modele_defaut == "transport.facture.energie":
                if ids:
                    return f"{modele_defaut}|write|{json.dumps(ids)}|{{\"statut\":\"payee\"}}"

            # Boutons workflow avec IDs
            if ids:
                return f"{modele_defaut}|{methode_odoo}|{json.dumps(ids)}"

            # IDs absents mais référence présente → chercher l'ID d'abord
            if ref:
                # Champ reference selon le modele (assurance utilise numero_police)
                _ref_field = "numero_police" if "assurance.bus" in modele_defaut else "name"
                return (
                    f"{modele_defaut}|search_read"
                    f"|[[\"{_ref_field}\",\"=\",\"{ref}\"]]"
                    f"|[\"id\",\"{_ref_field}\",\"state\"]"
                )

            # Fallback : liste pour que l'utilisateur choisisse
            return f"{modele_defaut}|search_read|[]|[\"id\",\"name\",\"state\"]"

    # ── 2. Lecture simple ────────────────────────────────────────────────────
    modele = "transport.exploitation.tournee"
    champs = ["name", "date", "state", "vehicle_id"]
    for mot, (m, c) in MODELES_RPC.items():
        if mot in q:
            modele = m
            champs = c
            break

    domaine = []

    # Filtre état
    for mot_etat, val_etat in ETATS_RPC.items():
        if mot_etat in q:
            domaine.append(["state", "=", val_etat])
            break

    # Filtre immatriculation
    match_plaque = re.search(
        r'\b(\d{1,4}\s*tu\s*\d{1,4}|\d{1,4}\s*tn\s*\d{1,4})\b', q
    )
    if match_plaque:
        plaque = match_plaque.group(0).upper().replace(" ", "")
        domaine.append(["license_plate", "ilike", plaque])

    # Filtre référence tournée
    ref = _extraire_ref_tournee(question)
    if ref:
        domaine.append(["name", "ilike", ref])

    # LLM pour domaine complexe si domaine vide
    if not domaine:
        try:
            prompt_rpc = (
                "You are an Odoo 19 expert. Build a search domain for this question.\n"
                f"Model: {modele}\n"
                f"Available fields: {champs}\n"
                "Return ONLY a valid Python list like: [[\"field\",\"op\",\"value\"]]\n"
                "Return [] if no filter is needed.\n"
                f"Question: {question}\n"
                "Domain:"
            )
            rep = llm.invoke(prompt_rpc).strip()
            rep = re.sub(r"```.*?```", "", rep, flags=re.DOTALL).strip()
            parsed = ast.literal_eval(rep)
            if isinstance(parsed, list):
                domaine = parsed
        except Exception as e:
            _logger.warning(f"LLM domain generation failed: {e}")
            domaine = []

    action = f"{modele}|search_read|{json.dumps(domaine)}|{json.dumps(champs)}"
    _logger.info(f"Action RPC générée: {action}")
    print(f"  -> RPC action: {action}")
    return action

# ---------------------------------------------------------------------------
# FORMULATION DE LA RÉPONSE — Python pur, 0 appel LLM sauf détail unique
# ---------------------------------------------------------------------------


_COLS_SCHEMA_EXCLUES = {
    "color", "color_float", "seats", "doors", "trailer_hook",
    "horsepower", "horsepower_tax", "co2", "co2_standard",
    "transmission", "power", "fuel_volume", "odometer_unit",
    "last_service_km", "next_assignation_km", "last_odometer",
    "default_fuel_type", "model_id", "driver_id", "company_id",
    "message_follower_ids", "message_ids", "activity_ids",
    "currency_id", "tag_ids", "image_128",
}

_GABARITS_COUNT = [
    (r"combien.*(bus|véhicul|vehicul)",        "Il y a **{v}** bus dans le parc."),
    (r"combien.*(tournee|tournée)",             "Il y a **{v}** tournée(s) enregistrée(s)."),
    (r"combien.*(facture|steg|sonede)",         "Il y a **{v}** facture(s) trouvée(s)."),
    (r"combien.*(chauffeur|conducteur|employ)", "Il y a **{v}** chauffeur(s) enregistré(s)."),
    (r"combien.*(sinistre|accident)",           "Il y a **{v}** sinistre(s) enregistré(s)."),
    (r"combien.*(station)",                     "Il y a **{v}** station(s) enregistrée(s)."),
    (r"total.*(km|kilomet)",                    "Le kilométrage total est de **{v}** km."),
    (r"total.*(litre|carburant|bgi|bge)",       "La quantité totale est de **{v}** litres."),
    (r"total.*(montant|facture)",               "Le montant total est de **{v}** TND."),
]


def _formuler_count(question: str, valeur: str, langue: str = "fr") -> str:
    q = question.lower()
    # Utiliser les gabarits de la langue détectée
    gabarits = GABARITS_COUNT.get(langue, GABARITS_COUNT["fr"])
    for pattern, gabarit in gabarits:
        if re.search(pattern, q):
            return gabarit.format(v=valeur)
    # Fallback : français si non trouvé dans la langue
    if langue != "fr":
        for pattern, gabarit in GABARITS_COUNT["fr"]:
            if re.search(pattern, question.lower()):
                return gabarit.format(v=valeur)
    labels = {"fr": "Résultat", "en": "Result", "ar": "النتيجة"}
    return f"{labels.get(langue, 'Résultat')} : **{valeur}**"


def formuler_reponse(question: str, donnees: str, llm: OllamaLLM, langue: str = "fr") -> str:
    if re.search(r'\[[A-Za-zÀ-ÿ ]+\]', donnees):
        return msg("placeholder_incomplete", langue)
    if any(x in donnees for x in ["Acces refuse", "Requete non valide", "Placeholder detecte"]):
        return msg("access_denied", langue)
    if not donnees.strip() or "Aucun résultat" in donnees or "Aucun resultat" in donnees:
        return msg("no_data", langue)

    lignes = [l for l in donnees.strip().split("\n") if l.strip()]
    if not lignes:
        return msg("no_data", langue)

    entete = lignes[0] if lignes else ""
    colonnes = [c.strip() for c in entete.split("|") if c.strip()]
    lignes_data = [l for l in lignes[1:] if "----" not in l and "====" not in l]

    if not lignes_data:
        _res_label = {"fr": "Résultat", "en": "Result", "ar": "النتيجة"}
        return f"{_res_label.get(langue, 'Résultat')} :\n{donnees}"

    nb = len(lignes_data)

    # ── COUNT/SUM (1 colonne) → Python pur, 0 LLM ──
    if len(colonnes) == 1:
        valeur = lignes_data[0].strip() if lignes_data else "?"
        return _formuler_count(question, valeur, langue)

    # ── Listes (≥2 lignes) et détail unique → voir après définition de _formater_valeur ──
    # Labels localisés selon la langue détectée
    LABELS = LABELS_COLONNES.get(langue, LABELS_COLONNES["fr"])

    # Utiliser les statuts dans la langue détectée
    _statuts_langue = STATUTS_TRADUITS.get(langue, STATUTS_TRADUITS["fr"])

    STATUTS = {
        # Factures / Paiements
        "payee": "✅ Payée", "saisie": "📝 Saisie", "validee": "✔️ Validée",
        # Assurance
        "active": "✅ Active", "expire": "❌ Expirée",
        "resilie": "🚫 Résiliée", "brouillon": "📝 Brouillon",
        # Tournées
        "planifie": "📅 Planifiée", "en_cours": "🔄 En cours",
        "realise": "✅ Réalisée", "annule": "❌ Annulée",
        # Courrier
        "enregistre": "📝 Enregistré", "classe": "✔️ Classé",
        # Patrimoine
        "en_service": "✅ En service", "cede": "🔄 Cédé",
        # Odoo général
        "draft": "📝 Brouillon", "posted": "✅ Validée", "cancel": "❌ Annulée",
        # Booléen
        "true": "✅ Oui", "false": "❌ Non",
        # Direction tournée
        "aller": "➡️ Aller", "retour": "⬅️ Retour",
        # Type bon carburant
        "internal": "🏠 BGI (Interne)", "external": "🏢 BGE (Externe)",
    }

    # Colonnes à masquer si valeur = 0 ou vide
    COLS_MASQUER_SI_ZERO = {
        "heure_depart_reel", "heure_arrivee_reel",
        "km_realise", "ecart_km", "compteur_arrivee",
    }
    # Colonnes qui contiennent des heures décimales (8.0 → 08:00)
    COLS_HEURE = {
        "heure_depart_prevu", "heure_arrivee_prevu",
        "heure_depart_reel", "heure_arrivee_reel",
    }
    # Colonnes compteur — afficher en km entiers
    COLS_COMPTEUR = {"compteur_depart", "compteur_arrivee"}

    def _decimal_vers_heure(val: str) -> str:
        """8.5 → 08:30 / 9.0 → 09:00"""
        try:
            h_total = float(val)
            if h_total == 0:
                return None  # heure 0 = non renseignée
            h = int(h_total)
            m = int(round((h_total - h) * 60))
            return f"{h:02d}:{m:02d}"
        except Exception:
            return val

    def _extraire_jsonb(val: str) -> str:
        """'{"fr_TN":"Bab Saadoun","en_US":"..."}' → 'Bab Saadoun'"""
        import json, re as _re
        v = val.strip()
        if v.startswith("{") and "}" in v:
            try:
                d = json.loads(v)
                return d.get("fr_TN") or d.get("fr_FR") or d.get("en_US") or v
            except Exception:
                # Tentative regex si json invalide
                m = _re.search(r'"fr_TN"\s*:\s*"([^"]+)"', v)
                if m: return m.group(1)
                m = _re.search(r'"en_US"\s*:\s*"([^"]+)"', v)
                if m: return m.group(1)
        return v

    def _formater_valeur(col: str, val: str) -> str:
        """Formate une valeur brute en valeur lisible."""
        if not val or val.strip() in ("—", "None", "False", ""):
            return None
        v = val.strip()

        # Extraire jsonb avant tout traitement
        if v.startswith("{"):
            v = _extraire_jsonb(v)
            if not v:
                return None

        col_lower = col.lower()

        # Masquer colonnes à 0 si non pertinent
        if col_lower in COLS_MASQUER_SI_ZERO:
            try:
                if float(v) == 0:
                    return None
            except Exception:
                pass

        # Colonnes compteur → entier + " km"
        if col_lower in COLS_COMPTEUR:
            try:
                return f"{LABELS.get(col_lower, col)} : {int(float(v))} km"
            except Exception:
                pass

        # Colonnes heure décimale → HH:MM
        if col_lower in COLS_HEURE:
            h = _decimal_vers_heure(v)
            if h is None:
                return None
            label = LABELS.get(col_lower, col.replace("_", " ").title())
            return f"{label} : {h}"

        # Masquer ID si c'est juste un entier seul
        if col_lower == "id":
            return None

        label = LABELS.get(col_lower, col.replace("_", " ").title())
        affiche = _statuts_langue.get(v.lower(), STATUTS.get(v.lower(), v))
        return f"{label} : {affiche}"

    if nb == 1:
        # ── Détail unique : affichage direct, 0 LLM ──────────────────────────
        valeurs = [v.strip() for v in lignes_data[0].split("|")]
        parties = []
        for j, col in enumerate(colonnes):
            if j >= len(valeurs):
                break
            ligne_fmt = _formater_valeur(col, valeurs[j])
            if ligne_fmt:
                parties.append(ligne_fmt)
        if parties:
            return "\n".join(f"• {p}" for p in parties)
        return donnees

    # ── Listes (≥2 lignes) : tableau numéroté ──
    _headers = {
        "fr": f"**{nb} résultat(s) trouvé(s)** :\n\n",
        "en": f"**{nb} result(s) found** :\n\n",
        "ar": f"**{nb} نتيجة (نتائج) موجودة** :\n\n",
    }
    reponse = _headers.get(langue, _headers["fr"])
    for i, ligne in enumerate(lignes_data, 1):
        valeurs = [v.strip() for v in ligne.split("|")]
        parties = []
        for j, col in enumerate(colonnes):
            if j >= len(valeurs):
                break
            ligne_fmt = _formater_valeur(col, valeurs[j])
            if ligne_fmt:
                parties.append(ligne_fmt)
        if parties:
            reponse += f"**{i}.** " + "  |  ".join(parties) + "\n"

    return reponse.strip()

# ---------------------------------------------------------------------------
# AGENT PRINCIPAL
# ---------------------------------------------------------------------------


def create_agent():
    llm = OllamaLLM(
        base_url=os.getenv("OLLAMA_BASE_URL"),
        model=os.getenv("OLLAMA_MODEL"),
        temperature=0.0,
        num_predict=2048,
    )
    try:
        schema = charger_schema_detaille()
        nb = schema.count("TABLE:")
        _logger.info(f"Connexion PostgreSQL OK — {nb} tables principales vérifiées")
        print(f"  -> Connexion PostgreSQL OK: {nb} tables vérifiées")
    except Exception as e:
        _logger.error(f"Erreur connexion PostgreSQL: {e}")
    return llm



# ---------------------------------------------------------------------------
# RÉPONSES RAG STATIQUES — quand ChromaDB est vide (0 appel LLM)
# ---------------------------------------------------------------------------

_RAG_STATIQUE = [
    # Carburant
    (r"\bbgi\b",
     "Un **BGI** (Bon de ravitaillement Interne) est un bon de carburant émis "
     "pour ravitailler les bus depuis les cuves internes du dépôt. "
     "Il est saisi par le responsable dépôt, signé par le chauffeur, "
     "et enregistré dans le module Carburant (type : 'internal')."),
    (r"\bbge\b",
     "Un **BGE** (Bon de ravitaillement Externe) est un bon de carburant "
     "utilisé pour les ravitaillements dans les stations-service externes. "
     "Il est soumis à validation avant utilisation (type : 'external')."),
    (r"cuve",
     "Une **cuve** est un réservoir de carburant interne au dépôt. "
     "Son stock est mis à jour à chaque émission d'un BGI. "
     "Le suivi du niveau est disponible dans le module Carburant."),
    # Tournées
    (r"tournee|tournée",
     "Une **tournée** est un trajet planifié effectué par un bus sur une ligne. "
     "États possibles : 📝 Brouillon → 📅 Planifiée → 🔄 En cours → ✅ Réalisée / ❌ Annulée. "
     "Elle enregistre les KM prévus et réalisés, le chauffeur, et les heures de départ/arrivée."),
    (r"ligne de transport|ligne de bus",
     "Une **ligne** est un itinéraire régulier entre deux terminus, composé de stations d'arrêt. "
     "Chaque tournée est rattachée à une ligne. Les lignes ont une direction aller et retour."),
    (r"station",
     "Une **station** est un point d'arrêt sur une ligne de transport. "
     "L'ERP gère 54 stations réparties en Tunisie avec leur ville et type (intermédiaire/terminus)."),
    # Véhicules
    (r"bus|véhicule|parc",
     "Le **parc de bus** regroupe tous les véhicules de l'entreprise. "
     "Chaque bus a une immatriculation, un état (En service / Hors service / Réformé), "
     "et est suivi en assurance, tournées, et kilométrage."),
    (r"sinistre|accident",
     "Un **sinistre** est un incident impliquant un bus (accident, dommage). "
     "Il est enregistré avec la date, le véhicule concerné, et les détails du dommage."),
    # Assurance
    (r"assurance|police d'assurance",
     "L'**assurance bus** couvre les véhicules du parc. "
     "États : ✅ Active / ❌ Expirée / 🚫 Résiliée. "
     "Chaque police a une date de début, date de fin, et est liée à un bus spécifique."),
    # Patrimoine
    (r"patrimoine|immobilisation|amortissement",
     "Le module **Patrimoine** gère les immobilisations de l'entreprise (équipements, bâtiments, véhicules). "
     "Chaque immobilisation a un coût d'acquisition, une durée d'amortissement, "
     "une valeur nette comptable, et peut être cédée ou inventoriée."),
    # Énergie
    (r"steg|sonede|facture.*(énergie|energie|eau|électricité)",
     "Les **factures énergie** (STEG pour l'électricité, SONEDE pour l'eau) "
     "sont saisies dans le module Énergie. "
     "États : 📝 Saisie → ✔️ Validée → ✅ Payée. "
     "Chaque facture indique le site, le compteur, la quantité et le montant."),
    # BOC
    (r"boc|courrier|bureau d'ordre",
     "Le **BOC** (Bureau d'Ordre Central) gère les courriers entrants (arrivée) "
     "et sortants (départ). Chaque courrier a un numéro de référence, un sujet, "
     "un expéditeur/destinataire, et un état (Enregistré → Classé)."),
    # États
    (r"état|etat|statut|workflow",
     "**États principaux dans l'ERP :\n**"
     "• Tournée : Brouillon → Planifiée → En cours → Réalisée / Annulée\n"
     "• Assurance : Active / Expirée / Résiliée\n"
     "• Facture énergie : Saisie → Validée → Payée\n"
     "• Bus : En service / Hors service / Réformé\n"
     "• Courrier : Enregistré → Classé"),
    # Lubrifiant
    (r"lubrifiant|huile",
     "Le module **Lubrifiant** gère les bons de lubrifiant et le stock en dépôt. "
     "Les bons sont émis pour l'entretien des bus et déduisent du stock disponible."),
]

_RAG_DEFAUT = (
    "Je n'ai pas trouvé d'information sur ce sujet dans la base de connaissances. "
    "Vous pouvez alimenter la base via l'interface d'administration ou reformuler votre question."
)


def _reponse_rag_statique(question: str) -> str:
    """Retourne une réponse statique pour les questions de définition fréquentes."""
    q = question.lower()
    for pattern, reponse in _RAG_STATIQUE:
        if re.search(pattern, q):
            return reponse
    return _RAG_DEFAUT


# ---------------------------------------------------------------------------
# PIPELINE RPC 2 ÉTAPES — résoudre référence puis appeler le bouton
# ---------------------------------------------------------------------------


def _resoudre_id_par_sql(modele_odoo: str, ref: str) -> int:
    """Résout une référence Odoo en ID via SQL direct — zéro LLM."""
    TABLE_MAP = {
        "transport.exploitation.tournee": ("transport_exploitation_tournee", "name"),
        "boc.courrier.arrivee":           ("boc_courrier_arrivee",           "name"),
        "boc.courrier.depart":            ("boc_courrier_depart",            "name"),
        "transport.fuel.voucher":         ("transport_fuel_voucher",         "name"),
        "transport.facture.energie":      ("transport_facture_energie",      "name"),
        "patrimoine.immobilisation":      ("patrimoine_immobilisation",      "name"),
        "transport.assurance.bus":        ("transport_assurance_bus",        "numero_police"),
        "transport.assurance.sinistre":   ("transport_assurance_sinistre",   "name"),
        "patrimoine.cession":             ("patrimoine_cession",             "name"),
    }
    if modele_odoo not in TABLE_MAP:
        return None
    table, col = TABLE_MAP[modele_odoo]
    try:
        conn = get_pg_connection()
        cur  = conn.cursor()
        cur.execute("SELECT id FROM " + table + " WHERE " + col + " = %s LIMIT 1", (ref,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        _logger.warning(f"_resoudre_id_par_sql erreur: {e}")
        return None


def _detecter_intention(question: str) -> tuple:
    """Détecte l'intention d'écriture sans LLM."""
    import unicodedata
    q = question.lower()
    q_norm = unicodedata.normalize("NFD", q)
    q_norm = "".join(c for c in q_norm if unicodedata.category(c) != "Mn")
    for mots_cles, methode_odoo, modele_defaut in INTENTIONS_ECRITURE:
        if any(mot in q or mot in q_norm for mot in mots_cles):
            return methode_odoo, modele_defaut
    return None, None


def _extraire_ref_sql(question: str) -> str:
    """Extrait la référence Odoo (ex: TOURN/2026/00020)."""
    m = re.search(r"[A-Z][A-Z0-9\-]*/\d{4}/\d+", question, re.IGNORECASE)
    return m.group(0).upper() if m else ""


def _extraire_ids_question(question: str) -> list:
    """Extrait les IDs numériques bruts (ex: 'id 42')."""
    matches = re.findall(r"(?:id[:\s#]+)(\d+)", question.lower())
    return [int(x) for x in matches] if matches else []


def _executer_rpc(question: str, llm, allowed_tables: list, is_admin: bool, session_id: str = "default") -> str:
    """
    Pipeline RPC sans LLM — résolution SQL directe.
    Étape 1: détection intention Python pur (< 1ms)
    Étape 2: résolution ID via PostgreSQL (< 10ms)
    Étape 3: appel bouton Odoo XML-RPC
    Total: < 15s au lieu de 90s+
    """
    import json as _json

    methode_cible, modele_cible = _detecter_intention(question)
    ref       = _extraire_ref_sql(question)
    ids_bruts = _extraire_ids_question(question)

    _logger.info(f"RPC: methode={methode_cible} modele={modele_cible} ref={ref} ids={ids_bruts}")
    print(f"  -> RPC: {methode_cible} | {modele_cible} | ref={ref} | ids={ids_bruts}")

    # Pas d intention → lecture SQL
    if not methode_cible:
        requete = generer_sql(question, llm, allowed_tables, is_admin)
        donnees = sql_tool.invoke(requete)
        return formuler_reponse(question, donnees, llm, "fr")

    # CREATE
    if methode_cible == "create":
        import datetime
        defaults = {
            "transport.exploitation.tournee": {
                "date": str(datetime.date.today()), "state": "brouillon"},
            "transport.assurance.bus": {"state": "brouillon"},
            "transport.fuel.voucher": {"state": "draft", "voucher_type": "internal"},
        }
        valeurs = defaults.get(modele_cible, {})
        action  = modele_cible + "|create|" + _json.dumps(valeurs, ensure_ascii=False)
        donnees = rpc_tool.invoke(action)
        return donnees if donnees and "Erreur" not in donnees else "Création effectuée."

    # WRITE bus état
    if methode_cible == "write" and modele_cible == "fleet.vehicle":
        q = question.lower()
        # IDs reels fleet.vehicle.state : 47=En service, 48=Hors service, 5=En panne, 6=En maintenance
        if any(w in q for w in ["hors service", "immobiliser"]):
            etat_id = 48
        elif any(w in q for w in ["en panne", "panne"]):
            etat_id = 5
        elif any(w in q for w in ["maintenance", "en maintenance"]):
            etat_id = 6
        elif any(w in q for w in ["en service", "remettre en service"]):
            etat_id = 47
        else:
            etat_id = 47
        ids = ids_bruts[:]

        # Résolution par immatriculation si pas d'IDs numériques
        if not ids:
            import re as _re_immat
            m_immat = _re_immat.search(
                r'(?<![a-zA-Z])(\d{1,4}\s+[a-zA-Z]{1,3}\s+\d{2,4})',
                question, _re_immat.IGNORECASE
            )
            if m_immat:
                plaque = m_immat.group(0).strip()
                action_search = 'fleet.vehicle|search_read|[["license_plate","ilike","' + plaque + '"]]|["id","name","license_plate"]'
                res_search = rpc_tool.invoke(action_search)
                id_matches = _re_immat.findall(r'\[(\d+)\]', res_search)
                ids = [int(i) for i in id_matches] if id_matches else []

        # Ajouter "remet en service" dans les mots clés détectés
        if any(w in question.lower() for w in ["remet en service", "remets en service"]) and etat_id != 47:
            etat_id = 47

        if ids:
            etat_val = '{"state_id":' + str(etat_id) + "}"
            action   = "fleet.vehicle|write|" + _json.dumps(ids) + "|" + etat_val
            donnees  = rpc_tool.invoke(action)
            return donnees if donnees and "Erreur" not in donnees else "État du bus modifié."
        return "Bus introuvable. Précise l'immatriculation exacte (ex: 'Mets le bus 158 tu 2026 en service')."

    # WRITE affecter chauffeur/bus sur une tournée
    if methode_cible == "write" and modele_cible == "transport.exploitation.tournee":
        import re as _re2
        q = question.lower()  # définir q localement
        import unicodedata as _ud
        q_norm = _ud.normalize("NFD", q)
        q_norm = "".join(c for c in q_norm if _ud.category(c) != "Mn")
        # Chercher nom chauffeur dans la question
        ids_tournee = ids_bruts[:]
        # Résoudre ref depuis la question
        if not ids_tournee and ref:
            id_sql = _resoudre_id_par_sql(modele_cible, ref)
            if id_sql:
                ids_tournee = [id_sql]
        # Fallback : chercher ref dans le contexte conversationnel
        if not ids_tournee:
            ctx = _extraire_contexte_session(session_id)
            print(f"  -> Contexte session: ref={ctx['derniere_ref']} modele={ctx['dernier_modele']}")
            if ctx["derniere_ref"] and (ctx["dernier_modele"] is None or ctx["dernier_modele"] == modele_cible):
                id_sql = _resoudre_id_par_sql(modele_cible, ctx["derniere_ref"])
                if id_sql:
                    ids_tournee = [id_sql]
                    print(f"  -> ID depuis contexte session: {id_sql} (ref={ctx['derniere_ref']})")
        if ids_tournee:
            vals = {}
            # Chercher chauffeur par nom — recherche dynamique dans la base
            try:
                conn_tmp = get_pg_connection()
                cur_tmp = conn_tmp.cursor()
                # Récupérer tous les chauffeurs actifs
                cur_tmp.execute(
                    "SELECT id, name FROM hr_employee WHERE active=true ORDER BY name"
                )
                employes = cur_tmp.fetchall()
                conn_tmp.close()
                # Chercher lequel est mentionné dans la question
                for emp_id, emp_name in employes:
                    if emp_name.lower() in q or any(
                        part.lower() in q
                        for part in emp_name.split()
                        if len(part) > 2
                    ):
                        vals["chauffeur_id"] = emp_id
                        print(f"  -> Chauffeur trouvé: {emp_name} (ID={emp_id})")
                        break
            except Exception as e_emp:
                _logger.warning(f"Recherche chauffeur échouée: {e_emp}")
            if vals:
                action = modele_cible + "|write|" + _json.dumps(ids_tournee) + "|" + _json.dumps(vals, ensure_ascii=False)
                donnees = rpc_tool.invoke(action)
                return donnees if donnees and "Erreur" not in donnees else "Affectation effectuée."
            else:
                return "Précise le nom du chauffeur à affecter."
        return "Précise la référence de la tournée (ex: TOURN/2026/00018)."

    # WRITE facture payée
    if methode_cible == "write" and modele_cible == "transport.facture.energie":
        ids = ids_bruts[:]
        if not ids and ref:
            id_sql = _resoudre_id_par_sql(modele_cible, ref)
            if id_sql:
                ids = [id_sql]
        if ids:
            action  = modele_cible + "|write|" + _json.dumps(ids) + '|{"statut":"payee"}'
            donnees = rpc_tool.invoke(action)
            return donnees if donnees and "Erreur" not in donnees else "Facture marquée payée."
        return "Référence facture non trouvée."

    # BOUTON WORKFLOW — résolution SQL directe
    ids = ids_bruts[:]
    if not ids and ref:
        id_sql = _resoudre_id_par_sql(modele_cible, ref)
        if id_sql:
            ids = [id_sql]
            print(f"  -> ID résolu SQL: {id_sql} (ref={ref})")
        else:
            return "Aucun enregistrement trouvé pour '" + ref + "'. Vérifiez la référence."

    if not ids:
        # Fallback : chercher dans le contexte conversationnel
        ctx = _extraire_contexte_session(session_id)
        if ctx["derniere_ref"] and (
            not ctx["dernier_modele"] or ctx["dernier_modele"] == modele_cible
        ):
            id_sql = _resoudre_id_par_sql(modele_cible, ctx["derniere_ref"])
            if id_sql:
                ids = [id_sql]
                print(f"  -> ID depuis contexte session: {id_sql} (ref={ctx['derniere_ref']})")

    if not ids:
        ctx = _extraire_contexte_session(session_id)
        ref_ctx = ctx.get("derniere_ref", "?")
        hint = f" Dernière référence : {ref_ctx}" if ref_ctx and ref_ctx != "?" else ""
        return "Précise la référence de l'enregistrement à modifier." + hint

    action  = modele_cible + "|" + methode_cible + "|" + _json.dumps(ids)
    print(f"  -> Action bouton: {action}")
    donnees = rpc_tool.invoke(action)

    if not donnees or not donnees.strip():
        return "Action '" + methode_cible + "' exécutée avec succès."
    if "Erreur RPC" in donnees and "Action impossible" not in donnees:
        _logger.warning(f"RPC bouton échoué: {donnees[:100]}")
        requete = generer_sql(question, llm, allowed_tables, is_admin)
        donnees = sql_tool.invoke(requete)
        return formuler_reponse(question, donnees, llm, "fr")
    return donnees



# ---------------------------------------------------------------------------
# CONTEXTE CONVERSATIONNEL — extraction de la tournée/référence précédente
# ---------------------------------------------------------------------------

def _extraire_contexte_session(session_id: str) -> dict:
    """
    Analyse le contexte actif — utilise d'abord le cache RAM (synchrone),
    puis l'historique SQLite en fallback.
    """
    import re as _re
    contexte = {
        "derniere_ref": None,
        "derniere_erreur": None,
        "dernier_modele": None,
        "derniere_action_echouee": None,
    }

    # Priorité 1 : cache RAM (immédiat, toujours à jour)
    if session_id in _SESSION_CONTEXT:
        ctx_ram = _SESSION_CONTEXT[session_id]
        contexte["derniere_ref"]    = ctx_ram.get("ref")
        contexte["dernier_modele"]  = ctx_ram.get("modele")
        contexte["derniere_erreur"] = ctx_ram.get("erreur")
        if contexte["derniere_ref"]:
            print(f"  -> Contexte RAM trouvé: ref={contexte['derniere_ref']}")
            return contexte  # Retour immédiat sans SQLite

    # Mapping préfixe → modèle
    PREFIXES = {
        "TOURN": "transport.exploitation.tournee",
        "POL-BUS": "transport.assurance.bus",
        "POL-CHAUF": "transport.assurance.chauffeur",
        "ARR": "boc.courrier.arrivee",
        "DEP": "boc.courrier.depart",
        "BGI": "transport.fuel.voucher",
        "BGE": "transport.fuel.voucher",
        "STEG": "transport.facture.energie",
        "SONEDE": "transport.facture.energie",
        "IMM": "patrimoine.immobilisation",
        "CES": "patrimoine.cession",
        "SIN": "transport.assurance.sinistre",
    }

    try:
        historique = charger_historique(session_id, limite=5)
        for role, contenu in historique:
            # Chercher une référence Odoo
            m = _re.search(r"[A-Z][A-Z0-9\-]*/\d{4}/\d+", contenu, _re.IGNORECASE)
            if m and not contexte["derniere_ref"]:
                ref = m.group(0).upper()
                contexte["derniere_ref"] = ref
                # Déduire le modèle depuis le préfixe
                for prefix, modele in PREFIXES.items():
                    if ref.startswith(prefix):
                        contexte["dernier_modele"] = modele
                        break

            # Détecter les erreurs métier dans les réponses assistant
            if role == "assistant":
                erreurs_metier = [
                    "Veuillez affecter un véhicule",
                    "Veuillez affecter un chauffeur",
                    "Veuillez saisir le compteur",
                    "Veuillez sélectionner un motif",
                    "Bus non assuré",
                    "Conflit de disponibilité",
                    "Statut patrimoine",
                    "Stock insuffisant",
                    "doit être confirmé avant",
                    "Impossible de confirmer",
                    "Action impossible",
                ]
                for err in erreurs_metier:
                    if err in contenu and not contexte["derniere_erreur"]:
                        contexte["derniere_erreur"] = err
                        contexte["derniere_action_echouee"] = contenu[:200]
                        break

    except Exception as e:
        _logger.warning(f"_extraire_contexte_session erreur: {e}")

    return contexte



def _enrichir_question(question: str, session_id: str) -> str:
    """
    Enrichit la question avec le contexte de la conversation précédente.
    Couvre tous les modules : tournée, assurance, carburant, BOC, patrimoine.
    """
    import re as _re
    q = question.lower()

    # Si la question contient déjà une référence → pas besoin d'enrichir
    if _re.search(r"[A-Z][A-Z0-9\-]*/\d{4}/\d+", question, _re.IGNORECASE):
        return question

    # Mots-clés qui suggèrent un contexte implicite
    mots_contexte = [
        # Chauffeur / bus
        "chauffeur disponible", "chauffeurs disponibles", "qui peut conduire",
        "affecter", "assigner", "attribuer",
        # Actions sans référence
        "planifie", "planifier", "demarrer", "démarrer", "terminer",
        "annuler", "confirmer", "valider",
        "activer", "résilier", "resilier",
        "classer", "traiter", "diffuser",
        "payer", "mettre en service", "mettre hors service",
        # Contexte implicite
        "et pour", "et la", "et le", "même", "ce bus", "cette tournée",
        "cette police", "ce courrier", "ce bon", "cette facture",
        "pour ça", "pour ca", "pour cette", "pour ce",
    ]

    if any(mot in q for mot in mots_contexte):
        # Priorité 1 : cache RAM (synchrone, toujours à jour)
        ref = None
        if session_id in _SESSION_CONTEXT:
            ref = _SESSION_CONTEXT[session_id].get("ref")
            if ref:
                print(f"  -> Enrichissement depuis RAM: ref={ref}")

        # Priorité 2 : historique SQLite
        if not ref:
            contexte = _extraire_contexte_session(session_id)
            ref = contexte.get("derniere_ref")

        if ref:
            _logger.info(f"Enrichissement question avec ref: {ref}")
            question_enrichie = question.rstrip("?").rstrip() + f" la tournée {ref} ?" \
                if any(w in q for w in ["planifie","demarrer","terminer","annuler","confirmer"]) \
                else question.rstrip("?").rstrip() + f" pour {ref} ?"
            return question_enrichie

    return question




# ---------------------------------------------------------------------------
# GÉNÉRATION DE SYNTHÈSES ET RAPPORTS
# ---------------------------------------------------------------------------

TEMPLATES_RAPPORTS = {

    # ─────────────────────────────────────────────────────────────────────────
    # EXPLOITATION — JOURNALIER
    # ─────────────────────────────────────────────────────────────────────────
    "rapport_journalier": {
        "label": "Rapport journalier d'exploitation",
        "labels": {"fr": "Rapport journalier d'exploitation", "en": "Daily Operations Report", "ar": "التقرير اليومي للاستغلال"},
        "requetes": {
            "tournees_planifiees": "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date = CURRENT_DATE AND state = 'planifie'",
            "tournees_en_cours":   "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date = CURRENT_DATE AND state = 'en_cours'",
            "tournees_realisees":  "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date = CURRENT_DATE AND state = 'realise'",
            "tournees_annulees":   "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date = CURRENT_DATE AND state = 'annule'",
            "km_total":            "SELECT COALESCE(SUM(km_realise),0) FROM transport_exploitation_tournee WHERE date = CURRENT_DATE AND state = 'realise'",
            "ecart_moyen":         "SELECT COALESCE(ROUND(AVG(ecart_km)::numeric,1),0) FROM transport_exploitation_tournee WHERE date = CURRENT_DATE AND state = 'realise'",
            # Detail tournees du jour — name jsonb pour ligne, agence, motif
            "detail_tournees": (
                "SELECT t.name AS tournee, "
                "COALESCE(l.name->>'fr_FR', l.name->>'en_US', l.name::text) AS ligne, "
                "e.name AS chauffeur, v.license_plate AS bus, "
                "t.direction, t.state, "
                "t.heure_depart_reel, t.heure_arrivee_reel, "
                "t.km_realise, t.ecart_km "
                "FROM transport_exploitation_tournee t "
                "LEFT JOIN transport_exploitation_ligne l ON t.ligne_id = l.id "
                "LEFT JOIN hr_employee e ON t.chauffeur_id = e.id "
                "LEFT JOIN fleet_vehicle v ON t.vehicle_id = v.id "
                "WHERE t.date = CURRENT_DATE "
                "ORDER BY t.state, t.heure_depart_reel"
            ),
            "detail_annulees": (
                "SELECT t.name AS tournee, "
                "COALESCE(l.name->>'fr_FR', l.name->>'en_US') AS ligne, "
                "e.name AS chauffeur, "
                "COALESCE(m.name->>'fr_FR', m.name->>'en_US') AS motif, "
                "t.note_annulation "
                "FROM transport_exploitation_tournee t "
                "LEFT JOIN transport_exploitation_ligne l ON t.ligne_id = l.id "
                "LEFT JOIN hr_employee e ON t.chauffeur_id = e.id "
                "LEFT JOIN transport_exploitation_motif m ON t.motif_annulation_id = m.id "
                "WHERE t.date = CURRENT_DATE AND t.state = 'annule'"
            ),
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # EXPLOITATION — HEBDOMADAIRE
    # ─────────────────────────────────────────────────────────────────────────
    "rapport_hebdomadaire": {
        "label": "Rapport hebdomadaire d'exploitation",
        "labels": {"fr": "Rapport hebdomadaire d'exploitation", "en": "Weekly Operations Report", "ar": "التقرير الأسبوعي للاستغلال"},
        "requetes": {
            "tournees_realisees": "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'realise'",
            "tournees_annulees":  "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'annule'",
            "tournees_total":     "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days'",
            "km_total":           "SELECT COALESCE(SUM(km_realise),0) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'realise'",
            "ecart_moyen":        "SELECT COALESCE(ROUND(AVG(ecart_km)::numeric,1),0) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'realise'",
            "top_chauffeurs": (
                "SELECT e.name AS chauffeur, COUNT(*) AS nb_tournees, "
                "COALESCE(SUM(t.km_realise),0) AS km_total "
                "FROM transport_exploitation_tournee t "
                "JOIN hr_employee e ON t.chauffeur_id = e.id "
                "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'realise' "
                "GROUP BY e.name ORDER BY nb_tournees DESC LIMIT 5"
            ),
            "km_par_bus": (
                "SELECT v.name AS bus, v.license_plate, "
                "COUNT(*) AS nb_tournees, COALESCE(SUM(t.km_realise),0) AS km "
                "FROM transport_exploitation_tournee t "
                "JOIN fleet_vehicle v ON t.vehicle_id = v.id "
                "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'realise' "
                "GROUP BY v.name, v.license_plate ORDER BY km DESC"
            ),
            "annulations_motif": (
                "SELECT COALESCE(m.name->>'fr_FR', m.name->>'en_US', 'Sans motif') AS motif, "
                "COUNT(*) AS nb "
                "FROM transport_exploitation_tournee t "
                "LEFT JOIN transport_exploitation_motif m ON t.motif_annulation_id = m.id "
                "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'annule' "
                "GROUP BY m.name ORDER BY nb DESC"
            ),
            "activite_lignes": (
                "SELECT COALESCE(l.name->>'fr_FR', l.name->>'en_US') AS ligne, "
                "COUNT(*) AS nb_tournees, COALESCE(SUM(t.km_realise),0) AS km_total "
                "FROM transport_exploitation_tournee t "
                "JOIN transport_exploitation_ligne l ON t.ligne_id = l.id "
                "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'realise' "
                "GROUP BY l.name ORDER BY nb_tournees DESC LIMIT 5"
            ),
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # EXPLOITATION — MENSUEL
    # ─────────────────────────────────────────────────────────────────────────
    "rapport_mensuel": {
        "label": "Rapport mensuel d'exploitation",
        "labels": {"fr": "Rapport mensuel d'exploitation", "en": "Monthly Operations Report", "ar": "التقرير الشهري للاستغلال"},
        "requetes": {
            "tournees_realisees": "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE) AND state='realise'",
            "tournees_annulees":  "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE) AND state='annule'",
            "tournees_total":     "SELECT COUNT(*) FROM transport_exploitation_tournee WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "km_total":           "SELECT COALESCE(SUM(km_realise),0) FROM transport_exploitation_tournee WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE) AND state='realise'",
            "ecart_moyen":        "SELECT COALESCE(ROUND(AVG(ecart_km)::numeric,1),0) FROM transport_exploitation_tournee WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE) AND state='realise'",
            "top_chauffeurs": (
                "SELECT e.name AS chauffeur, COUNT(*) AS nb_tournees, "
                "COALESCE(SUM(t.km_realise),0) AS km_total "
                "FROM transport_exploitation_tournee t "
                "JOIN hr_employee e ON t.chauffeur_id = e.id "
                "WHERE EXTRACT(MONTH FROM t.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM t.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "AND t.state='realise' "
                "GROUP BY e.name ORDER BY nb_tournees DESC LIMIT 5"
            ),
            "km_par_bus": (
                "SELECT v.name AS bus, v.license_plate, "
                "COUNT(*) AS nb_tournees, COALESCE(SUM(t.km_realise),0) AS km "
                "FROM transport_exploitation_tournee t "
                "JOIN fleet_vehicle v ON t.vehicle_id = v.id "
                "WHERE EXTRACT(MONTH FROM t.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM t.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "AND t.state='realise' "
                "GROUP BY v.name, v.license_plate ORDER BY km DESC"
            ),
            "annulations_motif": (
                "SELECT COALESCE(m.name->>'fr_FR', m.name->>'en_US', 'Sans motif') AS motif, "
                "COUNT(*) AS nb "
                "FROM transport_exploitation_tournee t "
                "LEFT JOIN transport_exploitation_motif m ON t.motif_annulation_id = m.id "
                "WHERE EXTRACT(MONTH FROM t.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM t.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "AND t.state='annule' "
                "GROUP BY m.name ORDER BY nb DESC"
            ),
            "activite_lignes": (
                "SELECT COALESCE(l.name->>'fr_FR', l.name->>'en_US') AS ligne, "
                "COUNT(*) AS nb_tournees, COALESCE(SUM(t.km_realise),0) AS km_total "
                "FROM transport_exploitation_tournee t "
                "JOIN transport_exploitation_ligne l ON t.ligne_id = l.id "
                "WHERE EXTRACT(MONTH FROM t.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM t.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "AND t.state='realise' "
                "GROUP BY l.name ORDER BY nb_tournees DESC"
            ),
            "repartition_direction": (
                "SELECT direction, COUNT(*) AS nb "
                "FROM transport_exploitation_tournee "
                "WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "AND state='realise' GROUP BY direction"
            ),
            "recettes_mois": (
                "SELECT COALESCE(SUM(recette_reelle),0) AS recette_reelle, "
                "COALESCE(SUM(recette_prevue),0) AS recette_prevue "
                "FROM transport_exploitation_tournee "
                "WHERE EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "AND state='realise'"
            ),
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PARC BUS
    # fleet_vehicle_state.name → jsonb
    # ─────────────────────────────────────────────────────────────────────────
    "bilan_parc": {
        "label": "Synthese etat du parc bus",
        "labels": {"fr": "Synthese etat du parc bus", "en": "Fleet Status Summary", "ar": "ملخص حالة الأسطول"},
        "requetes": {
            "total_bus":        "SELECT COUNT(*) FROM fleet_vehicle WHERE active = True",
            "en_service":       "SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 47",
            "hors_service":     "SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 48",
            "en_panne":         "SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 5",
            "en_maintenance":   "SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 6",
            "polices_actives":  "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='active'",
            "polices_alerte":   "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='alerte'",
            "polices_expirees": "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='expirée'",
            # fleet_vehicle_state.name est jsonb
            "detail_bus": (
                "SELECT v.name AS bus, v.license_plate AS immatriculation, "
                "COALESCE(s.name->>'fr_FR', s.name->>'en_US', s.name::text) AS etat, "
                "a.numero_police, "
                "TO_CHAR(a.date_fin,'DD/MM/YYYY') AS expiration_police, "
                "c.name AS compagnie, "
                "COALESCE(SUM(t.km_realise),0) AS km_mois "
                "FROM fleet_vehicle v "
                "LEFT JOIN fleet_vehicle_state s ON v.state_id = s.id "
                "LEFT JOIN transport_assurance_bus a ON a.vehicle_id = v.id AND a.state = 'active' "
                "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
                "LEFT JOIN transport_exploitation_tournee t "
                "  ON t.vehicle_id = v.id AND t.state = 'realise' "
                "  AND EXTRACT(MONTH FROM t.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "  AND EXTRACT(YEAR FROM t.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "WHERE v.active = True "
                "GROUP BY v.name, v.license_plate, s.name, "
                "a.numero_police, a.date_fin, c.name "
                "ORDER BY v.name"
            ),
            "bus_sans_assurance": (
                "SELECT v.name AS bus, v.license_plate, "
                "COALESCE(s.name->>'fr_FR', s.name->>'en_US', s.name::text) AS etat "
                "FROM fleet_vehicle v "
                "LEFT JOIN fleet_vehicle_state s ON v.state_id = s.id "
                "LEFT JOIN transport_assurance_bus a ON a.vehicle_id = v.id AND a.state = 'active' "
                "WHERE a.id IS NULL AND v.active = True"
            ),
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # ASSURANCE
    # transport_assurance_sinistre : employe_id (pas chauffeur_id)
    #   montant_reclame, montant_accorde, montant_net_verse, franchise_appliquee
    # transport_assurance_type.name : jsonb
    # transport_assurance_chauffeur : employe_id (pas chauffeur_id)
    # ─────────────────────────────────────────────────────────────────────────
    "bilan_assurance": {
        "label": "Bilan mensuel assurance et sinistres",
        "labels": {"fr": "Bilan mensuel assurance et sinistres", "en": "Monthly Insurance & Claims Report", "ar": "بيان التأمين والحوادث الشهري"},
        "requetes": {
            "polices_actives":   "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='active'",
            "polices_alerte":    "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='alerte'",
            "polices_expirees":  "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='expirée'",
            "polices_resiliees": "SELECT COUNT(*) FROM transport_assurance_bus WHERE state='résiliée'",
            "sinistres_mois": (
                "SELECT COUNT(*) FROM transport_assurance_sinistre "
                "WHERE EXTRACT(MONTH FROM date_sinistre)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM date_sinistre)=EXTRACT(YEAR FROM CURRENT_DATE)"
            ),
            "montant_sinistres": (
                "SELECT COALESCE(SUM(montant_accorde),0) FROM transport_assurance_sinistre "
                "WHERE EXTRACT(MONTH FROM date_sinistre)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM date_sinistre)=EXTRACT(YEAR FROM CURRENT_DATE)"
            ),
            "montant_net_verse": (
                "SELECT COALESCE(SUM(montant_net_verse),0) FROM transport_assurance_sinistre "
                "WHERE EXTRACT(MONTH FROM date_sinistre)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM date_sinistre)=EXTRACT(YEAR FROM CURRENT_DATE)"
            ),
            # type_police name est jsonb
            "detail_polices_actives": (
                "SELECT a.numero_police, "
                "COALESCE(tp.name->>'en_US', tp.name->>'fr_FR', tp.code) AS type_police, "
                "c.name AS compagnie, v.name AS bus, v.license_plate, "
                "TO_CHAR(a.date_debut,'DD/MM/YYYY') AS date_debut, "
                "TO_CHAR(a.date_fin,'DD/MM/YYYY') AS date_fin, "
                "a.prime_annuelle, "
                "CASE WHEN a.is_obligatoire THEN 'Oui' ELSE 'Non' END AS obligatoire "
                "FROM transport_assurance_bus a "
                "LEFT JOIN fleet_vehicle v ON a.vehicle_id = v.id "
                "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
                "LEFT JOIN transport_assurance_type tp ON a.type_police_id = tp.id "
                "WHERE a.state = 'active' ORDER BY a.date_fin ASC"
            ),
            # employe_id (pas chauffeur_id), montant_accorde (pas montant_dommage)
            "detail_sinistres": (
                "SELECT s.name AS reference, s.state, "
                "TO_CHAR(s.date_sinistre,'DD/MM/YYYY') AS date_sinistre, "
                "s.nature_sinistre, s.lieu, "
                "s.montant_reclame, s.montant_accorde, s.montant_net_verse, "
                "v.name AS bus, v.license_plate, "
                "e.name AS chauffeur, "
                "LEFT(s.description,60) AS description "
                "FROM transport_assurance_sinistre s "
                "LEFT JOIN fleet_vehicle v ON s.vehicle_id = v.id "
                "LEFT JOIN hr_employee e ON s.employe_id = e.id "
                "WHERE EXTRACT(MONTH FROM s.date_sinistre)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM s.date_sinistre)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "ORDER BY s.date_sinistre DESC"
            ),
            "expiration_30j": (
                "SELECT a.numero_police, "
                "COALESCE(tp.name->>'en_US', tp.name->>'fr_FR', tp.code) AS type_police, "
                "c.name AS compagnie, v.name AS bus, "
                "TO_CHAR(a.date_fin,'DD/MM/YYYY') AS date_fin, "
                "a.prime_annuelle, "
                "CASE WHEN a.is_obligatoire THEN 'Oui' ELSE 'Non' END AS obligatoire "
                "FROM transport_assurance_bus a "
                "LEFT JOIN fleet_vehicle v ON a.vehicle_id = v.id "
                "LEFT JOIN transport_assurance_compagnie c ON a.compagnie_id = c.id "
                "LEFT JOIN transport_assurance_type tp ON a.type_police_id = tp.id "
                "WHERE a.state = 'active' "
                "AND a.date_fin <= CURRENT_DATE + INTERVAL '30 days' "
                "ORDER BY a.date_fin ASC"
            ),
            # employe_id (pas chauffeur_id)
            "assurances_chauffeurs": (
                "SELECT sc.numero_police, e.name AS chauffeur, "
                "COALESCE(tp.name->>'en_US', tp.name->>'fr_FR', tp.code) AS type_police, "
                "sc.state, "
                "TO_CHAR(sc.date_debut,'DD/MM/YYYY') AS date_debut, "
                "TO_CHAR(sc.date_fin,'DD/MM/YYYY') AS date_fin, "
                "cmp.name AS compagnie, sc.prime_annuelle, "
                "CASE WHEN sc.is_obligatoire THEN 'Oui' ELSE 'Non' END AS obligatoire "
                "FROM transport_assurance_chauffeur sc "
                "LEFT JOIN hr_employee e ON sc.employe_id = e.id "
                "LEFT JOIN transport_assurance_compagnie cmp ON sc.compagnie_id = cmp.id "
                "LEFT JOIN transport_assurance_type tp ON sc.type_police_id = tp.id "
                "ORDER BY sc.date_fin ASC LIMIT 10"
            ),
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CARBURANT
    # transport_fuel_voucher n'a PAS de vehicle_id direct
    # vehicle_id est dans transport_fuel_voucher_line
    # total_cost existe dans transport_fuel_voucher
    # ─────────────────────────────────────────────────────────────────────────
    "bilan_carburant": {
        "label": "Rapport mensuel consommation carburant",
        "labels": {"fr": "Rapport mensuel consommation carburant", "en": "Monthly Fuel Consumption Report", "ar": "تقرير استهلاك الوقود الشهري"},
        "requetes": {
            "bons_valides": "SELECT COUNT(*) FROM transport_fuel_voucher WHERE state='done' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "litres_total": "SELECT COALESCE(SUM(total_quantity),0) FROM transport_fuel_voucher WHERE state='done' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "bgi_count":    "SELECT COUNT(*) FROM transport_fuel_voucher WHERE state='done' AND voucher_type='internal' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "bge_count":    "SELECT COUNT(*) FROM transport_fuel_voucher WHERE state='done' AND voucher_type='external' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "litres_bgi":   "SELECT COALESCE(SUM(total_quantity),0) FROM transport_fuel_voucher WHERE state='done' AND voucher_type='internal' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "litres_bge":   "SELECT COALESCE(SUM(total_quantity),0) FROM transport_fuel_voucher WHERE state='done' AND voucher_type='external' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "cout_total":   "SELECT COALESCE(SUM(total_cost),0) FROM transport_fuel_voucher WHERE state='done' AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM CURRENT_DATE)",
            # vehicle via fuel_voucher_line
            "litres_par_bus": (
                "SELECT v.name AS bus, v.license_plate, "
                "COUNT(DISTINCT f.id) AS nb_bons, "
                "COALESCE(SUM(CASE WHEN f.voucher_type='internal' THEN fl.quantity ELSE 0 END),0) AS litres_bgi, "
                "COALESCE(SUM(CASE WHEN f.voucher_type='external' THEN fl.quantity ELSE 0 END),0) AS litres_bge, "
                "COALESCE(SUM(fl.quantity),0) AS total_litres "
                "FROM transport_fuel_voucher f "
                "JOIN transport_fuel_voucher_line fl ON fl.voucher_id = f.id "
                "JOIN fleet_vehicle v ON fl.vehicle_id = v.id "
                "WHERE f.state='done' "
                "AND EXTRACT(MONTH FROM f.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM f.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "GROUP BY v.name, v.license_plate ORDER BY total_litres DESC"
            ),
            "detail_bons_recents": (
                "SELECT f.name AS reference, "
                "CASE WHEN f.voucher_type='internal' THEN 'BGI' ELSE 'BGE' END AS type, "
                "TO_CHAR(f.date,'DD/MM/YYYY') AS date_bon, "
                "f.total_quantity AS litres, "
                "COALESCE(f.total_cost,0) AS cout_tnd "
                "FROM transport_fuel_voucher f "
                "WHERE f.state='done' "
                "AND EXTRACT(MONTH FROM f.date)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM f.date)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "ORDER BY f.date DESC LIMIT 10"
            ),
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # COURRIER BOC
    # boc_courrier_arrivee : expediteur_nom (jsonb, pas expediteur)
    #                        date_arrivee (timestamp)
    #                        en_retard (boolean calculé)
    # boc_courrier_depart  : date_depart (pas date_envoi)
    # ─────────────────────────────────────────────────────────────────────────
    "bilan_boc": {
        "label": "Synthese courrier BOC",
        "labels": {"fr": "Synthese courrier BOC", "en": "BOC Mail Summary", "ar": "ملخص بريد مكتب الضبط"},
        "requetes": {
            "total_arrivee": "SELECT COUNT(*) FROM boc_courrier_arrivee WHERE EXTRACT(MONTH FROM date_arrivee)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date_arrivee)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "en_attente":    "SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state IN ('enregistre','diffuse') AND EXTRACT(MONTH FROM date_arrivee)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date_arrivee)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "traites":       "SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state='traite' AND EXTRACT(MONTH FROM date_arrivee)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date_arrivee)=EXTRACT(YEAR FROM CURRENT_DATE)",
            "classes":       "SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state='classe' AND EXTRACT(MONTH FROM date_arrivee)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date_arrivee)=EXTRACT(YEAR FROM CURRENT_DATE)",
            # en_retard est un boolean calculé dans la table
            "en_retard":     "SELECT COUNT(*) FROM boc_courrier_arrivee WHERE en_retard = True",
            # date_depart (pas date_envoi)
            "total_depart":  "SELECT COUNT(*) FROM boc_courrier_depart WHERE EXTRACT(MONTH FROM date_depart)=EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM date_depart)=EXTRACT(YEAR FROM CURRENT_DATE)",
            # expediteur_nom est jsonb
            "detail_retard": (
                "SELECT c.name AS reference, c.sujet, "
                "COALESCE(c.expediteur_nom->>'fr_FR', c.expediteur_nom->>'en_US', c.expediteur_nom::text) AS expediteur, "
                "TO_CHAR(c.date_arrivee,'DD/MM/YYYY') AS date_arrivee, "
                "c.state, c.type_arrivee, "
                "CURRENT_DATE - c.date_arrivee::date AS jours_retard "
                "FROM boc_courrier_arrivee c "
                "WHERE c.en_retard = True "
                "ORDER BY c.date_arrivee ASC LIMIT 15"
            ),
            "detail_en_attente": (
                "SELECT c.name AS reference, c.sujet, "
                "COALESCE(c.expediteur_nom->>'fr_FR', c.expediteur_nom->>'en_US', c.expediteur_nom::text) AS expediteur, "
                "TO_CHAR(c.date_arrivee,'DD/MM/YYYY') AS date_arrivee, "
                "c.state, c.type_arrivee, "
                "TO_CHAR(c.date_echeance,'DD/MM/YYYY') AS echeance "
                "FROM boc_courrier_arrivee c "
                "WHERE c.state IN ('enregistre','diffuse') "
                "AND EXTRACT(MONTH FROM c.date_arrivee)=EXTRACT(MONTH FROM CURRENT_DATE) "
                "AND EXTRACT(YEAR FROM c.date_arrivee)=EXTRACT(YEAR FROM CURRENT_DATE) "
                "ORDER BY c.date_echeance ASC LIMIT 15"
            ),
        }
    },
}


def _executer_requetes_rapport(requetes: dict) -> dict:
    """Exécute toutes les requêtes SQL d'un rapport et retourne les résultats."""
    resultats = {}
    try:
        conn = get_pg_connection()
        cur  = conn.cursor()
        for cle, sql in requetes.items():
            try:
                cur.execute(sql)
                rows = cur.fetchall()
                if rows and len(rows) == 1 and len(rows[0]) == 1:
                    resultats[cle] = rows[0][0]  # valeur scalaire
                else:
                    resultats[cle] = rows         # liste
            except Exception as e:
                _logger.warning(f"Rapport SQL erreur ({cle}): {e}")
                resultats[cle] = None
        conn.close()
    except Exception as e:
        _logger.error(f"Connexion rapport échouée: {e}")
    return resultats


def _detecter_rapport(question: str) -> str | None:
    """
    Détecte quel type de rapport prédéfini est demandé.
    Ordre : du plus spécifique au plus général.
    Retourne None si aucun rapport prédéfini ne correspond
    (→ laisse generer_rapport_libre prendre le relais).
    """
    import unicodedata
    q = question.lower().strip()
    q_norm = unicodedata.normalize("NFD", q)
    q_norm = "".join(c for c in q_norm if unicodedata.category(c) != "Mn")

    # ── Ordre IMPORTANT : plus spécifique d'abord ─────────────────────────────
    patterns = [
        # BOC
        ("bilan_boc", [
            "bilan courrier", "rapport courrier", "synthese courrier",
            "bilan boc", "etat courriers", "courriers mois",
            "courrier boc", "arrivee courrier", "depart courrier",
            "courriers en attente", "courriers en retard", "boite ordre",
            # AR
            "تقرير البريد", "ملخص البريد", "البريد الوارد", "البريد الصادر",
            # EN
            "mail report", "mail summary", "incoming mail", "outgoing mail",
        ]),
        # ASSURANCE
        ("bilan_assurance", [
            "bilan assurance", "rapport assurance", "synthese assurance",
            "bilan sinistres", "rapport sinistres", "etat assurance",
            "polices assurance", "assurance bus", "sinistres bus",
            "bilan mensuel assurance",
            # AR
            "تقرير التامين", "تقرير التأمين", "ملخص التأمين",
            "بوليصات التأمين", "الحوادث",
            # EN
            "insurance report", "insurance summary", "claims report",
        ]),
        # CARBURANT
        ("bilan_carburant", [
            "bilan carburant", "rapport carburant", "consommation carburant",
            "synthese carburant", "bons carburant", "rapport fuel",
            "consommation mensuelle carburant", "bgi bge",
            # AR
            "تقرير الوقود", "استهلاك الوقود", "ملخص الوقود",
            # EN
            "fuel report", "fuel consumption", "fuel summary",
        ]),
        # PARC BUS
        ("bilan_parc", [
            "etat du parc", "bilan parc", "synthese parc",
            "etat des bus", "parc bus", "flotte bus",
            "disponibilite bus", "etat flotte",
            # AR
            "حالة الأسطول", "تقرير الأسطول", "ملخص الحافلات",
            "حالة الحافلات",
            # EN
            "fleet report", "fleet status", "bus fleet",
        ]),
        # JOURNALIER
        ("rapport_journalier", [
            "rapport journalier", "resume journalier", "bilan journalier",
            "rapport du jour", "journee exploitation",
            "resume du jour", "synthese du jour",
            "rapport exploitation journalier", "tournees du jour",
            # AR
            "تقرير يومي", "تقرير التشغيل اليومي", "ملخص اليوم",
            "الرحلات اليومية",
            # EN
            "daily report", "daily summary", "today report",
            "daily operations",
        ]),
        # HEBDOMADAIRE
        ("rapport_hebdomadaire", [
            "rapport hebdomadaire", "bilan semaine", "resume semaine",
            "rapport semaine", "synthese semaine", "bilan hebdomadaire",
            "cette semaine exploitation", "semaine exploitation",
            # AR
            "تقرير أسبوعي", "تقرير اسبوعي", "ملخص الأسبوع",
            # EN
            "weekly report", "weekly summary", "this week",
        ]),
        # MENSUEL
        ("rapport_mensuel", [
            "rapport mensuel exploitation", "bilan mensuel exploitation",
            "rapport mensuel tournees", "bilan mensuel tournees",
            "synthese mensuelle exploitation", "rapport du mois exploitation",
            "bilan du mois exploitation", "mois exploitation",
            "genere le rapport mensuel", "rapport mensuel",
            "rapport_mensuel",
            # AR
            "تقرير شهري", "تقرير التشغيل الشهري", "ملخص الشهر",
            "الرحلات الشهرية",
            # EN
            "monthly report", "monthly summary", "this month report",
        ]),
        # IDs directs JS
        ("rapport_journalier",   ["rapport_journalier"]),
        ("rapport_hebdomadaire", ["rapport_hebdomadaire"]),
        ("bilan_parc",           ["genere le bilan_parc"]),
        ("bilan_assurance",      ["genere le bilan_assurance"]),
        ("bilan_carburant",      ["genere le bilan_carburant"]),
        ("bilan_boc",            ["genere le bilan_boc"]),
    ]

    for type_rapport, mots_cles in patterns:
        for mot in mots_cles:
            if mot in q_norm:
                return type_rapport
    return None


def generer_rapport(type_rapport: str, llm, langue: str = "fr") -> str:
    """
    Génère un rapport complet en français pour le type demandé.
    Exécute les requêtes SQL puis demande au LLM de rédiger la synthèse.
    """
    from datetime import date

    if type_rapport not in TEMPLATES_RAPPORTS:
        return "Type de rapport non reconnu."

    template = TEMPLATES_RAPPORTS[type_rapport]
    label    = template["label"]

    _logger.info(f"Génération rapport: {label}")
    print(f"  -> Rapport: {label}")

    # Exécuter toutes les requêtes SQL
    resultats = _executer_requetes_rapport(template["requetes"])
    print(f"  -> Résultats SQL: {len(resultats)} indicateurs")

    # Construire le contexte pour le LLM
    contexte_str = f"Date du rapport : {date.today().strftime('%d/%m/%Y')}\n\n"
    contexte_str += "Données extraites de la base PostgreSQL :\n"
    for cle, valeur in resultats.items():
        if valeur is None:
            continue
        if isinstance(valeur, list):
            if valeur:
                contexte_str += f"  {cle} :\n"
                for row in valeur[:5]:
                    contexte_str += f"    - {' | '.join(str(v) for v in row)}\n"
        else:
            contexte_str += f"  {cle} : {valeur}\n"

    # Prompt LLM localisé selon la langue
    _rapport_prompts = {
        "fr": (
            f"Tu es l'assistant IA d'un ERP de transport terrestre tunisien.\n"
            f"Rédige un {label} professionnel et concis en français.\n"
            f"Utilise les données suivantes :\n\n{contexte_str}\n"
            f"Format : paragraphes courts, chiffres en gras, "
            f"points positifs et points d'attention. "
            f"Maximum 250 mots. Commence directement par le rapport."
        ),
        "en": (
            f"You are an AI assistant for a Tunisian transport ERP.\n"
            f"Write a professional and concise {label} in English.\n"
            f"Use the following data:\n\n{contexte_str}\n"
            f"Format: short paragraphs, bold numbers, "
            f"highlights and attention points. "
            f"Maximum 250 words. Start directly with the report."
        ),
        "ar": (
            f"أنت مساعد ذكاء اصطناعي لنظام ERP لنقل بري تونسي.\n"
            f"اكتب {label} مهنياً وموجزاً باللغة العربية.\n"
            f"استخدم البيانات التالية:\n\n{contexte_str}\n"
            f"التنسيق: فقرات قصيرة، أرقام بالخط العريض، "
            f"نقاط إيجابية ونقاط تحتاج انتباه. "
            f"250 كلمة كحد أقصى. ابدأ مباشرة بالتقرير."
        ),
    }
    prompt = _rapport_prompts.get(langue, _rapport_prompts["fr"])

    if llm is None:
        _logger.warning("LLM non disponible pour rapport — retour brut")
    else:
        try:
            rapport = llm.invoke(prompt)
            return f"**{label} — {date.today().strftime('%d/%m/%Y')}**\n\n{rapport}"
        except Exception as e:
            _logger.error(f"LLM rapport échoué: {e}")
        # Fallback : rapport brut sans LLM — formatage lisible
        from datetime import date as _date
        aujourd_hui = _date.today().strftime("%d/%m/%Y")
        rapport_brut = f"**{label}**\n*Généré le {aujourd_hui}*\n\n"

        # Labels lisibles pour chaque indicateur
        labels_fr = {
            "tournees_planifiees": "🗓 Tournées planifiées",
            "tournees_en_cours":   "🚌 Tournées en cours",
            "tournees_realisees":  "✅ Tournées réalisées",
            "tournees_annulees":   "❌ Tournées annulées",
            "tournees_total":      "📊 Total tournées",
            "km_total":            "📏 Km total parcourus",
            "ecart_moyen":         "⚠ Écart km moyen",
            "chauffeur_top":       "🏆 Meilleur chauffeur",
            "bus_top_km":          "🚗 Bus avec plus de km",
            "top_chauffeurs":      "🏆 Top chauffeurs",
            "km_par_bus":          "📏 Km par bus",
            "annulations_motif":   "❌ Motifs d'annulation",
            "detail_annulees":     "❌ Tournées annulées",
            "total_bus":           "🚌 Total bus dans le parc",
            "en_service":          "✅ Bus en service",
            "hors_service":        "🔴 Bus hors service",
            "en_panne":            "⚠ Bus en panne",
            "en_maintenance":      "🔧 Bus en maintenance",
            "polices_actives":     "✅ Polices actives",
            "polices_alerte":      "⚠ Polices en alerte",
            "polices_expirees":    "❌ Polices expirées",
            "polices_resiliees":   "🚫 Polices résiliées",
            "sinistres_mois":      "🚨 Sinistres ce mois",
            "montant_sinistres":   "💰 Montant sinistres (TND)",
            "detail_sinistres":    "🚨 Détail sinistres",
            "expiration_30j":      "⏰ Polices expirant dans 30j",
            "bons_valides":        "✅ Bons carburant validés",
            "litres_total":        "⛽ Litres consommés",
            "bgi_count":           "🏠 Bons BGI (internes)",
            "bge_count":           "🔄 Bons BGE (externes)",
            "litres_par_bus":      "⛽ Consommation par bus",
            "total_arrivee":       "📬 Courriers reçus",
            "en_attente":          "⏳ En attente de traitement",
            "traites":             "✅ Traités",
            "classes":             "📁 Classés",
            "en_retard":           "⚠ En retard (> 7 jours)",
            "detail_bus":          "🚌 Détail du parc",
        }

        for cle, valeur in resultats.items():
            if valeur is None:
                continue
            label_fr = labels_fr.get(cle, cle.replace("_", " ").title())
            if isinstance(valeur, list):
                if valeur:
                    rapport_brut += f"\n**{label_fr}** :\n"
                    for row in valeur[:8]:
                        row_str = " | ".join(str(v) for v in row if v is not None)
                        rapport_brut += f"  • {row_str}\n"
            elif valeur == 0 or valeur:
                # Formater les nombres
                if isinstance(valeur, float):
                    valeur = round(valeur, 1)
                rapport_brut += f"**{label_fr}** : {valeur}\n"

        return rapport_brut


def generer_rapport_libre(question: str, llm, allowed_tables: list = None,
                          is_admin: bool = False, langue: str = "fr") -> dict:
    """
    Génère un rapport PDF à partir d'une question libre.
    1. Génère le SQL via le LLM
    2. Exécute la requête
    3. Crée le PDF avec les données
    Retourne {"label": str, "pdf_path": Path, "data": dict}
    """
    from datetime import date, datetime
    from pathlib import Path

    _logger.info(f"Rapport libre: {question}")

    # ── Étape 1 : générer le SQL ──────────────────────────────────────────────
    try:
        requete = generer_sql(question, llm, allowed_tables, is_admin)
        # Post-traitement : forcer ILIKE pour license_plate
        import re as _re_lp
        def _fix_lp(m):
            val = _re_lp.search(r"['\"]([^'\"]+)['\"]", m.group(0))
            if not val:
                return m.group(0)
            parties = _re_lp.split(r"\s+", val.group(1).strip().lower())
            pattern = "%" + "%".join(parties) + "%"
            return f"license_plate ILIKE '{pattern}'"
        requete = _re_lp.sub(
            r"license_plate\s*=\s*['\"][^'\"]+['\"]",
            _fix_lp, requete, flags=_re_lp.IGNORECASE
        )
        print(f"  -> SQL rapport libre: {requete}")
    except Exception as e:
        _logger.error(f"Erreur génération SQL rapport libre: {e}")
        return {"erreur": f"Impossible de générer la requête SQL : {e}"}

    if not requete or not requete.strip().upper().startswith("SELECT"):
        return {"erreur": "La question ne correspond pas à une requête de données."}

    # ── Étape 2 : exécuter la requête ────────────────────────────────────────
    try:
        conn = get_pg_connection()
        cur  = conn.cursor()

        # Vérifier et corriger si erreur SQL
        valide, erreur_col = verifier_colonnes_sql(requete)
        if not valide:
            diagnostic = diagnostiquer_erreur_sql(requete, erreur_col)
            extra = (
                "\nERREUR DETECTEE: " + str(erreur_col) + "\n" +
                str(diagnostic) + "\n" +
                "Reecrire avec les colonnes correctes.\n"
            )
            requete = generer_sql(question, llm, allowed_tables, is_admin,
                                  diagnostic_extra=extra)

        cur.execute(requete)
        rows    = cur.fetchall()
        colonnes = [desc[0] for desc in cur.description] if cur.description else []
        conn.close()
    except Exception as e:
        _logger.error(f"Erreur SQL rapport libre: {e}")
        return {"erreur": f"Erreur lors de l'exécution de la requête : {e}"}

    if not rows:
        return {"erreur": msg("no_data", langue if langue else "fr")}

    # ── Étape 3 : construire le label et le nom de fichier ───────────────────
    # Normaliser la question en slug pour le nom de fichier
    import unicodedata, re as _re2
    def _slugify(s, max_len=40):
        s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
        s = _re2.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
        return s[:max_len] or "rapport"

    slug  = _slugify(question)
    label = question.strip().capitalize()
    if len(label) > 60:
        label = label[:57] + "..."

    # ── Étape 4 : construire data pour rapport_pdf ────────────────────────────
    # Séparer scalaires et listes
    data = {}

    if len(rows) == 1 and len(rows[0]) == 1:
        # Résultat scalaire unique
        data["resultat"] = rows[0][0]
    elif len(rows) >= 1:
        # Résultat tabulaire → une seule clé "resultats" avec les lignes
        data["resultats"] = rows
        # Stocker les noms de colonnes pour le PDF
        data["_colonnes"] = colonnes

    # ── Étape 5 : générer le PDF ──────────────────────────────────────────────
    try:
        from rapport_pdf import generer_pdf_rapport_libre
        rapports_dir = Path(__file__).parent.parent / "rapports"
        rapports_dir.mkdir(exist_ok=True)
        nom = f"{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        chemin = rapports_dir / nom

        generer_pdf_rapport_libre(
            label=label,
            question=question,
            data=data,
            colonnes=colonnes,
            rows=rows,
            chemin=chemin,
            llm=llm,
            langue=langue,
        )

        _logger.info(f"Rapport libre généré: {chemin}")
        return {"label": label, "pdf_path": chemin, "nom": nom, "data": data}

    except Exception as e:
        _logger.error(f"Erreur génération PDF rapport libre: {e}")
        return {"erreur": f"Erreur génération PDF : {e}"}



def ask_agent(question: str, llm: OllamaLLM,
              allowed_tables: list = None,
              is_admin: bool = False,
              session_id: str = "default",
              mode_rapport: bool = False,
              mode_stats: bool = False,
              langue: str = None) -> str:
    try:
        # ── Détection automatique de langue (0 LLM) ──────────────────────────
        if not langue:
            # Détection robuste : arabe d'abord par ratio de caractères
            _chars_ar = sum(1 for c in question if '\u0600' <= c <= '\u06FF')
            _chars_tot = sum(1 for c in question if c.strip())
            if _chars_tot > 0 and _chars_ar / _chars_tot > 0.10:
                langue = "ar"
            else:
                langue = detecter_langue(question)
        _logger.info(f"Langue détectée: {langue} pour: {question[:50]}")

        # Enrichir la question avec le contexte conversationnel si nécessaire
        question = _enrichir_question(question, session_id)

        # ── MODE STATISTIQUES : générer JSON avec KPIs + visualisation ────────
        if mode_stats:
            _logger.info(f"Mode stats activé pour: {question}")
            try:
                import json as _json

                # ── Étape 1 : générer le SQL avec contexte métier + retry ────
                # Labels BOC selon la langue
                _BOC_LABELS = {
                    "fr": ("Arrivée", "Départ"),
                    "en": ("Incoming", "Outgoing"),
                    "ar": ("وارد", "صادر"),
                }
                _lbl_arr, _lbl_dep = _BOC_LABELS.get(langue, _BOC_LABELS["fr"])

                HINT_STATS = (
                    f"\nRÈGLES SQL STATISTIQUES:\n"
                    f"- Pour répartition arrivée/départ BOC : "
                    f"SELECT \'{_lbl_arr}\' AS type, COUNT(*) FROM boc_courrier_arrivee "
                    f"UNION ALL SELECT \'{_lbl_dep}\' FROM boc_courrier_depart\n"
                    "- Pour répartition état bus : "
                    "SELECT s.name->>'en_US' AS etat, COUNT(*) FROM fleet_vehicle v "
                    "JOIN fleet_vehicle_state s ON v.state_id=s.id GROUP BY s.name\n"
                    "- Pour BGI vs BGE : "
                    "SELECT voucher_type, COUNT(*), SUM(total_quantity) "
                    "FROM transport_fuel_voucher WHERE state='done' GROUP BY voucher_type\n"
                    "- Pour répartition état polices : "
                    "SELECT state, COUNT(*) FROM transport_assurance_bus GROUP BY state\n"
                    "- Pour tendance/évolution sur N mois (courriers arrivée) : "
                    "SELECT TO_CHAR(date_reception, 'YYYY-MM') AS mois, COUNT(*) "
                    "FROM boc_courrier_arrivee "
                    "WHERE date_reception >= CURRENT_DATE - INTERVAL '6 months' "
                    "GROUP BY mois ORDER BY mois\n"
                    "- Pour tendance/évolution sur N mois (courriers départ) : "
                    "SELECT TO_CHAR(date_envoi, 'YYYY-MM') AS mois, COUNT(*) "
                    "FROM boc_courrier_depart "
                    "WHERE date_envoi >= CURRENT_DATE - INTERVAL '6 months' "
                    "GROUP BY mois ORDER BY mois\n"
                    "- Pour tendance tournées par mois : "
                    "SELECT TO_CHAR(date, 'YYYY-MM') AS mois, COUNT(*) "
                    "FROM transport_exploitation_tournee "
                    "WHERE date >= CURRENT_DATE - INTERVAL '6 months' "
                    "GROUP BY mois ORDER BY mois\n"
                    "- IMPORTANT: Toujours utiliser CURRENT_DATE pour les dates récentes\n"
                    "- IMPORTANT: NE JAMAIS utiliser des dates hardcodées comme '2030-05'\n"
                    "- NE JAMAIS joindre boc_courrier_arrivee et boc_courrier_depart pour les compter\n"
                    "- Toujours utiliser GROUP BY pour les répartitions\n"
                )
                requete = generer_sql(question, llm, allowed_tables, is_admin,
                                      diagnostic_extra=HINT_STATS)
                print(f"  -> SQL stats: {requete}")

                # Vérification colonnes avant exécution
                valide, erreur_col = verifier_colonnes_sql(requete)
                if not valide:
                    diagnostic = diagnostiquer_erreur_sql(requete, erreur_col)
                    extra = (
                        HINT_STATS +
                        "\nERREUR COLONNES: " + str(erreur_col) + "\n" +
                        str(diagnostic) + "\n" +
                        "Utiliser UNIQUEMENT les colonnes listées dans le diagnostic.\n"
                    )
                    requete = generer_sql(question, llm, allowed_tables, is_admin, diagnostic_extra=extra)
                    print(f"  -> SQL stats corrigé: {requete}")

                donnees = sql_tool.invoke(requete)

                # Retry si erreur SQL à l'exécution
                if "Erreur SQL" in donnees:
                    diagnostic = diagnostiquer_erreur_sql(requete, donnees)
                    extra = (
                        "\nSQL ÉCHOUÉ: " + requete + "\nErreur: " + donnees[:200] + "\n" +
                        str(diagnostic) + "\n" +
                        "Réécrire avec les colonnes exactes du diagnostic.\n"
                    )
                    requete2 = generer_sql(question, llm, allowed_tables, is_admin, diagnostic_extra=extra)
                    if requete2 != requete and requete2.upper().startswith("SELECT"):
                        print(f"  -> SQL stats re-corrigé: {requete2}")
                        donnees = sql_tool.invoke(requete2)

                if not donnees or not donnees.strip():
                    donnees = msg("no_data", langue)

                # ── Étape 2 : générer le JSON stats avec le LLM ──────────────
                # Contexte métier pour guider le SQL et l'interprétation
                CONTEXTE_METIER = (
                    "CONTEXTE ERP TRANSPORT TUNISIE:\n"
                    "- boc_courrier_arrivee : courriers reçus (state: brouillon/enregistre/diffuse/traite/classe)\n"
                    "- boc_courrier_depart : courriers envoyés (state: brouillon/enregistre/envoye/classe)\n"
                    "- transport_assurance_sinistre : sinistres (montant_reclame, montant_accorde, montant_net_verse)\n"
                    "- fleet_vehicle : bus (state_id: 47=En service, 48=Hors service, 5=En panne, 6=En maintenance)\n"
                    "- transport_exploitation_tournee : tournées (state: brouillon/planifie/en_cours/realise/annule)\n"
                    "- transport_fuel_voucher : bons carburant (voucher_type: internal=BGI, external=BGE)\n"
                    "NE PAS faire de jointure entre arrivee et depart — les compter séparément.\n"
                )

                # Prompt stats entièrement localisé selon la langue
                if langue == "ar":
                    prompt_stats = (
                        "CRITICAL INSTRUCTION: You MUST respond with Arabic text only for all string values.\n"
                        "You are an AI assistant for a Tunisian land transport ERP.\n"
                        f"{CONTEXTE_METIER}\n"
                        f"Question (Arabic): {question}\n"
                        f"SQL Data:\n{donnees[:800]}\n\n"
                        "Generate ONLY valid JSON (no markdown). ALL text values MUST be in Arabic:\n"
                        "{\n"
                        "  \"texte\": \"[Arabic summary sentence with key numbers]\",\n"
                        "  \"kpis\": [{\"label\": \"[Arabic indicator name]\", \"valeur\": \"[formatted value]\", \"tendance\": \"↑|↓|=\"}],\n"
                        "  \"visualisation\": {\"type\": \"bar|line|donut|pie|kpi\", \"title\": \"[Arabic title]\", \"labels\": [\"[Arabic label 1]\", \"[Arabic label 2]\"], \"data\": []}\n"
                        "}\n"
                        "RULES:\n"
                        "1. ALL labels, texte, title MUST be in Arabic script. NO French or English text.\n"
                        "2. For incoming vs outgoing mail: labels=[\"وارد\", \"صادر\"] NOT [\"Arrivée\", \"Départ\"]\n"
                        "3. For bus status: labels=[\"في الخدمة\", \"خارج الخدمة\"]\n"
                        "4. data = numbers only. tendance = ↑ or ↓ or =\n"
                        "5. If 1 value: type=\"kpi\". If multiple: type=\"bar\" or \"donut\".\n"
                        "Respond ONLY with the JSON object."
                    )
                elif langue == "en":
                    prompt_stats = (
                        "You are an AI assistant for a Tunisian land transport ERP.\n"
                        f"{CONTEXTE_METIER}\n"
                        f"Question: {question}\n"
                        f"SQL Data:\n{donnees[:800]}\n\n"
                        "Generate ONLY valid JSON (no markdown). ALL text values MUST be in English:\n"
                        "{\n"
                        "  \"texte\": \"[English summary sentence with key numbers]\",\n"
                        "  \"kpis\": [{\"label\": \"[English indicator name]\", \"valeur\": \"[formatted value]\", \"tendance\": \"↑|↓|=\"}],\n"
                        "  \"visualisation\": {\"type\": \"bar|line|donut|pie|kpi\", \"title\": \"[English title]\", \"labels\": [], \"data\": []}\n"
                        "}\n"
                        "RULES: data = numbers only. tendance = ↑ or ↓ or =. If 1 value: type=\"kpi\".\n"
                        "Respond ONLY with the JSON object."
                    )
                else:
                    prompt_stats = (
                        f"Tu es l'assistant IA d'un ERP transport terrestre tunisien.\n"
                        f"{CONTEXTE_METIER}\n"
                        f"Question : {question}\n"
                        f"Données SQL :\n{donnees[:800]}\n\n"
                        "Génère UNIQUEMENT un JSON valide (sans markdown) :\n"
                        "{\n"
                        "  \"texte\": \"phrase résumé en français avec les chiffres clés\",\n"
                        "  \"kpis\": [{\"label\": \"nom indicateur\", \"valeur\": \"valeur formatée\", \"tendance\": \"↑|↓|=\"}],\n"
                        "  \"visualisation\": {\"type\": \"bar|line|donut|pie|kpi\", \"title\": \"titre\", \"labels\": [], \"data\": []}\n"
                        "}\n"
                        "RÈGLES: data=nombres. Si 1 valeur: type=\"kpi\". Si plusieurs: type=\"bar\" ou \"donut\".\n"
                        "Réponds UNIQUEMENT avec le JSON."
                    )

                raw_stats = llm.invoke(prompt_stats).strip()
                raw_stats = raw_stats.replace("```json","").replace("```","").strip()

                # Extraire le JSON même s'il y a du texte autour
                import re as _re_json
                m_json = _re_json.search(r'\{[\s\S]+\}', raw_stats)
                if m_json:
                    raw_stats = m_json.group(0)

                stats_data = _json.loads(raw_stats)
                return _json.dumps(stats_data, ensure_ascii=False)

            except Exception as e:
                _logger.error(f"Erreur mode stats: {e}")
                # Fallback : retourner une réponse texte simple
                try:
                    donnees_fb = sql_tool.invoke(generer_sql(question, llm, allowed_tables, is_admin))
                    reponse_fb = formuler_reponse(question, donnees_fb, llm, langue)
                    fallback = {"texte": reponse_fb, "kpis": [], "visualisation": None}
                    return _json.dumps(fallback, ensure_ascii=False)
                except Exception as e2:
                    _logger.error(f"Fallback stats échoué: {e2}")
                    err = {"texte": "Impossible de générer les statistiques pour cette question.", "kpis": [], "visualisation": None}
                    return _json.dumps(err, ensure_ascii=False)

        # ── MODE RAPPORT LIBRE : générer un PDF pour n'importe quelle question ──
        if mode_rapport:
            _logger.info(f"Mode rapport activé pour: {question} | langue={langue}")
            # _detecter_rapport gère fr/en/ar — on l'appelle EN PREMIER
            type_rapport = _detecter_rapport(question)
            if type_rapport:
                agent_url = _AGENT_URL
                lien_pdf  = f"{agent_url}/rapport/{type_rapport}/pdf?langue={langue}"
                label     = TEMPLATES_RAPPORTS[type_rapport].get("labels", {}).get(langue, TEMPLATES_RAPPORTS[type_rapport]["label"])
                from datetime import date as _date
                return (
                    f"✅ Rapport prêt : **{label}**\n"
                    f"Généré le {_date.today().strftime('%d/%m/%Y')}\n"
                    f"PDF_URL:{lien_pdf}"
                )
            # Aucun rapport prédéfini → rapport libre SQL
            _logger.info(f"Rapport libre: {question}")
            resultat = generer_rapport_libre(question, llm, allowed_tables, is_admin, langue)
            if "erreur" in resultat:
                return f"❌ {resultat['erreur']}"
            agent_url = _AGENT_URL
            nom       = resultat["nom"]
            print(f"  [DEBUG] _AGENT_URL = {_AGENT_URL!r}")
            print(f"  [DEBUG] nom fichier = {nom!r}")
            lien_pdf  = f"{agent_url}/rapports/fichiers/{nom}"
            print(f"  [DEBUG] lien_pdf = {lien_pdf!r}")
            from datetime import date as _date
            return (
                f"✅ Rapport prêt : **{resultat['label']}**\n"
                f"Généré le {_date.today().strftime('%d/%m/%Y')}\n"
                f"PDF_URL:{lien_pdf}"
            )

        acces_erreur = verifier_acces_question(question, allowed_tables, is_admin)
        if acces_erreur:
            return acces_erreur

        # Détecter si c'est une demande de rapport/synthèse
        type_rapport = _detecter_rapport(question)
        if type_rapport:
            _logger.info(f"Rapport détecté: {type_rapport}")
            print(f"  -> Rapport: {type_rapport}")
            agent_url  = _AGENT_URL
            lien_pdf   = f"{agent_url}/rapport/{type_rapport}/pdf?langue={langue}"
            _tpl2      = TEMPLATES_RAPPORTS[type_rapport]
            label      = _tpl2.get("labels", {}).get(langue, _tpl2["label"])
            from datetime import date as _date
            return (
                f"✅ Rapport prêt : **{label}**\n"
                f"Généré le {_date.today().strftime('%d/%m/%Y')}\n"
                f"PDF_URL:{lien_pdf}"
            )

        outil = detecter_outil(question, llm)
        _logger.info(f"Outil: {outil} | Admin: {is_admin}")
        print(f"  -> Outil : {outil} | Admin : {is_admin}")

        if outil == "sql":
            # Tenter le cache SQL d'abord (0 LLM, instantané)
            requete = _chercher_cache_sql(question)
            if requete is None:
                requete = generer_sql(question, llm, allowed_tables, is_admin)
            print(f"  -> SQL : {requete}")

            valide, erreur_col = verifier_colonnes_sql(requete)
            if not valide:
                _logger.warning(f"Colonne invalide avant exécution: {erreur_col}")
                diagnostic = diagnostiquer_erreur_sql(requete, erreur_col)
                extra = (
                    f"\nERREUR DÉTECTÉE: {erreur_col}\n{diagnostic}\n"
                    "Réécrire en utilisant UNIQUEMENT les colonnes du diagnostic.\n"
                )
                requete = generer_sql(question, llm, allowed_tables, is_admin,
                                      diagnostic_extra=extra)
                print(f"  -> SQL corrigé (pré-vérif): {requete}")

            donnees = sql_tool.invoke(requete)
            print(f"  -> Données: {donnees[:150]}")

            if "Erreur SQL" in donnees:
                _logger.warning("Erreur SQL — diagnostic PostgreSQL en cours...")
                diagnostic = diagnostiquer_erreur_sql(requete, donnees)
                _logger.info(f"Diagnostic: {diagnostic[:300]}")
                print(f"  -> Diagnostic: {diagnostic[:200]}")
                extra = (
                    f"\nLA REQUÊTE A ÉCHOUÉ:\n{requete}\nErreur: {donnees[:200]}\n"
                    f"{diagnostic}\n"
                    "Réécrire en utilisant UNIQUEMENT les tables et colonnes du diagnostic.\n"
                )
                requete2 = generer_sql(question, llm, allowed_tables, is_admin,
                                       diagnostic_extra=extra)
                if requete2 != requete and requete2.upper().startswith("SELECT"):
                    print(f"  -> SQL recorrigé: {requete2}")
                    donnees = sql_tool.invoke(requete2)
                    if "Erreur SQL" in donnees:
                        _logger.error(f"Erreur persistante: {donnees[:200]}")
                        return msg("error_retry", langue)

            if not donnees.strip():
                return msg("no_data", langue)

            reponse = formuler_reponse(question, donnees, llm, langue)

        # -----------------------------------------------------------------
        # FIX 1 + FIX 4 — RPC dynamique avec timeout et fallback SQL
        # -----------------------------------------------------------------
        elif outil == "rpc":
            try:
                # Extraire et mémoriser la référence en RAM AVANT l'appel
                import re as _re_ctx
                _m_ctx = _re_ctx.search(r"[A-Z][A-Z0-9\-]*/\d{4}/\d+", question, _re_ctx.IGNORECASE)
                if _m_ctx:
                    _ref_ctx = _m_ctx.group(0).upper()
                    _SESSION_CONTEXT[session_id] = {
                        "ref": _ref_ctx,
                        "modele": next(
                            (m for p, m in {
                                "TOURN": "transport.exploitation.tournee",
                                "POL-BUS": "transport.assurance.bus",
                                "ARR": "boc.courrier.arrivee",
                                "BGI": "transport.fuel.voucher",
                                "BGE": "transport.fuel.voucher",
                            }.items() if _ref_ctx.startswith(p)), None
                        ),
                        "erreur": None,
                    }
                    print(f"  -> Contexte RAM: ref={_ref_ctx} sauvegardé pour session {session_id}")
                reponse = _executer_rpc(question, llm, allowed_tables, is_admin, session_id)
                # Mémoriser l'erreur si action impossible
                if "Action impossible" in reponse and session_id in _SESSION_CONTEXT:
                    _SESSION_CONTEXT[session_id]["erreur"] = reponse
            except Exception as e_rpc:
                _logger.warning(f"RPC exception: {e_rpc} — fallback SQL")
                try:
                    requete = generer_sql(question, llm, allowed_tables, is_admin)
                    donnees = sql_tool.invoke(requete)
                    reponse = formuler_reponse(question, donnees, llm, langue)
                except Exception as e_sql:
                    _logger.error(f"Fallback SQL aussi échoué: {e_sql}")
                    reponse = "Impossible de récupérer ces informations. Veuillez réessayer."

        # -----------------------------------------------------------------
        # FIX 4 — RAG avec timeout et fallback LLM direct
        # -----------------------------------------------------------------
        else:
            # 1. Tenter la réponse statique en premier (instantané, 0 appel)
            reponse_statique = _reponse_rag_statique(question)
            if reponse_statique != _RAG_DEFAUT:
                _logger.info("RAG statique utilisé — 0 appel LLM/ChromaDB")
                reponse = reponse_statique
            else:
                # 2. ChromaDB seulement si pas de réponse statique
                try:
                    donnees = rag_tool.invoke(question)
                    chroma_ok = (
                        donnees.strip()
                        and "vide" not in donnees.lower()
                        and "Erreur RAG" not in donnees
                        and "base de connaissances est vide" not in donnees
                        and "Aucune information" not in donnees
                    )
                    if chroma_ok:
                        reponse = llm.invoke(
                            f"ERP transport tunisien. Réponds en français, max 3 phrases.\n"
                            f"Info: {donnees[:500]}\nQ: {question}"
                        ).strip()
                    else:
                        reponse = msg("no_answer_found", langue)
                except Exception as e_rag:
                    _logger.warning(f"RAG exception: {e_rag}")
                    reponse = msg("no_answer_found", langue)

        # FIX 3 — Persistance SQLite
        sauvegarder_historique(session_id, question, reponse)
        return reponse

    except Exception as e:
        msg = str(e)
        _logger.error(f"Erreur ask_agent: {msg}")
        if "system memory" in msg or "memory" in msg.lower():
            return msg('error_memory', langue)
        return f"Erreur : {msg}"