# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PatrimoineCategorie(models.Model):
    """Catégorie d'immobilisation (ex: Terrains, Constructions, Matériel, Mobilier…)"""
    _name = 'patrimoine.categorie'
    _description = 'Catégorie d\'immobilisation'
    _order = 'code, name'

    name = fields.Char(string='Désignation', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    actif = fields.Boolean(string='Actif', default=True)
    notes = fields.Text(string='Notes')

    # ── COMPTES COMPTABLES PAR DÉFAUT ───────────────────────────
    compte_immobilisation_id = fields.Many2one(
        'account.account',
        string='Compte immobilisation',
        help='Compte d\'actif immobilisé (ex: 2xx)',
    )
    compte_amortissement_id = fields.Many2one(
        'account.account',
        string='Compte amortissements cumulés',
        help='Compte de dépréciation (ex: 28xx)',
    )
    compte_dotation_id = fields.Many2one(
        'account.account',
        string='Compte dotation amortissement',
        help='Compte de charge (ex: 68xx)',
    )
    compte_cession_id = fields.Many2one(
        'account.account',
        string='Compte produit de cession',
        help='Compte produit cession immobilisation',
    )
    compte_perte_id = fields.Many2one(
        'account.account',
        string='Compte perte sur cession/rebut',
        help='Compte charge de perte sur sortie',
    )
    compte_depreciation_id = fields.Many2one(
        'account.account',
        string='Compte dépréciation',
        help='Compte perte de valeur exceptionnelle',
    )
    compte_contrepartie_id = fields.Many2one(
        'account.account',
        string='Compte contrepartie entrée',
        help=(
            'Compte crédité lors de la mise en service (ex: 404 Fournisseurs d\'immobilisations, '
            '101 Capital, 131 Subventions d\'équipement). '
            'Obligatoire si aucune facture d\'achat n\'est rattachée à l\'immobilisation.'
        ),
    )

    # ── AMORTISSEMENT PAR DÉFAUT ─────────────────────────────────
    methode_amortissement = fields.Selection([
        ('lineaire',   'Linéaire'),
        ('degressif',  'Dégressif'),
        ('manuel',     'Manuel'),
    ], string='Méthode par défaut', default='lineaire')

    duree_amortissement = fields.Integer(
        string='Durée par défaut (années)',
        default=5,
        help='Durée d\'amortissement en années appliquée par défaut aux immobilisations de cette catégorie',
    )
    taux_degressif = fields.Float(
        string='Coefficient dégressif',
        default=1.5,
        digits=(4, 2),
        help='Coefficient multiplicateur pour la méthode dégressive (ex: 1.5, 2.0)',
    )

    sous_categorie_ids = fields.One2many(
        'patrimoine.sous.categorie',
        'categorie_id',
        string='Sous-catégories',
    )
    nb_immobilisations = fields.Integer(
        string='Nb immobilisations',
        compute='_compute_nb_immobilisations',
    )

    @api.depends('sous_categorie_ids.immobilisation_ids')
    def _compute_nb_immobilisations(self):
        for rec in self:
            rec.nb_immobilisations = self.env['patrimoine.immobilisation'].search_count([
                ('categorie_id', '=', rec.id)
            ])

    @api.constrains('code')
    def _check_code_unique(self):
        for rec in self:
            doublon = self.search([('code', '=', rec.code), ('id', '!=', rec.id)], limit=1)
            if doublon:
                raise ValidationError("Le code '%s' est déjà utilisé par la catégorie '%s'." % (rec.code, doublon.name))


class PatrimoineSousCategorie(models.Model):
    """Sous-catégorie (ex: Matériel informatique, Véhicules de transport, …)"""
    _name = 'patrimoine.sous.categorie'
    _description = 'Sous-catégorie d\'immobilisation'
    _order = 'categorie_id, code'

    name = fields.Char(string='Désignation', required=True, translate=True)
    code = fields.Char(string='Code')
    categorie_id = fields.Many2one(
        'patrimoine.categorie',
        string='Catégorie',
        required=True,
        ondelete='restrict',
    )
    actif = fields.Boolean(string='Actif', default=True)
    notes = fields.Text(string='Notes')

    # Surcharge des paramètres de la catégorie si besoin
    methode_amortissement = fields.Selection([
        ('lineaire',   'Linéaire'),
        ('degressif',  'Dégressif'),
        ('manuel',     'Manuel'),
        ('herite',     'Hériter de la catégorie'),
    ], string='Méthode (surcharge)', default='herite')

    duree_amortissement = fields.Integer(
        string='Durée (surcharge, années)',
        default=0,
        help='0 = hériter de la catégorie',
    )

    immobilisation_ids = fields.One2many(
        'patrimoine.immobilisation',
        'sous_categorie_id',
        string='Immobilisations',
    )


class PatrimoineEmplacement(models.Model):
    """Emplacement physique d'une immobilisation (site, bâtiment, bureau…)"""
    _name = 'patrimoine.emplacement'
    _description = 'Emplacement / Site'
    _order = 'site, name'

    name = fields.Char(string='Désignation emplacement', required=True, translate=True)
    site = fields.Char(string='Site / Agence', required=True, translate=True)
    batiment = fields.Char(string='Bâtiment / Bloc', translate=True)
    etage = fields.Char(string='Étage / Niveau')
    bureau = fields.Char(string='Bureau / Local')
    code = fields.Char(string='Code emplacement')
    actif = fields.Boolean(string='Actif', default=True)

    # Entité organisationnelle
    department_id = fields.Many2one('hr.department', string='Département / Direction')
    responsable_id = fields.Many2one('res.users', string='Responsable site')

    display_name = fields.Char(
        string='Désignation complète',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('site', 'name', 'batiment')
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.site, rec.batiment, rec.name]
            rec.display_name = ' / '.join(p for p in parts if p)
