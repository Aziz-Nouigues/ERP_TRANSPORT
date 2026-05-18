"""
rapport_pdf.py v2 — Design professionnel avec KPI cards
"""
from pathlib import Path
from datetime import date, datetime


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

    BLEU   = HexColor("#1a3a6b")
    BLEU_C = HexColor("#2196F3")
    BLEU_L = HexColor("#e8f0fe")
    GRIS   = HexColor("#f8f9fa")
    GRIS_B = HexColor("#e9ecef")
    VERT   = HexColor("#28a745")
    ROUGE  = HexColor("#dc3545")
    ORANGE = HexColor("#fd7e14")
    TEXTE  = HexColor("#212529")
    TSEC   = HexColor("#6c757d")

    styles = getSampleStyleSheet()
    W = 17.4 * cm

    S_TITRE = ParagraphStyle("titre", parent=styles["Normal"],
        fontSize=22, textColor=BLEU, alignment=TA_CENTER,
        spaceAfter=2, fontName="Helvetica-Bold")
    S_DATE  = ParagraphStyle("date", parent=styles["Normal"],
        fontSize=10, textColor=TSEC, alignment=TA_CENTER, spaceAfter=14)
    S_NORM  = ParagraphStyle("norm", parent=styles["Normal"],
        fontSize=10, textColor=TEXTE, spaceAfter=4)
    S_PIED  = ParagraphStyle("pied", parent=styles["Normal"],
        fontSize=8,  textColor=TSEC, alignment=TA_CENTER)

    doc = SimpleDocTemplate(
        str(chemin), pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        title=f"{label} — {date.today().strftime('%d/%m/%Y')}",
        author="Agent IA Transport",
    )

    story = []

    # En-tête
    barre = Table([[" "]], colWidths=[W], rowHeights=[0.4*cm])
    barre.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLEU)]))
    story.append(barre)
    story.append(Spacer(1, 0.35*cm))
    story.append(Paragraph(label, S_TITRE))
    story.append(Paragraph(
        f"ERP Transport Terrestre — {date.today().strftime('%d/%m/%Y')} à {datetime.now().strftime('%H:%M')}",
        S_DATE
    ))
    story.append(HRFlowable(width=W, thickness=1.5, color=BLEU_C))
    story.append(Spacer(1, 0.4*cm))

    CONFIG = {
        "tournees_planifiees": ("Planifiées",        BLEU_C, False, None),
        "tournees_en_cours":   ("En cours",          ORANGE, False, None),
        "tournees_realisees":  ("Réalisées",         VERT,   False, None),
        "tournees_annulees":   ("Annulées",          ROUGE,  False, None),
        "tournees_total":      ("Total tournées",    BLEU,   False, None),
        "km_total":            ("Km parcourus",      BLEU,   False, None),
        "ecart_moyen":         ("Écart km moyen",    ORANGE, False, None),
        "top_chauffeurs":      ("Top chauffeurs",    None,   True,  ["Chauffeur","Tournées"]),
        "km_par_bus":          ("Km par bus",        None,   True,  ["Bus","Km"]),
        "annulations_motif":   ("Motifs annulation", None,   True,  ["Motif","Nombre"]),
        "detail_annulees":     ("Tournées annulées", None,   True,  ["Tournée","Motif"]),
        "total_bus":           ("Total bus",         BLEU,   False, None),
        "en_service":          ("En service",        VERT,   False, None),
        "hors_service":        ("Hors service",      ROUGE,  False, None),
        "en_panne":            ("En panne",          ORANGE, False, None),
        "en_maintenance":      ("En maintenance",    ORANGE, False, None),
        "detail_bus":          ("Détail parc bus",   None,   True,  ["Bus","Immat.","État","Police","Expiration"]),
        "polices_actives":     ("Polices actives",   VERT,   False, None),
        "polices_alerte":      ("En alerte",         ORANGE, False, None),
        "polices_expirees":    ("Expirées",          ROUGE,  False, None),
        "polices_resiliees":   ("Résiliées",         ROUGE,  False, None),
        "sinistres_mois":      ("Sinistres ce mois", ORANGE, False, None),
        "montant_sinistres":   ("Montant TND",       ROUGE,  False, None),
        "detail_sinistres":    ("Détail sinistres",  None,   True,  ["Réf.","État","Date","Montant","Bus"]),
        "expiration_30j":      ("Expire dans 30j",   None,   True,  ["Police","Expiration","Bus"]),
        "bons_valides":        ("Bons validés",      VERT,   False, None),
        "litres_total":        ("Litres consommés",  BLEU,   False, None),
        "bgi_count":           ("Bons BGI",          BLEU,   False, None),
        "bge_count":           ("Bons BGE",          BLEU,   False, None),
        "litres_par_bus":      ("Litres par bus",    None,   True,  ["Bus","Litres"]),
        "total_arrivee":       ("Courriers reçus",   BLEU,   False, None),
        "en_attente":          ("En attente",        ORANGE, False, None),
        "traites":             ("Traités",           VERT,   False, None),
        "classes":             ("Classés",           VERT,   False, None),
        "en_retard":           ("En retard",         ROUGE,  False, None),
    }

    def cfg(cle):
        return CONFIG.get(cle, (cle.replace("_"," ").title(), BLEU, False, None))

    scalaires = [(k,v) for k,v in data.items() if not isinstance(v,list) and v is not None]
    listes    = [(k,v) for k,v in data.items() if isinstance(v,list) and v]

    # ── KPI CARDS ────────────────────────────────────────────────────────────
    if scalaires:
        # Bandeau section
        sh = Table([[Paragraph("Indicateurs clés", ParagraphStyle("sh",
            parent=styles["Normal"], fontSize=11, textColor=white,
            fontName="Helvetica-Bold", leftIndent=6))]],
            colWidths=[W], rowHeights=[0.65*cm])
        sh.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLEU),
                                ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story.append(sh)
        story.append(Spacer(1,0.25*cm))

        items = scalaires
        for i in range(0, len(items), 3):
            groupe = items[i:i+3]
            cells = []
            for cle, valeur in groupe:
                c = cfg(cle)
                lbl = c[0]
                col = c[1] or BLEU
                if isinstance(valeur, float):
                    val_str = f"{valeur:,.1f}"
                else:
                    val_str = str(valeur)
                cell_t = Table([
                    [Paragraph(val_str, ParagraphStyle("kv", parent=styles["Normal"],
                        fontSize=26, textColor=col, alignment=TA_CENTER,
                        fontName="Helvetica-Bold"))],
                    [Paragraph(lbl, ParagraphStyle("kl", parent=styles["Normal"],
                        fontSize=9, textColor=TSEC, alignment=TA_CENTER))],
                ], colWidths=[W/3 - 0.3*cm])
                cell_t.setStyle(TableStyle([
                    ("TOPPADDING",(0,0),(-1,-1),10),
                    ("BOTTOMPADDING",(0,0),(-1,-1),10),
                ]))
                cells.append(cell_t)
            while len(cells) < 3:
                cells.append(Paragraph("",S_NORM))
            row_t = Table([cells], colWidths=[W/3]*3)
            row_t.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1),GRIS),
                ("BOX",(0,0),(-1,-1),0.5,GRIS_B),
                ("INNERGRID",(0,0),(-1,-1),0.5,GRIS_B),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ]))
            story.append(row_t)
            story.append(Spacer(1,0.15*cm))
        story.append(Spacer(1,0.25*cm))

    # ── TABLEAUX DÉTAIL ────────────────────────────────────────────────────────
    for cle, valeur in listes:
        c = cfg(cle)
        lbl_det = c[0]
        entetes = c[3]

        sh2 = Table([[Paragraph(lbl_det, ParagraphStyle("sh2",
            parent=styles["Normal"], fontSize=11, textColor=white,
            fontName="Helvetica-Bold", leftIndent=6))]],
            colWidths=[W], rowHeights=[0.65*cm])
        sh2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLEU_C),
                                 ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))

        nb = len(valeur[0]) if valeur else 1
        cw = [W/nb]*nb
        ents = (entetes or [f"Col {i+1}" for i in range(nb)])[:nb]
        while len(ents) < nb: ents.append("")

        s_hdr  = ParagraphStyle("th", parent=styles["Normal"], fontSize=9,
                                fontName="Helvetica-Bold", textColor=white, leftIndent=4)
        s_cell = ParagraphStyle("td", parent=styles["Normal"], fontSize=9,
                                textColor=TEXTE, leftIndent=4)

        trows = [[Paragraph(str(h), s_hdr) for h in ents]]
        for row in valeur[:20]:
            trow = []
            for cell in list(row)[:nb]:
                if cell is None: v = "-"
                elif isinstance(cell, float): v = f"{cell:,.1f}"
                else: v = str(cell)[:50]
                trow.append(Paragraph(v, s_cell))
            while len(trow) < nb: trow.append(Paragraph("",s_cell))
            trows.append(trow[:nb])

        det = Table(trows, colWidths=cw, repeatRows=1)
        det.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),BLEU_C),
            ("TEXTCOLOR",(0,0),(-1,0),white),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[white,GRIS]),
            ("GRID",(0,0),(-1,-1),0.4,GRIS_B),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ]))

        story.append(KeepTogether([sh2, Spacer(1,0.2*cm), det, Spacer(1,0.3*cm)]))

    # Pied de page
    story.append(Spacer(1,0.4*cm))
    bb = Table([[" "]], colWidths=[W], rowHeights=[0.2*cm])
    bb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLEU_C)]))
    story.append(bb)
    story.append(Spacer(1,0.15*cm))
    story.append(Paragraph(
        f"Généré par Agent IA Transport — ERP Odoo 19 — {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        S_PIED
    ))

    doc.build(story)