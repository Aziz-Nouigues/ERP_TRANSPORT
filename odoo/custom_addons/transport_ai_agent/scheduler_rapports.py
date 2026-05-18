"""
scheduler_rapports.py
Génère automatiquement un rapport hebdomadaire PDF chaque vendredi à 18h00.

Installation des dépendances :
    venv\Scripts\pip install reportlab schedule

Lancement (daemon) :
    venv\Scripts\python scheduler_rapports.py

Lancement en arrière-plan Windows :
    start /B venv\Scripts\python scheduler_rapports.py > logs\scheduler.log 2>&1
"""

import os
import sys
import logging
import schedule
import time
from datetime import datetime, date
from pathlib import Path

# Ajouter le dossier parent au path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# Dossier de sauvegarde des rapports
RAPPORTS_DIR = BASE_DIR / "rapports"
RAPPORTS_DIR.mkdir(exist_ok=True)
(BASE_DIR / "logs").mkdir(exist_ok=True)


# ── Connexion PostgreSQL ─────────────────────────────────────────────────────

def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "erp_db2"),
        user=os.getenv("PG_USER", "erp_user2"),
        password=os.getenv("PG_PASSWORD", ""),
        client_encoding="utf8",
    )


def run_sql(sql, params=None):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"SQL erreur: {e}")
        return []


# ── Collecte des données hebdomadaires ──────────────────────────────────────

def collecter_donnees_semaine():
    """Collecte tous les indicateurs pour le rapport hebdomadaire."""
    logger.info("Collecte des données hebdomadaires...")
    data = {}

    # Tournées
    data["tournees_realisees"] = run_sql(
        "SELECT COUNT(*) FROM transport_exploitation_tournee "
        "WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'realise'"
    )[0][0] if run_sql("SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'realise'") else 0

    data["tournees_annulees"] = run_sql(
        "SELECT COUNT(*) FROM transport_exploitation_tournee "
        "WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'annule'"
    )[0][0] if run_sql("SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'annule'") else 0

    data["tournees_total"] = run_sql(
        "SELECT COUNT(*) FROM transport_exploitation_tournee "
        "WHERE date >= CURRENT_DATE - INTERVAL '7 days'"
    )[0][0] if run_sql("SELECT COUNT(*) FROM transport_exploitation_tournee WHERE date >= CURRENT_DATE - INTERVAL '7 days'") else 0

    res_km = run_sql(
        "SELECT COALESCE(SUM(km_realise),0) FROM transport_exploitation_tournee "
        "WHERE date >= CURRENT_DATE - INTERVAL '7 days' AND state = 'realise'"
    )
    data["km_total"] = float(res_km[0][0]) if res_km else 0

    # Top chauffeur
    top_chauf = run_sql(
        "SELECT e.name, COUNT(*) AS nb FROM transport_exploitation_tournee t "
        "JOIN hr_employee e ON t.chauffeur_id = e.id "
        "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'realise' "
        "GROUP BY e.name ORDER BY nb DESC LIMIT 3"
    )
    data["top_chauffeurs"] = top_chauf

    # Top bus km
    top_bus = run_sql(
        "SELECT v.name, COALESCE(SUM(t.km_realise),0) AS km "
        "FROM transport_exploitation_tournee t "
        "JOIN fleet_vehicle v ON t.vehicle_id = v.id "
        "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'realise' "
        "GROUP BY v.name ORDER BY km DESC LIMIT 3"
    )
    data["km_par_bus"] = top_bus

    # Détail annulations
    annul = run_sql(
        "SELECT t.name, COALESCE(m.name,'Autre') FROM transport_exploitation_tournee t "
        "LEFT JOIN transport_exploitation_motif m ON t.motif_annulation_id = m.id "
        "WHERE t.date >= CURRENT_DATE - INTERVAL '7 days' AND t.state = 'annule'"
    )
    data["detail_annulees"] = annul

    # Parc bus
    data["bus_en_service"]   = run_sql("SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 47")[0][0] if run_sql("SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 47") else 0
    data["bus_hors_service"] = run_sql("SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 48")[0][0] if run_sql("SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 48") else 0
    data["bus_en_panne"]     = run_sql("SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 5")[0][0] if run_sql("SELECT COUNT(*) FROM fleet_vehicle WHERE state_id = 5") else 0

    # Assurance — polices expirant dans 30 jours
    polices_alerte = run_sql(
        "SELECT a.numero_police, a.date_fin, v.name AS bus "
        "FROM transport_assurance_bus a "
        "LEFT JOIN fleet_vehicle v ON a.vehicle_id = v.id "
        "WHERE a.state = 'active' AND a.date_fin <= CURRENT_DATE + INTERVAL '30 days' "
        "ORDER BY a.date_fin"
    )
    data["polices_alerte_30j"] = polices_alerte

    # Carburant
    res_litres = run_sql(
        "SELECT COALESCE(SUM(total_quantity),0) FROM transport_fuel_voucher "
        "WHERE state = 'done' AND date >= CURRENT_DATE - INTERVAL '7 days'"
    )
    data["litres_semaine"] = float(res_litres[0][0]) if res_litres else 0

    data["bons_valides"] = run_sql(
        "SELECT COUNT(*) FROM transport_fuel_voucher "
        "WHERE state = 'done' AND date >= CURRENT_DATE - INTERVAL '7 days'"
    )[0][0] if run_sql("SELECT COUNT(*) FROM transport_fuel_voucher WHERE state = 'done' AND date >= CURRENT_DATE - INTERVAL '7 days'") else 0

    # Sinistres semaine
    data["sinistres_semaine"] = run_sql(
        "SELECT COUNT(*) FROM transport_assurance_sinistre "
        "WHERE date_sinistre >= CURRENT_DATE - INTERVAL '7 days'"
    )[0][0] if run_sql("SELECT COUNT(*) FROM transport_assurance_sinistre WHERE date_sinistre >= CURRENT_DATE - INTERVAL '7 days'") else 0

    # Courrier BOC
    data["courriers_reçus"]   = run_sql("SELECT COUNT(*) FROM boc_courrier_arrivee WHERE date_arrivee >= CURRENT_DATE - INTERVAL '7 days'")[0][0] if run_sql("SELECT COUNT(*) FROM boc_courrier_arrivee WHERE date_arrivee >= CURRENT_DATE - INTERVAL '7 days'") else 0
    data["courriers_classes"] = run_sql("SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state = 'classe' AND date_arrivee >= CURRENT_DATE - INTERVAL '7 days'")[0][0] if run_sql("SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state = 'classe' AND date_arrivee >= CURRENT_DATE - INTERVAL '7 days'") else 0
    data["courriers_en_attente"] = run_sql("SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state IN ('enregistre','diffuse')")[0][0] if run_sql("SELECT COUNT(*) FROM boc_courrier_arrivee WHERE state IN ('enregistre','diffuse')") else 0

    logger.info(f"Données collectées : {len(data)} indicateurs")
    return data


# ── Génération PDF ───────────────────────────────────────────────────────────

def generer_pdf(data: dict, chemin: Path):
    """Génère le rapport PDF avec reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    aujourd_hui = date.today()
    debut_semaine = aujourd_hui.strftime("%d/%m/%Y")

    doc = SimpleDocTemplate(
        str(chemin),
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Rapport Hebdomadaire Transport — {debut_semaine}",
        author="Agent IA Transport",
    )

    styles = getSampleStyleSheet()
    BLEU    = HexColor("#1a3a6b")
    BLEU_C  = HexColor("#2196F3")
    GRIS    = HexColor("#f5f5f5")
    ORANGE  = HexColor("#FF9800")
    ROUGE   = HexColor("#F44336")
    VERT    = HexColor("#4CAF50")

    style_titre = ParagraphStyle("titre", parent=styles["Title"],
        fontSize=20, textColor=BLEU, alignment=TA_CENTER, spaceAfter=4)
    style_sous_titre = ParagraphStyle("sous_titre", parent=styles["Normal"],
        fontSize=11, textColor=HexColor("#555555"), alignment=TA_CENTER, spaceAfter=16)
    style_section = ParagraphStyle("section", parent=styles["Heading2"],
        fontSize=13, textColor=white, backColor=BLEU,
        spaceAfter=8, spaceBefore=12, leftIndent=-10, rightIndent=-10,
        borderPad=6)
    style_normal = ParagraphStyle("normal", parent=styles["Normal"],
        fontSize=10, spaceAfter=4)
    style_alerte = ParagraphStyle("alerte", parent=styles["Normal"],
        fontSize=10, textColor=ROUGE, spaceAfter=4)
    style_ok = ParagraphStyle("ok", parent=styles["Normal"],
        fontSize=10, textColor=VERT, spaceAfter=4)

    story = []

    # ── En-tête ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("RAPPORT HEBDOMADAIRE", style_titre))
    story.append(Paragraph(
        f"ERP Transport Terrestre Tunisie — Semaine du {debut_semaine}",
        style_sous_titre
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=BLEU))
    story.append(Spacer(1, 0.5*cm))

    # ── KPIs résumé ──────────────────────────────────────────────────────────
    taux = round(data["tournees_realisees"] / data["tournees_total"] * 100, 1) if data["tournees_total"] > 0 else 0

    kpis = [
        ["Indicateur", "Valeur", "Statut"],
        ["Tournées réalisées", str(data["tournees_realisees"]), "✓" if taux >= 80 else "⚠"],
        ["Tournées annulées", str(data["tournees_annulees"]), "✓" if data["tournees_annulees"] == 0 else "⚠"],
        ["Taux de réalisation", f"{taux}%", "✓" if taux >= 80 else "⚠"],
        ["Km total parcourus", f"{data['km_total']:,.1f} km", "✓"],
        ["Bons carburant validés", str(data["bons_valides"]), "✓"],
        ["Litres consommés", f"{data['litres_semaine']:,.1f} L", "✓"],
        ["Sinistres déclarés", str(data["sinistres_semaine"]), "✓" if data["sinistres_semaine"] == 0 else "⚠"],
        ["Courriers reçus", str(data["courriers_reçus"]), "✓"],
        ["Courriers en attente", str(data["courriers_en_attente"]), "✓" if data["courriers_en_attente"] == 0 else "⚠"],
    ]

    t_kpis = Table(kpis, colWidths=[8*cm, 4*cm, 3*cm])
    t_kpis.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), BLEU),
        ("TEXTCOLOR",    (0,0), (-1,0), white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 10),
        ("ALIGN",        (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, GRIS]),
        ("GRID",         (0,0), (-1,-1), 0.5, HexColor("#cccccc")),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ]))
    story.append(Paragraph("Tableau de bord", style_section))
    story.append(t_kpis)
    story.append(Spacer(1, 0.5*cm))

    # ── Top chauffeurs ────────────────────────────────────────────────────────
    story.append(Paragraph("Exploitation — Tournées", style_section))
    if data["top_chauffeurs"]:
        rows = [["Chauffeur", "Tournées réalisées"]]
        for nom, nb in data["top_chauffeurs"]:
            rows.append([nom, str(nb)])
        t = Table(rows, colWidths=[9*cm, 6*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), BLEU_C),
            ("TEXTCOLOR",  (0,0), (-1,0), white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN",      (1,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, GRIS]),
            ("GRID",       (0,0), (-1,-1), 0.5, HexColor("#cccccc")),
            ("FONTSIZE",   (0,0), (-1,-1), 10),
            ("TOPPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(Paragraph("Top chauffeurs de la semaine :", style_normal))
        story.append(t)
    else:
        story.append(Paragraph("Aucune tournée réalisée cette semaine.", style_normal))

    story.append(Spacer(1, 0.3*cm))

    # km par bus
    if data["km_par_bus"]:
        rows = [["Bus", "Km parcourus"]]
        for bus, km in data["km_par_bus"]:
            rows.append([bus, f"{float(km):,.1f} km"])
        t = Table(rows, colWidths=[9*cm, 6*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), BLEU_C),
            ("TEXTCOLOR",  (0,0), (-1,0), white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN",      (1,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, GRIS]),
            ("GRID",       (0,0), (-1,-1), 0.5, HexColor("#cccccc")),
            ("FONTSIZE",   (0,0), (-1,-1), 10),
            ("TOPPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(Paragraph("Kilométrage par bus :", style_normal))
        story.append(t)

    # Annulations
    if data["detail_annulees"]:
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("Tournées annulées :", style_alerte))
        for ref, motif in data["detail_annulees"]:
            story.append(Paragraph(f"  • {ref} — Motif : {motif}", style_alerte))

    story.append(Spacer(1, 0.5*cm))

    # ── Parc bus ──────────────────────────────────────────────────────────────
    story.append(Paragraph("État du Parc Bus", style_section))
    parc_data = [
        ["État", "Nombre"],
        ["✓ En service",    str(data["bus_en_service"])],
        ["✗ Hors service",  str(data["bus_hors_service"])],
        ["⚠ En panne",      str(data["bus_en_panne"])],
    ]
    t_parc = Table(parc_data, colWidths=[9*cm, 6*cm])
    t_parc.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), BLEU),
        ("TEXTCOLOR",    (0,0), (-1,0), white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN",        (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, GRIS]),
        ("GRID",         (0,0), (-1,-1), 0.5, HexColor("#cccccc")),
        ("FONTSIZE",     (0,0), (-1,-1), 10),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
    ]))
    story.append(t_parc)

    # Polices en alerte
    if data["polices_alerte_30j"]:
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("⚠ Polices d'assurance expirant dans 30 jours :", style_alerte))
        for police, date_fin, bus in data["polices_alerte_30j"]:
            story.append(Paragraph(
                f"  • {police} — Bus : {bus} — Expire le : {date_fin}",
                style_alerte
            ))
    else:
        story.append(Paragraph("✓ Aucune police n'expire dans les 30 prochains jours.", style_ok))

    story.append(Spacer(1, 0.5*cm))

    # ── Pied de page ──────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=BLEU))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Rapport généré automatiquement par l'Agent IA Transport — {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        ParagraphStyle("pied", parent=styles["Normal"], fontSize=8,
                       textColor=HexColor("#888888"), alignment=TA_CENTER)
    ))

    doc.build(story)
    logger.info(f"PDF généré : {chemin}")


# ── Tâche planifiée ──────────────────────────────────────────────────────────

def generer_rapport_hebdomadaire():
    """Tâche principale exécutée chaque vendredi à 18h00."""
    logger.info("="*50)
    logger.info("DÉMARRAGE GÉNÉRATION RAPPORT HEBDOMADAIRE")
    logger.info("="*50)

    try:
        # Collecter les données
        data = collecter_donnees_semaine()

        # Nom du fichier
        semaine = date.today().strftime("%Y-S%W")
        nom_fichier = f"rapport_hebdomadaire_{semaine}.pdf"
        chemin_pdf  = RAPPORTS_DIR / nom_fichier

        # Générer le PDF
        generer_pdf(data, chemin_pdf)

        logger.info(f"✓ Rapport sauvegardé : {chemin_pdf}")
        logger.info(f"  Taille : {chemin_pdf.stat().st_size / 1024:.1f} Ko")
        return str(chemin_pdf)

    except Exception as e:
        logger.error(f"✗ Erreur génération rapport : {e}", exc_info=True)
        return None


def test_immediat():
    """Génère un rapport immédiatement pour tester."""
    logger.info("TEST — Génération immédiate du rapport")
    chemin = generer_rapport_hebdomadaire()
    if chemin:
        print(f"\n✓ Rapport PDF généré : {chemin}")
    else:
        print("\n✗ Échec de la génération")


# ── Scheduler ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scheduler rapports transport")
    parser.add_argument("--test", action="store_true",
                        help="Générer un rapport immédiatement pour tester")
    args = parser.parse_args()

    if args.test:
        test_immediat()
        sys.exit(0)

    logger.info("Scheduler démarré — rapport chaque vendredi à 18h00")
    logger.info(f"Rapports sauvegardés dans : {RAPPORTS_DIR}")

    # Planifier chaque vendredi à 18h00
    schedule.every().friday.at("18:00").do(generer_rapport_hebdomadaire)

    # Afficher la prochaine exécution
    prochaine = schedule.next_run()
    logger.info(f"Prochaine génération : {prochaine}")

    print(f"\n{'='*50}")
    print("Scheduler Rapports Transport — ACTIF")
    print(f"Fréquence : Chaque vendredi à 18h00")
    print(f"Rapports  : {RAPPORTS_DIR}")
    print(f"Prochain  : {prochaine}")
    print(f"{'='*50}")
    print("Ctrl+C pour arrêter\n")

    while True:
        schedule.run_pending()
        time.sleep(30)