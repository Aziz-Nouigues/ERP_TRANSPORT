"""
rapport_pdf.py v3 — Design professionnel avec KPI cards + synthèse analytique
Points positifs / Points d'attention générés automatiquement depuis les données SQL
"""
from pathlib import Path
from datetime import date, datetime


# ---------------------------------------------------------------------------
# ANALYSE CONTEXTUELLE
# ---------------------------------------------------------------------------

def _analyser_rapport(type_rapport: str, data: dict) -> tuple:
    """
    Retourne (points_positifs, points_attention) selon le type de rapport et les données.
    """
    positifs   = []
    attentions = []

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
                f"{actives} police(s) d'assurance active(s) — couverture du parc assurée."
            )
        if alerte == 0 and expirees == 0 and resiliees == 0:
            positifs.append(
                "Aucune police en alerte, expirée ou résiliée — stabilité contractuelle optimale."
            )
        if sinistres == 0:
            positifs.append(
                "Aucun sinistre enregistré ce mois — bilan sécurité routière excellent."
            )
        if alerte > 0:
            attentions.append(
                f"{alerte} police(s) en état d'alerte — renouvellement urgent requis."
            )
        if expirees > 0:
            attentions.append(
                f"{expirees} police(s) expirée(s) — des bus circulent sans couverture active."
            )
        if resiliees > 0:
            attentions.append(
                f"{resiliees} police(s) résiliée(s) — vérifier la couverture des véhicules concernés."
            )
        if sinistres > 0:
            m_fmt = f"{montant:,.0f} TND" if isinstance(montant, (int, float)) else str(montant)
            attentions.append(
                f"{sinistres} sinistre(s) déclaré(s) ce mois pour un montant de {m_fmt} — "
                "analyser les causes et renforcer les mesures de prévention."
            )
        if isinstance(expir30, list) and len(expir30) > 0:
            attentions.append(
                f"{len(expir30)} police(s) expirant dans les 30 prochains jours — "
                "planifier les renouvellements sans délai."
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
                f"Taux de disponibilité du parc : {taux}% ({en_service}/{total} bus en service) — niveau satisfaisant."
            )
        if actives == total and total > 0:
            positifs.append(
                "Tous les bus disposent d'une police d'assurance active."
            )
        if en_panne == 0 and maintenance == 0:
            positifs.append(
                "Aucun bus en panne ni en maintenance — parc en excellente condition opérationnelle."
            )
        if taux < 80:
            attentions.append(
                f"Taux de disponibilité à {taux}% — en dessous du seuil recommandé de 80%."
            )
        if en_panne > 0:
            attentions.append(
                f"{en_panne} bus en panne — mobiliser la maintenance pour réduire l'immobilisation."
            )
        if maintenance > 0:
            attentions.append(
                f"{maintenance} bus en maintenance — vérifier les délais de remise en service."
            )
        if hors_svc > 0:
            attentions.append(
                f"{hors_svc} bus hors service — évaluer si une remise en état ou une réforme est nécessaire."
            )

    elif type_rapport in ("rapport_journalier", "rapport_hebdomadaire", "rapport_mensuel"):
        realisees = data.get("tournees_realisees", 0) or 0
        annulees  = data.get("tournees_annulees",  0) or 0
        total     = data.get("tournees_total",     0) or 0
        ecart     = data.get("ecart_moyen",        0) or 0

        taux_real = round(realisees / total * 100) if total > 0 else 0
        if taux_real >= 90:
            positifs.append(
                f"Taux de réalisation : {taux_real}% ({realisees}/{total} tournées) — performance opérationnelle élevée."
            )
        if annulees == 0:
            positifs.append(
                "Aucune tournée annulée — continuité de service assurée."
            )
        if isinstance(ecart, (int, float)) and abs(ecart) <= 5:
            positifs.append(
                f"Écart kilométrique moyen de {ecart:.1f} km — planification conforme au terrain."
            )
        if taux_real < 90 and total > 0:
            attentions.append(
                f"Taux de réalisation à {taux_real}% — identifier et corriger les causes de non-réalisation."
            )
        if annulees > 0:
            attentions.append(
                f"{annulees} tournée(s) annulée(s) — analyser les motifs et prendre des mesures correctives."
            )
        if isinstance(ecart, (int, float)) and abs(ecart) > 10:
            attentions.append(
                f"Écart kilométrique moyen de {ecart:.1f} km — revoir la planification des itinéraires."
            )

    elif type_rapport == "bilan_carburant":
        litres  = data.get("litres_total", 0) or 0
        valides = data.get("bons_valides", 0) or 0
        bgi     = data.get("bgi_count",   0) or 0
        bge     = data.get("bge_count",   0) or 0

        if valides > 0:
            positifs.append(
                f"{valides} bon(s) carburant validé(s) ce mois — consommation totale : {litres:,.0f} litres."
            )
        if bgi >= bge and bgi > 0:
            positifs.append(
                f"Majorité de ravitaillements BGI ({bgi} internes vs {bge} externes) — maîtrise des coûts carburant."
            )
        if litres == 0:
            attentions.append(
                "Aucune consommation carburant enregistrée ce mois — vérifier la saisie des bons."
            )
        if bge > bgi:
            attentions.append(
                f"Plus de BGE ({bge}) que de BGI ({bgi}) — optimiser l'utilisation de la cuve interne."
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
                f"{taux_t}% des courriers traités ou classés ({traites + classes}/{total}) — gestion documentaire efficace."
            )
        if retard == 0:
            positifs.append(
                "Aucun courrier en retard de traitement — délais respectés."
            )
        if retard > 0:
            attentions.append(
                f"{retard} courrier(s) en retard (> 7 jours) — prioriser leur traitement immédiat."
            )
        if attente > 0:
            attentions.append(
                f"{attente} courrier(s) en attente de traitement ou de diffusion."
            )

    if not positifs:
        positifs.append("Rapport généré avec succès — aucune anomalie majeure détectée.")
    if not attentions:
        attentions.append("Aucun point d'attention critique — situation nominale.")

    return positifs, attentions


# ---------------------------------------------------------------------------
# GÉNÉRATION PDF
# ---------------------------------------------------------------------------

def generer_pdf_rapport(type_rapport: str, label: str, data: dict, chemin: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER

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

    S_TITRE    = ParagraphStyle("titre", parent=styles["Normal"],
        fontSize=22, textColor=BLEU, alignment=TA_CENTER,
        spaceAfter=2, fontName="Helvetica-Bold")
    S_DATE     = ParagraphStyle("date", parent=styles["Normal"],
        fontSize=10, textColor=TSEC, alignment=TA_CENTER, spaceAfter=14)
    S_NORM     = ParagraphStyle("norm", parent=styles["Normal"],
        fontSize=10, textColor=TEXTE, spaceAfter=4)
    S_PIED     = ParagraphStyle("pied", parent=styles["Normal"],
        fontSize=8, textColor=TSEC, alignment=TA_CENTER)
    S_SH       = ParagraphStyle("sh", parent=styles["Normal"],
        fontSize=11, textColor=white, fontName="Helvetica-Bold", leftIndent=6)
    S_BULLET_V = ParagraphStyle("bv", parent=styles["Normal"],
        fontSize=10, textColor=VERT_B, leftIndent=10, spaceAfter=5)
    S_BULLET_R = ParagraphStyle("br", parent=styles["Normal"],
        fontSize=10, textColor=ROUGE_B, leftIndent=10, spaceAfter=5)
    S_CONCL    = ParagraphStyle("concl", parent=styles["Normal"],
        fontSize=10, textColor=TEXTE, leftIndent=8, rightIndent=8,
        spaceBefore=4, spaceAfter=4)

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
    story.append(Paragraph(label, S_TITRE))
    story.append(Paragraph(
        f"ERP Transport Terrestre — {date.today().strftime('%d/%m/%Y')} a {datetime.now().strftime('%H:%M')}",
        S_DATE
    ))
    story.append(HRFlowable(width=W, thickness=1.5, color=BLEU_C))
    story.append(Spacer(1, 0.4*cm))

    # ── CONFIG INDICATEURS ────────────────────────────────────────────────────
    CONFIG = {
        # ── Exploitation ──────────────────────────────────────────────────────
        "tournees_planifiees":    ("Planifiees",            BLEU_C, False, None),
        "tournees_en_cours":      ("En cours",              ORANGE, False, None),
        "tournees_realisees":     ("Realisees",             VERT,   False, None),
        "tournees_annulees":      ("Annulees",              ROUGE,  False, None),
        "tournees_total":         ("Total tournees",        BLEU,   False, None),
        "km_total":               ("Km parcourus",          BLEU,   False, None),
        "ecart_moyen":            ("Ecart km moyen",        ORANGE, False, None),
        "detail_tournees":        ("Detail tournees",       None,   True,
            ["Tournee","Ligne","Chauffeur","Bus","Direction","Etat","Dep.","Arr.","Km","Ecart"]),
        "top_chauffeurs":         ("Top chauffeurs",        None,   True,
            ["Chauffeur","Tournees","Km total"]),
        "km_par_bus":             ("Km par bus",            None,   True,
            ["Bus","Immat.","Tournees","Km"]),
        "annulations_motif":      ("Motifs annulation",     None,   True,
            ["Motif","Nombre"]),
        "detail_annulees":        ("Tournees annulees",     None,   True,
            ["Tournee","Ligne","Chauffeur","Motif","Note"]),
        "activite_lignes":        ("Activite par ligne",    None,   True,
            ["Ligne","Tournees","Km total"]),
        "repartition_direction":  ("Repartition direction", None,   True,
            ["Direction","Nombre"]),
        # ── Parc bus ──────────────────────────────────────────────────────────
        "total_bus":              ("Total bus",             BLEU,   False, None),
        "en_service":             ("En service",            VERT,   False, None),
        "hors_service":           ("Hors service",          ROUGE,  False, None),
        "en_panne":               ("En panne",              ORANGE, False, None),
        "en_maintenance":         ("En maintenance",        ORANGE, False, None),
        "detail_bus":             ("Detail parc bus",       None,   True,
            ["Bus","Immat.","Etat","Police","Expiration","Compagnie","Km mois"]),
        "bus_sans_assurance":     ("Bus sans assurance",    None,   True,
            ["Bus","Immat.","Etat"]),
        # ── Assurance ─────────────────────────────────────────────────────────
        "polices_actives":        ("Polices actives",       VERT,   False, None),
        "polices_alerte":         ("En alerte",             ORANGE, False, None),
        "polices_expirees":       ("Expirees",              ROUGE,  False, None),
        "polices_resiliees":      ("Resiliees",             ROUGE,  False, None),
        "sinistres_mois":         ("Sinistres ce mois",     ORANGE, False, None),
        "montant_sinistres":      ("Montant accorde TND",   ROUGE,  False, None),
        "montant_net_verse":      ("Montant net verse TND", VERT,   False, None),
        "detail_polices_actives": ("Polices actives detail",None,   True,
            ["Police","Type","Compagnie","Bus","Immat.","Debut","Fin","Prime TND","Obligatoire"]),
        "detail_sinistres":       ("Sinistres du mois",     None,   True,
            ["Ref.","Etat","Date","Nature","Lieu","Reclame","Accorde","Net verse","Bus","Immat.","Chauffeur","Description"]),
        "expiration_30j":         ("Polices expirant <30j", None,   True,
            ["Police","Type","Compagnie","Bus","Expiration","Prime TND","Obligatoire"]),
        "assurances_chauffeurs":  ("Assurances chauffeurs", None,   True,
            ["Police","Chauffeur","Type","Etat","Debut","Fin","Compagnie","Prime TND","Obligatoire"]),
        # ── Carburant ─────────────────────────────────────────────────────────
        "bons_valides":           ("Bons valides",          VERT,   False, None),
        "litres_total":           ("Litres consommes",      BLEU,   False, None),
        "bgi_count":              ("Bons BGI",              BLEU,   False, None),
        "bge_count":              ("Bons BGE",              BLEU,   False, None),
        "litres_bgi":             ("Litres BGI",            BLEU,   False, None),
        "litres_bge":             ("Litres BGE",            ORANGE, False, None),
        "cout_total":             ("Cout total TND",        ROUGE,  False, None),
        "litres_par_bus":         ("Consommation par bus",  None,   True,
            ["Bus","Immat.","Bons","Litres BGI","Litres BGE","Total litres"]),
        "detail_bons_recents":    ("10 derniers bons",      None,   True,
            ["Reference","Type","Date","Litres","Cout TND"]),
        # ── BOC ───────────────────────────────────────────────────────────────
        "total_arrivee":          ("Courriers recus",       BLEU,   False, None),
        "total_depart":           ("Courriers envoyes",     BLEU,   False, None),
        "en_attente":             ("En attente",            ORANGE, False, None),
        "traites":                ("Traites",               VERT,   False, None),
        "classes":                ("Classes",               VERT,   False, None),
        "en_retard":              ("En retard",             ROUGE,  False, None),
        "total_depart":           ("Courriers envoyes",     BLEU,   False, None),
        "detail_retard":          ("Courriers en retard",   None,   True,
            ["Ref.","Sujet","Expediteur","Date arrivee","Etat","Type","Jours retard"]),
        "detail_en_attente":      ("Courriers en attente",  None,   True,
            ["Ref.","Sujet","Expediteur","Date arrivee","Etat","Type","Echeance"]),
    }

    def cfg(cle):
        return CONFIG.get(cle, (cle.replace("_", " ").title(), BLEU, False, None))

    scalaires = [(k, v) for k, v in data.items() if not isinstance(v, list) and v is not None]
    listes    = [(k, v) for k, v in data.items() if isinstance(v, list) and v]

    # ── KPI CARDS ─────────────────────────────────────────────────────────────
    if scalaires:
        sh = Table([[Paragraph("Indicateurs cles", S_SH)]],
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
                    [Paragraph(val_str, ParagraphStyle("kv", parent=styles["Normal"],
                        fontSize=26, textColor=col, alignment=TA_CENTER,
                        fontName="Helvetica-Bold"))],
                    [Paragraph(lbl, ParagraphStyle("kl", parent=styles["Normal"],
                        fontSize=9, textColor=TSEC, alignment=TA_CENTER))],
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

        sh2 = Table([[Paragraph(lbl_det, S_SH)]],
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

        s_hdr  = ParagraphStyle("th", parent=styles["Normal"],
            fontSize=9, fontName="Helvetica-Bold", textColor=white, leftIndent=4)
        s_cell = ParagraphStyle("td", parent=styles["Normal"],
            fontSize=9, textColor=TEXTE, leftIndent=4)

        trows = [[Paragraph(str(h), s_hdr) for h in ents]]
        for row in valeur[:20]:
            trow = []
            for cell in list(row)[:nb]:
                if cell is None:
                    v = "-"
                elif isinstance(cell, float):
                    v = f"{cell:,.1f}"
                else:
                    v = str(cell)[:55]
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
    positifs, attentions = _analyser_rapport(type_rapport, data)

    story.append(Spacer(1, 0.2*cm))

    sh_syn = Table([[Paragraph("Synthese analytique", S_SH)]],
        colWidths=[W], rowHeights=[0.65*cm])
    sh_syn.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BLEU),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(sh_syn)
    story.append(Spacer(1, 0.25*cm))

    col_w = (W - 0.3*cm) / 2

    def _build_bloc(titre, points, bg_header, bg_body, bullet_style):
        header = Table(
            [[Paragraph(titre, ParagraphStyle("bh", parent=styles["Normal"],
                fontSize=10, fontName="Helvetica-Bold", textColor=white, leftIndent=6))]],
            colWidths=[col_w], rowHeights=[0.55*cm]
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg_header),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))
        rows = [[Paragraph(f"  {pt}", bullet_style)] for pt in points] or \
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

    h_v, b_v = _build_bloc("Points positifs",    positifs,   VERT,  VERT_L,  S_BULLET_V)
    h_r, b_r = _build_bloc("Points d'attention", attentions, ROUGE, ROUGE_L, S_BULLET_R)

    # En-têtes côte à côte
    row_h = Table([[h_v, h_r]], colWidths=[col_w, col_w])
    # Corps côte à côte
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
    if nb_att == 0 or (nb_att == 1 and "nominale" in attentions[0]):
        conclusion = (
            "Bilan global satisfaisant. Les indicateurs sont dans les normes attendues. "
            "Maintenir les bonnes pratiques en cours."
        )
    elif nb_ok >= nb_att:
        conclusion = (
            "Bilan globalement positif avec quelques points a surveiller. "
            "Les actions correctives identifiees permettront d'optimiser les performances."
        )
    else:
        conclusion = (
            "Plusieurs points d'attention necessitent une intervention rapide. "
            "Il est recommande de traiter en priorite les alertes signalees dans ce rapport."
        )

    concl_table = Table(
        [[Paragraph(f"Conclusion : {conclusion}", S_CONCL)]],
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
        f"Genere par Agent IA Transport — ERP Odoo 19 — {datetime.now().strftime('%d/%m/%Y a %H:%M')}",
        S_PIED
    ))

    doc.build(story)