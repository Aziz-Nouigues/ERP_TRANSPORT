# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FleetVehicleAssurance(models.Model):
    """Ajout des informations d'assurance directement sur la fiche bus."""
    _inherit = 'fleet.vehicle'

    # ── POLICES D'ASSURANCE ──────────────────────────────────────
    assurance_bus_ids = fields.One2many(
        'transport.assurance.bus',
        'vehicle_id',
        string='Polices d\'assurance',
    )

    # ── STATUT ASSURANCE (computed) ──────────────────────────────
    assurance_statut = fields.Selection([
        ('assure',     'Assuré'),
        ('non_assure', 'Non assuré'),
        ('alerte',     'Alerte échéance'),
    ], string='Statut assurance',
        compute='_compute_assurance_statut',
        store=True,
    )
    assurance_nb_polices = fields.Integer(
        string='Polices actives',
        compute='_compute_assurance_statut',
        store=True,
    )
    assurance_prochaine_echeance = fields.Date(
        string='Prochaine échéance',
        compute='_compute_assurance_statut',
        store=True,
    )

    @api.depends('assurance_bus_ids.state', 'assurance_bus_ids.date_fin')
    def _compute_assurance_statut(self):
        today = fields.Date.today()
        for rec in self:
            polices_actives = rec.assurance_bus_ids.filtered(
                lambda p: p.state in ('active', 'alerte') and p.date_fin >= today
            )
            polices_alerte = rec.assurance_bus_ids.filtered(
                lambda p: p.state == 'alerte' and p.date_fin >= today
            )
            rec.assurance_nb_polices = len(polices_actives)
            if polices_actives:
                rec.assurance_prochaine_echeance = min(polices_actives.mapped('date_fin'))
                rec.assurance_statut = 'alerte' if polices_alerte else 'assure'
            else:
                rec.assurance_prochaine_echeance = False
                rec.assurance_statut = 'non_assure'
