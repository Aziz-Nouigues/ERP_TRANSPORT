# test_rapport_pdf.py v2
# Teste que le chat retourne pdf_url et ouvre le PDF dans le navigateur
import requests, webbrowser, time

BASE = "http://localhost:8000"

questions = [
    "Rapport consommation carburant",
    "Bilan assurance et sinistres",
    "État du parc bus",
    "Rapport journalier d'exploitation",
    "Bilan courrier BOC",
]

print("=" * 60)
print("TEST RAPPORT PDF v2")
print("=" * 60)

for question in questions:
    print(f"\nQuestion : {question}")
    r = requests.post(f"{BASE}/chat",
        json={"question": question, "session_id": "test_pdf", "is_admin": True},
        timeout=120)
    data = r.json()

    reponse      = data.get("reponse", "")
    pdf_url      = data.get("pdf_url")
    type_rapport = data.get("type_rapport")

    print(f"Réponse   : {reponse[:100]}")
    print(f"PDF URL   : {pdf_url}")

    if pdf_url:
        # Vérifier que le PDF se génère correctement
        r_pdf = requests.get(pdf_url, timeout=60)
        if r_pdf.status_code == 200:
            taille = len(r_pdf.content) // 1024
            print(f"✓ PDF OK : {taille} Ko")

            # Sauvegarder et ouvrir dans le navigateur
            nom = f"{type_rapport}.pdf"
            with open(nom, "wb") as f:
                f.write(r_pdf.content)
            webbrowser.open(f"file:///{nom}")
            time.sleep(1)
        else:
            print(f"✗ Erreur PDF {r_pdf.status_code}: {r_pdf.text[:200]}")
    else:
        print("✗ Pas de pdf_url")

print("\n" + "=" * 60)
print("Les PDFs s'ouvrent dans le navigateur.")
print("Clic droit → Enregistrer sous pour télécharger.")
print("=" * 60)