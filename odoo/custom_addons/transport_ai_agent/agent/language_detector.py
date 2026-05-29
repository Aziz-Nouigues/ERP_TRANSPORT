# -*- coding: utf-8 -*-
"""
Détection de langue naturelle — 0 appel LLM, < 1ms
Supporte : français (fr), anglais (en), arabe (ar)
"""
import re
import unicodedata

# ── Mots-clés haute confiance par langue ─────────────────────────────────────

_MOTS_FR = {
    "combien", "liste", "quels", "quelle", "quelles", "donnez", "montrez",
    "afficher", "quel", "est-ce", "comment", "pourquoi", "planifier",
    "annuler", "valider", "créer", "modifier", "tournée", "véhicule",
    "chauffeur", "assurance", "carburant", "courrier", "immobilisation",
    "rapport", "bilan", "synthèse", "bonjour", "merci", "s'il", "voici",
    "de", "du", "des", "les", "une", "par", "sur", "avec", "dans",
    "pour", "tout", "tous", "état", "états",
}

_MOTS_EN = {
    "how", "many", "what", "which", "list", "show", "give", "get",
    "display", "create", "validate", "cancel", "plan", "assign",
    "vehicle", "driver", "insurance", "fuel", "report", "summary",
    "the", "and", "for", "with", "from", "that", "this", "are", "is",
    "hello", "please", "thank", "status", "trip", "bus",
    # Mots courants anglais manquants
    "incoming", "outgoing", "vs", "versus", "between", "compare",
    "total", "count", "number", "of", "in", "by", "per", "all",
    "active", "expired", "pending", "done", "my", "me", "can", "do",
    "sent", "received", "mail", "letter", "fleet", "maintenance",
    "breakdown", "service", "out", "monthly", "weekly", "daily",
    "consumption", "accident", "claim", "policy", "contract",
    "trend", "month", "evolution", "over", "time", "chart",
    "graph", "plot", "analysis", "analyze", "week", "year",
    "quarter", "history", "historical", "growth", "increase",
    "decrease", "average", "avg", "report", "summary", "data",
}

_MOTS_AR = {
    "كم", "ما", "ماذا", "اعرض", "قائمة", "أظهر", "أعطني", "كيف",
    "لماذا", "خطط", "إلغاء", "تأكيد", "إنشاء", "تعديل", "رحلة",
    "سيارة", "سائق", "تأمين", "وقود", "تقرير", "ملخص", "مرحبا",
    "شكرا", "حافلة", "الحافلة", "الحافلات", "الرحلة", "الرحلات",
    "عدد", "جميع", "كل", "هل", "من", "في", "على", "مع",
}

# ── Détection de script arabe ─────────────────────────────────────────────────

_ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')


def _ratio_arabe(texte: str) -> float:
    """Fraction de caractères arabes dans le texte."""
    if not texte:
        return 0.0
    chars_arabes = sum(1 for c in texte if '\u0600' <= c <= '\u06FF'
                       or '\u0750' <= c <= '\u077F')
    chars_total = sum(1 for c in texte if c.strip())
    return chars_arabes / chars_total if chars_total > 0 else 0.0


def detecter_langue(texte: str) -> str:
    """
    Détecte la langue d'un texte parmi : 'fr', 'en', 'ar'.
    Retourne 'fr' par défaut si ambiguïté.

    Algorithme :
    1. Script arabe détecté → 'ar' immédiatement
    2. Comptage de mots-clés par langue
    3. Tiebreak : 'fr' (langue ERP par défaut)
    """
    if not texte or not texte.strip():
        return "fr"

    texte_strip = texte.strip()

    # ── 1. Arabe — détection par script (ultra-fiable) ───────────────────────
    if _ratio_arabe(texte_strip) > 0.15:
        return "ar"

    # ── 2. Normaliser pour compter les mots ──────────────────────────────────
    texte_lower = texte_strip.lower()
    # Supprimer accents pour comparer (évite fr/en confusion)
    texte_norm = unicodedata.normalize("NFD", texte_lower)
    texte_norm = "".join(c for c in texte_norm if unicodedata.category(c) != "Mn")

    mots = set(re.findall(r'\b\w+\b', texte_norm))

    score_fr = sum(1 for m in mots if m in _MOTS_FR)
    score_en = sum(1 for m in mots if m in _MOTS_EN)

    # ── 3. Décision ──────────────────────────────────────────────────────────
    if score_en > score_fr:
        print(f"  [LANGUAGE_DETECTOR] '{texte[:30]}' → en (score_en={score_en}, score_fr={score_fr}, mots={mots})", flush=True)
        return "en"
    print(f"  [LANGUAGE_DETECTOR] '{texte[:30]}' → fr (score_en={score_en}, score_fr={score_fr}, mots={mots})", flush=True)
    return "fr"  # défaut ERP tunisien


# ── Traductions des réponses système ─────────────────────────────────────────

_MESSAGES = {
    "no_data": {
        "fr": "Aucune donnée trouvée pour cette question.",
        "en": "No data found for this question.",
        "ar": "لم يتم العثور على بيانات لهذا السؤال.",
    },
    "access_denied": {
        "fr": "Vous n'avez pas les droits d'accès pour consulter ces données.",
        "en": "You do not have access rights to view this data.",
        "ar": "ليس لديك صلاحية للوصول إلى هذه البيانات.",
    },
    "error_retry": {
        "fr": "Je n'ai pas pu récupérer ces données. Veuillez reformuler votre question.",
        "en": "I could not retrieve this data. Please rephrase your question.",
        "ar": "لم أتمكن من استرداد هذه البيانات. يرجى إعادة صياغة سؤالك.",
    },
    "error_memory": {
        "fr": "⚠️ Mémoire insuffisante pour traiter cette requête.",
        "en": "⚠️ Insufficient memory to process this request.",
        "ar": "⚠️ ذاكرة غير كافية لمعالجة هذا الطلب.",
    },
    "specify_record": {
        "fr": "Précise la référence de l'enregistrement à modifier.",
        "en": "Please specify the record reference to update.",
        "ar": "يرجى تحديد مرجع السجل المراد تعديله.",
    },
    "action_done": {
        "fr": "Action effectuée avec succès.",
        "en": "Action completed successfully.",
        "ar": "تمت العملية بنجاح.",
    },
    "report_ready": {
        "fr": "✅ Rapport prêt",
        "en": "✅ Report ready",
        "ar": "✅ التقرير جاهز",
    },
    "ask_question": {
        "fr": "Veuillez poser une question.",
        "en": "Please ask a question.",
        "ar": "يرجى طرح سؤال.",
    },
    "no_answer_found": {
        "fr": "Je n'ai pas trouvé d'information sur ce sujet dans la base de connaissances.",
        "en": "I did not find information on this topic in the knowledge base.",
        "ar": "لم أجد معلومات حول هذا الموضوع في قاعدة المعرفة.",
    },
    "greeting_fr": {
        "fr": "Bonjour ! Je suis votre assistant ERP Transport. Comment puis-je vous aider ?",
        "en": "Hello! I'm your Transport ERP assistant. How can I help you?",
        "ar": "مرحباً! أنا مساعد نظام إدارة النقل. كيف يمكنني مساعدتك؟",
    },
    "placeholder_incomplete": {
        "fr": "Les données sont incomplètes. Veuillez reformuler votre question.",
        "en": "The data is incomplete. Please rephrase your question.",
        "ar": "البيانات غير مكتملة. يرجى إعادة صياغة سؤالك.",
    },
}


def msg(cle: str, langue: str) -> str:
    """Retourne le message traduit, défaut français si manquant."""
    return _MESSAGES.get(cle, {}).get(langue) or _MESSAGES.get(cle, {}).get("fr", cle)


# ── Adaptation du prompt système selon la langue ─────────────────────────────

SYSTEM_PROMPT_MULTILINGUE = {
    "fr": """
Tu es un assistant IA intégré dans un ERP de transport terrestre tunisien développé sur Odoo 19.
Tu réponds TOUJOURS en français.
Tu es précis, concis et professionnel.

MODULES ERP :
1. fleet_etat_bus        — Parc de bus : états, historique, Kanban
2. transport_exploitation — Lignes, tournées, planification, feuilles de route
3. transport_assurance    — Polices bus/chauffeurs, sinistres
4. transport_energy       — Carburant (BGI/BGE), lubrifiants, cuves
5. transport_patrimoine   — Immobilisations, amortissements, inventaire
6. transport_boc          — Bureau d'ordre : courrier arrivée/départ

ÉTATS TOURNÉES : brouillon → planifie → en_cours → realise / annule
""",
    "en": """
You are an AI assistant integrated in a Tunisian terrestrial transport ERP built on Odoo 19.
You ALWAYS respond in English.
You are precise, concise and professional.

ERP MODULES:
1. fleet_etat_bus        — Bus fleet: statuses, history, Kanban
2. transport_exploitation — Lines, trips, planning, route sheets
3. transport_assurance    — Bus/driver insurance policies, claims
4. transport_energy       — Fuel (BGI/BGE), lubricants, tanks
5. transport_patrimoine   — Fixed assets, depreciation, inventory
6. transport_boc          — Mail management: incoming/outgoing

TRIP STATES: draft → planned → in_progress → done / cancelled
""",
    "ar": """
أنت مساعد ذكاء اصطناعي مدمج في نظام ERP لشركة نقل بري تونسية مبني على Odoo 19.
تجيب دائماً باللغة العربية.
أنت دقيق وموجز ومحترف.

وحدات النظام:
1. fleet_etat_bus        — أسطول الحافلات: الحالات، السجل، كانبان
2. transport_exploitation — الخطوط، الرحلات، التخطيط، صحائف الطريق
3. transport_assurance    — بوليصات التأمين، المطالبات
4. transport_energy       — الوقود (BGI/BGE)، المزلقات، الخزانات
5. transport_patrimoine   — الأصول الثابتة، الاستهلاك، الجرد
6. transport_boc          — إدارة البريد: الوارد والصادر

حالات الرحلة: مسودة ← مخططة ← قيد التنفيذ ← منجزة / ملغاة
""",
}


def get_system_prompt(langue: str) -> str:
    """Retourne le prompt système dans la langue demandée."""
    return SYSTEM_PROMPT_MULTILINGUE.get(langue, SYSTEM_PROMPT_MULTILINGUE["fr"])


# ── Mots-clés métier traduits pour la détection d'outil ─────────────────────

TABLES_METIER_EN = {
    # Bus / Fleet
    "bus":             ["fleet_vehicle", "transport_assurance_bus"],
    "vehicle":         ["fleet_vehicle"],
    "fleet":           ["fleet_vehicle"],
    "registration":    ["fleet_vehicle"],
    "status":          ["fleet_vehicle", "fleet_vehicle_state"],
    "history":         ["fleet_vehicle", "fleet_vehicle_state"],
    "odometer":        ["fleet_vehicle_odometer", "fleet_vehicle"],
    "mileage":         ["fleet_vehicle_odometer", "fleet_vehicle"],
    # Assurance
    "insurance":       ["transport_assurance_bus", "fleet_vehicle"],
    "policy":          ["transport_assurance_bus", "fleet_vehicle"],
    "claim":           ["transport_assurance_sinistre"],
    "accident":        ["transport_assurance_sinistre"],
    # Exploitation
    "trip":            ["transport_exploitation_tournee"],
    "trips":           ["transport_exploitation_tournee"],
    "route":           ["transport_exploitation_tournee"],
    "planned":         ["transport_exploitation_tournee"],
    "completed":       ["transport_exploitation_tournee"],
    "line":            ["transport_exploitation_ligne"],
    "driver":          ["hr_employee", "transport_assurance_chauffeur"],
    "employee":        ["hr_employee"],
    # Carburant
    "fuel":            ["transport_fuel_voucher", "transport_fuel_station"],
    "voucher":         ["transport_fuel_voucher"],
    "tank":            ["transport_fuel_cuve"],
    "station":         ["transport_exploitation_station", "transport_fuel_station"],
    "lubricant":       ["transport_bon_lubrifiant"],
    "oil":             ["transport_bon_lubrifiant"],
    # Patrimoine
    "asset":           ["patrimoine_immobilisation"],
    "depreciation":    ["patrimoine_immobilisation"],
    "inventory":       ["patrimoine_inventaire"],
    # BOC
    "mail":            ["boc_courrier_arrivee", "boc_courrier_depart"],
    "letter":          ["boc_courrier_arrivee", "boc_courrier_depart"],
    "incoming":        ["boc_courrier_arrivee"],
    "outgoing":        ["boc_courrier_depart"],
    # Énergie
    "invoice":         ["transport_facture_energie"],
    "electricity":     ["transport_facture_energie"],
    "water":           ["transport_facture_energie"],
    "energy":          ["transport_facture_energie"],
}

TABLES_METIER_AR = {
    # Bus / Fleet
    "حافلة":        ["fleet_vehicle", "transport_assurance_bus"],
    "حافلات":       ["fleet_vehicle"],
    "سيارة":        ["fleet_vehicle"],
    "أسطول":        ["fleet_vehicle"],
    "لوحة":         ["fleet_vehicle"],
    "حالة":         ["fleet_vehicle", "fleet_vehicle_state"],
    "عداد":         ["fleet_vehicle_odometer"],
    "مسافة":        ["fleet_vehicle_odometer"],
    # Assurance
    "تأمين":        ["transport_assurance_bus"],
    "بوليصة":       ["transport_assurance_bus"],
    "حادث":         ["transport_assurance_sinistre"],
    "مطالبة":       ["transport_assurance_sinistre"],
    # Exploitation
    "رحلة":         ["transport_exploitation_tournee"],
    "رحلات":        ["transport_exploitation_tournee"],
    "خط":           ["transport_exploitation_ligne"],
    "محطة":         ["transport_exploitation_station"],
    "سائق":         ["hr_employee", "transport_assurance_chauffeur"],
    "موظف":         ["hr_employee"],
    # Carburant
    "وقود":         ["transport_fuel_voucher", "transport_fuel_station"],
    "خزان":         ["transport_fuel_cuve"],
    "وصل":          ["transport_fuel_voucher"],
    # Patrimoine
    "أصول":         ["patrimoine_immobilisation"],
    "استهلاك":      ["patrimoine_immobilisation"],
    "جرد":          ["patrimoine_inventaire"],
    # BOC
    "بريد":         ["boc_courrier_arrivee", "boc_courrier_depart"],
    "مراسلة":       ["boc_courrier_arrivee", "boc_courrier_depart"],
    "وارد":         ["boc_courrier_arrivee"],
    "صادر":         ["boc_courrier_depart"],
    # Énergie
    "فاتورة":       ["transport_facture_energie"],
    "كهرباء":       ["transport_facture_energie"],
    "ماء":          ["transport_facture_energie"],
    "طاقة":         ["transport_facture_energie"],
}

# ── Labels de colonnes traduits pour l'affichage ─────────────────────────────

LABELS_COLONNES = {
    "fr": {
        "id": "ID", "name": "Référence", "nom": "Nom",
        "code": "Code", "reference": "Référence", "ref": "Référence",
        "license_plate": "Immatriculation", "license_pla": "Immatriculation",
        "nom_bus": "Bus", "nom_vehicule": "Véhicule", "vehicle_name": "Bus",
        "etat": "État", "state": "État", "statut": "Statut",
        "tournee_name": "Tournée", "date": "Date", "direction": "Direction",
        "heure_depart_prevu": "Départ prévu (h)", "heure_arrivee_prevu": "Arrivée prévue (h)",
        "heure_depart_reel": "Départ réel (h)", "heure_arrivee_reel": "Arrivée réelle (h)",
        "km_realise": "KM réalisés", "km_prevu": "KM prévus",
        "ecart_km": "Écart KM", "total_km": "Total KM",
        "driver_name": "Chauffeur", "nom_chauffeur": "Chauffeur",
        "chauffeur": "Chauffeur", "ligne": "Ligne", "bus": "Bus",
        "compteur_depart": "Compteur départ", "compteur_arrivee": "Compteur arrivée",
        "numero_police": "N° Police", "date_debut": "Date début", "date_fin": "Date fin",
        "site": "Site / Agence", "type_facture": "Type", "type_energie": "Type énergie",
        "numero_compteur": "N° Compteur", "unite_mesure": "Unité",
        "date_debut_periode": "Début période", "date_fin_periode": "Fin période",
        "date_reception": "Date réception", "date_facture": "Date",
        "quantite_consommee": "Quantité consommée",
        "montant": "Montant (TND)", "montant_ttc": "Montant TTC",
        "total_quantity": "Quantité (L)", "voucher_type": "Type bon",
        "nom_station": "Station", "type_station": "Type station",
        "ville": "Ville", "agence_id": "Agence",
        "cout_acquisition": "Coût acquisition", "valeur_nette_comptable": "Valeur nette",
        "amortissements_cumules": "Amort. cumulés",
        "sujet": "Sujet", "expediteur": "Expéditeur",
        "job_title": "Poste", "active": "Actif",
    },
    "en": {
        "id": "ID", "name": "Reference", "nom": "Name",
        "code": "Code", "reference": "Reference", "ref": "Reference",
        "license_plate": "Plate number", "license_pla": "Plate number",
        "nom_bus": "Bus", "nom_vehicule": "Vehicle", "vehicle_name": "Bus",
        "etat": "Status", "state": "Status", "statut": "Status",
        "tournee_name": "Trip", "date": "Date", "direction": "Direction",
        "heure_depart_prevu": "Planned departure", "heure_arrivee_prevu": "Planned arrival",
        "heure_depart_reel": "Actual departure", "heure_arrivee_reel": "Actual arrival",
        "km_realise": "Actual KM", "km_prevu": "Planned KM",
        "ecart_km": "KM deviation", "total_km": "Total KM",
        "driver_name": "Driver", "nom_chauffeur": "Driver",
        "chauffeur": "Driver", "ligne": "Line", "bus": "Bus",
        "compteur_depart": "Start odometer", "compteur_arrivee": "End odometer",
        "numero_police": "Policy N°", "date_debut": "Start date", "date_fin": "End date",
        "site": "Site / Agency", "type_facture": "Type", "type_energie": "Energy type",
        "numero_compteur": "Meter N°", "unite_mesure": "Unit",
        "date_debut_periode": "Period start", "date_fin_periode": "Period end",
        "date_reception": "Receipt date", "date_facture": "Date",
        "quantite_consommee": "Quantity consumed",
        "montant": "Amount (TND)", "montant_ttc": "Total amount",
        "total_quantity": "Quantity (L)", "voucher_type": "Voucher type",
        "nom_station": "Station", "type_station": "Station type",
        "ville": "City", "agence_id": "Agency",
        "cout_acquisition": "Acquisition cost", "valeur_nette_comptable": "Net value",
        "amortissements_cumules": "Cumul. depreciation",
        "sujet": "Subject", "expediteur": "Sender",
        "job_title": "Position", "active": "Active",
    },
    "ar": {
        "id": "المعرف", "name": "المرجع", "nom": "الاسم",
        "code": "الرمز", "reference": "المرجع", "ref": "المرجع",
        "license_plate": "رقم اللوحة", "license_pla": "رقم اللوحة",
        "nom_bus": "الحافلة", "nom_vehicule": "المركبة", "vehicle_name": "الحافلة",
        "etat": "الحالة", "state": "الحالة", "statut": "الحالة",
        "tournee_name": "الرحلة", "date": "التاريخ", "direction": "الاتجاه",
        "heure_depart_prevu": "وقت الانطلاق المخطط", "heure_arrivee_prevu": "وقت الوصول المخطط",
        "heure_depart_reel": "وقت الانطلاق الفعلي", "heure_arrivee_reel": "وقت الوصول الفعلي",
        "km_realise": "الكم المنجز", "km_prevu": "الكم المخطط",
        "ecart_km": "فارق الكم", "total_km": "مجموع الكم",
        "driver_name": "السائق", "nom_chauffeur": "السائق",
        "chauffeur": "السائق", "ligne": "الخط", "bus": "الحافلة",
        "compteur_depart": "العداد عند الانطلاق", "compteur_arrivee": "العداد عند الوصول",
        "numero_police": "رقم البوليصة", "date_debut": "تاريخ البداية", "date_fin": "تاريخ النهاية",
        "site": "الموقع / الوكالة", "type_facture": "النوع", "type_energie": "نوع الطاقة",
        "numero_compteur": "رقم العداد", "unite_mesure": "الوحدة",
        "date_debut_periode": "بداية الفترة", "date_fin_periode": "نهاية الفترة",
        "date_reception": "تاريخ الاستلام", "date_facture": "التاريخ",
        "quantite_consommee": "الكمية المستهلكة",
        "montant": "المبلغ (دينار)", "montant_ttc": "المبلغ الإجمالي",
        "total_quantity": "الكمية (لتر)", "voucher_type": "نوع الوصل",
        "nom_station": "المحطة", "type_station": "نوع المحطة",
        "ville": "المدينة", "agence_id": "الوكالة",
        "cout_acquisition": "تكلفة الاقتناء", "valeur_nette_comptable": "القيمة الصافية",
        "amortissements_cumules": "الاستهلاك المتراكم",
        "sujet": "الموضوع", "expediteur": "المرسل",
        "job_title": "المنصب", "active": "نشط",
    },
}

# ── Statuts traduits ──────────────────────────────────────────────────────────

STATUTS_TRADUITS = {
    "fr": {
        "realise": "✅ Réalisée", "planifie": "📅 Planifiée",
        "en_cours": "🔄 En cours", "annule": "❌ Annulée",
        "brouillon": "📝 Brouillon", "active": "✅ Active",
        "payee": "✅ Payée", "saisie": "📝 Saisie",
        "internal": "🏠 BGI (Interne)", "external": "🏢 BGE (Externe)",
        "true": "✅ Oui", "false": "❌ Non",
    },
    "en": {
        "realise": "✅ Completed", "planifie": "📅 Planned",
        "en_cours": "🔄 In progress", "annule": "❌ Cancelled",
        "brouillon": "📝 Draft", "active": "✅ Active",
        "payee": "✅ Paid", "saisie": "📝 Entered",
        "internal": "🏠 BGI (Internal)", "external": "🏢 BGE (External)",
        "true": "✅ Yes", "false": "❌ No",
        # Odoo text values
        "en service": "✅ In service", "hors service": "🔴 Out of service",
        "en panne": "⚠️ Broken down", "en maintenance": "🔧 Under maintenance",
        "réformé": "🗑️ Decommissioned",
        "réalisée": "✅ Completed", "planifiée": "📅 Planned",
        "annulée": "❌ Cancelled", "en cours": "🔄 In progress",
        "expirée": "❌ Expired", "résiliée": "🚫 Terminated",
        "payée": "✅ Paid", "validée": "✔️ Validated",
    },
    "ar": {
        "realise": "✅ منجزة", "planifie": "📅 مخططة",
        "en_cours": "🔄 قيد التنفيذ", "annule": "❌ ملغاة",
        "brouillon": "📝 مسودة", "active": "✅ نشطة",
        "payee": "✅ مدفوعة", "saisie": "📝 مسجلة",
        "internal": "🏠 BGI (داخلي)", "external": "🏢 BGE (خارجي)",
        "true": "✅ نعم", "false": "❌ لا",
        # Valeurs textuelles Odoo (affichées directement)
        "en service": "✅ في الخدمة", "hors service": "🔴 خارج الخدمة",
        "en panne": "⚠️ في عطل", "en maintenance": "🔧 في الصيانة",
        "réformé": "🗑️ مُصلَح", "reformé": "🗑️ مُصلَح",
        "réalisée": "✅ منجزة", "planifiée": "📅 مخططة",
        "annulée": "❌ ملغاة", "en cours": "🔄 قيد التنفيذ",
        "active": "✅ نشطة", "expirée": "❌ منتهية", "résiliée": "🚫 ملغاة",
        "payée": "✅ مدفوعة", "validée": "✔️ مُصادق عليها",
        "enregistré": "📝 مسجل", "classé": "✔️ مُؤرشَف",
    },
}

# ── Gabarits COUNT traduits ───────────────────────────────────────────────────

GABARITS_COUNT = {
    "fr": [
        (r"combien.*(bus|véhicul|vehicul)", "Il y a **{v}** bus dans le parc."),
        (r"combien.*(tournee|tournée)",     "Il y a **{v}** tournée(s) enregistrée(s)."),
        (r"combien.*(chauffeur|conducteur)","Il y a **{v}** chauffeur(s) enregistré(s)."),
        (r"combien.*(sinistre|accident)",   "Il y a **{v}** sinistre(s) enregistré(s)."),
        (r"combien.*(station)",             "Il y a **{v}** station(s) enregistrée(s)."),
        (r"total.*(km|kilomet)",            "Le kilométrage total est de **{v}** km."),
        (r"total.*(litre|carburant)",       "La quantité totale est de **{v}** litres."),
        (r"total.*(montant|facture)",       "Le montant total est de **{v}** TND."),
    ],
    "en": [
        (r"how many.*(bus|vehicle|fleet)",  "There are **{v}** buses in the fleet."),
        (r"how many.*(trip|route)",         "There are **{v}** trip(s) recorded."),
        (r"how many.*(driver|employee)",    "There are **{v}** driver(s) registered."),
        (r"how many.*(claim|accident)",     "There are **{v}** claim(s) recorded."),
        (r"how many.*(station)",            "There are **{v}** station(s) registered."),
        (r"total.*(km|mileage)",            "Total mileage is **{v}** km."),
        (r"total.*(liter|fuel)",            "Total quantity is **{v}** liters."),
        (r"total.*(amount|invoice)",        "Total amount is **{v}** TND."),
    ],
    "ar": [
        (r"كم.*(حافلة|سيارة|أسطول)",      "يوجد **{v}** حافلة في الأسطول."),
        (r"كم.*(رحلة)",                    "يوجد **{v}** رحلة مسجلة."),
        (r"كم.*(سائق|موظف)",              "يوجد **{v}** سائق مسجل."),
        (r"كم.*(حادث|مطالبة)",            "يوجد **{v}** حادث مسجل."),
        (r"كم.*(محطة)",                   "يوجد **{v}** محطة مسجلة."),
        (r"مجموع.*(كم|مسافة)",             "إجمالي المسافة **{v}** كيلومتر."),
        (r"مجموع.*(لتر|وقود)",             "الكمية الإجمالية **{v}** لتر."),
        (r"مجموع.*(مبلغ|فاتورة)",          "المبلغ الإجمالي **{v}** دينار."),
    ],
}