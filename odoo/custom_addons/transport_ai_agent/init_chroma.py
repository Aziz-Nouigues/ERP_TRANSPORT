import chromadb
import os
from dotenv import load_dotenv

load_dotenv()
os.environ["ANONYMIZED_TELEMETRY"] = "False"

client = chromadb.PersistentClient(path=os.getenv("CHROMA_PATH"))

try:
    client.delete_collection("transport_procedures")
    print("Ancienne collection supprimée.")
except:
    pass

collection = client.create_collection(name="transport_procedures")

documents = [

    # ── TOURNÉES ─────────────────────────────────────────────────
    "Une tournée est un trajet de bus planifié sur une ligne à une date donnée, avec un chauffeur et un véhicule affectés.",
    "Le workflow d'une tournée est : brouillon → planifié → en_cours → réalisé. Elle peut aussi être annulée.",
    "Une tournée est bloquée automatiquement si le bus affecté n'a pas d'assurance obligatoire valide à la date du trajet.",
    "L'écart kilométrique (ecart_km) est calculé automatiquement : ecart_km = km_realise - km_prevu. Un écart positif signifie plus de km que prévu.",
    "Le champ compteur_defaillant indique que le compteur kilométrique du bus est en panne. Dans ce cas l'écart kilométrique n'est pas fiable.",
    "Une feuille de route regroupe toutes les tournées d'un bus sur une journée complète.",
    "La direction d'une tournée peut être : aller, retour, ou aller-retour.",
    "Le type de ligne peut être urbain (dans la ville) ou interurbain (entre plusieurs villes).",
    "Pour planifier une tournée, il faut d'abord la créer en brouillon, affecter la ligne, le bus et le chauffeur, puis cliquer sur Planifier.",
    "Pour annuler une tournée planifiée, il faut renseigner un motif d'annulation avant de confirmer l'annulation.",

    # ── ASSURANCE ────────────────────────────────────────────────
    "Une police d'assurance obligatoire (is_obligatoire=True) doit absolument être renouvelée avant sa date d'expiration.",
    "Si une police obligatoire expire, toutes les tournées du bus concerné sont automatiquement bloquées.",
    "Les types de polices d'assurance sont : responsabilité civile, tous risques, assurance chauffeur, assurance voyageurs.",
    "Un sinistre doit être déclaré dans les 48 heures suivant l'incident avec le numéro de police concerné.",
    "Le renouvellement d'une assurance se fait depuis le menu Assurance → Polices → bouton Renouveler.",
    "Une police d'assurance chauffeur couvre le chauffeur indépendamment du bus qu'il conduit.",
    "La compagnie d'assurance et le type de police sont obligatoires pour créer une nouvelle police.",

    # ── CARBURANT ────────────────────────────────────────────────
    "Un BGI (Bon de ravitaillement Interne) est un bon de carburant prélevé depuis la cuve interne de l'entreprise.",
    "Un BGE (Bon de ravitaillement Externe) est un bon de carburant acheté dans une station externe tierce.",
    "Pour créer un BGI, il faut sélectionner la cuve, le bus, et renseigner le compteur pompe de début et de fin.",
    "Pour créer un BGE AGILIS, il faut renseigner la carte AGILIS utilisée. Le système crée automatiquement une utilisation AGILIS.",
    "Le stock restant d'une cuve (current_stock) est mis à jour automatiquement après chaque validation de BGI.",
    "Une carte AGILIS est une carte de carburant prépayée utilisée dans les stations partenaires.",
    "Le jaugeage est l'opération de mesure physique du stock de carburant dans une cuve pour vérifier le stock théorique.",
    "La consommation moyenne d'un bus se calcule : total_quantity / km_realise * 100 (litres aux 100 km).",
    "STEG est le fournisseur d'électricité tunisien. SONEDE est le fournisseur d'eau. Ils peuvent être gérés dans transport_energy.",

    # ── PARC BUS ─────────────────────────────────────────────────
    "Pour changer l'état d'un bus, utiliser le wizard de changement d'état depuis la fiche du véhicule.",
    "Les états possibles d'un bus sont : en service, en panne, en maintenance, hors service, en réforme.",
    "L'historique des états d'un bus est conservé dans fleet_etat_bus_historique avec la date et le km compteur.",
    "Un bus hors service ne peut pas être affecté à une nouvelle tournée.",
    "La vue Kanban du parc bus permet de visualiser tous les bus groupés par état en un seul coup d'œil.",

    # ── PATRIMOINE ───────────────────────────────────────────────
    "Une immobilisation est un bien durable de l'entreprise : bus, équipement, bâtiment, matériel informatique.",
    "L'amortissement est calculé automatiquement selon la durée de vie et le coût d'acquisition de l'immobilisation.",
    "Le champ fin_amortissement indique la date à laquelle l'immobilisation est entièrement amortie.",
    "Une immobilisation avec statut hors_service mais fin_amortissement non atteint doit être réévaluée.",
    "La cession d'une immobilisation se fait depuis la fiche en renseignant la date de cession et le motif.",
    "Le numéro d'inventaire est unique pour chaque immobilisation et sert à l'identifier lors des inventaires physiques.",

    # ── BOC ──────────────────────────────────────────────────────
    "Le BOC (Bureau d'Ordre Central) gère tout le courrier entrant (arrivée) et sortant (départ) de l'entreprise.",
    "Un courrier arrivée doit être enregistré avec : date d'arrivée, expéditeur, objet, et service destinataire.",
    "Un bordereau de transmission regroupe plusieurs courriers envoyés ensemble vers un même service.",
    "Le numéro d'enregistrement BOC est généré automatiquement dans le format BOC/ARRIVEE/AAAA/XXXXX.",
    "Les courriers urgents doivent être traités dans les 24 heures suivant leur réception au BOC.",

    # ── RÈGLES MÉTIER GÉNÉRALES ──────────────────────────────────
    "Toutes les données sont saisies en langue française. L'interface supporte aussi l'arabe et l'anglais.",
    "Les rapports PDF peuvent être générés depuis chaque module via le bouton Imprimer.",
    "Les droits d'accès sont gérés par profil utilisateur : opérateur, dispatcher, responsable, directeur.",
    "Un dispatcher peut créer et planifier des tournées. Seul un responsable peut les valider ou annuler.",
    "Les alertes automatiques sont envoyées par email 30, 15 et 7 jours avant l'expiration d'une assurance.",
]

ids = [f"doc_{i:03d}" for i in range(len(documents))]

collection.add(
    documents=documents,
    ids=ids
)

print(f"ChromaDB enrichi — {collection.count()} documents indexés.")
print("Catégories indexées :")
print("  - Tournées        : 10 documents")
print("  - Assurance       :  7 documents")
print("  - Carburant       :  9 documents")
print("  - Parc bus        :  5 documents")
print("  - Patrimoine      :  6 documents")
print("  - BOC             :  5 documents")
print("  - Règles générales:  5 documents")