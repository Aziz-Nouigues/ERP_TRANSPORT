#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de fichiers .po pour Odoo 19
========================================
Génère des fichiers .po 100% compatibles avec le parser d'Odoo 19.

Usage:
    python odoo19_po_generator.py --module /chemin/vers/mon_module --lang fr_FR
    python odoo19_po_generator.py --module /chemin/vers/mon_module --lang fr_FR --lang ar_001
    python odoo19_po_generator.py --scan /chemin/vers/addons --lang fr_FR
    python odoo19_po_generator.py --module ./mon_module --lang fr_FR --keep-existing

Le fichier .po généré contient UNIQUEMENT les entrées au format
  #: code:addons/MODULE/fichier.py:0
que le webclient Odoo 19 parse sans erreur.

Pour traduire les champs/vues (model: et model_terms:) :
  Paramètres → Traductions → Importer/Exporter dans Odoo
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Patterns d'extraction
# ─────────────────────────────────────────────────────────────────────────────

# Python: _('texte') / _("texte") / _('texte %s', ...) / _("texte", ...)
PY_SINGLE  = re.compile(r"""_\(\s*'((?:[^'\\]|\\.)*)'\s*[,%\)]""")
PY_DOUBLE  = re.compile(r'''_\(\s*"((?:[^"\\]|\\.)*)"\s*[,%\)]''')

# XML vues: attributs string, label, help, title, confirm, placeholder
XML_ATTRS  = re.compile(
    r'\b(?:string|label|help|title|confirm|placeholder|summary)=["\']([^"\']{2,})["\']'
)
# Texte direct dans balises Odoo
XML_NODES  = re.compile(
    r'<(?:button|field|label|h[1-6]|span|div|p)\b[^>]*>\s*'
    r'([A-ZÀ-ŸA-Za-zà-ÿ][^<\n]{2,50}?)\s*</'
)

# JS/OWL: _t('...') / _t("...") / env._t('...')
JS_T       = re.compile(r"""(?:^|[^a-zA-Z_])_t\(\s*['"](.+?)['"]\s*\)""")
# Template OWL: t-esc="_t('...')"
JS_TMPL    = re.compile(r"""t-esc=['""]_t\('(.+?)'\)['""]""")


# ─────────────────────────────────────────────────────────────────────────────
# Filtres
# ─────────────────────────────────────────────────────────────────────────────

IGNORE_EXACT = {
    'True', 'False', 'None', 'true', 'false', 'null', 'undefined',
    'id', 'name', 'model', 'type', 'state', 'active', 'sequence',
    'create_uid', 'write_uid', 'create_date', 'write_date',
    'res.users', 'res.partner', 'ir.model', 'ir.ui.view',
}

IGNORE_RE = re.compile(
    r'^('
    r'[a-z_\.]+|'          # identifiants snake_case
    r'[\d\s\-_/:.,%]+|'    # chiffres et ponctuation
    r'[A-Z_]{3,}|'         # CONSTANTES
    r'https?://\S+|'       # URLs
    r'%[sd]\s*$'           # format strings seuls
    r')$'
)


def keep(s: str) -> bool:
    s = s.strip()
    if len(s) < 2:
        return False
    if s in IGNORE_EXACT:
        return False
    if IGNORE_RE.match(s):
        return False
    # Doit contenir au moins une lettre
    if not re.search(r'[A-Za-zÀ-ÿ]', s):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Extraction par type de fichier
# ─────────────────────────────────────────────────────────────────────────────

def loc(module_name: str, module_path: Path, filepath: Path) -> str:
    """Construit la référence #: code:addons/... correcte."""
    try:
        rel = filepath.relative_to(module_path)
        return f'code:addons/{module_name}/{str(rel).replace(os.sep, "/")}:0'
    except ValueError:
        return f'code:addons/{module_name}/{filepath.name}:0'


def from_python(fp: Path, module_name: str, module_path: Path) -> dict:
    try:
        src = fp.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return {}
    found = set()
    for p in (PY_SINGLE, PY_DOUBLE):
        for m in p.finditer(src):
            s = m.group(1).replace('\\n', '\n').replace("\\'", "'").strip()
            s = ' '.join(s.split())   # normaliser les espaces
            if keep(s):
                found.add(s)
    ref = loc(module_name, module_path, fp)
    return {s: {ref} for s in found}


def from_xml(fp: Path, module_name: str, module_path: Path) -> dict:
    try:
        src = fp.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return {}
    found = set()
    for p in (XML_ATTRS, XML_NODES):
        for m in p.finditer(src):
            s = m.group(1).strip()
            if keep(s):
                found.add(s)
    ref = loc(module_name, module_path, fp)
    return {s: {ref} for s in found}


def from_js(fp: Path, module_name: str, module_path: Path) -> dict:
    try:
        src = fp.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return {}
    found = set()
    for p in (JS_T, JS_TMPL):
        for m in p.finditer(src):
            s = m.group(1).strip()
            if keep(s):
                found.add(s)
    ref = loc(module_name, module_path, fp)
    return {s: {ref} for s in found}


# ─────────────────────────────────────────────────────────────────────────────
# Collecte complète du module
# ─────────────────────────────────────────────────────────────────────────────

SKIP_DIRS  = {'__pycache__', '.git', 'node_modules', 'i18n', 'lib', 'tests'}
SKIP_FILES = {'__manifest__.py', '__init__.py', 'hooks.py'}


def collect(module_path: Path, module_name: str) -> dict:
    """Parcourt le module et retourne {msgid: set(locations)}."""
    all_entries: dict[str, set] = {}

    for root, dirs, files in os.walk(module_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            fp = Path(root) / fname
            if fname.endswith('.py') and fname not in SKIP_FILES:
                new = from_python(fp, module_name, module_path)
            elif fname.endswith('.xml'):
                new = from_xml(fp, module_name, module_path)
            elif fname.endswith(('.js', '.owl')):
                new = from_js(fp, module_name, module_path)
            else:
                continue
            for msgid, locs in new.items():
                all_entries.setdefault(msgid, set()).update(locs)

    return all_entries


# ─────────────────────────────────────────────────────────────────────────────
# Chargement d'un .po existant
# ─────────────────────────────────────────────────────────────────────────────

def load_po(po_path: Path) -> dict:
    """Retourne {msgid: msgstr} depuis un .po existant."""
    result = {}
    if not po_path.exists():
        return result
    try:
        content = po_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return result

    for block in re.split(r'\n{2,}', content):
        id_m  = re.search(r'^msgid\s+"(.*)"', block, re.MULTILINE)
        str_m = re.search(r'^msgstr\s+"(.*)"', block, re.MULTILINE)
        if id_m and str_m and id_m.group(1) and str_m.group(1):
            result[id_m.group(1)] = str_m.group(1)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Génération du .po
# ─────────────────────────────────────────────────────────────────────────────

HEADER = (
    '# Translation of {module} in {lang}\n'
    '# Generated by odoo19_po_generator.py — {date}\n'
    '# Only "code:" entries are included (compatible Odoo 19 webclient).\n'
    '# For model fields/views, use: Settings > Translations > Export in Odoo.\n'
    '#\n'
    'msgid ""\n'
    'msgstr ""\n'
    '"Project-Id-Version: Odoo {module}\\n"\n'
    '"Report-Msgid-Bugs-To: \\n"\n'
    '"POT-Creation-Date: {date}\\n"\n'
    '"PO-Revision-Date: {date}\\n"\n'
    '"Last-Translator: \\n"\n'
    '"Language-Team: \\n"\n'
    '"Language: {lang}\\n"\n'
    '"MIME-Version: 1.0\\n"\n'
    '"Content-Type: text/plain; charset=UTF-8\\n"\n'
    '"Content-Transfer-Encoding: 8bit\\n"\n'
    '\n'
)


def esc(s: str) -> str:
    return (s
            .replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace('\n', '\\n"\n"')
            .replace('\r', '\\r')
            .replace('\t', '\\t'))


def build_po(module_path: Path, module_name: str, lang: str,
             existing: dict | None = None) -> str:
    if existing is None:
        existing = {}

    entries = collect(module_path, module_name)
    now     = datetime.utcnow().strftime('%Y-%m-%d %H:%M+0000')
    out     = [HEADER.format(module=module_name, lang=lang, date=now)]

    if not entries:
        out.append(
            f'# INFORMATION: No _("...") strings found in {module_name}.\n'
            f'# To translate model fields and views, use:\n'
            f'#   Odoo > Settings > Translations > Export\n'
        )
        return ''.join(out)

    for msgid in sorted(entries, key=str.lower):
        locs   = sorted(entries[msgid])
        msgstr = existing.get(msgid, '')
        for loc_ref in locs[:3]:
            out.append(f'#: {loc_ref}\n')
        out.append(f'msgid "{esc(msgid)}"\n')
        out.append(f'msgstr "{esc(msgstr)}"\n')
        out.append('\n')

    return ''.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Générateur .po Odoo 19 — format webclient compatible',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    ap.add_argument('--module', '-m', type=Path,
                    help='Chemin du module Odoo')
    ap.add_argument('--scan',   '-s', type=Path,
                    help='Scanner tous les modules d\'un dossier addons')
    ap.add_argument('--lang',   '-l', action='append', dest='langs', default=[],
                    metavar='LANG',
                    help='Langue (ex: fr_FR, ar_001). Répétable.')
    ap.add_argument('--keep-existing', '-k', action='store_true',
                    help='Conserver les traductions déjà présentes dans le .po')
    ap.add_argument('--output', '-o', type=Path,
                    help='Dossier de sortie (défaut: MODULE/i18n/)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Afficher sans écrire les fichiers')
    args = ap.parse_args()

    if not args.langs:
        args.langs = ['fr_FR']

    # Collecter les modules
    modules: list[Path] = []
    if args.module:
        if not args.module.exists():
            print(f'ERREUR: {args.module} introuvable')
            sys.exit(1)
        modules.append(args.module.resolve())
    elif args.scan:
        if not args.scan.exists():
            print(f'ERREUR: {args.scan} introuvable')
            sys.exit(1)
        for d in sorted(args.scan.iterdir()):
            if d.is_dir() and (d / '__manifest__.py').exists():
                modules.append(d.resolve())
    else:
        cwd = Path('.').resolve()
        if (cwd / '__manifest__.py').exists():
            modules.append(cwd)
        else:
            ap.print_help()
            sys.exit(0)

    if not modules:
        print('Aucun module trouvé.')
        sys.exit(1)

    written = 0
    for module_path in modules:
        module_name = module_path.name
        entries     = collect(module_path, module_name)
        n           = len(entries)
        print(f'\n📦 {module_name}  →  {n} chaîne(s) trouvée(s)')

        if args.output:
            i18n_dir = (args.output / module_name).resolve()
        else:
            i18n_dir = module_path / 'i18n'
        i18n_dir.mkdir(parents=True, exist_ok=True)

        for lang in args.langs:
            po_path = i18n_dir / f'{lang}.po'
            existing = load_po(po_path) if args.keep_existing else {}
            if args.keep_existing and existing:
                print(f'   ↩  {lang}: {len(existing)} traduction(s) rechargée(s)')

            content = build_po(module_path, module_name, lang, existing)

            if args.dry_run:
                print(f'\n── {po_path} (dry-run) ──')
                print(content[:800])
                print('...' if len(content) > 800 else '')
            else:
                po_path.write_text(content, encoding='utf-8')
                print(f'   ✅  {po_path}')
                written += 1

    if not args.dry_run:
        print(f'\n✨ {written} fichier(s) .po généré(s).')
        print()
        print('Prochaines étapes:')
        print('  1. Ouvrir les .po avec Poedit (https://poedit.net) ou un éditeur')
        print('  2. Remplir chaque msgstr "" avec la traduction')
        print('  3. Sauvegarder → redémarrer Odoo ou upgrader le module')
        print()
        print('Champs/vues (model fields) — non inclus ici:')
        print('  Odoo → Paramètres → Traductions → Exporter le module')


if __name__ == '__main__':
    main()