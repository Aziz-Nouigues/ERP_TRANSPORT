from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BonLubrifiant(models.Model):
    """Bon de Ravitaillement Lubrifiant"""
    _name = 'transport.bon.lubrifiant'
    _description = 'Bon de Ravitaillement Lubrifiant'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # ── IDENTIFICATION ───────────────────────────────────────
    name = fields.Char(
        string='N° du Bon',
        required=True,
        copy=False,
        readonly=True,
        default='Nouveau',
        translate=False,
    )

    statut = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme',  'Confirmé'),
        ('valide',    'Validé'),
        ('annule',    'Annulé'),
    ], string='Statut', default='brouillon', tracking=True)

    # ── DATE & LIEU ──────────────────────────────────────────
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today
    )

    atelier = fields.Char(
        string='Atelier / Magasin',
        required=True,
        translate=True,
        help='Atelier ou magasin qui effectue l\'opération'
    )

    agence = fields.Char(
        string='Agence / Dépôt',
        translate=True,
    )

    # ── VÉHICULE ────────────────────────────────────────────
    vehicule_id = fields.Many2one(
        'fleet.vehicle',
        string='Bus / Véhicule',
        required=True,
        tracking=True
    )

    code_service = fields.Char(
        string='Code service (المصلحة)',
        related='vehicule_id.service_code',
        store=True,
        readonly=True
    )

    # ── CHAUFFEUR ───────────────────────────────────────────
    code_chauffeur = fields.Char(
        string='Code chauffeur',
        translate=False,
    )

    nom_chauffeur = fields.Char(
        string='Nom chauffeur',
        translate=True,
    )

    # ── KILOMÉTRAGE ─────────────────────────────────────────
    kilometrage = fields.Float(
        string='Kilométrage actuel (km)',
        digits=(12, 1),
        required=True
    )

    dernier_vidange_km = fields.Float(
        string='Km dernière vidange',
        digits=(12, 1)
    )

    prochain_vidange_km = fields.Float(
        string='Km prochaine vidange',
        digits=(12, 1),
        compute='_calcul_prochain_vidange',
        store=True
    )

    # ── LIGNES ──────────────────────────────────────────────
    ligne_ids = fields.One2many(
        'transport.bon.lubrifiant.ligne',
        'bon_id',
        string='Lignes lubrifiants'
    )

    # ── TOTAUX ──────────────────────────────────────────────
    quantite_totale = fields.Float(
        string='Quantité totale (L)',
        compute='_calcul_totaux',
        store=True,
        digits=(10, 2)
    )

    notes = fields.Text(string='Observations', translate=False)

    # ── CALCULS ─────────────────────────────────────────────
    @api.depends('ligne_ids.quantite')
    def _calcul_totaux(self):
        for bon in self:
            bon.quantite_totale = sum(
                ligne.quantite for ligne in bon.ligne_ids
            )

    @api.depends('dernier_vidange_km', 'vehicule_id')
    def _calcul_prochain_vidange(self):
        """Calcule le km de la prochaine vidange"""
        for bon in self:
            if (bon.dernier_vidange_km > 0 and
                    bon.vehicule_id and
                    bon.vehicule_id.theoretical_oil_consumption > 0):
                # Intervalle vidange = 1000 / conso théorique huile
                intervalle = 1000 / bon.vehicule_id.theoretical_oil_consumption
                bon.prochain_vidange_km = bon.dernier_vidange_km + intervalle
            else:
                bon.prochain_vidange_km = 0

    # ── WORKFLOW ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code(
                        'transport.bon.lubrifiant'
                    ) or 'Nouveau'
                )
        return super().create(vals_list)

    def action_confirmer(self):
        for bon in self:
            if not bon.ligne_ids:
                raise ValidationError(
                    "Impossible de confirmer un bon sans lignes !"
                )
            bon.write({'statut': 'confirme'})

    def action_valider(self):
        for bon in self:
            if bon.statut != 'confirme':
                raise ValidationError(
                    "Le bon doit être confirmé avant validation !"
                )
            bon.write({'statut': 'valide'})

    def action_annuler(self):
        for bon in self:
            if bon.statut == 'valide':
                raise ValidationError(
                    "Impossible d'annuler un bon déjà validé !"
                )
            bon.write({'statut': 'annule'})

    def action_brouillon(self):
        self.write({'statut': 'brouillon'})


class BonLubrifiantLigne(models.Model):
    """Ligne du Bon de Lubrifiant — 1 ligne = 1 produit"""
    _name = 'transport.bon.lubrifiant.ligne'
    _description = 'Ligne de bon lubrifiant'

    bon_id = fields.Many2one(
        'transport.bon.lubrifiant',
        string='Bon lubrifiant',
        required=True,
        ondelete='cascade'
    )

    # ── TYPE OPÉRATION ───────────────────────────────────────
    type_operation = fields.Selection([
        ('vidange',  'Vidange (remplacement complet)'),
        ('addition', '➕ Addition (appoint)'),
    ], string='Type opération',
       required=True,
       default='addition'
    )

    # ── LUBRIFIANT ──────────────────────────────────────────
    type_lubrifiant_id = fields.Many2one(
        'transport.energy.type',
        string='Type de lubrifiant',
        required=True,
        domain="[('category', '=', 'lubrifiant')]"
    )

    # ── QUANTITÉS ───────────────────────────────────────────
    quantite_videe = fields.Float(
        string='Quantité vidée (L)',
        digits=(8, 2),
        help='Uniquement pour les vidanges'
    )

    quantite = fields.Float(
        string='Quantité ajoutée (L)',
        required=True,
        digits=(8, 2)
    )

    # ── CONTRAINTES ─────────────────────────────────────────
    @api.constrains('quantite')
    def _verifier_quantite(self):
        for ligne in self:
            if ligne.quantite <= 0:
                raise ValidationError(
                    "La quantité ajoutée doit être supérieure à 0 !"
                )

    @api.constrains('type_operation', 'quantite_videe')
    def _verifier_vidange(self):
        for ligne in self:
            if (ligne.type_operation == 'vidange' and
                    ligne.quantite_videe <= 0):
                raise ValidationError(
                    "Pour une vidange, la quantité vidée est obligatoire !"
                )