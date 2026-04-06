# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AgilisCarte(models.Model):
    """Carte AGILIS pour ravitaillement externe.
    Les utilisations sont creees automatiquement par la validation du BGE.
    La creation directe d'une utilisation standalone est deconseilee.
    """
    _name = 'transport.agilis.carte'
    _description = 'Carte AGILIS ravitaillement externe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Numero de carte', required=True, tracking=True, translate=False)
    statut = fields.Selection([
        ('active',  'Active'),
        ('bloquee', 'Bloquee'),
        ('expiree', 'Expiree'),
    ], string='Statut', default='active', tracking=True)

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicule assigne', tracking=True)
    chauffeur_principal = fields.Char(string='Chauffeur principal', translate=True)
    date_emission = fields.Date(string='Date emission', default=fields.Date.today)
    date_expiration = fields.Date(string='Date expiration')
    notes = fields.Text(string='Notes', translate=False)

    recharge_ids = fields.One2many('transport.agilis.recharge', 'carte_id', string='Rechargements')
    utilisation_ids = fields.One2many(
        'transport.agilis.utilisation', 'carte_id',
        string='Utilisations',
        help="Creees automatiquement par la validation du BGE. Ne pas saisir manuellement."
    )

    solde_minimum = fields.Float(string='Solde minimum alerte (TND)', digits=(10, 3), default=100.0)
    total_recharge = fields.Float(string='Total recharge (TND)', compute='_calcul_solde', store=True, digits=(10, 3))
    total_utilise = fields.Float(string='Total utilise (TND)', compute='_calcul_solde', store=True, digits=(10, 3))
    solde_actuel = fields.Float(string='Solde actuel (TND)', compute='_calcul_solde', store=True, digits=(10, 3))
    nb_utilisations = fields.Integer(string='Nb utilisations', compute='_calcul_solde', store=True)
    alerte_solde = fields.Boolean(string='Alerte solde bas', compute='_calcul_solde', store=True)

    @api.depends('recharge_ids.montant', 'utilisation_ids.montant')
    def _calcul_solde(self):
        for carte in self:
            total_r = sum(carte.recharge_ids.mapped('montant'))
            total_u = sum(carte.utilisation_ids.mapped('montant'))
            carte.total_recharge = total_r
            carte.total_utilise = total_u
            carte.solde_actuel = total_r - total_u
            carte.nb_utilisations = len(carte.utilisation_ids)
            carte.alerte_solde = carte.solde_actuel < carte.solde_minimum

    def action_bloquer(self):
        self.write({'statut': 'bloquee'})

    def action_activer(self):
        self.write({'statut': 'active'})


class AgilisRecharge(models.Model):
    _name = 'transport.agilis.recharge'
    _description = 'Rechargement carte AGILIS'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    carte_id = fields.Many2one(
        'transport.agilis.carte', string='Carte AGILIS',
        required=True, ondelete='cascade'
    )
    date = fields.Date(string='Date rechargement', required=True, default=fields.Date.today)
    montant = fields.Float(string='Montant recharge (TND)', required=True, digits=(10, 3), tracking=True)
    reference = fields.Char(string='Reference virement', translate=False)
    notes = fields.Text(string='Notes', translate=False)

    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('valide',    'Validé'),
        ('annule',    'Annulé'),
    ], string='État', default='brouillon', tracking=True, readonly=True)
    valide_par = fields.Many2one('res.users', string='Validé par', readonly=True, copy=False)
    date_validation = fields.Datetime(string='Date validation', readonly=True, copy=False)

    def action_valider(self):
        """Valider le rechargement — réservé au Responsable Energie et Directeur."""
        for rec in self:
            if not self.env.user.has_group('transport_energy.group_responsable_energie'):
                raise ValidationError(
                    "Seul un Responsable Energie ou un Directeur peut valider un rechargement."
                )
            rec.write({
                'state': 'valide',
                'valide_par': self.env.user.id,
                'date_validation': fields.Datetime.now(),
            })

    def action_annuler(self):
        """Annuler le rechargement — réservé au Directeur (admin)."""
        for rec in self:
            if not self.env.user.has_group('transport_energy.group_directeur_energie'):
                raise ValidationError(
                    "Seul le Directeur peut annuler un rechargement."
                )
            rec.write({'state': 'annule'})

    def action_reset_brouillon(self):
        """Remettre en brouillon — réservé au Directeur (admin)."""
        for rec in self:
            if not self.env.user.has_group('transport_energy.group_directeur_energie'):
                raise ValidationError(
                    "Seul le Directeur peut remettre un rechargement en brouillon."
                )
            rec.write({
                'state': 'brouillon',
                'valide_par': False,
                'date_validation': False,
            })

    @api.constrains('montant')
    def _verifier_montant(self):
        montant_max = float(self.env['ir.config_parameter'].sudo().get_param(
            'transport_energy.agilis_montant_max_recharge', default='0'
        ))
        for r in self:
            if r.montant <= 0:
                raise ValidationError("Le montant de rechargement doit etre positif.")
            if montant_max > 0 and r.montant > montant_max:
                raise ValidationError(
                    f"Le montant ({r.montant:.3f} TND) dépasse le plafond configuré ({montant_max:.3f} TND)."
                )


class AgilisUtilisation(models.Model):
    """Utilisation carte AGILIS en station externe.
    IMPORTANT : ne pas creer manuellement. Cet enregistrement est cree
    automatiquement par transport.fuel.voucher.action_validate() quand
    payment_mode='agilis'. Le lien voucher_id garantit la tracabilite.
    """
    _name = 'transport.agilis.utilisation'
    _description = 'Utilisation carte AGILIS (creee automatiquement par BGE)'
    _order = 'date desc'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default='Nouveau', translate=False
    )
    carte_id = fields.Many2one(
        'transport.agilis.carte', string='Carte AGILIS',
        required=True, ondelete='cascade'
    )
    # Lien obligatoire vers le BGE source — garantit zero double saisie
    voucher_id = fields.Many2one(
        'transport.fuel.voucher',
        string='BGE source',
        readonly=True,
        help="Bon de gasoil externe qui a genere cette utilisation."
    )
    date = fields.Datetime(string='Date et heure', required=True, default=fields.Datetime.now)
    station_externe = fields.Char(string='Station externe', required=True, translate=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicule', related='carte_id.vehicle_id', store=True)
    chauffeur = fields.Char(string='Chauffeur', translate=True)
    fuel_type_id = fields.Many2one(
        'transport.energy.type', string='Type carburant',
        domain="[('category','=','fuel')]"
    )
    quantite = fields.Float(string='Quantite (L)', required=True, digits=(10, 2))
    prix_unitaire = fields.Float(string='Prix unitaire (TND/L)', digits=(10, 3))
    montant = fields.Float(string='Montant (TND)', digits=(10, 3), compute='_calcul_montant', store=True)

    @api.depends('quantite', 'prix_unitaire')
    def _calcul_montant(self):
        for u in self:
            u.montant = round(u.quantite * u.prix_unitaire, 3)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'transport.agilis.utilisation'
                ) or 'Nouveau'
        return super().create(vals_list)

    @api.constrains('quantite')
    def _verifier_quantite(self):
        for u in self:
            if u.quantite <= 0:
                raise ValidationError("La quantite doit etre positive.")
