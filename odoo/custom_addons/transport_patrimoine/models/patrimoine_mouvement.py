# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PatrimoineMouvement(models.Model):
    """
    Transfert d'une immobilisation d'un emplacement vers un autre.
    Conserve l'historique complet des emplacements.
    """
    _name = 'patrimoine.mouvement'
    _description = 'Transfert d\'immobilisation'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N° Transfert',
        readonly=True,
        copy=False,
        default='Nouveau',
    )
    immobilisation_id = fields.Many2one(
        'patrimoine.immobilisation',
        string='Immobilisation',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    numero_inventaire = fields.Char(
        string='N° Inventaire',
        related='immobilisation_id.numero_inventaire',
        store=True,
        readonly=True,
    )
    date = fields.Date(
        string='Date de transfert',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )

    # Emplacements
    emplacement_origine_id = fields.Many2one(
        'patrimoine.emplacement',
        string='Emplacement d\'origine',
        required=True,
        tracking=True,
    )
    emplacement_destination_id = fields.Many2one(
        'patrimoine.emplacement',
        string='Emplacement de destination',
        required=True,
        tracking=True,
    )
    responsable_origine_id = fields.Many2one(
        'res.users',
        string='Responsable sortant',
    )
    responsable_destination_id = fields.Many2one(
        'res.users',
        string='Responsable entrant',
        tracking=True,
    )

    motif = fields.Char(string='Motif du transfert', required=True)
    state = fields.Selection([
        ('brouillon',  'Brouillon'),
        ('confirme',   'Confirmé'),
        ('annule',     'Annulé'),
    ], string='État', default='brouillon', tracking=True)

    notes = fields.Text(string='Observations')

    @api.constrains('emplacement_origine_id', 'emplacement_destination_id')
    def _check_emplacements(self):
        for rec in self:
            if rec.emplacement_origine_id == rec.emplacement_destination_id:
                raise ValidationError(
                    "L'emplacement d'origine et de destination ne peuvent pas être identiques."
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('patrimoine.mouvement') or 'Nouveau'
                )
        return super().create(vals_list)

    def action_confirmer(self):
        """Effectuer le transfert : mettre à jour l'emplacement de l'immobilisation."""
        for rec in self:
            if rec.state != 'brouillon':
                continue
            immo = rec.immobilisation_id
            # Vérifier la cohérence de l'emplacement actuel
            if immo.emplacement_id and immo.emplacement_id != rec.emplacement_origine_id:
                raise ValidationError(
                    "L'emplacement d'origine (%s) ne correspond pas à l'emplacement "
                    "actuel de l'immobilisation (%s)."
                    % (rec.emplacement_origine_id.display_name,
                       immo.emplacement_id.display_name)
                )
            # Mettre à jour l'emplacement
            immo.write({
                'emplacement_id': rec.emplacement_destination_id.id,
                'responsable_id': rec.responsable_destination_id.id or immo.responsable_id.id,
            })
            rec.state = 'confirme'

    def action_annuler(self):
        for rec in self:
            if rec.state == 'confirme':
                # Annuler le mouvement en revenant à l'origine
                rec.immobilisation_id.emplacement_id = rec.emplacement_origine_id
            rec.state = 'annule'

    def action_imprimer_bon_sortie(self):
        """Imprimer le bon de sortie du magasin."""
        self.ensure_one()
        return self.env.ref(
            'transport_patrimoine.action_rapport_bon_sortie'
        ).report_action(self)
