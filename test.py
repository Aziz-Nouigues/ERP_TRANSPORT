import sys

sys.path.insert(0, r"C:\Users\azizn\Desktop\ERP Transport\ERP\odoo19\odoo")
sys.path.insert(0, r"C:\Users\azizn\Desktop\ERP Transport\ERP\odoo19")

import odoo
from odoo import api

odoo.tools.config.parse_config([
    '--config', r'C:\Users\azizn\Desktop\ERP Transport\ERP\odoo19\odoo.conf',
    '--database', 'erp_db2',
])

registry = odoo.registry('erp_db2')

with registry.cursor() as cr:
    env = api.Environment(cr, 1, {})  # 1 = admin

    # Chercher les bons validés
    bons = env['transport.fuel.voucher'].search([
        ('date', '>=', '2026-03-09'),
        ('date', '<=', '2026-03-09'),
        ('state', '=', 'done'),
    ])
    print(f"\n✅ Bons trouvés: {len(bons)}")
    for bon in bons:
        print(f"  → {bon.name} | lignes: {len(bon.line_ids)}")
        for ligne in bon.line_ids:
            print(f"      Bus: {ligne.vehicle_id.name} | Qté: {ligne.quantity} | km: {ligne.distance_estimated}")

    # Créer wizard et tester
    wizard = env['transport.wizard.rapport'].create({
        'date_debut': '2026-03-09',
        'date_fin': '2026-03-09',
        'type_rapport': 'par_vehicule',
    })
    result = wizard._get_donnees_par_vehicule()
    print(f"\n📊 Résultat par_vehicule: {len(result)} véhicules")
    for r in result:
        print(f"  → {r}")

    result2 = wizard._get_donnees_par_station()
    print(f"\n📊 Résultat par_station: {len(result2)} stations")
    for r in result2:
        print(f"  → {r}")