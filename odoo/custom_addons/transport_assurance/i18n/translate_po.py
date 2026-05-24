import polib
from deep_translator import GoogleTranslator
import time

INPUT_FILE = "ar_001.po"
OUTPUT_FILE = "en_US.po"

po = polib.pofile(INPUT_FILE)

# --- Corriger le header pour en_US ---
po.metadata["Language"] = "en_US"
po.metadata["Plural-Forms"] = "nplurals=2; plural=(n != 1);"
po.metadata["Language-Team"] = "English"

# Corriger le commentaire en haut du fichier
po.metadata_is_fuzzy = False

translator = GoogleTranslator(source='ar', target='en')

count = 0
errors = 0

for entry in po:
    # Ignorer les entrées vides
    if not entry.msgid or not entry.msgid.strip():
        continue

    # Ne pas retraduire si déjà traduit (utile si on relance le script)
    if entry.msgstr and entry.msgstr.strip():
        count += 1
        continue

    try:
        # GoogleTranslator a une limite de ~5000 caractères
        msgid = entry.msgid.strip()
        if len(msgid) > 4500:
            msgid = msgid[:4500]

        translated = translator.translate(msgid)

        if translated:
            entry.msgstr = translated
            count += 1
            print(f"[OK {count}] {repr(msgid[:60])} => {repr(translated[:60])}")
        else:
            print(f"[SKIP] Réponse vide pour : {repr(msgid[:60])}")

    except Exception as e:
        errors += 1
        print(f"[ERROR] {e} — msgid: {repr(entry.msgid[:60])}")
        # Petite pause pour éviter le rate-limit
        time.sleep(1)

po.save(OUTPUT_FILE)

print(f"\n✅ Sauvegardé dans : {OUTPUT_FILE}")
print(f"   Traductions réussies : {count}")
print(f"   Erreurs              : {errors}")