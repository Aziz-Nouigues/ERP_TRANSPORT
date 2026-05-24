# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class AssuranceBus(models.Model):
    """Police d'assurance véhicule (bus).

    Modèle autonome (pas d'héritage fleet.vehicle.log.contract
    pour éviter les incompatibilités entre versions Odoo).
    Lié à fleet.vehicle via vehicle_id.
    """
    _name = 'transport.assurance.bus'
    _description = 'Police assurance bus'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_fin, vehicle_id'

    # ── IDENTIFICATION ───────────────────────────────────────────
    numero_police = fields.Char(
        string='N° Police assurance',
        readonly=True, copy=False,
        default='Nouveau',
        tracking=True,
    )

    # ── VÉHICULE ─────────────────────────────────────────────────
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Bus / Véhicule',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain="[('active','=',True)]",
    )

    # ── CLASSIFICATION ───────────────────────────────────────────
    type_police_id = fields.Many2one(
        'transport.assurance.type',
        string='Type de police',
        required=True,
        domain="[('categorie', 'in', ['bus', 'both'])]",
        tracking=True,
        ondelete='restrict',
    )
    compagnie_id = fields.Many2one(
        'transport.assurance.compagnie',
        string='Compagnie',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    is_obligatoire = fields.Boolean(
        related='type_police_id.is_obligatoire',
        string='Obligatoire légalement',
        store=True, readonly=True,
    )

    # ── DATES ────────────────────────────────────────────────────
    date_debut = fields.Date(
        string='Date de début',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    date_fin = fields.Date(
        string='Date de fin / Expiration',
        required=True,
        tracking=True,
    )
    date_alerte = fields.Date(
        string='Date d\'alerte',
        compute='_compute_date_alerte',
        store=True,
        help='J-30 avant date_fin.'
    )

    # ── DONNÉES FINANCIÈRES ──────────────────────────────────────
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
    franchise = fields.Monetary(
        string='Franchise (TND)',
        currency_field='currency_id',
        tracking=True,
    )
    plafond_garantie = fields.Monetary(
        string='Plafond de garantie (TND)',
        currency_field='currency_id',
        tracking=True,
    )

    # ── WORKFLOW ─────────────────────────────────────────────────
    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('active',    'Active'),
        ('alerte',    'Alerte échéance'),
        ('expiree',   'Expirée'),
        ('resiliee',  'Résiliée'),
    ], string='État', default='brouillon', tracking=True, required=True)

    # ── VISITE TECHNIQUE (Règle Tunisie) ─────────────────────────
    date_visite_technique = fields.Date(
        string='Date visite technique',
        tracking=True,
        help='Obligatoire avant renouvellement RC en Tunisie.'
    )
    visite_technique_valide = fields.Boolean(
        string='Visite technique valide',
        compute='_compute_visite_valide',
        store=False,
    )

    # ── RENOUVELLEMENT ───────────────────────────────────────────
    est_renouvelable = fields.Boolean(
        string='Renouvellement possible',
        compute='_compute_est_renouvelable',
        store=False,
    )
    police_precedente_id = fields.Many2one(
        'transport.assurance.bus',
        string='Police précédente',
        readonly=True,
    )
    police_suivante_id = fields.Many2one(
        'transport.assurance.bus',
        string='Police suivante',
        readonly=True,
    )

    # ── SINISTRES ────────────────────────────────────────────────
    sinistre_ids = fields.One2many(
        'transport.assurance.sinistre', 'police_bus_id',
        string='Sinistres liés',
    )
    nb_sinistres = fields.Integer(
        string='Nb sinistres',
        compute='_compute_nb_sinistres',
        store=True,
    )
    montant_total_indemnise = fields.Monetary(
        string='Total indemnisé',
        compute='_compute_montant_total_indemnise',
        currency_field='currency_id',
        store=True,
    )

    notes = fields.Text(string='Notes / Conditions particulières')

    # ── COMPUTE ─────────────────────────────────────────────────
    @api.depends('prime_annuelle')
    def _compute_prime_mensuelle(self):
        for rec in self:
            rec.prime_mensuelle = (rec.prime_annuelle or 0.0) / 12.0

    @api.depends('date_visite_technique')
    def _compute_visite_valide(self):
        today = fields.Date.today()
        for rec in self:
            if not rec.date_visite_technique:
                rec.visite_technique_valide = False
            else:
                limite = rec.date_visite_technique + relativedelta(years=1)
                rec.visite_technique_valide = limite >= today

    @api.depends('date_fin')
    def _compute_date_alerte(self):
        for rec in self:
            if rec.date_fin:
                rec.date_alerte = rec.date_fin - relativedelta(days=30)
            else:
                rec.date_alerte = False

    @api.depends('type_police_id', 'date_visite_technique', 'visite_technique_valide')
    def _compute_est_renouvelable(self):
        for rec in self:
            if rec.type_police_id and rec.type_police_id.code == 'RC':
                rec.est_renouvelable = rec.visite_technique_valide
            else:
                rec.est_renouvelable = True

    @api.depends('sinistre_ids')
    def _compute_nb_sinistres(self):
        for rec in self:
            rec.nb_sinistres = len(rec.sinistre_ids)

    @api.depends('sinistre_ids.montant_accorde')
    def _compute_montant_total_indemnise(self):
        for rec in self:
            rec.montant_total_indemnise = sum(
                s.montant_accorde for s in rec.sinistre_ids
                if s.state == 'cloture'
            )

    # ── ONCHANGE ─────────────────────────────────────────────────
    @api.onchange('type_police_id')
    def _onchange_type_police(self):
        if (self.type_police_id
                and self.type_police_id.code == 'RC'
                and not self.date_visite_technique):
            return {
                'warning': {
                    'title': 'Visite technique requise',
                    'message': 'La police RC exige une visite technique valide '
                               '(règle Tunisie). Veuillez renseigner la date '
                               'de la dernière visite technique du véhicule.',
                }
            }

    # ── CONTRAINTES ──────────────────────────────────────────────
    @api.constrains('type_police_id', 'date_visite_technique', 'state')
    def _check_visite_technique_rc(self):
        for rec in self:
            if (rec.state == 'active'
                    and rec.type_police_id
                    and rec.type_police_id.code == 'RC'
                    and not rec.visite_technique_valide):
                raise ValidationError(
                    f'Impossible d\'activer la police RC du véhicule '
                    f'{rec.vehicle_id.name} : la visite technique est '
                    f'absente ou expirée (règle Tunisie).'
                )

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
            rec._check_visite_technique_rc()
            if rec.numero_police == 'Nouveau':
                rec.numero_police = self.env['ir.sequence'].next_by_code(
                    'transport.assurance.bus'
                ) or 'POL-BUS-??'
            rec.state = 'active'

    def action_resilier(self):
        for rec in self:
            if rec.state not in ('active', 'alerte', 'expiree'):
                raise UserError('Impossible de résilier une police dans cet état.')
            rec.state = 'resiliee'

    def action_renouveler(self):
        self.ensure_one()
        if not self.est_renouvelable:
            raise UserError(
                'Renouvellement impossible : la visite technique du véhicule '
                'doit être valide avant de renouveler la police RC (règle Tunisie).'
            )
        return {
            'name': 'Renouveler la police',
            'type': 'ir.actions.act_window',
            'res_model': 'transport.assurance.wizard.renouvellement',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_police_bus_id': self.id,
                'default_vehicle_id': self.vehicle_id.id,
                'default_type_police_id': self.type_police_id.id,
                'default_compagnie_id': self.compagnie_id.id,
                'default_prime_annuelle': self.prime_annuelle,
                'default_franchise': self.franchise,
                'default_plafond_garantie': self.plafond_garantie,
            },
        }

    def action_voir_sinistres(self):
        self.ensure_one()
        return {
            'name': f'Sinistres — {self.vehicle_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'transport.assurance.sinistre',
            'view_mode': 'list,form',
            'domain': [('police_bus_id', '=', self.id)],
            'context': {'default_police_bus_id': self.id},
        }

    @api.model
    def vehicle_has_valid_rc(self, vehicle_id):
        """Vérifie qu'un bus a au moins une police active (quelle que soit son type).
        Retourne (True, None) si au moins une police valide existe,
        (False, None) sinon.
        """
        today = fields.Date.today()
        valide = self.search_count([
            ('vehicle_id', '=', vehicle_id),
            ('state', '=', 'active'),
            ('date_fin', '>=', today),
        ])
        if not valide:
            return False, None
        return True, None