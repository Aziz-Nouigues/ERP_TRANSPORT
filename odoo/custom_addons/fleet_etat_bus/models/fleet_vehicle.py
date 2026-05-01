# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FleetVehicleEtat(models.Model):
    """Extension de fleet.vehicle pour le parc bus transport terrestre."""
    _inherit = 'fleet.vehicle'

    # ── TYPE DE VÉHICULE ─────────────────────────────────────────
    type_vehicule = fields.Selection([
        ('urbain',      'Urbain'),
        ('interurbain', 'Interurbain'),
        ('mixte',       'Mixte (Urbain + Interurbain)'),
    ], string='Type de véhicule',
       help='Définit si ce bus est affecté aux lignes urbaines, interurbaines ou les deux.',
       default='urbain', tracking=True,
    )

    # ── ÉTAT ACTUEL ──────────────────────────────────────────────
    state_cause = fields.Text(
        string='Cause / Motif de l\'état',
        help='Raison du passage à l\'état actuel (ex: panne moteur, révision périodique…)'
    )
    state_date_debut = fields.Datetime(
        string='En cet état depuis', readonly=True
        # store=True implicite (champ regular) — triable en liste sans problème
    )

    # store=False : calculé à la volée, jamais écrit en base.
    # NE PAS afficher dans les vues liste/kanban (pas de colonne SQL).
    # Visible uniquement dans la fiche form et l'onglet historique.
    state_duree_jours = fields.Integer(
        string='Jours dans cet état',
        compute='_compute_state_duree',
        store=False,
    )

    # ── HISTORIQUE ───────────────────────────────────────────────
    historique_etat_ids = fields.One2many(
        'fleet.vehicle.historique.etat', 'vehicle_id',
        string='Historique des états'
    )
    # store=True OK : nb_historique est un Integer classique recalculé via read_group.
    # La colonne existe dès l'installation initiale du module.
    # Odoo 19 interdit @api.depends('field.id') → on utilise read_group.
    nb_historique = fields.Integer(
        string='Nb changements',
        compute='_compute_nb_historique',
        store=True,
    )

    # ── COMPUTED ─────────────────────────────────────────────────
    @api.depends('historique_etat_ids')
    def _compute_nb_historique(self):
        if not self.ids:
            for rec in self:
                rec.nb_historique = 0
            return
        groups = self.env['fleet.vehicle.historique.etat'].read_group(
            domain=[('vehicle_id', 'in', self.ids)],
            fields=['vehicle_id'],
            groupby=['vehicle_id'],
        )
        counts = {g['vehicle_id'][0]: g['vehicle_id_count'] for g in groups}
        for rec in self:
            rec.nb_historique = counts.get(rec.id, 0)

    @api.depends('state_date_debut')
    def _compute_state_duree(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state_date_debut:
                rec.state_duree_jours = (now - rec.state_date_debut).days
            else:
                rec.state_duree_jours = 0

    # ── ACTIONS ──────────────────────────────────────────────────
    def action_changer_etat(self):
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
        self.ensure_one()
        return {
            'name': f'Historique états — {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle.historique.etat',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    def action_imprimer_fiche(self):
        self.ensure_one()
        return self.env.ref(
            'fleet_etat_bus.action_report_fleet_etat_vehicle'
        ).report_action(self)
