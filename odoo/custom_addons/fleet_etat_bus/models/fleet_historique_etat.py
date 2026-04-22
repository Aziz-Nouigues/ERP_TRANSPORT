# -*- coding: utf-8 -*-
from odoo import models, fields


class FleetHistoriqueEtat(models.Model):
    """Historique des changements d'état d'un véhicule.
    Chaque enregistrement = un changement d'état avec sa cause et sa durée.
    """
    _name = 'fleet.vehicle.historique.etat'
    _description = "Historique des états du véhicule"
    _order = 'date_debut desc'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Véhicule',
        required=True, ondelete='cascade', index=True
    )
    state_id = fields.Many2one(
        'fleet.vehicle.state', string='État',
        required=True, ondelete='restrict'
    )
    cause = fields.Text(string='Cause / Motif', required=True)
    date_debut = fields.Datetime(
        string='Depuis le', required=True,
        default=fields.Datetime.now
    )
    date_fin = fields.Datetime(string='Jusqu\'au')
    duree_jours = fields.Integer(
        string='Durée (jours)',
        compute='_compute_duree', store=True
    )
    responsable_id = fields.Many2one(
        'res.users', string='Enregistré par',
        default=lambda self: self.env.user,
        readonly=True
    )
    notes = fields.Text(string='Observations')

    def _compute_duree(self):
        from datetime import datetime
        for rec in self:
            if rec.date_debut:
                fin = rec.date_fin or fields.Datetime.now()
                delta = fin - rec.date_debut
                rec.duree_jours = delta.days
            else:
                rec.duree_jours = 0
