from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AgilisCarte(models.Model):
    """Carte AGILIS pour ravitaillement externe"""
    _name = 'transport.agilis.carte'
    _description = 'Carte AGILIS'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── IDENTIFICATION ───────────────────────────────────────
    name = fields.Char(
        string='Numéro de carte',
        required=True,
        tracking=True
    )

    statut = fields.Selection([
        ('active', '✅ Active'),
        ('bloquee', '🔴 Bloquée'),
        ('expiree', '⚫ Expirée'),
    ], string='Statut', default='active', tracking=True)

    # ── VÉHICULE ────────────────────────────────────────────
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Véhicule assigné',
        tracking=True
    )

    chauffeur_principal = fields.Char(
        string='Chauffeur principal'
    )

    # ── SOLDE ───────────────────────────────────────────────
    solde_actuel = fields.Float(
        string='Solde actuel (DT)',
        digits=(10, 3),
        compute='_calcul_solde',
        store=True
    )

    solde_minimum = fields.Float(
        string='Solde minimum alerte (DT)',
        digits=(10, 3),
        default=100.0
    )

    alerte_solde = fields.Boolean(
        string='Alerte solde bas',
        compute='_calcul_solde',
        store=True
    )

    # ── DATES ───────────────────────────────────────────────
    date_emission = fields.Date(
        string='Date émission',
        default=fields.Date.today
    )

    date_expiration = fields.Date(
        string='Date expiration'
    )

    notes = fields.Text(string='Notes')

    # ── RELATIONS ───────────────────────────────────────────
    recharge_ids = fields.One2many(
        'transport.agilis.recharge',
        'carte_id',
        string='Rechargements'
    )

    utilisation_ids = fields.One2many(
        'transport.agilis.utilisation',
        'carte_id',
        string='Utilisations'
    )

    # ── STATISTIQUES ────────────────────────────────────────
    total_recharge = fields.Float(
        string='Total rechargé (DT)',
        compute='_calcul_solde',
        store=True,
        digits=(10, 3)
    )

    total_utilise = fields.Float(
        string='Total utilisé (DT)',
        compute='_calcul_solde',
        store=True,
        digits=(10, 3)
    )

    nb_utilisations = fields.Integer(
        string='Nb utilisations',
        compute='_calcul_solde',
        store=True
    )

    # ── CALCULS ─────────────────────────────────────────────
    @api.depends(
        'recharge_ids.montant',
        'utilisation_ids.montant'
    )
    def _calcul_solde(self):
        for carte in self:
            total_r = sum(carte.recharge_ids.mapped('montant'))
            total_u = sum(carte.utilisation_ids.mapped('montant'))
            carte.total_recharge = total_r
            carte.total_utilise = total_u
            carte.solde_actuel = total_r - total_u
            carte.nb_utilisations = len(carte.utilisation_ids)
            carte.alerte_solde = (
                    carte.solde_actuel < carte.solde_minimum
            )

    # ── ACTIONS ─────────────────────────────────────────────
    def action_bloquer(self):
        self.write({'statut': 'bloquee'})

    def action_activer(self):
        self.write({'statut': 'active'})


class AgilisRecharge(models.Model):
    """Rechargement d'une carte AGILIS"""
    _name = 'transport.agilis.recharge'
    _description = 'Rechargement Carte AGILIS'
    _order = 'date desc'

    carte_id = fields.Many2one(
        'transport.agilis.carte',
        string='Carte AGILIS',
        required=True,
        ondelete='cascade'
    )

    date = fields.Date(
        string='Date rechargement',
        required=True,
        default=fields.Date.today
    )

    montant = fields.Float(
        string='Montant rechargé (DT)',
        required=True,
        digits=(10, 3)
    )

    reference = fields.Char(
        string='Référence virement'
    )

    notes = fields.Text(string='Notes')

    @api.constrains('montant')
    def _verifier_montant(self):
        for r in self:
            if r.montant <= 0:
                raise ValidationError(
                    "Le montant de rechargement doit être positif !"
                )


class AgilisUtilisation(models.Model):
    """Utilisation d'une carte AGILIS en station"""
    _name = 'transport.agilis.utilisation'
    _description = 'Utilisation Carte AGILIS'
    _order = 'date desc'

    name = fields.Char(
        string='Référence',
        required=True,
        copy=False,
        readonly=True,
        default='Nouveau'
    )

    carte_id = fields.Many2one(
        'transport.agilis.carte',
        string='Carte AGILIS',
        required=True,
        ondelete='cascade'
    )

    # ── DATE & LIEU ──────────────────────────────────────────
    date = fields.Datetime(
        string='Date & Heure',
        required=True,
        default=fields.Datetime.now
    )

    station_externe = fields.Char(
        string='Station externe',
        required=True
    )

    # ── VÉHICULE ────────────────────────────────────────────
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Véhicule',
        related='carte_id.vehicle_id',
        store=True
    )

    chauffeur = fields.Char(
        string='Chauffeur'
    )

    # ── CARBURANT ───────────────────────────────────────────
    fuel_type_id = fields.Many2one(
        'transport.energy.type',
        string='Type carburant',
        domain="[('category', '=', 'fuel')]",

    )

    quantite = fields.Float(
        string='Quantité (L)',
        required=True,
        digits=(10, 2)
    )

    prix_unitaire = fields.Float(
        string='Prix unitaire (DT/L)',
        digits=(10, 3)
    )

    montant = fields.Float(
        string='Montant (DT)',
        digits=(10, 3),
        compute='_calcul_montant',
        store=True
    )

    odometer_value = fields.Float(
        string='Compteur (km)',
        digits=(10, 0)
    )

    # ── CALCUL ──────────────────────────────────────────────
    @api.depends('quantite', 'prix_unitaire')
    def _calcul_montant(self):
        for u in self:
            u.montant = u.quantite * u.prix_unitaire

    # ── SÉQUENCE ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                        self.env['ir.sequence'].next_by_code(
                            'transport.agilis.utilisation'
                        ) or 'Nouveau'
                )
        return super().create(vals_list)

    # ── CONTRAINTE ──────────────────────────────────────────
    @api.constrains('quantite')
    def _verifier_quantite(self):
        for u in self:
            if u.quantite <= 0:
                raise ValidationError(
                    "La quantité doit être positive !"
                )

    @api.constrains('carte_id', 'montant')
    def _verifier_solde(self):
        for u in self:
            # Solde avant cette utilisation = total_recharge - (total_utilise - montant_actuel)
            solde_avant = (
                    u.carte_id.total_recharge
                    - u.carte_id.total_utilise
                    + u.montant
            )
            if solde_avant < u.montant:
                raise ValidationError(
                    f"Solde insuffisant sur la carte {u.carte_id.name} !\n"
                    f"Solde disponible : {solde_avant:.3f} DT\n"
                    f"Montant requis   : {u.montant:.3f} DT"
                )