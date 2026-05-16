"""
Test de performance — agent IA transport.
Mesure le temps de réponse réel par question et affiche un résumé.
"""
import requests
import time

API_URL = "http://localhost:8000/chat"

TESTS = [
    {"q": "Combien de bus sont dans le parc ?",             "label": "COUNT simple (cache)"},
    {"q": "Combien de tournées ont été réalisées ce mois ?","label": "COUNT filtré (cache)"},
    {"q": "Donne moi toutes les factures STEG",             "label": "Liste filtrée (1 LLM)"},
    {"q": "Donne moi des détails sur le TOURN/2026/00020",  "label": "Détail unique (1 LLM)"},
    {"q": "Qu'est-ce qu'un BGI ?",                        "label": "RAG BGI (statique)"},
    {"q": "Qu'est-ce qu'une tournée ?",                   "label": "RAG tournée (statique)"},
    {"q": "Liste tous les bus du parc",                     "label": "Liste bus (cache)"},
]

SEUILS_OK = {   # temps max acceptable en secondes
    "COUNT simple (cache)":    5,
    "COUNT filtré (cache)":    5,
    "Liste bus (cache)":       5,
    "RAG BGI (statique)":     10,
    "RAG tournée (statique)": 10,
    "Liste filtrée (1 LLM)":  30,
    "Détail unique (1 LLM)":  30,
}

print("=" * 60)
print("  TEST DE PERFORMANCE — AGENT IA TRANSPORT")
print("=" * 60)

# Warmup
print("\n⏳ Warmup Ollama...", end=" ", flush=True)
try:
    r = requests.post(API_URL, json={
        "question": "test", "session_id": "warmup",
        "user_name": "Test", "is_admin": True, "allowed_tables": ["ALL"]
    }, timeout=90)
    print(f"OK ({r.status_code})\n")
except Exception as e:
    print(f"Skip ({e})\n")

resultats = []
for i, t in enumerate(TESTS, 1):
    print(f"[{i}/{len(TESTS)}] {t['label']}")
    print(f"      Q: {t['q']}")
    debut = time.time()
    try:
        r = requests.post(API_URL, json={
            "question": t["q"],
            "session_id": f"perf_{i}",
            "user_name": "Test",
            "is_admin": True,
            "allowed_tables": ["ALL"]
        }, timeout=120)
        duree = round(time.time() - debut, 1)
        data = r.json()
        statut = data.get("statut", "?")
        rep = data.get("reponse", "")[:100].replace("\n", " ")
        print(f"      ⏱  {duree}s  [{statut}]")
        print(f"      → {rep}")
        resultats.append({"label": t["label"], "duree": duree, "ok": statut == "ok"})
    except Exception as e:
        duree = round(time.time() - debut, 1)
        print(f"      ❌ Erreur après {duree}s : {e}")
        resultats.append({"label": t["label"], "duree": duree, "ok": False})
    print()

# Résumé
print("=" * 60)
print("  RÉSUMÉ")
print("=" * 60)
total = sum(r["duree"] for r in resultats)
for r in resultats:
    seuil = SEUILS_OK.get(r["label"], 30)
    rapide = r["duree"] <= seuil
    emoji = "✅" if (r["ok"] and rapide) else ("⚠️" if r["ok"] else "❌")
    barre = "█" * int(r["duree"])
    note = "" if rapide else f"  ← lent (seuil {seuil}s)"
    print(f"  {emoji} {r['label']:<30} {r['duree']:>5.1f}s  {barre}{note}")
print("-" * 60)
print(f"  Durée totale   : {total:.1f}s")
print(f"  Durée moyenne  : {total/len(resultats):.1f}s")
ok_count = sum(1 for r in resultats if r["ok"])
print(f"  Taux de succès : {ok_count}/{len(resultats)}")
print("=" * 60)