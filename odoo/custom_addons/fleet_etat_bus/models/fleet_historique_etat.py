# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


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
    date_fin = fields.Datetime(string="Jusqu'au")
    duree_jours = fields.Integer(
        string='Durée (jours)',
        compute='_compute_duree',
        store=False,   # calculé à la volée — pas de valeur figée en base
    )
    priorite = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Urgent'),
        ('2', 'Critique'),
    ], string='Priorité', default='0',
       help='Niveau de priorité de cet événement (panne critique, entretien planifié…)')
    responsable_id = fields.Many2one(
        'res.users', string='Enregistré par',
        default=lambda self: self.env.user,
        readonly=True
    )
    notes = fields.Text(string='Observations')

    # ── COMPUTED ──────────────────────────────────────────────────
    @api.depends('date_debut', 'date_fin')
    def _compute_duree(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.date_debut:
                fin = rec.date_fin or now
                rec.duree_jours = (fin - rec.date_debut).days
            else:
                rec.duree_jours = 0

    # ── CONTRAINTES ───────────────────────────────────────────────
    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        for rec in self:
            if rec.date_fin and rec.date_fin < rec.date_debut:
                raise ValidationError(
                    "La date de fin ne peut pas être antérieure à la date de début.\n"
                    f"Début : {rec.date_debut}  —  Fin : {rec.date_fin}"
                )
