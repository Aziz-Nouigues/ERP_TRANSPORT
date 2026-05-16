"""Test temps de réponse — 3 questions."""
import requests, time

API_URL = "http://localhost:8000/chat"

TESTS = [
    {"q": "Combien de bus sont dans le parc ?"},
    {"q": "Donne moi toutes les factures STEG"},
    {"q": "Donne moi des détails sur le TOURN/2026/00020"},
]

print("Warmup...", end=" ", flush=True)
try:
    requests.post(API_URL, json={"question": "test", "session_id": "w",
        "user_name": "T", "is_admin": True, "allowed_tables": ["ALL"]}, timeout=60)
    print("OK\n")
except: print("skip\n")

total = 0
for i, t in enumerate(TESTS, 1):
    print(f"[{i}] {t['q']}")
    debut = time.time()
    r = requests.post(API_URL, json={
        "question": t["q"], "session_id": f"perf_{i}",
        "user_name": "Test", "is_admin": True, "allowed_tables": ["ALL"]
    }, timeout=120)
    duree = round(time.time() - debut, 1)
    total += duree
    rep = r.json().get("reponse", "")[:120].replace("\n", " ")
    print(f"    ⏱️  {duree}s")
    print(f"    → {rep}\n")

print(f"Durée moyenne : {round(total/len(TESTS), 1)}s")