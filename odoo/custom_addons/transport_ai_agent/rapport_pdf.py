"""
rapport_pdf.py v3 — Design professionnel avec KPI cards + synthèse analytique
Points positifs / Points d'attention générés automatiquement depuis les données SQL
"""
from pathlib import Path
from datetime import date, datetime


# ---------------------------------------------------------------------------
# SUPPORT ARABE — reshaping + bidi
# ---------------------------------------------------------------------------

def _ar2(text: str) -> str:
    """
    Prépare le texte arabe pour ReportLab :
    - arabic_reshaper : connecte les lettres correctement
    - get_display (bidi) : inverse l'ordre pour l'affichage LTR de ReportLab
    Retourne le texte inchangé si ce n'est pas de l'arabe ou si libs absentes.
    """
    if not text or not any('؀' <= c <= 'ۿ' for c in text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except ImportError:
        return text


def _ar_cell(val) -> str:
    """Applique _ar2() sur une valeur de cellule (str ou autre)."""
    if isinstance(val, str):
        return _ar2(val)
    return val


# ---------------------------------------------------------------------------
# ANALYSE CONTEXTUELLE
# ---------------------------------------------------------------------------

def _analyser_rapport(type_rapport: str, data: dict, langue: str = "fr") -> tuple:
    """
    Retourne (points_positifs, points_attention) selon le type de rapport et les données.
    """
    positifs   = []
    attentions = []

    # Messages multilingues
    _M = {
        "fr": {
            # Assurance
            "ass_ok":      lambda a: f"{a} police(s) d'assurance active(s) — couverture du parc assurée.",
            "ass_stable":  "Aucune police en état d'alerte, expirée ou résiliée — stabilité contractuelle optimale.",
            "ass_0sin":    "Aucun sinistre enregistré ce mois — excellent bilan sécurité routière.",
            "ass_alerte":  lambda a: f"{a} police(s) en état d'alerte — renouvellement urgent requis.",
            "ass_exp":     lambda a: f"{a} police(s) expirée(s) — des bus circulent sans couverture active.",
            "ass_res":     lambda a: f"{a} police(s) résiliée(s) — vérifier la couverture des véhicules concernés.",
            "ass_sin":     lambda s,m: f"{s} sinistre(s) déclaré(s) ce mois pour un montant de {m} — analyser les causes.",
            "ass_exp30":   lambda n: f"{n} police(s) expirant dans les 30 prochains jours — planifier les renouvellements.",
            # Parc
            "parc_taux_ok":  lambda t,e,tot: f"Taux de disponibilité du parc : {t}% ({e}/{tot} bus en service) — niveau satisfaisant.",
            "parc_ass_ok":   "Tous les bus disposent d'une police d'assurance active.",
            "parc_sain":     "Aucun bus en panne ni en maintenance — parc en excellente condition opérationnelle.",
            "parc_taux_ko":  lambda t: f"Taux de disponibilité à {t}% — en dessous du seuil recommandé de 80%.",
            "parc_panne":    lambda n: f"{n} bus en panne — mobiliser la maintenance pour réduire l'immobilisation.",
            "parc_maint":    lambda n: f"{n} bus en maintenance — vérifier les délais de remise en service.",
            "parc_hors":     lambda n: f"{n} bus hors service — évaluer si une remise en état ou une réforme est nécessaire.",
            # Tournées
            "tour_real_ok":  lambda t,r,tot: f"Taux de réalisation : {t}% ({r}/{tot} tournées) — performance opérationnelle élevée.",
            "tour_0ann":     "Aucune tournée annulée — continuité du service assurée.",
            "tour_ecart_ok": lambda e: f"Écart kilométrique moyen de {e:.1f} km — planification conforme au terrain.",
            "tour_real_ko":  lambda t: f"Taux de réalisation à {t}% — identifier et corriger les causes de non-réalisation.",
            "tour_ann":      lambda n: f"{n} tournée(s) annulée(s) — analyser les motifs et prendre des mesures correctives.",
            "tour_ecart_ko": lambda e: f"Écart kilométrique moyen de {e:.1f} km — revoir la planification des itinéraires.",
            # Carburant
            "carb_ok":       lambda v,l: f"{v} bon(s) carburant validé(s) ce mois — consommation totale : {l:,.0f} litres.",
            "carb_bgi_ok":   lambda bi,be: f"Majorité de ravitaillements BGI ({bi} internes vs {be} externes) — maîtrise des coûts.",
            "carb_0":        "Aucune consommation carburant enregistrée ce mois — vérifier la saisie des bons.",
            "carb_bge_ko":   lambda be,bi: f"Plus de BGE ({be}) que de BGI ({bi}) — optimiser l'utilisation de la cuve interne.",
            # BOC
            "boc_ok":        lambda t,tc,tot: f"{t}% des courriers traités ou classés ({tc}/{tot}) — gestion documentaire efficace.",
            "boc_0ret":      "Aucun courrier en retard — délais respectés.",
            "boc_ret":       lambda n: f"{n} courrier(s) en retard (> 7 jours) — prioriser leur traitement immédiat.",
            "boc_att":       lambda n: f"{n} courrier(s) en attente de traitement ou de diffusion.",
            # Défaut
            "def_ok":        "Rapport généré avec succès — aucune anomalie majeure détectée.",
            "def_att":       "Aucun point d'attention critique — situation nominale.",
        },
        "en": {
            "ass_ok":      lambda a: f"{a} active insurance policy(ies) — fleet coverage ensured.",
            "ass_stable":  "No policy on alert, expired or terminated — optimal contractual stability.",
            "ass_0sin":    "No claim recorded this month — excellent road safety record.",
            "ass_alerte":  lambda a: f"{a} policy(ies) on alert — urgent renewal required.",
            "ass_exp":     lambda a: f"{a} expired policy(ies) — some buses operate without active coverage.",
            "ass_res":     lambda a: f"{a} terminated policy(ies) — verify coverage of affected vehicles.",
            "ass_sin":     lambda s,m: f"{s} claim(s) declared this month for {m} — analyze causes.",
            "ass_exp30":   lambda n: f"{n} policy(ies) expiring within 30 days — schedule renewals immediately.",
            "parc_taux_ok":  lambda t,e,tot: f"Fleet availability rate: {t}% ({e}/{tot} buses in service) — satisfactory level.",
            "parc_ass_ok":   "All buses have an active insurance policy.",
            "parc_sain":     "No bus broken down or under maintenance — fleet in excellent operational condition.",
            "parc_taux_ko":  lambda t: f"Availability rate at {t}% — below the recommended threshold of 80%.",
            "parc_panne":    lambda n: f"{n} bus(es) broken down — mobilize maintenance to reduce downtime.",
            "parc_maint":    lambda n: f"{n} bus(es) under maintenance — check return-to-service deadlines.",
            "parc_hors":     lambda n: f"{n} bus(es) out of service — assess whether repair or decommission is needed.",
            "tour_real_ok":  lambda t,r,tot: f"Completion rate: {t}% ({r}/{tot} trips) — high operational performance.",
            "tour_0ann":     "No cancelled trip — service continuity ensured.",
            "tour_ecart_ok": lambda e: f"Average km deviation of {e:.1f} km — planning in line with terrain.",
            "tour_real_ko":  lambda t: f"Completion rate at {t}% — identify and correct causes of non-completion.",
            "tour_ann":      lambda n: f"{n} cancelled trip(s) — analyze reasons and take corrective action.",
            "tour_ecart_ko": lambda e: f"Average km deviation of {e:.1f} km — review route planning.",
            "carb_ok":       lambda v,l: f"{v} validated fuel voucher(s) this month — total consumption: {l:,.0f} liters.",
            "carb_bgi_ok":   lambda bi,be: f"Majority of BGI refueling ({bi} internal vs {be} external) — fuel cost control.",
            "carb_0":        "No fuel consumption recorded this month — check voucher entry.",
            "carb_bge_ko":   lambda be,bi: f"More BGE ({be}) than BGI ({bi}) — optimize use of internal tank.",
            "boc_ok":        lambda t,tc,tot: f"{t}% of mail processed or filed ({tc}/{tot}) — efficient document management.",
            "boc_0ret":      "No overdue mail — deadlines respected.",
            "boc_ret":       lambda n: f"{n} overdue mail item(s) (> 7 days) — prioritize immediate processing.",
            "boc_att":       lambda n: f"{n} mail item(s) awaiting processing or distribution.",
            "def_ok":        "Report generated successfully — no major anomaly detected.",
            "def_att":       "No critical attention point — nominal situation.",
        },
        "ar": {
            "ass_ok":      lambda a: f"{a} بوليصة (بوليصات) تأمين نشطة — تأمين الأسطول مضمون.",
            "ass_stable":  "لا توجد بوليصة في حالة تنبيه أو منتهية أو ملغاة — استقرار تعاقدي مثالي.",
            "ass_0sin":    "لم يُسجَّل أي حادث هذا الشهر — سجل سلامة مرورية ممتاز.",
            "ass_alerte":  lambda a: f"{a} بوليصة (بوليصات) في حالة تنبيه — مطلوب تجديد عاجل.",
            "ass_exp":     lambda a: f"{a} بوليصة (بوليصات) منتهية — بعض الحافلات تعمل بدون تغطية نشطة.",
            "ass_res":     lambda a: f"{a} بوليصة (بوليصات) ملغاة — تحقق من تغطية المركبات المعنية.",
            "ass_sin":     lambda s,m: f"{s} حادث (حوادث) مُصرَّح به هذا الشهر بمبلغ {m} — تحليل الأسباب.",
            "ass_exp30":   lambda n: f"{n} بوليصة (بوليصات) تنتهي خلال 30 يوماً — جدوِلة التجديدات فوراً.",
            "parc_taux_ok":  lambda t,e,tot: f"معدل توفر الأسطول: {t}% ({e}/{tot} حافلة في الخدمة) — مستوى مُرضٍ.",
            "parc_ass_ok":   "جميع الحافلات لديها بوليصة تأمين نشطة.",
            "parc_sain":     "لا توجد حافلة في عطل أو صيانة — الأسطول في حالة تشغيلية ممتازة.",
            "parc_taux_ko":  lambda t: f"معدل التوفر عند {t}% — أقل من العتبة الموصى بها 80%.",
            "parc_panne":    lambda n: f"{n} حافلة في عطل — تعبئة الصيانة للحد من التوقف.",
            "parc_maint":    lambda n: f"{n} حافلة في الصيانة — التحقق من مواعيد إعادة الخدمة.",
            "parc_hors":     lambda n: f"{n} حافلة خارج الخدمة — تقييم ما إذا كانت الإصلاح أو الإصلاح ضروريًا.",
            "tour_real_ok":  lambda t,r,tot: f"معدل الإنجاز: {t}% ({r}/{tot} رحلة) — أداء تشغيلي عالٍ.",
            "tour_0ann":     "لا توجد رحلة ملغاة — استمرارية الخدمة مضمونة.",
            "tour_ecart_ok": lambda e: f"متوسط انحراف الكم: {e:.1f} كم — التخطيط متوافق مع الميدان.",
            "tour_real_ko":  lambda t: f"معدل الإنجاز عند {t}% — تحديد وتصحيح أسباب عدم الإنجاز.",
            "tour_ann":      lambda n: f"{n} رحلة (رحلات) ملغاة — تحليل الأسباب واتخاذ الإجراءات التصحيحية.",
            "tour_ecart_ko": lambda e: f"متوسط انحراف الكم: {e:.1f} كم — مراجعة تخطيط المسارات.",
            "carb_ok":       lambda v,l: f"{v} وصل (وصولات) وقود مُتحقَّق منه هذا الشهر — الاستهلاك الإجمالي: {l:,.0f} لتر.",
            "carb_bgi_ok":   lambda bi,be: f"غالبية التزود BGI ({bi} داخلي مقابل {be} خارجي) — ضبط تكاليف الوقود.",
            "carb_0":        "لم يُسجَّل أي استهلاك وقود هذا الشهر — تحقق من إدخال الوصولات.",
            "carb_bge_ko":   lambda be,bi: f"BGE ({be}) أكثر من BGI ({bi}) — تحسين استخدام الخزان الداخلي.",
            "boc_ok":        lambda t,tc,tot: f"{t}% من البريد مُعالَج أو مُؤرشَف ({tc}/{tot}) — إدارة وثائقية فعّالة.",
            "boc_0ret":      "لا يوجد بريد متأخر — الآجال محترمة.",
            "boc_ret":       lambda n: f"{n} بريد (بريود) متأخر (> 7 أيام) — إعطاء الأولوية للمعالجة الفورية.",
            "boc_att":       lambda n: f"{n} بريد (بريود) في انتظار المعالجة أو التوزيع.",
            "def_ok":        "تم إنشاء التقرير بنجاح — لا توجد شذوذات رئيسية.",
            "def_att":       "لا توجد نقاط انتباه حرجة — الوضع طبيعي.",
        },
    }
    m = _M.get(langue, _M["fr"])

    if type_rapport == "bilan_assurance":
        actives   = data.get("polices_actives",   0) or 0
        alerte    = data.get("polices_alerte",     0) or 0
        expirees  = data.get("polices_expirees",   0) or 0
        resiliees = data.get("polices_resiliees",  0) or 0
        sinistres = data.get("sinistres_mois",     0) or 0
        montant   = data.get("montant_sinistres",  0) or 0
        expir30   = data.get("expiration_30j",     [])

        if actives > 0:
            positifs.append(
                m["ass_ok"](actives)
            )
        if alerte == 0 and expirees == 0 and resiliees == 0:
            positifs.append(
                m["ass_stable"]
            )
        if sinistres == 0:
            positifs.append(
                m["ass_0sin"]
            )
        if alerte > 0:
            attentions.append(
                m["ass_alerte"](alerte)
            )
        if expirees > 0:
            attentions.append(
                m["ass_exp"](expirees)
            )
        if resiliees > 0:
            attentions.append(
                m["ass_res"](resiliees)
            )
        if sinistres > 0:
            m_fmt = f"{montant:,.0f} TND" if isinstance(montant, (int, float)) else str(montant)
            attentions.append(
                m["ass_sin"](sinistres, m_fmt)
            )
        if isinstance(expir30, list) and len(expir30) > 0:
            attentions.append(
                m["ass_exp30"](len(expir30))
            )

    elif type_rapport == "bilan_parc":
        total       = data.get("total_bus",       0) or 0
        en_service  = data.get("en_service",      0) or 0
        hors_svc    = data.get("hors_service",    0) or 0
        en_panne    = data.get("en_panne",        0) or 0
        maintenance = data.get("en_maintenance",  0) or 0
        actives     = data.get("polices_actives", 0) or 0

        taux = round(en_service / total * 100) if total > 0 else 0
        if taux >= 80:
            positifs.append(
                m["parc_taux_ok"](taux, en_service, total)
            )
        if actives == total and total > 0:
            positifs.append(
                m["parc_ass_ok"]
            )
        if en_panne == 0 and maintenance == 0:
            positifs.append(
                m["parc_sain"]
            )
        if taux < 80:
            attentions.append(
                m["parc_taux_ko"](taux)
            )
        if en_panne > 0:
            attentions.append(
                m["parc_panne"](en_panne)
            )
        if maintenance > 0:
            attentions.append(
                m["parc_maint"](maintenance)
            )
        if hors_svc > 0:
            attentions.append(
                m["parc_hors"](hors_svc)
            )

    elif type_rapport in ("rapport_journalier", "rapport_hebdomadaire", "rapport_mensuel"):
        realisees = data.get("tournees_realisees", 0) or 0
        annulees  = data.get("tournees_annulees",  0) or 0
        total     = data.get("tournees_total",     0) or 0
        ecart     = data.get("ecart_moyen",        0) or 0

        taux_real = round(realisees / total * 100) if total > 0 else 0
        if taux_real >= 90:
            positifs.append(
                m["tour_real_ok"](taux_real, realisees, total)
            )
        if annulees == 0:
            positifs.append(
                m["tour_0ann"]
            )
        if isinstance(ecart, (int, float)) and abs(ecart) <= 5:
            positifs.append(
                m["tour_ecart_ok"](ecart)
            )
        if taux_real < 90 and total > 0:
            attentions.append(
                m["tour_real_ko"](taux_real)
            )
        if annulees > 0:
            attentions.append(
                m["tour_ann"](annulees)
            )
        if isinstance(ecart, (int, float)) and abs(ecart) > 10:
            attentions.append(
                m["tour_ecart_ko"](ecart)
            )

    elif type_rapport == "bilan_carburant":
        litres  = data.get("litres_total", 0) or 0
        valides = data.get("bons_valides", 0) or 0
        bgi     = data.get("bgi_count",   0) or 0
        bge     = data.get("bge_count",   0) or 0

        if valides > 0:
            positifs.append(
                m["carb_ok"](valides, litres)
            )
        if bgi >= bge and bgi > 0:
            positifs.append(
                m["carb_bgi_ok"](bgi, bge)
            )
        if litres == 0:
            attentions.append(
                m["carb_0"]
            )
        if bge > bgi:
            attentions.append(
                m["carb_bge_ko"](bge, bgi)
            )

    elif type_rapport == "bilan_boc":
        total   = data.get("total_arrivee", 0) or 0
        attente = data.get("en_attente",    0) or 0
        traites = data.get("traites",       0) or 0
        classes = data.get("classes",       0) or 0
        retard  = data.get("en_retard",     0) or 0

        taux_t = round((traites + classes) / total * 100) if total > 0 else 0
        if taux_t >= 80:
            positifs.append(
                m["boc_ok"](taux_t, traites + classes, total)
            )
        if retard == 0:
            positifs.append(
                m["boc_0ret"]
            )
        if retard > 0:
            attentions.append(
                m["boc_ret"](retard)
            )
        if attente > 0:
            attentions.append(
                m["boc_att"](attente)
            )

    if not positifs:
        positifs.append(m["def_ok"])
    if not attentions:
        attentions.append(m["def_att"])

    return positifs, attentions


# ---------------------------------------------------------------------------
# GÉNÉRATION PDF
# ---------------------------------------------------------------------------

def generer_pdf_rapport(type_rapport: str, label: str, data: dict, chemin: Path, texte_synthese: str = None, langue: str = 'fr'):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    # ── Enregistrement police arabe (Windows) ────────────────────────────────
    _FONT_NORM = "Helvetica"
    _FONT_BOLD = "Helvetica-Bold"
    _FONT_ITAL = "Helvetica-Oblique"
    _RTL = (langue == "ar")
    print(f"  [RAPPORT_PDF v2] langue={langue!r} RTL={_RTL} arabic_reshaper={'OK' if _RTL else 'N/A'}")

    # Table de traduction des statuts (données PostgreSQL en FR)
    _STATUTS_TRAD = {}
    if langue == "ar":
        _STATUTS_TRAD = {'hors service': 'خارج الخدمة', 'en service': 'في الخدمة', 'en panne': 'في عطل', 'en maintenance': 'في الصيانة', 'réformé': 'مُصلَح', 'reformé': 'مُصلَح', 'réalisée': 'منجزة', 'planifiée': 'مخططة', 'annulée': 'ملغاة', 'en cours': 'قيد التنفيذ', 'brouillon': 'مسودة', 'active': 'نشطة', 'expirée': 'منتهية', 'résiliée': 'ملغاة', 'alerte': 'تنبيه', 'payée': 'مدفوعة', 'validée': 'مُصادق عليها'}
    elif langue == "en":
        _STATUTS_TRAD = {'hors service': 'Out of service', 'en service': 'In service', 'en panne': 'Broken down', 'en maintenance': 'Under maintenance', 'réalisée': 'Completed', 'planifiée': 'Planned', 'annulée': 'Cancelled', 'en cours': 'In progress', 'brouillon': 'Draft', 'active': 'Active', 'expirée': 'Expired', 'résiliée': 'Terminated', 'alerte': 'Alert'}

    def _trad_val(val: str) -> str:
        """Traduit une valeur de statut selon la langue."""
        if not val or not _STATUTS_TRAD:
            return val
        return _STATUTS_TRAD.get(val.lower(), val)

    if langue == "ar":
        _arabic_fonts = [
            # Linux — FreeSerif (unicode étendu, support arabe natif)
            ("/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
             "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"),
            # Linux — Noto Naskh Arabic
            ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
             "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
            # Linux — Amiri
            ("/usr/share/fonts/truetype/amiri/amiri-regular.ttf",
             "/usr/share/fonts/truetype/amiri/amiri-bold.ttf"),
            # Windows system fonts avec support arabe
            (r"C:\Windows\Fonts\arial.ttf",   r"C:\Windows\Fonts\arialbd.ttf"),
            (r"C:\Windows\Fonts\tahoma.ttf",  r"C:\Windows\Fonts\tahomabd.ttf"),
            (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
        ]
        for norm_path, bold_path in _arabic_fonts:
            if os.path.exists(norm_path):
                try:
                    if "ArabicFont" not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont("ArabicFont",      norm_path))
                        pdfmetrics.registerFont(TTFont("ArabicFont-Bold", bold_path if os.path.exists(bold_path) else norm_path))
                    _FONT_NORM = "ArabicFont"
                    _FONT_BOLD = "ArabicFont-Bold"
                    _FONT_ITAL = "ArabicFont"
                    print(f"  [POLICE ARABE] {norm_path}")
                    break
                except Exception as _fe:
                    print(f"  [POLICE ARABE] échec {norm_path}: {_fe}")

    BLEU    = HexColor("#1a3a6b")
    BLEU_C  = HexColor("#2196F3")
    GRIS    = HexColor("#f8f9fa")
    GRIS_B  = HexColor("#e9ecef")
    VERT    = HexColor("#28a745")
    VERT_L  = HexColor("#d4edda")
    VERT_B  = HexColor("#155724")
    ROUGE   = HexColor("#dc3545")
    ROUGE_L = HexColor("#f8d7da")
    ROUGE_B = HexColor("#721c24")
    ORANGE  = HexColor("#fd7e14")
    TEXTE   = HexColor("#212529")
    TSEC    = HexColor("#6c757d")
    BLEU_LT = HexColor("#e8f0fe")

    styles = getSampleStyleSheet()
    W = 17.4 * cm
    _ALIGN_TITRE = TA_CENTER
    _ALIGN_NORM  = TA_RIGHT if _RTL else 0  # 0 = TA_LEFT
    _INDENT_L    = 0 if _RTL else 10
    _INDENT_R    = 10 if _RTL else 0
    _TA_TITRE    = TA_CENTER

    S_TITRE    = ParagraphStyle("titre", parent=styles["Normal"],
        fontSize=22, textColor=BLEU, alignment=TA_CENTER,
        spaceAfter=2, fontName=_FONT_BOLD)
    S_DATE     = ParagraphStyle("date", parent=styles["Normal"],
        fontSize=10, textColor=TSEC, alignment=TA_CENTER, spaceAfter=14,
        fontName=_FONT_NORM)
    S_NORM     = ParagraphStyle("norm", parent=styles["Normal"],
        fontSize=10, textColor=TEXTE, spaceAfter=4,
        fontName=_FONT_NORM, alignment=TA_RIGHT if _RTL else 0)
    S_PIED     = ParagraphStyle("pied", parent=styles["Normal"],
        fontSize=8, textColor=TSEC, alignment=TA_CENTER,
        fontName=_FONT_NORM)
    S_SH       = ParagraphStyle("sh", parent=styles["Normal"],
        fontSize=11, textColor=white, fontName=_FONT_BOLD, leftIndent=6)
    S_BULLET_V = ParagraphStyle("bv", parent=styles["Normal"],
        fontSize=10, textColor=VERT_B, spaceAfter=5, fontName=_FONT_NORM,
        leftIndent=_INDENT_L, rightIndent=_INDENT_R,
        alignment=TA_RIGHT if _RTL else 0)
    S_BULLET_R = ParagraphStyle("br", parent=styles["Normal"],
        fontSize=10, textColor=ROUGE_B, spaceAfter=5, fontName=_FONT_NORM,
        leftIndent=_INDENT_L, rightIndent=_INDENT_R,
        alignment=TA_RIGHT if _RTL else 0)
    S_CONCL    = ParagraphStyle("concl", parent=styles["Normal"],
        fontSize=10, textColor=TEXTE, leftIndent=8, rightIndent=8,
        spaceBefore=4, spaceAfter=4, fontName=_FONT_NORM,
        alignment=TA_RIGHT if _RTL else 0)

    doc = SimpleDocTemplate(
        str(chemin), pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        title=f"{label} — {date.today().strftime('%d/%m/%Y')}",
        author="Agent IA Transport",
    )

    story = []

    # ── EN-TÊTE ───────────────────────────────────────────────────────────────
    barre = Table([[" "]], colWidths=[W], rowHeights=[0.4*cm])
    barre.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), BLEU)]))
    story.append(barre)
    story.append(Spacer(1, 0.35*cm))
    story.append(Paragraph(_ar2(label) if _RTL else label, S_TITRE))
    if _RTL:
        # En RTL : tout en latin pour éviter les inversions bidi de ReportLab
        _date_str = f"ERP Transport Terrestre — {date.today().strftime('%d/%m/%Y')} — {datetime.now().strftime('%H:%M')}"
    else:
        _date_str = f"ERP Transport Terrestre — {date.today().strftime('%d/%m/%Y')} {'a' if langue=='fr' else 'at'} {datetime.now().strftime('%H:%M')}"
    story.append(Paragraph(_date_str, S_DATE))
    story.append(HRFlowable(width=W, thickness=1.5, color=BLEU_C))
    story.append(Spacer(1, 0.4*cm))

    # ── CONFIG INDICATEURS — multilingue ─────────────────────────────────────
    _C = {
        "fr": {
            "tournees_planifiees": "Planifiees", "tournees_en_cours": "En cours",
            "tournees_realisees": "Realisees",  "tournees_annulees": "Annulees",
            "tournees_total": "Total tournees", "km_total": "Km parcourus",
            "ecart_moyen": "Ecart km moyen",
            "detail_tournees": ("Detail tournees", ["Tournee","Ligne","Chauffeur","Bus","Direction","Etat","Dep.","Arr.","Km","Ecart"]),
            "top_chauffeurs": ("Top chauffeurs", ["Chauffeur","Tournees","Km total"]),
            "km_par_bus": ("Km par bus", ["Bus","Immat.","Tournees","Km"]),
            "annulations_motif": ("Motifs annulation", ["Motif","Nombre"]),
            "detail_annulees": ("Tournees annulees", ["Tournee","Ligne","Chauffeur","Motif","Note"]),
            "activite_lignes": ("Activite par ligne", ["Ligne","Tournees","Km total"]),
            "repartition_direction": ("Repartition direction", ["Direction","Nombre"]),
            "total_bus": "Total bus", "en_service": "En service",
            "hors_service": "Hors service", "en_panne": "En panne",
            "en_maintenance": "En maintenance",
            "detail_bus": ("Detail parc bus", ["Bus","Immat.","Etat","Police","Expiration","Compagnie","Km mois"]),
            "bus_sans_assurance": ("Bus sans assurance", ["Bus","Immat.","Etat"]),
            "polices_actives": "Polices actives", "polices_alerte": "En alerte",
            "polices_expirees": "Expirees", "polices_resiliees": "Resiliees",
            "sinistres_mois": "Sinistres ce mois", "montant_sinistres": "Montant accorde TND",
            "montant_net_verse": "Montant net verse TND",
            "detail_polices_actives": ("Polices actives detail", ["Police","Type","Compagnie","Bus","Immat.","Debut","Fin","Prime TND","Obligatoire"]),
            "detail_sinistres": ("Sinistres du mois", ["Ref.","Etat","Date","Nature","Lieu","Reclame","Accorde","Net verse","Bus","Chauffeur","Desc."]),
            "expiration_30j": ("Polices expirant <30j", ["Police","Type","Compagnie","Bus","Expiration","Prime TND","Obligatoire"]),
            "assurances_chauffeurs": ("Assurances chauffeurs", ["Police","Chauffeur","Type","Etat","Debut","Fin","Compagnie","Prime TND"]),
            "bons_valides": "Bons valides", "litres_total": "Litres consommes",
            "bgi_count": "Bons BGI", "bge_count": "Bons BGE",
            "litres_bgi": "Litres BGI", "litres_bge": "Litres BGE",
            "cout_total": "Cout total TND",
            "litres_par_bus": ("Consommation par bus", ["Bus","Immat.","Bons","Litres BGI","Litres BGE","Total litres"]),
            "detail_bons_recents": ("10 derniers bons", ["Reference","Type","Date","Litres","Cout TND"]),
            "total_arrivee": "Courriers recus", "total_depart": "Courriers envoyes",
            "en_attente": "En attente", "traites": "Traites", "classes": "Classes", "en_retard": "En retard",
            "detail_retard": ("Courriers en retard", ["Ref.","Sujet","Expediteur","Date arrivee","Etat","Type","Jours retard"]),
            "detail_en_attente": ("Courriers en attente", ["Ref.","Sujet","Expediteur","Date arrivee","Etat","Type","Echeance"]),
        },
        "en": {
            "tournees_planifiees": "Planned trips", "tournees_en_cours": "In progress",
            "tournees_realisees": "Completed",      "tournees_annulees": "Cancelled",
            "tournees_total": "Total trips",         "km_total": "Km traveled",
            "ecart_moyen": "Avg km deviation",
            "detail_tournees": ("Trip details", ["Trip","Line","Driver","Bus","Direction","Status","Dep.","Arr.","Km","Dev."]),
            "top_chauffeurs": ("Top drivers", ["Driver","Trips","Total km"]),
            "km_par_bus": ("Km per bus", ["Bus","Plate","Trips","Km"]),
            "annulations_motif": ("Cancellation reasons", ["Reason","Count"]),
            "detail_annulees": ("Cancelled trips", ["Trip","Line","Driver","Reason","Note"]),
            "activite_lignes": ("Line activity", ["Line","Trips","Total km"]),
            "repartition_direction": ("Direction split", ["Direction","Count"]),
            "total_bus": "Total buses", "en_service": "In service",
            "hors_service": "Out of service", "en_panne": "Broken down",
            "en_maintenance": "Under maintenance",
            "detail_bus": ("Fleet details", ["Bus","Plate","Status","Policy","Expiry","Company","Monthly km"]),
            "bus_sans_assurance": ("Uninsured buses", ["Bus","Plate","Status"]),
            "polices_actives": "Active policies", "polices_alerte": "Alert",
            "polices_expirees": "Expired",        "polices_resiliees": "Terminated",
            "sinistres_mois": "Claims this month", "montant_sinistres": "Granted TND",
            "montant_net_verse": "Net paid TND",
            "detail_polices_actives": ("Active policies detail", ["Policy","Type","Company","Bus","Plate","Start","End","Premium TND","Mandatory"]),
            "detail_sinistres": ("Monthly claims", ["Ref.","Status","Date","Type","Location","Claimed","Granted","Net","Bus","Driver","Desc."]),
            "expiration_30j": ("Expiring <30d", ["Policy","Type","Company","Bus","Expiry","Premium TND","Mandatory"]),
            "assurances_chauffeurs": ("Driver insurance", ["Policy","Driver","Type","Status","Start","End","Company","Premium TND"]),
            "bons_valides": "Valid vouchers", "litres_total": "Liters consumed",
            "bgi_count": "BGI vouchers",     "bge_count": "BGE vouchers",
            "litres_bgi": "BGI liters",      "litres_bge": "BGE liters",
            "cout_total": "Total cost TND",
            "litres_par_bus": ("Consumption per bus", ["Bus","Plate","Vouchers","BGI L","BGE L","Total L"]),
            "detail_bons_recents": ("Last 10 vouchers", ["Reference","Type","Date","Liters","Cost TND"]),
            "total_arrivee": "Incoming mail", "total_depart": "Outgoing mail",
            "en_attente": "Pending", "traites": "Processed", "classes": "Filed", "en_retard": "Overdue",
            "detail_retard": ("Overdue mail", ["Ref.","Subject","Sender","Arrival","Status","Type","Days late"]),
            "detail_en_attente": ("Pending mail", ["Ref.","Subject","Sender","Arrival","Status","Type","Deadline"]),
        },
        "ar": {
            "tournees_planifiees": "مخططة", "tournees_en_cours": "جارية",
            "tournees_realisees": "منجزة",  "tournees_annulees": "ملغاة",
            "tournees_total": "مجموع الرحلات", "km_total": "الكم المقطوع",
            "ecart_moyen": "متوسط انحراف الكم",
            "detail_tournees": ("تفاصيل الرحلات", ["الرحلة","الخط","السائق","الحافلة","الاتجاه","الحالة","الانطلاق","الوصول","الكم","الانحراف"]),
            "top_chauffeurs": ("أفضل السائقين", ["السائق","الرحلات","مجموع الكم"]),
            "km_par_bus": ("الكم لكل حافلة", ["الحافلة","اللوحة","الرحلات","الكم"]),
            "annulations_motif": ("أسباب الإلغاء", ["السبب","العدد"]),
            "detail_annulees": ("الرحلات الملغاة", ["الرحلة","الخط","السائق","السبب","ملاحظة"]),
            "activite_lignes": ("نشاط الخطوط", ["الخط","الرحلات","مجموع الكم"]),
            "repartition_direction": ("توزيع الاتجاهات", ["الاتجاه","العدد"]),
            "total_bus": "مجموع الحافلات", "en_service": "في الخدمة",
            "hors_service": "خارج الخدمة", "en_panne": "في عطل",
            "en_maintenance": "في الصيانة",
            "detail_bus": ("تفاصيل الأسطول", ["الحافلة","اللوحة","الحالة","البوليصة","الانتهاء","الشركة","كم الشهر"]),
            "bus_sans_assurance": ("حافلات غير مؤمنة", ["الحافلة","اللوحة","الحالة"]),
            "polices_actives": "بوليصات نشطة", "polices_alerte": "في تنبيه",
            "polices_expirees": "منتهية",      "polices_resiliees": "ملغاة",
            "sinistres_mois": "حوادث الشهر",   "montant_sinistres": "المبلغ الممنوح TND",
            "montant_net_verse": "المبلغ الصافي TND",
            "detail_polices_actives": ("تفاصيل البوليصات", ["البوليصة","النوع","الشركة","الحافلة","اللوحة","البداية","النهاية","القسط TND","إلزامي"]),
            "detail_sinistres": ("حوادث الشهر", ["المرجع","الحالة","التاريخ","النوع","المكان","المطالبة","الممنوح","الصافي","الحافلة","السائق","وصف"]),
            "expiration_30j": ("تنتهي خلال 30 يوم", ["البوليصة","النوع","الشركة","الحافلة","الانتهاء","القسط TND","إلزامي"]),
            "assurances_chauffeurs": ("تأمين السائقين", ["البوليصة","السائق","النوع","الحالة","البداية","النهاية","الشركة","القسط TND"]),
            "bons_valides": "وصولات صحيحة", "litres_total": "اللترات المستهلكة",
            "bgi_count": "وصولات BGI",      "bge_count": "وصولات BGE",
            "litres_bgi": "لترات BGI",      "litres_bge": "لترات BGE",
            "cout_total": "التكلفة الإجمالية TND",
            "litres_par_bus": ("الاستهلاك لكل حافلة", ["الحافلة","اللوحة","الوصولات","لترات BGI","لترات BGE","المجموع"]),
            "detail_bons_recents": ("آخر 10 وصولات", ["المرجع","النوع","التاريخ","اللترات","التكلفة TND"]),
            "total_arrivee": "البريد الوارد", "total_depart": "البريد الصادر",
            "en_attente": "قيد الانتظار", "traites": "معالج", "classes": "مؤرشف", "en_retard": "متأخر",
            "detail_retard": ("البريد المتأخر", ["المرجع","الموضوع","المرسل","التاريخ","الحالة","النوع","أيام التأخير"]),
            "detail_en_attente": ("البريد قيد الانتظار", ["المرجع","الموضوع","المرسل","التاريخ","الحالة","النوع","الموعد"]),
        },
    }
    _cfg = _C.get(langue, _C["fr"])

    def _label(key):
        v = _cfg.get(key, key)
        return v[0] if isinstance(v, tuple) else v

    def _cols(key, default):
        v = _cfg.get(key)
        return v[1] if isinstance(v, tuple) else default

    CONFIG = {
        # ── Exploitation ──────────────────────────────────────────────────────
        "tournees_planifiees":    (_label("tournees_planifiees"),  BLEU_C, False, None),
        "tournees_en_cours":      (_label("tournees_en_cours"),    ORANGE, False, None),
        "tournees_realisees":     (_label("tournees_realisees"),   VERT,   False, None),
        "tournees_annulees":      (_label("tournees_annulees"),    ROUGE,  False, None),
        "tournees_total":         (_label("tournees_total"),       BLEU,   False, None),
        "km_total":               (_label("km_total"),             BLEU,   False, None),
        "ecart_moyen":            (_label("ecart_moyen"),          ORANGE, False, None),
        "detail_tournees":        (_label("detail_tournees"),      None,   True,  _cols("detail_tournees",["Tournee","Ligne","Chauffeur","Bus","Direction","Etat","Dep.","Arr.","Km","Ecart"])),
        "top_chauffeurs":         (_label("top_chauffeurs"),       None,   True,  _cols("top_chauffeurs",["Chauffeur","Tournees","Km total"])),
        "km_par_bus":             (_label("km_par_bus"),           None,   True,  _cols("km_par_bus",["Bus","Immat.","Tournees","Km"])),
        "annulations_motif":      (_label("annulations_motif"),    None,   True,  _cols("annulations_motif",["Motif","Nombre"])),
        "detail_annulees":        (_label("detail_annulees"),      None,   True,  _cols("detail_annulees",["Tournee","Ligne","Chauffeur","Motif","Note"])),
        "activite_lignes":        (_label("activite_lignes"),      None,   True,  _cols("activite_lignes",["Ligne","Tournees","Km total"])),
        "repartition_direction":  (_label("repartition_direction"),None,   True,  _cols("repartition_direction",["Direction","Nombre"])),
        # ── Parc bus ──────────────────────────────────────────────────────────
        "total_bus":              (_label("total_bus"),            BLEU,   False, None),
        "en_service":             (_label("en_service"),           VERT,   False, None),
        "hors_service":           (_label("hors_service"),         ROUGE,  False, None),
        "en_panne":               (_label("en_panne"),             ORANGE, False, None),
        "en_maintenance":         (_label("en_maintenance"),       ORANGE, False, None),
        "detail_bus":             (_label("detail_bus"),           None,   True,  _cols("detail_bus",["Bus","Immat.","Etat","Police","Expiration","Compagnie","Km mois"])),
        "bus_sans_assurance":     (_label("bus_sans_assurance"),   None,   True,  _cols("bus_sans_assurance",["Bus","Immat.","Etat"])),
        # ── Assurance ─────────────────────────────────────────────────────────
        "polices_actives":        (_label("polices_actives"),      VERT,   False, None),
        "polices_alerte":         (_label("polices_alerte"),       ORANGE, False, None),
        "polices_expirees":       (_label("polices_expirees"),     ROUGE,  False, None),
        "polices_resiliees":      (_label("polices_resiliees"),    ROUGE,  False, None),
        "sinistres_mois":         (_label("sinistres_mois"),       ORANGE, False, None),
        "montant_sinistres":      (_label("montant_sinistres"),    ROUGE,  False, None),
        "montant_net_verse":      (_label("montant_net_verse"),    VERT,   False, None),
        "detail_polices_actives": (_label("detail_polices_actives"),None,  True,  _cols("detail_polices_actives",["Police","Type","Compagnie","Bus","Immat.","Debut","Fin","Prime TND","Obligatoire"])),
        "detail_sinistres":       (_label("detail_sinistres"),     None,   True,  _cols("detail_sinistres",["Ref.","Etat","Date","Nature","Lieu","Reclame","Accorde","Net verse","Bus","Chauffeur","Desc."])),
        "expiration_30j":         (_label("expiration_30j"),       None,   True,  _cols("expiration_30j",["Police","Type","Compagnie","Bus","Expiration","Prime TND","Obligatoire"])),
        "assurances_chauffeurs":  (_label("assurances_chauffeurs"),None,   True,  _cols("assurances_chauffeurs",["Police","Chauffeur","Type","Etat","Debut","Fin","Compagnie","Prime TND"])),
        # ── Carburant ─────────────────────────────────────────────────────────
        "bons_valides":           (_label("bons_valides"),         VERT,   False, None),
        "litres_total":           (_label("litres_total"),         BLEU,   False, None),
        "bgi_count":              (_label("bgi_count"),            BLEU,   False, None),
        "bge_count":              (_label("bge_count"),            BLEU,   False, None),
        "litres_bgi":             (_label("litres_bgi"),           BLEU,   False, None),
        "litres_bge":             (_label("litres_bge"),           ORANGE, False, None),
        "cout_total":             (_label("cout_total"),           ROUGE,  False, None),
        "litres_par_bus":         (_label("litres_par_bus"),       None,   True,  _cols("litres_par_bus",["Bus","Immat.","Bons","Litres BGI","Litres BGE","Total litres"])),
        "detail_bons_recents":    (_label("detail_bons_recents"),  None,   True,  _cols("detail_bons_recents",["Reference","Type","Date","Litres","Cout TND"])),
        # ── BOC ───────────────────────────────────────────────────────────────
        "total_arrivee":          (_label("total_arrivee"),        BLEU,   False, None),
        "total_depart":           (_label("total_depart"),         BLEU,   False, None),
        "en_attente":             (_label("en_attente"),         ORANGE, False, None),
        "traites":                (_label("traites"),             VERT,   False, None),
        "classes":                (_label("classes"),             VERT,   False, None),
        "en_retard":              (_label("en_retard"),           ROUGE,  False, None),
        "detail_retard":          (_label("detail_retard"),       None,   True,  _cols("detail_retard",["Ref.","Sujet","Expediteur","Date arrivee","Etat","Type","Jours retard"])),
        "detail_en_attente":      (_label("detail_en_attente"),   None,   True,  _cols("detail_en_attente",["Ref.","Sujet","Expediteur","Date arrivee","Etat","Type","Echeance"])),
    }

    def cfg(cle):
        return CONFIG.get(cle, (cle.replace("_", " ").title(), BLEU, False, None))

    scalaires = [(k, v) for k, v in data.items() if not isinstance(v, list) and v is not None]
    listes    = [(k, v) for k, v in data.items() if isinstance(v, list) and v]

    # ── KPI CARDS ─────────────────────────────────────────────────────────────
    if scalaires:
        _sh_kpi = {"ar":"المؤشرات الرئيسية","en":"Key indicators","fr":"Indicateurs cles"}.get(langue,"Indicateurs cles")
        sh = Table([[Paragraph(_ar2(_sh_kpi) if _RTL else _sh_kpi, S_SH)]],
            colWidths=[W], rowHeights=[0.65*cm])
        sh.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), BLEU),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(sh)
        story.append(Spacer(1, 0.25*cm))

        for i in range(0, len(scalaires), 3):
            groupe = scalaires[i:i+3]
            cells  = []
            for cle, valeur in groupe:
                c = cfg(cle)
                lbl = c[0]
                col = c[1] or BLEU
                val_str = f"{valeur:,.1f}" if isinstance(valeur, float) else str(valeur)
                cell_t = Table([
                    [Paragraph(_ar2(_trad_val(val_str)) if _RTL else _trad_val(val_str), ParagraphStyle("kv", parent=styles["Normal"],
                        fontSize=26, textColor=col, alignment=TA_CENTER,
                        fontName=_FONT_BOLD))],
                    [Paragraph(_ar2(lbl) if _RTL else lbl, ParagraphStyle("kl", parent=styles["Normal"],
                        fontSize=9, textColor=TSEC, alignment=TA_CENTER, fontName=_FONT_NORM))],
                ], colWidths=[W/3 - 0.3*cm])
                cell_t.setStyle(TableStyle([
                    ("TOPPADDING",    (0,0), (-1,-1), 10),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                ]))
                cells.append(cell_t)
            while len(cells) < 3:
                cells.append(Paragraph("", S_NORM))
            row_t = Table([cells], colWidths=[W/3]*3)
            row_t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), GRIS),
                ("BOX",        (0,0), (-1,-1), 0.5, GRIS_B),
                ("INNERGRID",  (0,0), (-1,-1), 0.5, GRIS_B),
                ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ]))
            story.append(row_t)
            story.append(Spacer(1, 0.15*cm))
        story.append(Spacer(1, 0.3*cm))

    # ── TABLEAUX DÉTAIL ───────────────────────────────────────────────────────
    for cle, valeur in listes:
        c       = cfg(cle)
        lbl_det = c[0]
        entetes = c[3]

        sh2 = Table([[Paragraph(_ar2(lbl_det) if _RTL else lbl_det, S_SH)]],
            colWidths=[W], rowHeights=[0.65*cm])
        sh2.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), BLEU_C),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))

        nb   = len(valeur[0]) if valeur else 1
        cw   = [W/nb]*nb
        ents = (entetes or [f"Col {i+1}" for i in range(nb)])[:nb]
        while len(ents) < nb:
            ents.append("")

        from reportlab.lib.enums import TA_RIGHT as _TA_R
        s_hdr  = ParagraphStyle("th", parent=styles["Normal"],
            fontSize=9, fontName=_FONT_BOLD, textColor=white,
            leftIndent=0 if _RTL else 4, rightIndent=4 if _RTL else 0,
            alignment=_TA_R if _RTL else 0)
        s_cell = ParagraphStyle("td", parent=styles["Normal"],
            fontSize=9, textColor=TEXTE, fontName=_FONT_NORM,
            leftIndent=0 if _RTL else 4, rightIndent=4 if _RTL else 0,
            alignment=_TA_R if _RTL else 0)

        trows = [[Paragraph(_ar2(str(h)) if _RTL else str(h), s_hdr) for h in ents]]
        for row in valeur[:20]:
            trow = []
            for cell in list(row)[:nb]:
                if cell is None:
                    v = "-"
                elif isinstance(cell, float):
                    v = f"{cell:,.1f}"
                else:
                    v = _trad_val(str(cell))[:55]
                v = _ar2(v) if _RTL else v
                trow.append(Paragraph(v, s_cell))
            while len(trow) < nb:
                trow.append(Paragraph("", s_cell))
            trows.append(trow[:nb])

        det = Table(trows, colWidths=cw, repeatRows=1)
        det.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  BLEU_C),
            ("TEXTCOLOR",     (0,0), (-1,0),  white),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [white, GRIS]),
            ("GRID",          (0,0), (-1,-1), 0.4, GRIS_B),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))

        story.append(KeepTogether([sh2, Spacer(1, 0.2*cm), det, Spacer(1, 0.35*cm)]))

    # ── SYNTHÈSE ANALYTIQUE ───────────────────────────────────────────────────
    positifs, attentions = _analyser_rapport(type_rapport, data, langue)

    story.append(Spacer(1, 0.2*cm))

    _labels = {
        "ar": {"synthese": "الملخص التحليلي", "positifs": "النقاط الإيجابية",
               "attentions": "نقاط الانتباه", "conclusion": "الخلاصة",
               "pied": "تم الإنشاء بواسطة وكيل الذكاء الاصطناعي للنقل"},
        "en": {"synthese": "Analytical summary", "positifs": "Positive points",
               "attentions": "Attention points", "conclusion": "Conclusion",
               "pied": "Generated by Transport AI Agent"},
        "fr": {"synthese": "Synthese analytique", "positifs": "Points positifs",
               "attentions": "Points d'attention", "conclusion": "Conclusion",
               "pied": "Genere par Agent IA Transport"},
    }
    _L = _labels.get(langue, _labels["fr"])
    _dbg = _L.get("synthese", "?")
    print(f"  [DEBUG rapport_pdf] langue={langue!r} synthese={_dbg!r}")

    # Si texte_synthese fourni, l'utiliser à la place du contenu généré ici
    if texte_synthese:
        story.append(Spacer(1, 0.3*cm))
        for ligne in texte_synthese.split("\n"):
            ligne = ligne.strip()
            if not ligne or ligne.startswith("**") and ligne.endswith("**"):
                continue
            story.append(Paragraph(_ar2(ligne.replace("**", "")) if _RTL else ligne.replace("**", ""), S_NORM))
            story.append(Spacer(1, 0.1*cm))

    sh_syn = Table([[Paragraph(_ar2(_L["synthese"]) if _RTL else _L["synthese"], S_SH)]],
        colWidths=[W], rowHeights=[0.65*cm])
    sh_syn.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BLEU),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(sh_syn)
    story.append(Spacer(1, 0.25*cm))

    col_w = (W - 0.3*cm) / 2

    def _build_bloc(titre, points, bg_header, bg_body, bullet_style):
        titre_affiche = _ar2(titre) if _RTL else titre
        header = Table(
            [[Paragraph(titre_affiche, ParagraphStyle("bh", parent=styles["Normal"],
                fontSize=10, fontName=_FONT_BOLD, textColor=white, leftIndent=6))]],
            colWidths=[col_w], rowHeights=[0.55*cm]
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg_header),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))
        rows = [[Paragraph(_ar2(f"  {pt}") if _RTL else f"  {pt}", bullet_style)] for pt in points] or \
               [[Paragraph("  —", bullet_style)]]
        body = Table(rows, colWidths=[col_w])
        body.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), bg_body),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ]))
        return header, body

    h_v, b_v = _build_bloc(_L["positifs"],       positifs,   VERT,  VERT_L,  S_BULLET_V)
    h_r, b_r = _build_bloc(_L["attentions"],     attentions, ROUGE, ROUGE_L, S_BULLET_R)

    # Ordre fixe : positifs (vert) toujours en premier dans le tableau
    # ReportLab place la 1ère cellule à gauche en LTR, à droite en RTL via alignment
    row_h = Table([[h_v, h_r]], colWidths=[col_w, col_w])
    row_b = Table([[b_v, b_r]], colWidths=[col_w, col_w])
    row_b.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))

    story.append(KeepTogether([row_h, row_b]))

    # ── CONCLUSION ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.35*cm))

    nb_ok  = len(positifs)
    nb_att = len(attentions)
    _concl = {
        "ar": [
            "الوضع مُرضٍ. المؤشرات ضمن المعايير المتوقعة.",
            "الوضع إيجابي مع بعض النقاط التي تستدعي المتابعة.",
            "عدة نقاط انتباه تستوجب تدخلاً سريعاً. يُنصح بمعالجة التنبيهات ذات الأولوية."
        ],
        "en": [
            "Overall satisfactory. Indicators are within expected norms.",
            "Generally positive with a few points to monitor.",
            "Several attention points require prompt action."
        ],
        "fr": [
            "Bilan global satisfaisant. Les indicateurs sont dans les normes attendues.",
            "Bilan globalement positif avec quelques points a surveiller.",
            "Plusieurs points d'attention necessitent une intervention rapide."
        ],
    }
    _cl = _concl.get(langue, _concl["fr"])
    if nb_att == 0 or (nb_att == 1 and "nominale" in attentions[0]):
        conclusion = _cl[0]
    elif nb_ok >= nb_att:
        conclusion = _cl[1]
    else:
        conclusion = _cl[2]

    concl_table = Table(
        [[Paragraph(_ar2(f"{_L['conclusion']} : {conclusion}") if _RTL else f"{_L['conclusion']} : {conclusion}", S_CONCL)]],
        colWidths=[W]
    )
    concl_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BLEU_LT),
        ("BOX",           (0,0), (-1,-1), 0.8, BLEU_C),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    story.append(concl_table)

    # ── PIED DE PAGE ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    bb = Table([[" "]], colWidths=[W], rowHeights=[0.2*cm])
    bb.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), BLEU_C)]))
    story.append(bb)
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(
        (_ar2(f"{_L['pied']} — ERP Odoo 19 — {datetime.now().strftime('%d/%m/%Y %H:%M')}") if _RTL else f"{_L['pied']} — ERP Odoo 19 — {datetime.now().strftime('%d/%m/%Y %H:%M')}"),
        S_PIED
    ))

    doc.build(story)


# ---------------------------------------------------------------------------
# RAPPORT LIBRE — génère un PDF pour n'importe quelle question SQL
# ---------------------------------------------------------------------------

def generer_pdf_rapport_libre(label: str, question: str, data: dict,
                               colonnes: list, rows: list, chemin,
                               llm=None, langue: str = 'fr'):
    """
    Génère un PDF enrichi pour un rapport libre :
    - En-tête professionnel
    - KPI cards (si scalaire) ou tableau de données
    - Synthèse analytique générée par le LLM (ou fallback automatique)
    - Conclusion
    - Pied de page
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER
    from datetime import date, datetime
    import os

    # ── Langue / RTL ──────────────────────────────────────────────────────────
    # langue est reçu comme paramètre (défaut 'fr')
    _RTL = (langue == "ar")

    _FONT_NORM = "Helvetica"
    _FONT_BOLD = "Helvetica-Bold"
    _FONT_ITAL = "Helvetica-Oblique"

    if langue == "ar":
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        _arabic_fonts = [
            # Linux — FreeSerif (unicode étendu, support arabe natif)
            ("/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
             "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"),
            # Linux — Noto Naskh Arabic
            ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
             "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
            # Linux — Amiri
            ("/usr/share/fonts/truetype/amiri/amiri-regular.ttf",
             "/usr/share/fonts/truetype/amiri/amiri-bold.ttf"),
            # Windows system fonts avec support arabe
            (r"C:\Windows\Fonts\arial.ttf",   r"C:\Windows\Fonts\arialbd.ttf"),
            (r"C:\Windows\Fonts\tahoma.ttf",  r"C:\Windows\Fonts\tahomabd.ttf"),
            (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
        ]
        for norm_path, bold_path in _arabic_fonts:
            if os.path.exists(norm_path):
                try:
                    if "ArabicFont" not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont("ArabicFont",      norm_path))
                        pdfmetrics.registerFont(TTFont("ArabicFont-Bold", bold_path if os.path.exists(bold_path) else norm_path))
                    # ← assignation TOUJOURS faite si la police existe, même déjà enregistrée
                    _FONT_NORM = "ArabicFont"
                    _FONT_BOLD = "ArabicFont-Bold"
                    _FONT_ITAL = "ArabicFont"
                    print(f"  [POLICE ARABE] {norm_path}")
                    break
                except Exception as _fe:
                    print(f"  [POLICE ARABE] échec {norm_path}: {_fe}")

    _labels_libre = {
        "ar": {"synthese": "الملخص التحليلي", "positifs": "النقاط الإيجابية",
               "attentions": "نقاط الانتباه", "conclusion": "الخلاصة",
               "pied": "تم الإنشاء بواسطة وكيل الذكاء الاصطناعي للنقل",
               "donnees": "البيانات", "lignes": "سطر",
               "demande": "الطلب", "limite": "* عرض محدود بـ 50 سطراً من أصل"},
        "en": {"synthese": "Analytical summary", "positifs": "Positive points",
               "attentions": "Attention points", "conclusion": "Conclusion",
               "pied": "Generated by Transport AI Agent",
               "donnees": "Data", "lignes": "row(s)",
               "demande": "Request", "limite": "* Display limited to 50 rows out of"},
        "fr": {"synthese": "Synthese analytique", "positifs": "Points positifs",
               "attentions": "Points d'attention", "conclusion": "Conclusion",
               "pied": "Genere par Agent IA Transport",
               "donnees": "Donnees", "lignes": "ligne(s)",
               "demande": "Demande", "limite": "* Affichage limite a 50 lignes sur"},
    }
    _LL = _labels_libre.get(langue, _labels_libre["fr"])

    # ── Traduction noms de colonnes SQL → langue cible ────────────────────────
    _COL_TRAD = {
        "ar": {
            "bus": "الحافلة", "name": "الاسم", "license_plate": "اللوحة",
            "etat": "الحالة", "state": "الحالة", "status": "الحالة",
            "police": "البوليصة", "policy": "البوليصة",
            "expiry": "الانتهاء", "date_expiration": "تاريخ الانتهاء",
            "company": "الشركة", "assurance": "التأمين",
            "km": "الكيلومترات", "km_mois": "كم الشهر", "monthly_km": "كم الشهر",
            "chauffeur": "السائق", "driver": "السائق",
            "ligne": "الخط", "line": "الخط",
            "date": "التاريخ", "total": "المجموع", "count": "العدد",
            "montant": "المبلغ", "amount": "المبلغ",
            "tournee": "الرحلة", "trip": "الرحلة",
            "type": "النوع", "categorie": "الفئة", "category": "الفئة",
            "description": "الوصف", "notes": "ملاحظات",
            "employee": "الموظف", "employe": "الموظف",
        },
        "en": {
            "bus": "Bus", "name": "Name", "license_plate": "License Plate",
            "etat": "Status", "state": "State", "status": "Status",
            "police": "Policy", "policy": "Policy",
            "expiry": "Expiry", "date_expiration": "Expiry Date",
            "company": "Company", "assurance": "Insurance",
            "km": "KM", "km_mois": "Monthly KM", "monthly_km": "Monthly KM",
            "chauffeur": "Driver", "driver": "Driver",
            "ligne": "Line", "line": "Line",
            "date": "Date", "total": "Total", "count": "Count",
            "montant": "Amount", "amount": "Amount",
            "tournee": "Trip", "trip": "Trip",
            "type": "Type", "categorie": "Category", "category": "Category",
        },
    }
    _col_trad = _COL_TRAD.get(langue, {})

    def _traduire_colonne(col: str) -> str:
        """Traduit un nom de colonne SQL vers la langue cible."""
        key = col.lower().strip().replace(" ", "_")
        return _col_trad.get(key, col.replace("_", " ").title())

    # ── Traduction valeurs de statut ──────────────────────────────────────────
    _VAL_TRAD = {
        "ar": {
            "en service": "في الخدمة", "in service": "في الخدمة",
            "hors service": "خارج الخدمة", "out of service": "خارج الخدمة",
            "en panne": "في عطل", "broken down": "في عطل",
            "en maintenance": "في الصيانة", "under maintenance": "في الصيانة",
            "actif": "نشط", "active": "نشط",
            "expiré": "منتهي", "expired": "منتهي",
            "résilié": "ملغى", "terminated": "ملغى",
            "alerte": "تنبيه", "alert": "تنبيه",
            "planifié": "مخطط", "planned": "مخطط",
            "réalisé": "منجز", "completed": "منجز",
            "annulé": "ملغى", "cancelled": "ملغى",
            "en cours": "جارٍ", "in progress": "جارٍ",
            "brouillon": "مسودة", "draft": "مسودة",
            "oui": "نعم", "yes": "نعم",
            "non": "لا", "no": "لا",
        },
        "en": {
            "en service": "In service", "hors service": "Out of service",
            "en panne": "Broken down", "en maintenance": "Under maintenance",
            "actif": "Active", "expiré": "Expired",
            "résilié": "Terminated", "alerte": "Alert",
            "planifié": "Planned", "réalisé": "Completed",
            "annulé": "Cancelled", "en cours": "In progress",
            "brouillon": "Draft", "oui": "Yes", "non": "No",
        },
    }
    _val_trad = _VAL_TRAD.get(langue, {})

    def _traduire_valeur(val: str) -> str:
        """Traduit une valeur de statut si connue."""
        if not isinstance(val, str): return val
        return _val_trad.get(val.lower().strip(), val)

    # ── Couleurs ──────────────────────────────────────────────────────────────
    BLEU    = HexColor("#1a3a6b")
    BLEU_C  = HexColor("#2196F3")
    BLEU_LT = HexColor("#e8f0fe")
    GRIS    = HexColor("#f8f9fa")
    GRIS_B  = HexColor("#e9ecef")
    VERT    = HexColor("#28a745")
    VERT_L  = HexColor("#d4edda")
    VERT_B  = HexColor("#155724")
    ROUGE   = HexColor("#dc3545")
    ROUGE_L = HexColor("#f8d7da")
    ROUGE_B = HexColor("#721c24")
    TEXTE   = HexColor("#212529")
    TSEC    = HexColor("#6c757d")
    WHITE   = white

    styles = getSampleStyleSheet()
    W = 17.4 * cm

    S_TITRE  = ParagraphStyle("titre_libre", parent=styles["Normal"],
        fontSize=18, textColor=BLEU, alignment=TA_CENTER,
        spaceAfter=2, fontName=_FONT_BOLD)
    S_DATE   = ParagraphStyle("date_libre", parent=styles["Normal"],
        fontSize=10, textColor=TSEC, alignment=TA_CENTER,
        spaceAfter=6, fontName=_FONT_NORM)
    S_QUEST  = ParagraphStyle("quest_libre", parent=styles["Normal"],
        fontSize=10, textColor=TSEC, alignment=TA_CENTER,
        spaceAfter=14, fontName=_FONT_ITAL)
    S_PIED   = ParagraphStyle("pied_libre", parent=styles["Normal"],
        fontSize=8, textColor=TSEC, alignment=TA_CENTER,
        fontName=_FONT_NORM)
    from reportlab.lib.enums import TA_RIGHT as _TA_R_libre
    _ALIGN_LIBRE = _TA_R_libre if _RTL else 0
    _IND_L_libre = 0 if _RTL else 4
    _IND_R_libre = 4 if _RTL else 0

    S_HDR    = ParagraphStyle("th_libre", parent=styles["Normal"],
        fontSize=9, fontName=_FONT_BOLD, textColor=WHITE,
        leftIndent=_IND_L_libre, rightIndent=_IND_R_libre,
        alignment=_ALIGN_LIBRE)
    S_CELL   = ParagraphStyle("td_libre", parent=styles["Normal"],
        fontSize=9, textColor=TEXTE, fontName=_FONT_NORM,
        leftIndent=_IND_L_libre, rightIndent=_IND_R_libre,
        alignment=_ALIGN_LIBRE)
    S_SCAL   = ParagraphStyle("scal_libre", parent=styles["Normal"],
        fontSize=32, textColor=BLEU_C, alignment=TA_CENTER,
        fontName=_FONT_BOLD)
    S_SH     = ParagraphStyle("sh_libre", parent=styles["Normal"],
        fontSize=11, textColor=WHITE, fontName=_FONT_BOLD,
        leftIndent=0 if _RTL else 6, rightIndent=6 if _RTL else 0)
    S_BV     = ParagraphStyle("bv_libre", parent=styles["Normal"],
        fontSize=10, textColor=VERT_B, spaceAfter=5,
        fontName=_FONT_NORM,
        leftIndent=0 if _RTL else 10, rightIndent=10 if _RTL else 0,
        alignment=_ALIGN_LIBRE)
    S_BR     = ParagraphStyle("br_libre", parent=styles["Normal"],
        fontSize=10, textColor=ROUGE_B, spaceAfter=5,
        fontName=_FONT_NORM,
        leftIndent=0 if _RTL else 10, rightIndent=10 if _RTL else 0,
        alignment=_ALIGN_LIBRE)
    S_CONCL  = ParagraphStyle("concl_libre", parent=styles["Normal"],
        fontSize=10, textColor=TEXTE, leftIndent=8, rightIndent=8,
        spaceBefore=4, spaceAfter=4, fontName=_FONT_NORM,
        alignment=_ALIGN_LIBRE)

    doc = SimpleDocTemplate(
        str(chemin), pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        title=label, author="Agent IA Transport",
    )

    story = []

    # ── EN-TÊTE ───────────────────────────────────────────────────────────────
    barre = Table([[" "]], colWidths=[W], rowHeights=[0.4*cm])
    barre.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), BLEU)]))
    story.append(barre)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(_ar2(label) if _RTL else label, S_TITRE))
    if _RTL:
        # En RTL : tout en latin pour éviter les inversions bidi de ReportLab
        _date_str = f"ERP Transport Terrestre — {date.today().strftime('%d/%m/%Y')} — {datetime.now().strftime('%H:%M')}"
    else:
        _date_str = f"ERP Transport Terrestre — {date.today().strftime('%d/%m/%Y')} {'a' if langue=='fr' else 'at'} {datetime.now().strftime('%H:%M')}"
    story.append(Paragraph(_date_str, S_DATE))
    story.append(Paragraph(_ar2(f"{_LL['demande']} : {question}") if _RTL else f"{_LL['demande']} : {question}", S_QUEST))
    story.append(HRFlowable(width=W, thickness=1.5, color=BLEU_C))
    story.append(Spacer(1, 0.4*cm))

    # ── RÉSULTAT SCALAIRE ─────────────────────────────────────────────────────
    is_scalaire = len(rows) == 1 and len(rows[0]) == 1
    if is_scalaire:
        val     = rows[0][0]
        val_str = f"{val:,.1f}" if isinstance(val, float) else str(val)
        lbl_str = colonnes[0].replace("_", " ").title() if colonnes else "Resultat"

        card = Table([
            [Paragraph(val_str, S_SCAL)],
            [Paragraph(lbl_str, ParagraphStyle("lbl", parent=styles["Normal"],
                fontSize=12, textColor=TSEC, alignment=TA_CENTER))],
        ], colWidths=[W])
        card.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), GRIS),
            ("TOPPADDING",    (0,0), (-1,-1), 24),
            ("BOTTOMPADDING", (0,0), (-1,-1), 24),
            ("BOX",           (0,0), (-1,-1), 0.5, GRIS_B),
        ]))
        story.append(card)
        story.append(Spacer(1, 0.4*cm))

    # ── RÉSULTAT TABULAIRE ────────────────────────────────────────────────────
    elif rows and colonnes:
        nb  = min(len(colonnes), 8)
        cw  = [W / nb] * nb

        # Bandeau
        sh = Table([[Paragraph(_ar2(f"{_LL['donnees']} : {len(rows)} {_LL['lignes']}") if _RTL else f"{_LL['donnees']} : {len(rows)} {_LL['lignes']}", S_SH)]],
            colWidths=[W], rowHeights=[0.65*cm])
        sh.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), BLEU_C),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(sh)
        story.append(Spacer(1, 0.2*cm))

        # Tableau
        # En RTL, inverser l'ordre des colonnes pour lecture droite→gauche
        col_indices = list(range(nb))
        if _RTL:
            col_indices = list(reversed(col_indices))
        hdr = [Paragraph(_ar2(_traduire_colonne(colonnes[i])) if _RTL else _traduire_colonne(colonnes[i]), S_HDR) for i in col_indices]
        trows = [hdr]
        for row in rows[:50]:
            trow = []
            for i in col_indices:
                cell = list(row)[i] if i < len(row) else None
                if cell is None:     v = "-"
                elif isinstance(cell, float): v = f"{cell:,.2f}"
                else:                v = _traduire_valeur(str(cell)[:55])
                trow.append(Paragraph(_ar2(v) if _RTL else v, S_CELL))
            trows.append(trow)

        det = Table(trows, colWidths=cw, repeatRows=1)
        det.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  BLEU_C),
            ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [white, GRIS]),
            ("GRID",          (0,0), (-1,-1), 0.4, GRIS_B),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(det)

        if len(rows) > 50:
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(
                f"{_LL['limite']} {len(rows)} resultats.",
                ParagraphStyle("note", parent=styles["Normal"], fontSize=8, textColor=TSEC)
            ))
        story.append(Spacer(1, 0.4*cm))

    # ── SYNTHÈSE ANALYTIQUE ───────────────────────────────────────────────────
    # Générer les points via LLM ou fallback automatique
    positifs   = []
    attentions = []

    if llm is not None and rows:
        try:
            # Résumé des données pour le LLM
            nb_lignes  = len(rows)
            apercu     = []
            for row in rows[:5]:
                apercu.append(" | ".join(str(v) for v in row if v is not None))
            apercu_str = "\n".join(apercu)

            _LANG_INSTR = {
                "fr": ("Réponds UNIQUEMENT en français.",
                       "Rédige en JSON UNIQUEMENT (sans markdown) :"),
                "en": ("Reply ONLY in English.",
                       "Write in JSON ONLY (no markdown):"),
                "ar": ("أجب باللغة العربية فقط.",
                       "اكتب بتنسيق JSON فقط (بدون markdown):"),
            }
            _li = _LANG_INSTR.get(langue, _LANG_INSTR["fr"])

            prompt_synthese = (
                f"{_li[0]}\n"
                f"Tu analyses un rapport ERP Transport Terrestre tunisien.\n"
                f"Question : {question}\n"
                f"Nombre de resultats : {nb_lignes}\n"
                f"Apercu des donnees :\n{apercu_str}\n\n"
                f"{_li[1]}\n"
                f"{{\n"
                f"  \"positifs\": [\"point1\", \"point2\"],\n"
                f"  \"attentions\": [\"point1\", \"point2\"],\n"
                f"  \"conclusion\": \"texte court\"\n"
                f"}}\n"
                f"Maximum 2 points chacun. Sois concis et factuel."
            )
            import json as _json
            raw = llm.invoke(prompt_synthese).strip()
            # Nettoyer le JSON
            raw = raw.replace("```json", "").replace("```", "").strip()
            parsed = _json.loads(raw)
            positifs   = parsed.get("positifs",   [])[:3]
            attentions = parsed.get("attentions", [])[:3]
            conclusion_llm = parsed.get("conclusion", "")
        except Exception:
            positifs   = []
            attentions = []
            conclusion_llm = ""
    else:
        conclusion_llm = ""

    # Fallback si LLM n'a rien retourné
    _FB = {
        "fr": {
            "pos_scal":  lambda v:   f"Donnee recuperee avec succes : {v}",
            "pos_tab":   lambda n:   f"{n} enregistrement(s) trouve(s) pour cette demande.",
            "att_nodata":"Aucune donnee trouvee pour cette periode ou ce filtre.",
            "att_limit": "Resultats limites a 50 lignes — filtrer pour plus de precision.",
            "att_ok":    "Aucun point d'attention critique detecte.",
            "concl_0":   "Aucune donnee disponible pour cette demande.",
            "concl_ok":  lambda n:   f"Rapport genere avec succes. {n} enregistrement(s) correspondent a la demande.",
        },
        "en": {
            "pos_scal":  lambda v:   f"Data retrieved successfully: {v}",
            "pos_tab":   lambda n:   f"{n} record(s) found for this request.",
            "att_nodata":"No data found for this period or filter.",
            "att_limit": "Results limited to 50 rows — filter for more precision.",
            "att_ok":    "No critical attention point detected.",
            "concl_0":   "No data available for this request.",
            "concl_ok":  lambda n:   f"Report generated successfully. {n} record(s) match the request.",
        },
        "ar": {
            "pos_scal":  lambda v:   f"تم استرداد البيانات بنجاح : {v}",
            "pos_tab":   lambda n:   f"تم العثور على {n} سجل(ات) لهذا الطلب.",
            "att_nodata":"لا توجد بيانات لهذه الفترة أو هذا التصفية.",
            "att_limit": "النتائج محدودة بـ 50 سطراً — استخدم تصفية أدق.",
            "att_ok":    "لا توجد نقاط انتباه حرجة.",
            "concl_0":   "لا توجد بيانات متاحة لهذا الطلب.",
            "concl_ok":  lambda n:   f"تم إنشاء التقرير بنجاح. {n} سجل(ات) تطابق الطلب.",
        },
    }
    _fb = _FB.get(langue, _FB["fr"])

    if not positifs and rows:
        nb = len(rows)
        if is_scalaire:
            positifs = [_fb["pos_scal"](rows[0][0])]
        else:
            positifs = [_fb["pos_tab"](nb)]

    if not attentions:
        if not rows:
            attentions = [_fb["att_nodata"]]
        elif len(rows) >= 50:
            attentions = [_fb["att_limit"]]
        else:
            attentions = [_fb["att_ok"]]

    if not conclusion_llm:
        if not rows:
            conclusion_llm = _fb["concl_0"]
        else:
            conclusion_llm = _fb["concl_ok"](len(rows))

    # Bandeau synthèse
    sh_syn = Table([[Paragraph(_ar2(_LL["synthese"]) if _RTL else _LL["synthese"], S_SH)]],
        colWidths=[W], rowHeights=[0.65*cm])
    sh_syn.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BLEU),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(sh_syn)
    story.append(Spacer(1, 0.25*cm))

    col_w = (W - 0.3*cm) / 2

    def _bloc(titre, points, bg_h, bg_b, sty, icone):
        titre_aff = _ar2(titre) if _RTL else titre
        hdr = Table([[Paragraph(f"{icone}  {titre_aff}", ParagraphStyle("bh_libre",
                parent=styles["Normal"], fontSize=10,
                fontName=_FONT_BOLD, textColor=WHITE, leftIndent=6))]],
            colWidths=[col_w], rowHeights=[0.55*cm])
        hdr.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg_h),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))
        lignes = [[Paragraph(_ar2(f"• {pt}") if _RTL else f"• {pt}", sty)] for pt in points] or                  [[Paragraph("  —", sty)]]
        bdy = Table(lignes, colWidths=[col_w])
        bdy.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), bg_b),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ]))
        return hdr, bdy

    h_v, b_v = _bloc(_LL["positifs"],    positifs,   VERT,  VERT_L,  S_BV, "✔")
    h_r, b_r = _bloc(_LL["attentions"], attentions, ROUGE, ROUGE_L, S_BR, "⚠")

    # Ordre fixe : positifs (vert) toujours en premier dans le tableau
    # ReportLab place la 1ère cellule à gauche en LTR, à droite en RTL via alignment
    row_h = Table([[h_v, h_r]], colWidths=[col_w, col_w])
    row_b = Table([[b_v, b_r]], colWidths=[col_w, col_w])
    row_b.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    story.append(KeepTogether([row_h, row_b]))

    # ── CONCLUSION ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.35*cm))
    concl = Table([[Paragraph(_ar2(f"{_LL['conclusion']} : {conclusion_llm}") if _RTL else f"{_LL['conclusion']} : {conclusion_llm}", S_CONCL)]],
        colWidths=[W])
    concl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BLEU_LT),
        ("BOX",           (0,0), (-1,-1), 0.8, BLEU_C),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    story.append(concl)

    # ── PIED DE PAGE ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    bb = Table([[" "]], colWidths=[W], rowHeights=[0.2*cm])
    bb.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), BLEU_C)]))
    story.append(bb)
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(
        (_ar2(f"{_LL['pied']} — ERP Odoo 19 — {datetime.now().strftime('%d/%m/%Y %H:%M')}") if _RTL else f"{_LL['pied']} — ERP Odoo 19 — {datetime.now().strftime('%d/%m/%Y %H:%M')}"),
        S_PIED
    ))

    doc.build(story)