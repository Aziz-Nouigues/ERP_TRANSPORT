# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WizardRapportAssurance(models.TransientModel):
    """Wizard de génération des 6 rapports assurance."""
    _name = 'transport.assurance.wizard.rapport'
    _description = 'Wizard rapports assurance'

    type_rapport = fields.Selection([
        ('polices_actives',  'Polices actives (bus + chauffeurs)'),
        ('echeancier',       'Échéancier des renouvellements'),
        ('cout',             'Coût des assurances (primes)'),
        ('sinistres',        'Sinistres par véhicule'),
        ('sinistralite',     'Taux de sinistralité'),
        ('bus_non_assures',  'Bus non assurés — alerte légale'),
    ], string='Rapport', required=True, default='polices_actives')

    # ── FILTRES ──────────────────────────────────────────────────
    date_debut = fields.Date(string='Du', default=lambda self: fields.Date.today().replace(month=1, day=1))
    date_fin = fields.Date(string='Au', default=fields.Date.today)
    compagnie_id = fields.Many2one(
        'transport.assurance.compagnie', string='Compagnie (filtre)'
    )
    type_police_id = fields.Many2one(
        'transport.assurance.type', string='Type de police (filtre)'
    )
    echeance_horizon = fields.Selection([
        ('3',  '3 mois'),
        ('6',  '6 mois'),
        ('12', '12 mois'),
    ], string='Horizon échéancier', default='3')
    inclure_bus = fields.Boolean(string='Inclure polices bus', default=True)
    inclure_chauffeurs = fields.Boolean(string='Inclure polices chauffeurs', default=True)

    def action_imprimer(self):
        self.ensure_one()
        rapport_map = {
            'polices_actives': 'transport_assurance.report_polices_actives_action',
            'echeancier':      'transport_assurance.report_echeancier_action',
            'sinistres':       'transport_assurance.report_sinistres_action',
            'bus_non_assures': 'transport_assurance.report_bus_non_assures_action',
        }
        action_ref = rapport_map.get(self.type_rapport)
        if action_ref:
            return self.env.ref(action_ref).report_action(self)
        # Pour sinistralite et cout : retourner les données dans une vue pivot
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'transport.assurance.sinistre',
            'view_mode': 'pivot,list',
            'name': 'Taux de sinistralité',
        }
