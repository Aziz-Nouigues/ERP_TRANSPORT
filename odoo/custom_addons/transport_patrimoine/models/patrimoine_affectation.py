# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PatrimoineAffectation(models.Model):
    """
    Distribution d'une immobilisation à un utilisateur / département.
    Suivi des quantités distribuées et non encore distribuées.
    """
    _name = 'patrimoine.affectation'
    _description = 'Affectation / Distribution d\'immobilisation'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N° Affectation',
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
        related='immobilisation_id.numero_inventaire',
        store=True,
        readonly=True,
    )
    date = fields.Date(
        string='Date d\'affectation',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )

    # Affectataire
    beneficiaire_id = fields.Many2one(
        'res.users',
        string='Bénéficiaire',
        tracking=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Département / Direction',
        tracking=True,
    )
    emplacement_id = fields.Many2one(
        'patrimoine.emplacement',
        string='Emplacement d\'affectation',
        tracking=True,
    )

    quantite = fields.Float(
        string='Quantité distribuée',
        default=1.0,
        digits=(10, 2),
        required=True,
    )
    state = fields.Selection([
        ('active',   'Active'),
        ('retiree',  'Retirée'),
        ('annulee',  'Annulée'),
    ], string='État', default='active', tracking=True)

    date_retour = fields.Date(string='Date de retour / fin affectation')
    motif_retour = fields.Char(string='Motif de retour')
    est_premiere_affectation = fields.Boolean(
        string='Première affectation',
        default=False,
        help='Si coché, un bon de sortie du magasin sera édité',
    )
    bon_sortie_imprime = fields.Boolean(string='Bon de sortie imprimé', default=False)
    notes = fields.Text(string='Observations')

    @api.constrains('quantite', 'immobilisation_id')
    def _check_quantite(self):
        for rec in self:
            if rec.quantite <= 0:
                raise ValidationError("La quantité distribuée doit être positive.")
            immo = rec.immobilisation_id
            total_distribue = sum(
                a.quantite for a in immo.affectation_ids
                if a.state == 'active' and a.id != rec.id
            )
            if total_distribue + rec.quantite > immo.quantite:
                raise ValidationError(
                    "Impossible de distribuer %.2f unité(s) : "
                    "la quantité disponible est de %.2f."
                    % (rec.quantite, immo.quantite - total_distribue)
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('patrimoine.affectation') or 'Nouveau'
                )
        return super().create(vals_list)

    def action_retirer(self):
        for rec in self:
            rec.write({
                'state': 'retiree',
                'date_retour': fields.Date.today(),
            })
            # Mettre à jour la quantité disponible sur l'immo
            rec.immobilisation_id._compute_quantites()

    def action_imprimer_bon_sortie(self):
        """Édition du bon de sortie magasin (première affectation)."""
        self.ensure_one()
        self.bon_sortie_imprime = True
        return self.env.ref(
            'transport_patrimoine.action_rapport_bon_sortie_affectation'
        ).report_action(self)
