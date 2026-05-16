import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv
from langchain_ollama import OllamaLLM

from agent.tools.sql_tool import sql_tool, get_pg_connection
from agent.tools.rpc_tool import rpc_tool
from agent.tools.rag_tool import rag_tool
from agent.prompts import SYSTEM_PROMPT

load_dotenv(Path(__file__).parent.parent / ".env")

_logger = logging.getLogger(__name__)

HISTORIQUE = {}

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
    # ── Factures énergie : TOUJOURS transport_facture_energie ──
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
    # ── Comptabilité générale uniquement ──
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

# Catalogue complet des tables avec description métier
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
    # Essayer le LLM en premier si disponible
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
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        schema = ""
        tables_chargees = 0
        for table in sorted(set(tables)):
            try:
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                    AND column_name NOT IN (
                        'create_uid', 'write_uid', 'create_date', 'write_date'
                    )
                    ORDER BY ordinal_position
                """, (table,))
                cols = cur.fetchall()
                if not cols:
                    _logger.warning(f"Table '{table}' absente de PostgreSQL")
                    continue
                col_desc = [f"{c[0]}({c[1][:8]})" for c in cols]
                cur.execute(f"SELECT * FROM {table} LIMIT 1")
                sample = cur.fetchone()
                sample_str = ""
                if sample and cur.description:
                    for i, desc in enumerate(cur.description):
                        val = sample[i]
                        if val is not None and str(val).strip():
                            sample_str += f"{desc[0]}={repr(str(val)[:20])} "
                schema += f"\nTABLE: {table}\n"
                schema += f"COLUMNS: {', '.join(col_desc)}\n"
                if sample_str:
                    schema += f"SAMPLE: {sample_str[:250]}\n"
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
# DÉTECTION D'OUTIL
# ---------------------------------------------------------------------------

def detecter_outil(question: str, llm: OllamaLLM) -> str:
    prompt = (
        "Classify this question with ONE word only: sql, rag, or rpc\n"
        "sql = data query (list, count, details, statistics)\n"
        "rag = definition, procedure, rule, how-to\n"
        "rpc = action (create, modify, validate)\n"
        f"Question: {question}\n"
        "Answer (one word):"
    )
    try:
        reponse = llm.invoke(prompt).strip().lower()
        first_word = reponse.split()[0] if reponse.split() else "sql"
        if "rpc" in first_word:
            return "rpc"
        elif "rag" in first_word:
            return "rag"
        return "sql"
    except Exception:
        return "sql"

# ---------------------------------------------------------------------------
# GÉNÉRATION SQL
# ---------------------------------------------------------------------------

def generer_sql(question: str, llm: OllamaLLM,
                allowed_tables: list = None,
                is_admin: bool = False,
                diagnostic_extra: str = "") -> str:

    tables_pertinentes = detecter_tables_pertinentes(question, llm)
    schema = charger_schema_tables(tables_pertinentes)
    _logger.info(f"Tables injectées dans le prompt: {tables_pertinentes}")
    print(f"  -> Tables pertinentes: {tables_pertinentes}")

    prompt = (
        "You are a PostgreSQL expert for an Odoo 19 transport ERP in Tunisia.\n"
        "Generate ONLY the SQL SELECT query. No explanation. No markdown. No comments.\n\n"
        "AVAILABLE TABLES (use ONLY these — loaded live from PostgreSQL):\n"
        f"{schema}\n"
        f"{diagnostic_extra}\n"
        "BUSINESS RULES:\n"
        "  [BUSES] fleet_vehicle has 3 buses. COUNT(*) needs NO WHERE filter.\n"
        "    To list all buses with plate: SELECT name, license_plate FROM fleet_vehicle\n"
        "    NEVER add WHERE clause when listing all buses.\n"
        "    state_id values: 47='En service', 48='Hors service', 49='Réformé'\n"
        "    CORRECT state query: SELECT v.name, v.license_plate, s.name AS etat\n"
        "      FROM fleet_vehicle v LEFT JOIN fleet_vehicle_state s ON v.state_id = s.id\n"
        "      WHERE v.license_plate ILIKE '%123 TU 456%'\n"
        "    fleet_vehicle_state.name is jsonb: use COALESCE(s.name->>'fr_FR', s.name->>'en_US')\n"
        "    No columns: date_arrivee, type_vehicule, activity_type, vehicle_type.\n"
        "  [ASSURANCE] transport_assurance_bus.state: active, expire, resilie, brouillon.\n"
        "    is_obligatoire is false for ALL records — never filter by it.\n"
        "    Insured buses: JOIN fleet_vehicle v ON a.vehicle_id = v.id WHERE a.state = 'active'\n"
        "  [TOURNEES] state: brouillon, planifie, en_cours, realise, annule.\n"
        "  [EMPLOYES] table name is hr_employee (NOT employe, NOT employees).\n"
        "    JOIN: hr_employee e ON a.employe_id = e.id\n"
        "    km columns: km_realise(actual km), km_prevu(planned), ecart_km(diff).\n"
        "    For km bus query: SUM(km_realise) grouped by vehicle. NEVER use compteur_depart/arrivee.\n"
        "    Filter by state='realise' for completed trips only.\n"
        "  [CARBURANT] transport_fuel_voucher: voucher_type='internal'=BGI, 'external'=BGE.\n"
        "    Quantity column: total_quantity. Never use placeholder names.\n"
        "  [ENERGIE/STEG/SONEDE] transport_facture_energie is THE ONLY table for energy invoices.\n"
        "    NEVER use account_move for STEG/SONEDE — it contains ONLY general accounting.\n"
        "    type_facture: 'steg' or 'sonede' (NOT type_energie).\n"
        "    statut: 'saisie', 'payee', 'validee' (NOT state).\n"
        "    REAL column names: name, type_facture, statut, site, numero_compteur,\n"
        "      unite_mesure, date_debut_periode, date_fin_periode, date_reception,\n"
        "      quantite_consommee, montant.\n"
        "    NEVER filter by statut unless user explicitly asks — show ALL by default.\n"
        "    CORRECT STEG query: SELECT name, site, numero_compteur,\n"
        "      quantite_consommee, unite_mesure, montant, statut, date_reception\n"
        "      FROM transport_facture_energie WHERE type_facture = 'steg'\n"
        "      ORDER BY date_reception DESC -- NO statut filter unless asked\n"
        "  [PATRIMOINE] patrimoine_immobilisation.statut: 'en_service', 'cede'.\n"
        "    name is jsonb: COALESCE(name->>'fr_FR', name->>'en_US') AS nom.\n"
        "  [STATIONS EXPLOITATION] transport_exploitation_station: 54 stations.\n"
        "    type_station values: 'intermediaire', 'terminus'\n"
        "    'gares' = all stations (no type filter). 'terminus' = type_station='terminus'\n"
        "    name is jsonb: COALESCE(name->>'fr_FR', name->>'en_US') AS nom\n"
        "    ville is jsonb: COALESCE(ville->>'fr_FR', ville->>'en_US') AS ville\n"
        "    For ALL stations: SELECT id, COALESCE(name->>'fr_FR',name->>'en_US') AS nom,\n"
        "      type_station, COALESCE(ville->>'fr_FR',ville->>'en_US') AS ville\n"
        "      FROM transport_exploitation_station ORDER BY nom\n"
        "    NEVER filter by active unless user asks for active/inactive.\n"
        "    Columns: code, name(jsonb), type_station, ville(jsonb), agence_id.\n"
        "    Count: SELECT COUNT(*) FROM transport_exploitation_station\n"
        "  [STATIONS CARBURANT] transport_fuel_station: fuel stations only.\n"
        "  [BOC] boc_courrier_arrivee.date_arrivee is timestamp.\n"
        "    boc_courrier_depart.state: 'enregistre', 'classe'.\n"
        "  [FUEL STATION] transport_fuel_station.name is jsonb.\n"
        "    JOIN: transport_fuel_station s ON fv.station_id = s.id\n"
        "CRITICAL RULES:\n"
        "1. Use ONLY columns listed in COLUMNS above. Never invent columns.\n"
        "2. ->> works ONLY on jsonb typed columns. NEVER on integer/date/numeric/boolean.\n"
        "3. Never filter by state unless user explicitly asks for a specific state.\n"
        "4. ILIKE for text searches. LIMIT 50 for lists, no LIMIT for COUNT.\n"
        "5. Always use table aliases. No accents in table names.\n"
        "   Always use LEFT JOIN for optional relations (chauffeur_id, vehicle_id may be NULL).\n"
        "   Use INNER JOIN only when the relation is guaranteed to exist.\n"
        "6. DATE: EXTRACT(MONTH FROM col)=EXTRACT(MONTH FROM CURRENT_DATE) for this month.\n"
        "7. Never use bracket placeholders like [total_litres] in SQL.\n\n"
        f"Question (French): {question}\n\nSQL:"
    )

    sql = llm.invoke(prompt).strip()
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
        # Avec alias (v.type_vehicule)
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
# FORMULATION DE LA RÉPONSE
# ---------------------------------------------------------------------------

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

    # Cas COUNT/SUM — une seule valeur
    if len(colonnes) == 1:
        valeur = lignes_data[0].strip() if lignes_data else "?"
        # Demander au LLM de formuler une phrase naturelle
        try:
            prompt = (
                f"Question posée : {question}\n"
                f"Résultat : {valeur}\n"
                "Formule une réponse courte et naturelle en français (1 phrase). "
                "Utilise le chiffre exact. Pas de markdown. Réponse :"
            )
            rep = llm.invoke(prompt).strip()
            if rep and len(rep) > 5 and len(rep) < 200:
                return rep
        except Exception:
            pass
        return f"Le résultat est : **{valeur}**"

    # Cas liste courte (≤5 résultats) — LLM pour mise en forme naturelle
    if nb <= 5:
        try:
            prompt = (
                f"Tu es un assistant ERP transport tunisien. Réponds en français.\n"
                "IMPORTANT: tournee=tournée de bus (jamais tournoi sportif). chauffeur=conducteur de bus.\n"
                f"Question : {question}\n"
                f"Données (colonnes: {', '.join(colonnes)}):\n{donnees}\n"
                f"Présente ces {nb} résultat(s) de façon claire et professionnelle. "
                "Utilise des labels français lisibles. Sans noms de tables SQL. Réponse :"
            )
            rep = llm.invoke(prompt).strip()
            if rep and len(rep) > 10:
                return rep
        except Exception:
            pass

    # Cas liste longue (>5) — formatage Python rapide
    # Mapping noms techniques -> noms lisibles en français
    LABELS = {
        "name": "Nom", "nom": "Nom", "id": "ID",
        "site": "Site / Agence", "site_agence": "Site / Agence",
        "numero_compteur": "N° Compteur",
        "quantite_consommee": "Quantité", "unite_mesure": "Unité",
        "montant": "Montant (TND)", "montant_ttc": "Montant TTC",
        "statut": "Statut", "state": "État",
        "date_reception": "Date", "date_facture": "Date",
        "date_debut_periode": "Début période", "date_fin_periode": "Fin période",
        "type_facture": "Type", "type_energie": "Type énergie",
        "license_plate": "Immatriculation", "license_pla": "Immatriculation",
        "nom_bus": "Bus", "nom_vehicule": "Véhicule",
        "numero_police": "N° Police",
        "date_debut": "Date début", "date_fin": "Date fin",
        "nom_chauffeur": "Chauffeur", "nom_station": "Station",
        "total_quantity": "Quantité (L)", "total_km": "Total KM",
        "km_realise": "KM réalisés", "km_prevu": "KM prévus",
        "ecart_km": "Écart KM",
        "sujet": "Sujet", "expediteur": "Expéditeur",
        "reference": "Référence", "ref": "Référence",
        "legal_name": "Nom légal", "login": "Login",
        "code": "Code", "active": "Actif",
        "type_station": "Type de station", "ville": "Ville",
        "agence_id": "Agence",

        "cout_acquisition": "Coût acquisition",
        "valeur_nette_comptable": "Valeur nette",
        "amortissements_cumules": "Amort. cumulés",
    }

    STATUTS = {
        "payee": "✅ Payée", "saisie": "📝 Saisie", "validee": "✔️ Validée",
        "active": "✅ Active", "expire": "❌ Expirée", "resilie": "🚫 Résiliée",
        "brouillon": "📝 Brouillon", "planifie": "📅 Planifiée",
        "realise": "✅ Réalisée", "annule": "❌ Annulée", "en_cours": "🔄 En cours",
        "enregistre": "📝 Enregistré", "classe": "✔️ Classé",
        "en_service": "✅ En service", "cede": "🔄 Cédé",
        "draft": "📝 Brouillon", "posted": "✅ Validée", "cancel": "❌ Annulée",
    }

    nb = len(lignes_data)
    reponse = f"**{nb} résultat(s) trouvé(s)** :\n\n"
    for i, ligne in enumerate(lignes_data, 1):
        valeurs = [v.strip() for v in ligne.split("|")]
        reponse += f"**{i}.** "
        parties = []
        for j, col in enumerate(colonnes):
            if j >= len(valeurs):
                break
            val = valeurs[j].strip()
            if not val or val == "—":
                continue
            label = LABELS.get(col.lower(), col.replace("_", " ").title())
            # Traduire les statuts
            val_affiche = STATUTS.get(val.lower(), val)
            parties.append(f"{label} : {val_affiche}")
        reponse += "  |  ".join(parties) + "\n"

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


def ask_agent(question: str, llm: OllamaLLM,
              allowed_tables: list = None,
              is_admin: bool = False,
              session_id: str = "default") -> str:
    global HISTORIQUE
    try:
        acces_erreur = verifier_acces_question(question, allowed_tables, is_admin)
        if acces_erreur:
            return acces_erreur

        outil = detecter_outil(question, llm)
        _logger.info(f"Outil: {outil} | Admin: {is_admin}")
        print(f"  -> Outil : {outil} | Admin : {is_admin}")

        if outil == "sql":
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

        elif outil == "rpc":
            donnees = rpc_tool.invoke(
                'transport.exploitation.tournee|search_read|[]|["name","date","state"]'
            )
            reponse = formuler_reponse(question, donnees, llm)
        else:
            donnees = rag_tool.invoke(question)
            reponse = llm.invoke(
                f"Réponds en français à partir de ces informations:\n{donnees}\n"
                f"Question: {question}"
            ).strip()

        if session_id not in HISTORIQUE:
            HISTORIQUE[session_id] = []
        HISTORIQUE[session_id].append({"question": question, "reponse": reponse})
        if len(HISTORIQUE[session_id]) > 10:
            HISTORIQUE[session_id].pop(0)

        return reponse

    except Exception as e:
        _logger.error(f"Erreur ask_agent: {e}")
        return f"Erreur : {str(e)}"