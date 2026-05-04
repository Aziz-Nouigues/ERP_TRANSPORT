# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AssuranceCompagnie(models.Model):
    """Référentiel des compagnies d'assurance agréées en Tunisie."""
    _name = 'transport.assurance.compagnie'
    _description = 'Compagnie d\'assurance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── IDENTIFICATION ───────────────────────────────────────────
    name = fields.Char(
        string='Raison sociale', required=True, tracking=True
    )
    code = fields.Char(
        string='Code compagnie', size=10, tracking=True,
        help='Identifiant court (ex : STAR, GAT, COMAR…)'
    )
    numero_agrement = fields.Char(
        string='N° agrément ministériel', tracking=True
    )
    active = fields.Boolean(default=True)

    # ── COORDONNÉES ──────────────────────────────────────────────
    adresse = fields.Text(string='Adresse', translate=True)
    ville = fields.Char(string='Ville', translate=True)
    telephone = fields.Char(string='Téléphone')
    fax = fields.Char(string='Fax')
    email = fields.Char(string='Email')
    site_web = fields.Char(string='Site web')

    # ── CONTACT DÉDIÉ ────────────────────────────────────────────
    contact_nom = fields.Char(string='Nom du contact dédié')
    contact_telephone = fields.Char(string='Téléphone contact')
    contact_email = fields.Char(string='Email contact')
    contact_poste = fields.Char(string='Poste / Fonction')

    # ── STATISTIQUES (computed) ──────────────────────────────────
    nb_polices_bus = fields.Integer(
        string='Polices bus actives',
        compute='_compute_stats', store=False
    )
    nb_polices_chauffeur = fields.Integer(
        string='Polices chauffeurs actives',
        compute='_compute_stats', store=False
    )
    nb_sinistres_ouverts = fields.Integer(
        string='Sinistres en cours',
        compute='_compute_stats', store=False
    )
    notes = fields.Text(string='Notes internes')

    # ── CONTRAINTES ──────────────────────────────────────────────
    _sql_constraints = [
        ('code_uniq', 'unique(code)',
         'Le code compagnie doit être unique.')
    ]

    # ── COMPUTE ─────────────────────────────────────────────────
    def _compute_stats(self):
        today = fields.Date.today()
        for rec in self:
            rec.nb_polices_bus = self.env['transport.assurance.bus'].search_count([
                ('compagnie_id', '=', rec.id),
                ('state', '=', 'active'),
                ('date_fin', '>=', today),
            ])
            rec.nb_polices_chauffeur = self.env['transport.assurance.chauffeur'].search_count([
                ('compagnie_id', '=', rec.id),
                ('state', '=', 'active'),
                ('date_fin', '>=', today),
            ])
            rec.nb_sinistres_ouverts = self.env['transport.assurance.sinistre'].search_count([
                ('compagnie_id', '=', rec.id),
                ('state', 'in', ['declare', 'instruction']),
            ])

    def name_get(self):
        result = []
        for rec in self:
            name = rec.name
            if rec.code:
                name = f'[{rec.code}] {name}'
            result.append((rec.id, name))
        return result
