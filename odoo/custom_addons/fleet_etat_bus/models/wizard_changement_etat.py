# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class WizardChangementEtat(models.TransientModel):
    """Wizard de changement d'état d'un véhicule.
    - Sélection du nouvel état
    - Saisie obligatoire de la cause
    - Enregistrement automatique dans l'historique
    - Clôture automatique de l'entrée historique précédente
    """
    _name = 'fleet.wizard.changement.etat'
    _description = 'Wizard — Changement état véhicule'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Véhicule',
        required=True, readonly=True
    )
    # Infos sur l'état actuel (lecture seule, affichage)
    state_actuel_id = fields.Many2one(
        'fleet.vehicle.state', string='État actuel',
        related='vehicle_id.state_id', readonly=True
    )
    state_cause_actuelle = fields.Text(
        string='Cause actuelle',
        related='vehicle_id.state_cause', readonly=True
    )
    state_date_debut_actuelle = fields.Datetime(
        string='En cet état depuis',
        related='vehicle_id.state_date_debut', readonly=True
    )

    # Nouvel état
    new_state_id = fields.Many2one(
        'fleet.vehicle.state', string='Nouvel état',
        required=True
    )
    cause = fields.Text(
        string='Cause / Motif',
        required=True,
        help='Décrivez la raison du changement d\'état.\n'
             'Ex: Panne moteur sur la ligne L12, Révision 50 000 km, Retour en service après réparation…'
    )
    date_debut = fields.Datetime(
        string='Depuis le',
        required=True,
        default=fields.Datetime.now
    )
    notes = fields.Text(string='Observations complémentaires')

    @api.constrains('new_state_id', 'state_actuel_id')
    def _check_etat_different(self):
        for rec in self:
            if rec.new_state_id == rec.state_actuel_id:
                raise ValidationError(
                    "Le nouvel état est identique à l'état actuel.\n"
                    "Veuillez sélectionner un état différent."
                )

    def action_confirmer(self):
        """Applique le changement d'état et enregistre dans l'historique."""
        self.ensure_one()
        vehicle = self.vehicle_id
        Historique = self.env['fleet.vehicle.historique.etat']

        # 1. Clôturer l'entrée historique en cours (sans date de fin)
        entree_en_cours = Historique.search([
            ('vehicle_id', '=', vehicle.id),
            ('date_fin',   '=', False),
        ], limit=1)
        if entree_en_cours:
            entree_en_cours.date_fin = self.date_debut

        # 2. Créer la nouvelle entrée historique
        Historique.create({
            'vehicle_id':  vehicle.id,
            'state_id':    self.new_state_id.id,
            'cause':       self.cause,
            'date_debut':  self.date_debut,
            'notes':       self.notes or '',
        })

        # 3. Mettre à jour le véhicule
        vehicle.write({
            'state_id':         self.new_state_id.id,
            'state_cause':      self.cause,
            'state_date_debut': self.date_debut,
        })

        # 4. Notification
        vehicle.message_post(
            body=(
                f"<b>Changement d'état</b><br/>"
                f"<b>Ancien état :</b> {self.state_actuel_id.name or '—'}<br/>"
                f"<b>Nouvel état :</b> {self.new_state_id.name}<br/>"
                f"<b>Cause :</b> {self.cause}"
            )
        )

        # 5. Si état indisponible → alerter les tournées planifiées impactées
        ETATS_INDISPONIBLES = {
            'En panne', 'En maintenance', 'Hors service',
            'Out of service', 'Written-off', 'Réformé',
        }
        if self.new_state_id.name in ETATS_INDISPONIBLES:
            from odoo import fields as odoo_fields
            today = odoo_fields.Date.today()
            tournees_impactees = self.env['transport.exploitation.tournee'].search([
                ('vehicle_id', '=', vehicle.id),
                ('state', 'in', ['planifie', 'brouillon']),
                ('date', '>=', today),
            ])
            if tournees_impactees:
                msg = (
                    f"<b>⚠ Alerte bus indisponible</b><br/>"
                    f"Le véhicule <b>{vehicle.name}</b> est passé à l'état "
                    f"<b>{self.new_state_id.name}</b>.<br/>"
                    f"<b>Cause :</b> {self.cause}<br/>"
                    f"Cette tournée doit être réaffectée à un autre bus."
                )
                for tournee in tournees_impactees:
                    tournee.message_post(body=msg)

                # Retourner une action listant les tournées impactées
                return {
                    'name': f'Tournées impactées — {vehicle.name}',
                    'type': 'ir.actions.act_window',
                    'res_model': 'transport.exploitation.tournee',
                    'view_mode': 'list,form',
                    'domain': [('id', 'in', tournees_impactees.ids)],
                    'target': 'current',
                    'context': {
                        'search_default_planifie': 1,
                    },
                }

        return {'type': 'ir.actions.act_window_close'}
