# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class AssuranceChauffeur(models.Model):
    """Police d'assurance chauffeur / personnel.

    Rien dans Odoo natif pour lier une assurance à hr.employee.
    Ce modèle couvre :
      - Accident de travail (CNAM) — obligatoire
      - Assurance vie groupe — optionnel
      - RC professionnelle chauffeur — obligatoire
      - Complémentaire santé — optionnel
    """
    _name = 'transport.assurance.chauffeur'
    _description = 'Police assurance chauffeur / personnel'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_fin, employe_id'

    # ── IDENTIFICATION ───────────────────────────────────────────
    numero_police = fields.Char(
        string='N° Police',
        readonly=True, copy=False,
        default='Nouveau',
        tracking=True,
    )
    name = fields.Char(
        string='Référence',
        compute='_compute_name',
        store=True,
    )

    # ── EMPLOYÉ / BÉNÉFICIAIRE ───────────────────────────────────
    employe_id = fields.Many2one(
        'hr.employee',
        string='Chauffeur / Employé',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain="[('active', '=', True)]",
    )
    department_id = fields.Many2one(
        'hr.department',
        related='employe_id.department_id',
        string='Département',
        store=True, readonly=True,
    )
    job_id = fields.Many2one(
        'hr.job',
        related='employe_id.job_id',
        string='Poste',
        store=True, readonly=True,
    )
    beneficiaire = fields.Char(
        string='Bénéficiaire désigné',
        tracking=True,
        help='Pour assurance vie groupe : nom du bénéficiaire en cas de décès.'
    )
    lien_beneficiaire = fields.Char(
        string='Lien avec l\'assuré',
        help='Ex : conjoint, enfant, parent…'
    )

    # ── POLICE ───────────────────────────────────────────────────
    type_police_id = fields.Many2one(
        'transport.assurance.type',
        string='Type de police',
        required=True,
        domain="[('categorie', 'in', ['chauffeur', 'both'])]",
        tracking=True,
        ondelete='restrict',
    )
    compagnie_id = fields.Many2one(
        'transport.assurance.compagnie',
        string='Compagnie / Organisme',
        required=True,
        tracking=True,
        ondelete='restrict',
        help='Pour l\'AT/CNAM, renseigner la CNAM comme compagnie.'
    )
    is_obligatoire = fields.Boolean(
        related='type_police_id.is_obligatoire',
        string='Obligatoire légalement',
        store=True, readonly=True,
    )
    numero_cnam = fields.Char(
        string='N° affilié CNAM',
        tracking=True,
        help='Renseigner pour les polices AT liées à la CNAM.'
    )

    # ── DATES & MONTANTS ─────────────────────────────────────────
    date_debut = fields.Date(
        string='Date de début', required=True,
        default=fields.Date.today, tracking=True,
    )
    date_fin = fields.Date(
        string='Date de fin / Expiration',
        required=True, tracking=True,
    )
    prime_annuelle = fields.Monetary(
        string='Prime annuelle (TND)',
        currency_field='currency_id',
        tracking=True,
    )
    prime_mensuelle = fields.Monetary(
        string='Prime mensuelle',
        compute='_compute_prime_mensuelle',
        currency_field='currency_id',
        store=False,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.TND', raise_if_not_found=False)
                             or self.env.company.currency_id,
    )
    capital_assure = fields.Monetary(
        string='Capital assuré / Plafond',
        currency_field='currency_id',
        tracking=True,
        help='Montant maximal couvert (ex : capital vie, plafond santé).'
    )
    franchise = fields.Monetary(
        string='Franchise (TND)',
        currency_field='currency_id',
        tracking=True,
    )

    # ── WORKFLOW ─────────────────────────────────────────────────
    state = fields.Selection([
        ('brouillon',  'Brouillon'),
        ('active',     'Active'),
        ('alerte',     'Alerte échéance'),
        ('expirée',    'Expirée'),
        ('résiliée',   'Résiliée'),
    ], string='État', default='brouillon', tracking=True, required=True)

    # ── ALERTES ──────────────────────────────────────────────────
    date_alerte = fields.Date(
        string='Date d\'alerte',
        compute='_compute_date_alerte',
        store=True,
    )
    jours_restants = fields.Integer(
        string='Jours restants',
        compute='_compute_jours_restants',
        store=False,
    )

    # ── SINISTRES ────────────────────────────────────────────────
    sinistre_ids = fields.One2many(
        'transport.assurance.sinistre', 'police_chauffeur_id',
        string='Sinistres liés',
    )
    nb_sinistres = fields.Integer(
        string='Nb sinistres',
        compute='_compute_nb_sinistres',
        store=True,
    )

    notes = fields.Text(string='Notes / Conditions particulières')

    # ── COMPUTE ─────────────────────────────────────────────────
    @api.depends('employe_id', 'type_police_id', 'numero_police')
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.numero_police and rec.numero_police != 'Nouveau':
                parts.append(rec.numero_police)
            if rec.employe_id:
                parts.append(rec.employe_id.name)
            if rec.type_police_id:
                parts.append(rec.type_police_id.name)
            rec.name = ' — '.join(parts) if parts else 'Nouvelle police'

    @api.depends('prime_annuelle')
    def _compute_prime_mensuelle(self):
        for rec in self:
            rec.prime_mensuelle = (rec.prime_annuelle or 0.0) / 12.0

    @api.depends('date_fin')
    def _compute_date_alerte(self):
        from dateutil.relativedelta import relativedelta
        for rec in self:
            if rec.date_fin:
                rec.date_alerte = rec.date_fin - relativedelta(days=30)
            else:
                rec.date_alerte = False

    @api.depends('date_fin')
    def _compute_jours_restants(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_fin:
                delta = rec.date_fin - today
                rec.jours_restants = delta.days
            else:
                rec.jours_restants = 0

    @api.depends('sinistre_ids')
    def _compute_nb_sinistres(self):
        for rec in self:
            rec.nb_sinistres = len(rec.sinistre_ids)

    # ── CONTRAINTES ──────────────────────────────────────────────
    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        for rec in self:
            if rec.date_debut and rec.date_fin and rec.date_fin < rec.date_debut:
                raise ValidationError(
                    'La date de fin ne peut pas être antérieure à la date de début.'
                )

    # ── ACTIONS WORKFLOW ─────────────────────────────────────────
    def action_activer(self):
        for rec in self:
            if rec.state != 'brouillon':
                raise UserError('Seule une police en brouillon peut être activée.')
            if rec.numero_police == 'Nouveau':
                rec.numero_police = self.env['ir.sequence'].next_by_code(
                    'transport.assurance.chauffeur'
                ) or 'POL-CHF-??'
            rec.state = 'active'

    def action_resilier(self):
        for rec in self:
            if rec.state not in ('active', 'alerte', 'expirée'):
                raise UserError('Impossible de résilier une police dans cet état.')
            rec.state = 'résiliée'

    def action_renouveler(self):
        self.ensure_one()
        return {
            'name': 'Renouveler la police',
            'type': 'ir.actions.act_window',
            'res_model': 'transport.assurance.wizard.renouvellement',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_police_chauffeur_id': self.id,
                'default_employe_id': self.employe_id.id,
                'default_type_police_id': self.type_police_id.id,
                'default_compagnie_id': self.compagnie_id.id,
                'default_prime_annuelle': self.prime_annuelle,
            },
        }
