# -*- coding: utf-8 -*-
"""
Migration 19.0.4.1.0 — fleet_etat_bus
Ajoute les colonnes res_config_settings manquantes si elles n'existent pas.
Ces colonnes sont de type TransientModel donc gérées par Odoo,
mais si la table existe déjà sans elles, il faut les créer manuellement.
"""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    columns = [
        ("fleet_alerte_immobilisation_jours", "INTEGER", "7"),
        ("fleet_motif_retour_service_obligatoire", "BOOLEAN", "TRUE"),
        ("fleet_impression_auto_changement", "BOOLEAN", "FALSE"),
    ]

    for col_name, col_type, default in columns:
        cr.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'res_config_settings'
              AND column_name = %s
        """, (col_name,))
        if not cr.fetchone():
            cr.execute(f"""
                ALTER TABLE res_config_settings
                ADD COLUMN {col_name} {col_type} DEFAULT {default}
            """)
            _logger.info("Migration fleet_etat_bus: colonne '%s' ajoutée à res_config_settings", col_name)
        else:
            _logger.info("Migration fleet_etat_bus: colonne '%s' déjà présente, ignorée", col_name)
