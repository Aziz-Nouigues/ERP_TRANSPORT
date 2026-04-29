# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FleetVehicleEtat(models.Model):
    """Extension de fleet.vehicle :
    - Cause de l'état actuel
    - Date de début de l'état actuel
    - Historique complet des changements d'état
    - Bouton d'action rapide pour changer l'état
    - Type de véhicule : urbain / interurbain
    """
    _inherit = 'fleet.vehicle'

    # ── TYPE DE VÉHICULE ─────────────────────────────────────────
    type_vehicule = fields.Selection([
        ('urbain',       'Urbain'),
        ('interurbain',  'Interurbain'),
        ('mixte',        'Mixte (Urbain + Interurbain)'),
    ], string='Type de véhicule',
       help='Définit si ce bus est affecté aux lignes urbaines, interurbaines ou les deux.',
       default='urbain',
       tracking=True,
    )

    # ── ÉTAT ACTUEL ──────────────────────────────────────────────
    state_cause = fields.Text(
        string='Cause / Motif de l\'état',
        help='Raison du passage à l\'état actuel (ex: panne moteur, révision périodique…)'
    )
    state_date_debut = fields.Datetime(
        string='En cet état depuis',
        readonly=True
    )
    state_duree_jours = fields.Integer(
        string='Jours dans cet état',
        compute='_compute_state_duree', store=False
    )

    # ── HISTORIQUE ───────────────────────────────────────────────
    historique_etat_ids = fields.One2many(
        'fleet.vehicle.historique.etat', 'vehicle_id',
        string='Historique des états'
    )
    nb_historique = fields.Integer(
        string='Nb changements',
        compute='_compute_nb_historique', store=True
    )

    # ── COMPUTED ────────────────────────────────────────────────
    @api.depends('historique_etat_ids')
    def _compute_nb_historique(self):
        for rec in self:
            rec.nb_historique = len(rec.historique_etat_ids)

    def _compute_state_duree(self):
        for rec in self:
            if rec.state_date_debut:
                delta = fields.Datetime.now() - rec.state_date_debut
                rec.state_duree_jours = delta.days
            else:
                rec.state_duree_jours = 0

    # ── ACTION : Wizard changement d'état ───────────────────────
    def action_changer_etat(self):
        """Ouvre le wizard de changement d'état."""
        self.ensure_one()
        return {
            'name': 'Changer l\'état du véhicule',
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.wizard.changement.etat',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_vehicle_id': self.id,
                'default_state_id': self.state_id.id if self.state_id else False,
            }
        }

    def action_voir_historique(self):
        """Ouvre l'historique complet des états."""
        self.ensure_one()
        return {
            'name': f'Historique états — {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle.historique.etat',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }