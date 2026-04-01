# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BonLubrifiant(models.Model):
    _name = 'transport.bon.lubrifiant'
    _description = 'Bon de ravitaillement lubrifiant'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N du Bon', required=True, copy=False,
        readonly=True, default='Nouveau', translate=False
    )
    statut = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme',  'Confirme'),
        ('valide',    'Valide'),
        ('annule',    'Annule'),
    ], string='Statut', default='brouillon', tracking=True)

    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    atelier = fields.Char(string='Atelier / Magasin', required=True, translate=True)
    agence = fields.Char(string='Agence / Depot', translate=True)

    vehicule_id = fields.Many2one('fleet.vehicle', string='Bus / Vehicule', required=True, tracking=True)
    code_service = fields.Char(
        string='Code service',
        related='vehicule_id.service_code',
        store=True, readonly=True
    )
    code_chauffeur = fields.Char(string='Code chauffeur', translate=False)
    nom_chauffeur = fields.Char(string='Nom chauffeur', translate=True)

    kilometrage = fields.Float(string='Kilometrage actuel (km)', digits=(12, 1), required=True)
    dernier_vidange_km = fields.Float(string='Km derniere vidange', digits=(12, 1))
    prochain_vidange_km = fields.Float(
        string='Km prochaine vidange',
        digits=(12, 1),
        compute='_calcul_prochain_vidange',
        store=True
    )

    ligne_ids = fields.One2many('transport.bon.lubrifiant.ligne', 'bon_id', string='Lignes lubrifiants')
    quantite_totale = fields.Float(
        string='Quantite totale',
        compute='_calcul_totaux',
        store=True,
        digits=(10, 2)
    )
    notes = fields.Text(string='Observations', translate=False)

    @api.depends('ligne_ids.quantite')
    def _calcul_totaux(self):
        for bon in self:
            bon.quantite_totale = sum(l.quantite for l in bon.ligne_ids)

    @api.depends('dernier_vidange_km', 'vehicule_id')
    def _calcul_prochain_vidange(self):
        for bon in self:
            if (bon.dernier_vidange_km > 0
                    and bon.vehicule_id
                    and bon.vehicule_id.theoretical_oil_consumption > 0):
                intervalle = 1000 / bon.vehicule_id.theoretical_oil_consumption
                bon.prochain_vidange_km = bon.dernier_vidange_km + intervalle
            else:
                bon.prochain_vidange_km = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'transport.bon.lubrifiant'
                ) or 'Nouveau'
        return super().create(vals_list)

    def action_confirmer(self):
        for bon in self:
            if not bon.ligne_ids:
                raise ValidationError("Impossible de confirmer un bon sans lignes.")
            bon.write({'statut': 'confirme'})

    def action_valider(self):
        for bon in self:
            if bon.statut != 'confirme':
                raise ValidationError("Le bon doit etre confirme avant validation.")
            # Debiter le stock magasin pour chaque ligne
            for ligne in bon.ligne_ids:
                stock = bon.env['transport.stock.lubrifiant'].search([
                    ('atelier', '=', bon.atelier),
                    ('type_lubrifiant_id', '=', ligne.type_lubrifiant_id.id),
                ], limit=1)
                if stock:
                    stock._consume_stock(ligne.quantite)
                else:
                    raise ValidationError(
                        f"Aucun stock magasin trouve pour '{ligne.type_lubrifiant_id.name}' "
                        f"dans l'atelier '{bon.atelier}'. "
                        f"Verifier la configuration du stock lubrifiant."
                    )
            bon.write({'statut': 'valide'})

    def action_annuler(self):
        for bon in self:
            if bon.statut == 'valide':
                raise ValidationError("Impossible d'annuler un bon deja valide.")
            bon.write({'statut': 'annule'})

    def action_brouillon(self):
        self.write({'statut': 'brouillon'})


class BonLubrifiantLigne(models.Model):
    _name = 'transport.bon.lubrifiant.ligne'
    _description = 'Ligne de bon lubrifiant'

    bon_id = fields.Many2one(
        'transport.bon.lubrifiant', string='Bon lubrifiant',
        required=True, ondelete='cascade'
    )
    type_operation = fields.Selection([
        ('vidange',  'Vidange (remplacement complet)'),
        ('addition', 'Addition (appoint)'),
    ], string='Type operation', required=True, default='addition')
    type_lubrifiant_id = fields.Many2one(
        'transport.energy.type',
        string='Type de lubrifiant',
        required=True,
        domain="[('category','=','lubrifiant')]"
    )
    unite = fields.Char(
        string='Unite',
        related='type_lubrifiant_id.unite',
        store=True,
        readonly=True,
    )
    quantite_videe = fields.Float(
        string='Quantite videe',
        digits=(8, 2),
        help='Uniquement pour les vidanges'
    )
    quantite = fields.Float(string='Quantite ajoutee', required=True, digits=(8, 2))

    @api.constrains('quantite')
    def _verifier_quantite(self):
        for ligne in self:
            if ligne.quantite <= 0:
                raise ValidationError("La quantite ajoutee doit etre superieure a 0.")

    @api.constrains('type_operation', 'quantite_videe')
    def _verifier_vidange(self):
        for ligne in self:
            if ligne.type_operation == 'vidange' and ligne.quantite_videe <= 0:
                raise ValidationError(
                    "Pour une vidange, saisir la quantite d'huile videe."
                )