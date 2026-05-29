"""
diagnostic_pdf_ar.py
====================
Place ce fichier dans :
  C:\\Users\\azizn\\Desktop\\ERP Transport\\ERP\\odoo19\\odoo\\custom_addons\\transport_ai_agent\\

Puis lance :
  python diagnostic_pdf_ar.py
"""

import os, sys, importlib, inspect
from pathlib import Path

SEP = "=" * 60
def titre(t): print(f"\n{SEP}\n  {t}\n{SEP}")

# ── 0. Environnement ─────────────────────────────────────────────────────────
titre("0. Environnement")
print(f"Python     : {sys.version}")
print(f"Répertoire : {os.getcwd()}")

# ── 1. Modules ───────────────────────────────────────────────────────────────
titre("1. Modules Python")
for pkg in ["reportlab", "arabic_reshaper", "bidi"]:
    try:
        m = importlib.import_module(pkg)
        print(f"  ✅ {pkg:<20} v{getattr(m,'__version__','?')}")
    except ImportError as e:
        print(f"  ❌ {pkg:<20} MANQUANT — {e}")
        sys.exit(1)

# ── 2. Polices arabes ────────────────────────────────────────────────────────
titre("2. Polices arabes disponibles sur ce Windows")
FONTS = [
    (r"C:\Windows\Fonts\arial.ttf",    r"C:\Windows\Fonts\arialbd.ttf",    "Arial"),
    (r"C:\Windows\Fonts\tahoma.ttf",   r"C:\Windows\Fonts\tahomabd.ttf",   "Tahoma"),
    (r"C:\Windows\Fonts\calibri.ttf",  r"C:\Windows\Fonts\calibrib.ttf",   "Calibri"),
    (r"C:\Windows\Fonts\times.ttf",    r"C:\Windows\Fonts\timesbd.ttf",    "Times New Roman"),
    (r"C:\Windows\Fonts\segoeui.ttf",  r"C:\Windows\Fonts\segoeuib.ttf",   "Segoe UI"),
    (r"C:\Windows\Fonts\trebuc.ttf",   r"C:\Windows\Fonts\trebucbd.ttf",   "Trebuchet"),
]
FONT_NORM = None
FONT_BOLD = None
FONT_NOM  = None

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

for norm, bold, nom in FONTS:
    existe = os.path.exists(norm)
    print(f"  {'✅' if existe else '❌'} {nom:<20} → {norm}")
    if existe and FONT_NORM is None:
        try:
            pdfmetrics.registerFont(TTFont("DiagN", norm))
            pdfmetrics.registerFont(TTFont("DiagB", bold if os.path.exists(bold) else norm))
            FONT_NORM = "DiagN"
            FONT_BOLD = "DiagB"
            FONT_NOM  = nom
            print(f"     → ✅ Enregistrée comme police de test")
        except Exception as e:
            print(f"     → ❌ Erreur : {e}")

# Scanner aussi tout C:\Windows\Fonts\ pour trouver d'autres polices
print("\n  Scan complet C:\\Windows\\Fonts\\ :")
fonts_dir = Path(r"C:\Windows\Fonts")
all_ttf = sorted(fonts_dir.glob("*.ttf")) if fonts_dir.exists() else []
print(f"  {len(all_ttf)} fichiers .ttf trouvés")
# Chercher des polices avec "arab" dans le nom
arab_fonts = [f for f in all_ttf if "arab" in f.name.lower()]
if arab_fonts:
    print(f"  Polices 'arab*' :")
    for f in arab_fonts:
        print(f"    ✅ {f.name}")
        if FONT_NORM is None:
            try:
                pdfmetrics.registerFont(TTFont("DiagN", str(f)))
                FONT_NORM = "DiagN"
                FONT_BOLD = "DiagN"
                FONT_NOM  = f.name
                print(f"    → ✅ Enregistrée")
            except Exception as e:
                print(f"    → ❌ {e}")
else:
    print("  Aucune police 'arab*' dans C:\\Windows\\Fonts\\")

if FONT_NORM is None:
    print("\n  ❌ AUCUNE police arabe trouvée !")
    print("  Solution : télécharge NotoNaskhArabic-Regular.ttf depuis")
    print("  https://fonts.google.com/noto/specimen/Noto+Naskh+Arabic")
    print("  et copie le .ttf dans C:\\Windows\\Fonts\\")
else:
    print(f"\n  → Police retenue pour test : {FONT_NOM}")

# ── 3. Test arabic_reshaper ──────────────────────────────────────────────────
titre("3. Test arabic_reshaper + bidi")
import arabic_reshaper
from bidi.algorithm import get_display

t = "تقرير حول الحافلات التي في خدمة"
r = arabic_reshaper.reshape(t)
b = get_display(r)
print(f"  Original : {t}")
print(f"  Reshapé  : {r}")
print(f"  Bidi     : {b}")
print(f"  ✅ OK" if r != t else "  ❌ Reshaper n'a rien changé !")

# ── 4. Vérification rapport_pdf.py ──────────────────────────────────────────
titre("4. Vérification rapport_pdf.py (corrections appliquées ?)")
try:
    if "rapport_pdf" in sys.modules:
        del sys.modules["rapport_pdf"]
    import rapport_pdf
    src = inspect.getfile(rapport_pdf)
    contenu = open(src, encoding="utf-8").read()
    mtime   = Path(src).stat().st_mtime
    import datetime
    print(f"  Fichier : {src}")
    print(f"  Modifié : {datetime.datetime.fromtimestamp(mtime)}")
    print()
    checks = [
        ("Windows arial.ttf présent",       r"C:\Windows\Fonts\arial.ttf"   in contenu),
        ("_ar2r() éliminés",                "_ar2r("                    not in contenu),
        ("_build_bloc RTL titre",           "titre_affiche = _ar2(titre)"   in contenu),
        ("_bloc libre RTL titre",           "titre_aff = _ar2(titre)"       in contenu),
        ("Cellules tableau _ar2",           "_ar2(v) if _RTL"               in contenu),
        ("Prompt LLM arabe",               "أجب باللغة العربية فقط"        in contenu),
        ("Fallbacks multilingues (pos_tab)","pos_tab"                        in contenu),
        ("_LL défini dans rapport_libre",   "_LL = _labels_libre"            in contenu),
        ("Styles RTL _ALIGN_LIBRE",         "_ALIGN_LIBRE"                   in contenu),
        ("except verbose [POLICE ARABE]",   "[POLICE ARABE] échec"           in contenu),
    ]
    all_ok = True
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌ MANQUE'} {label}")
        if not ok: all_ok = False
    if not all_ok:
        print("\n  ⚠️  Certaines corrections sont ABSENTES du fichier !")
        print("  → Remplace rapport_pdf.py par la dernière version corrigée.")
except Exception as e:
    print(f"  ❌ Impossible de charger rapport_pdf.py : {e}")

# ── 5. Génération PDF direct (sans passer par le module) ─────────────────────
titre("5. Génération PDF arabe direct (test isolé)")

if FONT_NORM is None:
    print("  ⏭  Sauté — aucune police arabe disponible (voir étape 2)")
else:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER

    def ar2(text):
        if not text: return str(text)
        if not any('\u0600' <= c <= '\u06ff' for c in str(text)): return str(text)
        return get_display(arabic_reshaper.reshape(str(text)))

    out = Path(__file__).parent / "diag_direct.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    s = getSampleStyleSheet()
    BLEU = HexColor("#1a3a6b")

    def sty(sz=12, bold=False, align=TA_RIGHT, color=HexColor("#212121")):
        return ParagraphStyle("_", parent=s["Normal"],
            fontName=FONT_BOLD if bold else FONT_NORM,
            fontSize=sz, alignment=align, textColor=color, spaceAfter=6)

    story = [
        Paragraph(ar2("تقرير تشخيصي — اختبار الخط العربي"), sty(18, bold=True, align=TA_CENTER, color=BLEU)),
        Spacer(1, 0.4*cm),
        Paragraph(ar2("تقرير حول الحافلات التي في خدمة"), sty(14)),
        Paragraph(ar2("الملخص التحليلي"), sty(12, bold=True, color=BLEU)),
        Paragraph(ar2("• جميع الحافلات في حالة تشغيل جيدة."), sty(11)),
        Paragraph(ar2("• لا توجد عطل مسجلة."), sty(11)),
        Paragraph(ar2("الخلاصة : الوضع إيجابي."), sty(10)),
        Spacer(1, 0.3*cm),
        Paragraph(ar2("تم الإنشاء بواسطة وكيل الذكاء الاصطناعي للنقل"), sty(9, align=TA_CENTER)),
    ]
    try:
        doc.build(story)
        print(f"  ✅ PDF généré : {out}  ({out.stat().st_size} octets)")
        print(f"  Ouvre ce PDF et vérifie que l'arabe s'affiche correctement.")
    except Exception as e:
        import traceback
        print(f"  ❌ Erreur génération : {e}")
        traceback.print_exc()

# ── 6. Test generer_pdf_rapport_libre ────────────────────────────────────────
titre("6. Test generer_pdf_rapport_libre (fonction réelle)")
try:
    if "rapport_pdf" in sys.modules:
        del sys.modules["rapport_pdf"]
    from rapport_pdf import generer_pdf_rapport_libre
    out2 = Path(__file__).parent / "diag_rapport_libre.pdf"
    print("  Appel avec langue='ar' ...")
    generer_pdf_rapport_libre(
        label    = "تقرير حول الحافلات التي في خدمة",
        question = "تقرير حول الحافلات التي في خدمة",
        data     = {},
        colonnes = ["Bus", "License Plate", "Etat"],
        rows     = [
            ("Volkswagen/Bus/158 tu 2026", "158 tu 2026", "En service"),
            ("Tesla Motors/tesla/255 TU 1550", "255 TU 1550", "En service"),
        ],
        chemin   = out2,
        llm      = None,
        langue   = "ar",
    )
    print(f"  ✅ PDF généré : {out2}  ({out2.stat().st_size} octets)")
    print(f"  Ouvre ce PDF et compare avec diag_direct.pdf")
except Exception as e:
    import traceback
    print(f"  ❌ Erreur : {e}")
    traceback.print_exc()

titre("FIN DU DIAGNOSTIC")
print("  Fichiers créés dans le même dossier :")
print("    diag_direct.pdf        → test isolé (police directe)")
print("    diag_rapport_libre.pdf → test via generer_pdf_rapport_libre")
print("\n  Colle TOUT ce log + dis si les PDFs affichent l'arabe correctement.")