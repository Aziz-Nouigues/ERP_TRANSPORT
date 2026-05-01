# -*- coding: utf-8 -*-
"""
hooks.py — exécuté une seule fois après l'installation du module.
Crée une entrée initiale dans fleet.vehicle.historique.etat
pour chaque véhicule existant qui n'en a pas encore.
"""
import logging
from odoo import fields

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Initialise l'historique des états pour les véhicules existants."""
    vehicles = env['fleet.vehicle'].search([])
    Historique = env['fleet.vehicle.historique.etat']

    count = 0
    for vehicle in vehicles:
        # Vérifier s'il existe déjà un enregistrement historique
        existing = Historique.search([('vehicle_id', '=', vehicle.id)], limit=1)
        if existing:
            continue

        # Créer une entrée initiale basée sur l'état actuel du véhicule
        if vehicle.state_id:
            Historique.create({
                'vehicle_id': vehicle.id,
                'state_id':   vehicle.state_id.id,
                'cause':      vehicle.state_cause or 'État initial à l\'installation du module',
                'date_debut': vehicle.state_date_debut or fields.Datetime.now(),
                'notes':      'Entrée créée automatiquement lors de l\'installation de fleet_etat_bus.',
            })
            count += 1

    _logger.info(
        'fleet_etat_bus: %d entrées historique créées pour les véhicules existants.', count
    )
