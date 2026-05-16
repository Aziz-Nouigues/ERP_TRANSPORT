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

load_dotenv(Path(__file__).parent.parent / ".env")

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIX 3 — Historique persistant dans SQLite (remplace dict en RAM)
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).parent.parent / "historique.db"
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
]

MOTS_CLES_PROTEGES = {
    'hr': ['employe', 'employee', 'salarie', 'staff', 'personnel'],
}


def verifier_acces_question(question: str, allowed_tables: list, is_admin: bool):
    if is_admin or (allowed_tables and "ALL" in allowed_tables):
        return None
    question_lower = question.lower()
    for mot in MOTS_TRANSPORT_AUTORISES:
        if mot in question_lower:
            return None
    for domaine, mots in MOTS_CLES_PROTEGES.items():
        for mot in mots:
            if mot in question_lower:
                tables_domaine = {'hr': ['hr_employee', 'hr_department']}
                autorise = any(t in (allowed_tables or [])
                               for t in tables_domaine.get(domaine, []))
                if not autorise:
                    return "Vous n'avez pas les droits d'accès pour consulter ces données."
    return None

# ---------------------------------------------------------------------------
# DÉTECTION RAPIDE D'OUTIL — 100% Python, 0 appel LLM
# ---------------------------------------------------------------------------

# Mots-clés qui indiquent une procédure/définition (rag)
_MOTS_RAG = {
    "comment", "procédure", "procedure", "définition", "definition",
    "qu'est-ce", "qu est ce", "c'est quoi", "expliquer", "expliquez",
    "comment faire", "règle", "regle", "workflow", "étapes", "etapes",
    "feuille de route", "manuel", "guide",
}

# Mots-clés qui indiquent une action Odoo (rpc)
_MOTS_RPC = {
    "créer", "creer", "créé", "ajouter", "ajoute", "nouveau", "nouvelle",
    "valider", "valide", "confirmer", "confirme", "modifier", "modifie",
    "annuler", "annule", "supprimer", "supprime", "enregistrer", "enregistre",
    "mettre à jour", "mettre a jour",
}


def detecter_outil(question: str, llm=None) -> str:
    """
    Détection de l'outil en Python pur — zéro appel LLM.
    RAG  : questions de définition/procédure
    RPC  : actions Odoo (créer, valider, modifier…)
    SQL  : tout le reste (liste, stats, détails)
    """
    q = question.lower()
    for mot in _MOTS_RAG:
        if mot in q:
            return "rag"
    for mot in _MOTS_RPC:
        if mot in q:
            return "rpc"
    return "sql"


# ---------------------------------------------------------------------------
# PIPELINE UNIFIÉ : 1 seul appel LLM (outil + tables + SQL en une fois)
# ---------------------------------------------------------------------------

def _tables_par_mots_cles(question: str) -> list:
    """Détection des tables 100% Python via TABLES_METIER."""
    q = question.lower()
    tables = set()
    for mot, tables_liees in TABLES_METIER.items():
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
        regles.append("ASSURANCE state: active,expire,resilie,brouillon. Never filter is_obligatoire.")
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
        f"{schema}\n"
        f"{diagnostic_extra}\n"
        "RULES:\n"
        "  [BUS] COUNT(*) FROM fleet_vehicle needs no WHERE. "
        "state jsonb: COALESCE(s.name->>'fr_FR',s.name->>'en_US'). "
        "No cols: type_vehicule,activity_type,vehicle_type.\n"
        "  [ASSURANCE] state: active,expire,resilie,brouillon. Never filter is_obligatoire.\n"
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
        "No bracket placeholders.\n\n"
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
# FIX 1 — Génération dynamique de l'action RPC
# ---------------------------------------------------------------------------

# Mapping question → modèle Odoo + champs pertinents
MODELES_RPC = {
    "tournee":         ("transport.exploitation.tournee",
                        ["name", "date", "state", "vehicle_id", "chauffeur_id",
                         "km_prevu", "km_realise", "ecart_km"]),
    "tournée":         ("transport.exploitation.tournee",
                        ["name", "date", "state", "vehicle_id", "chauffeur_id",
                         "km_prevu", "km_realise", "ecart_km"]),
    "bus":             ("fleet.vehicle",
                        ["name", "license_plate", "state_id"]),
    "vehicule":        ("fleet.vehicle",
                        ["name", "license_plate", "state_id"]),
    "véhicule":        ("fleet.vehicle",
                        ["name", "license_plate", "state_id"]),
    "assurance":       ("transport.assurance.bus",
                        ["name", "vehicle_id", "state", "date_debut", "date_fin"]),
    "police":          ("transport.assurance.bus",
                        ["name", "vehicle_id", "state", "date_debut", "date_fin"]),
    "sinistre":        ("transport.assurance.sinistre",
                        ["name", "vehicle_id", "date_sinistre", "state"]),
    "chauffeur":       ("hr.employee",
                        ["name", "job_title", "active"]),
    "conducteur":      ("hr.employee",
                        ["name", "job_title", "active"]),
    "carburant":       ("transport.fuel.voucher",
                        ["name", "voucher_type", "total_quantity", "date", "state"]),
    "bgi":             ("transport.fuel.voucher",
                        ["name", "voucher_type", "total_quantity", "date", "state"]),
    "bge":             ("transport.fuel.voucher",
                        ["name", "voucher_type", "total_quantity", "date", "state"]),
    "courrier":        ("boc.courrier.arrivee",
                        ["name", "sujet", "expediteur", "date_arrivee", "state"]),
    "facture":         ("transport.facture.energie",
                        ["name", "type_facture", "statut", "site", "montant",
                         "date_reception"]),
}

ETATS_RPC = {
    "réalisée": "realise", "realisee": "realise", "effectuée": "realise",
    "terminée": "realise", "complétée": "realise",
    "planifiée": "planifie", "planifie": "planifie",
    "prévue": "planifie", "programmée": "planifie",
    "en cours": "en_cours", "en_cours": "en_cours",
    "annulée": "annule", "annule": "annule",
    "brouillon": "brouillon",
    "active": "active", "expirée": "expire", "résiliée": "resilie",
}


def generer_action_rpc(question: str, llm: OllamaLLM) -> str:
    """
    Génère dynamiquement une action RPC à partir de la question.
    Retourne une chaîne au format: modele|methode|domaine|champs
    """
    q = question.lower()

    # 1. Détecter le modèle Odoo cible
    modele = "transport.exploitation.tournee"
    champs = ["name", "date", "state", "vehicle_id"]
    for mot, (m, c) in MODELES_RPC.items():
        if mot in q:
            modele = m
            champs = c
            break

    # 2. Construire le domaine de filtrage
    domaine = []

    # Filtre par état
    for mot_etat, val_etat in ETATS_RPC.items():
        if mot_etat in q:
            domaine.append(["state", "=", val_etat])
            break

    # Filtre par immatriculation / nom
    match_plaque = re.search(
        r'\b(\d{1,4}\s*tu\s*\d{1,4}|\d{1,4}\s*tn\s*\d{1,4})\b', q
    )
    if match_plaque:
        plaque = match_plaque.group(0).upper().replace(" ", "")
        domaine.append(["license_plate", "ilike", plaque])

    # Filtre par référence de tournée (ex: TOURN/2026/00020)
    match_ref = re.search(r'[A-Z]+/\d{4}/\d+', question, re.IGNORECASE)
    if match_ref:
        domaine.append(["name", "=", match_ref.group(0).upper()])

    # 3. Demander au LLM si le domaine est vide et la question est précise
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

    domaine_str = json.dumps(domaine)
    champs_str = json.dumps(champs)
    action = f"{modele}|search_read|{domaine_str}|{champs_str}"
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


def _formuler_count(question: str, valeur: str) -> str:
    q = question.lower()
    for pattern, gabarit in _GABARITS_COUNT:
        if re.search(pattern, q):
            return gabarit.format(v=valeur)
    return f"Résultat : **{valeur}**"


def formuler_reponse(question: str, donnees: str, llm: OllamaLLM) -> str:
    if re.search(r'\[[A-Za-zÀ-ÿ ]+\]', donnees):
        return "Les données sont incomplètes. Veuillez reformuler votre question."
    if any(msg in donnees for msg in ["Acces refuse", "Requete non valide", "Placeholder detecte"]):
        return "Vous n'avez pas les droits d'accès pour consulter ces données."
    if not donnees.strip() or "Aucun résultat" in donnees or "Aucun resultat" in donnees:
        return "Aucune donnée trouvée pour cette question."

    lignes = [l for l in donnees.strip().split("\n") if l.strip()]
    if not lignes:
        return "Aucune donnée trouvée."

    entete = lignes[0] if lignes else ""
    colonnes = [c.strip() for c in entete.split("|") if c.strip()]
    lignes_data = [l for l in lignes[1:] if "----" not in l and "====" not in l]

    if not lignes_data:
        return f"Résultat :\n{donnees}"

    nb = len(lignes_data)

    # ── COUNT/SUM (1 colonne) → Python pur, 0 LLM ──
    if len(colonnes) == 1:
        valeur = lignes_data[0].strip() if lignes_data else "?"
        return _formuler_count(question, valeur)

    # ── Listes (≥2 lignes) et détail unique → voir après définition de _formater_valeur ──
    LABELS = {
        # Identité
        "id": "ID", "name": "Référence", "nom": "Nom",
        "code": "Code", "reference": "Référence", "ref": "Référence",
        # Véhicules / Bus
        "license_plate": "Immatriculation", "license_pla": "Immatriculation",
        "nom_bus": "Bus", "nom_vehicule": "Véhicule", "vehicle_name": "Bus",
        "etat": "État", "state": "État", "statut": "Statut",
        # Tournées
        "tournee_name": "Tournée", "date": "Date",
        "direction": "Direction",
        "heure_depart_prevu": "Départ prévu (h)",
        "heure_arrivee_prevu": "Arrivée prévue (h)",
        "heure_depart_reel": "Départ réel (h)",
        "heure_arrivee_reel": "Arrivée réelle (h)",
        "km_realise": "KM réalisés", "km_prevu": "KM prévus",
        "ecart_km": "Écart KM", "total_km": "Total KM",
        "driver_name": "Chauffeur", "nom_chauffeur": "Chauffeur",
        "chauffeur": "Chauffeur", "ligne": "Ligne", "bus": "Bus",
        "compteur_depart": "Compteur départ", "compteur_arrivee": "Compteur arrivée",
        # Assurance / Police
        "numero_police": "N° Police",
        "date_debut": "Date début", "date_fin": "Date fin",
        # Énergie / Factures
        "site": "Site / Agence",
        "type_facture": "Type", "type_energie": "Type énergie",
        "numero_compteur": "N° Compteur",
        "unite_mesure": "Unité",
        "date_debut_periode": "Début période",
        "date_fin_periode": "Fin période",
        "date_reception": "Date réception",
        "date_facture": "Date",
        "quantite_consommee": "Quantité consommée",
        "montant": "Montant (TND)", "montant_ttc": "Montant TTC",
        # Carburant
        "total_quantity": "Quantité (L)", "voucher_type": "Type bon",
        # Stations / Lignes
        "nom_station": "Station", "type_station": "Type station",
        "ville": "Ville", "agence_id": "Agence",
        # Patrimoine
        "cout_acquisition": "Coût acquisition",
        "valeur_nette_comptable": "Valeur nette",
        "amortissements_cumules": "Amort. cumulés",
        # Courrier
        "sujet": "Sujet", "expediteur": "Expéditeur",
        # Employés
        "job_title": "Poste", "active": "Actif",
    }

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
        affiche = STATUTS.get(v.lower(), v)
        return f"{label} : {affiche}"

    if nb == 1:
        # ── Détail unique : données pré-formatées → LLM pour mise en phrases ──
        valeurs = [v.strip() for v in lignes_data[0].split("|")]
        parties = []
        for j, col in enumerate(colonnes):
            if j >= len(valeurs):
                break
            ligne_fmt = _formater_valeur(col, valeurs[j])
            if ligne_fmt:
                parties.append(ligne_fmt)
        donnees_propres = "\n".join(parties)
        try:
            prompt = (
                f"Tu es un assistant ERP transport tunisien. "
                f"Réponds en français, style professionnel, 3-5 phrases.\n"
                f"Question : {question}\n"
                f"Données :\n{donnees_propres}\n"
                f"Présente ces informations naturellement. "
                f"N'invente rien. Commence par 'Voici les détails'."
            )
            rep = llm.invoke(prompt).strip()
            if rep and len(rep) > 20:
                return rep
        except Exception:
            pass
        # Fallback : affichage bullet si LLM échoue
        if parties:
            return "\n".join(f"• {p}" for p in parties)
        return donnees

    # ── Listes (≥2 lignes) : tableau numéroté ──
    reponse = f"**{nb} résultat(s) trouvé(s)** :\n\n"
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

def ask_agent(question: str, llm: OllamaLLM,
              allowed_tables: list = None,
              is_admin: bool = False,
              session_id: str = "default") -> str:
    try:
        acces_erreur = verifier_acces_question(question, allowed_tables, is_admin)
        if acces_erreur:
            return acces_erreur

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
                        return "Je n'ai pas pu récupérer ces données. Veuillez reformuler votre question."

            if not donnees.strip():
                return "Aucune donnée trouvée."

            reponse = formuler_reponse(question, donnees, llm)

        # -----------------------------------------------------------------
        # FIX 1 + FIX 4 — RPC dynamique avec timeout et fallback SQL
        # -----------------------------------------------------------------
        elif outil == "rpc":
            try:
                action = generer_action_rpc(question, llm)
                donnees = rpc_tool.invoke(action)

                if "Erreur RPC" in donnees or not donnees.strip():
                    _logger.warning("RPC échoué — fallback SQL")
                    requete = generer_sql(question, llm, allowed_tables, is_admin)
                    donnees = sql_tool.invoke(requete)

                reponse = formuler_reponse(question, donnees, llm)

            except Exception as e_rpc:
                _logger.warning(f"RPC exception: {e_rpc} — fallback SQL")
                try:
                    requete = generer_sql(question, llm, allowed_tables, is_admin)
                    donnees = sql_tool.invoke(requete)
                    reponse = formuler_reponse(question, donnees, llm)
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
                        reponse = _RAG_DEFAUT
                except Exception as e_rag:
                    _logger.warning(f"RAG exception: {e_rag}")
                    reponse = _RAG_DEFAUT

        # FIX 3 — Persistance SQLite
        sauvegarder_historique(session_id, question, reponse)
        return reponse

    except Exception as e:
        msg = str(e)
        _logger.error(f"Erreur ask_agent: {msg}")
        if "system memory" in msg or "memory" in msg.lower():
            return (
                "⚠️ Mémoire insuffisante pour traiter cette requête. "
                "Essayez une question plus simple ou redémarrez Ollama : `ollama stop` puis relancez."
            )
        return f"Erreur : {msg}"