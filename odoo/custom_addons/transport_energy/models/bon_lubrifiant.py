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

    vehicule_id = fields.Many2one('fleet.vehicle', string='Bus / Vehicule',
                                   required=True, tracking=True)
    code_service = fields.Char(
        string='Code service', related='vehicule_id.service_code',
        store=True, readonly=True
    )
    code_chauffeur = fields.Char(string='Code chauffeur', translate=False)
    nom_chauffeur = fields.Char(string='Nom chauffeur', translate=True)

    kilometrage = fields.Float(string='Kilometrage actuel (km)', digits=(12, 1), required=True)
    dernier_vidange_km = fields.Float(string='Km derniere vidange', digits=(12, 1))
    prochain_vidange_km = fields.Float(
        string='Km prochaine vidange', digits=(12, 1),
        compute='_calcul_prochain_vidange', store=True
    )

    ligne_ids = fields.One2many('transport.bon.lubrifiant.ligne', 'bon_id',
                                 string='Lignes lubrifiants')
    quantite_totale = fields.Float(
        string='Quantite totale', compute='_calcul_totaux',
        store=True, digits=(10, 2)
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

    def _get_or_create_stock(self, atelier, type_lubrifiant_id):
        """FIX : Retrouve ou crée automatiquement le stock magasin.
        Evite le blocage quand le stock n'est pas pre-configure.
        """
        stock = self.env['transport.stock.lubrifiant'].search([
            ('atelier', '=', atelier),
            ('type_lubrifiant_id', '=', type_lubrifiant_id),
        ], limit=1)
        if not stock:
            # Créer automatiquement avec stock = 0
            # _consume_stock() lèvera l'erreur de solde insuffisant si besoin
            type_lub = self.env['transport.energy.type'].browse(type_lubrifiant_id)
            stock = self.env['transport.stock.lubrifiant'].create({
                'atelier': atelier,
                'type_lubrifiant_id': type_lubrifiant_id,
                'agence': self.agence or '',
                'stock_actuel': 0.0,
            })
            self.message_post(
                body=(
                    f"Stock lubrifiant cree automatiquement : "
                    f"{type_lub.name} — Atelier '{atelier}' (stock initial : 0 L). "
                    f"Veuillez configurer le stock initial via Configuration > Stocks Lubrifiants."
                ),
                message_type='notification'
            )
        return stock

    def action_confirmer(self):
        for bon in self:
            if not bon.ligne_ids:
                raise ValidationError("Impossible de confirmer un bon sans lignes.")
            bon.write({'statut': 'confirme'})

    def action_valider(self):
        for bon in self:
            if bon.statut != 'confirme':
                raise ValidationError("Le bon doit etre confirme avant validation.")
            for ligne in bon.ligne_ids:
                # FIX : création automatique du stock si inexistant
                stock = bon._get_or_create_stock(
                    bon.atelier, ligne.type_lubrifiant_id.id
                )
                stock._consume_stock(ligne.quantite)
            bon.write({'statut': 'valide'})

    def action_annuler(self):
        """Annulation uniquement pour les bons non validés."""
        for bon in self:
            if bon.statut == 'valide':
                raise ValidationError(
                    "Impossible d'annuler un bon deja valide. "
                    "Utiliser 'Annuler (directeur)' pour restituer le stock."
                )
            bon.write({'statut': 'annule'})

    def action_annuler_valide(self):
        """FIX : Annulation d'un bon validé avec restitution du stock (directeur)."""
        for bon in self:
            if bon.statut != 'valide':
                raise ValidationError("Ce bon n'est pas dans l'etat 'Valide'.")
            for ligne in bon.ligne_ids:
                stock = self.env['transport.stock.lubrifiant'].search([
                    ('atelier', '=', bon.atelier),
                    ('type_lubrifiant_id', '=', ligne.type_lubrifiant_id.id),
                ], limit=1)
                if stock:
                    stock._add_stock(ligne.quantite)
                    bon.message_post(
                        body=(
                            f"Annulation validee — Stock restitue : "
                            f"+{ligne.quantite:.2f} L de {ligne.type_lubrifiant_id.name} "
                            f"dans l'atelier '{bon.atelier}'"
                        ),
                        message_type='notification'
                    )
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
        'transport.energy.type', string='Type de lubrifiant',
        required=True, domain="[('category','=','lubrifiant')]"
    )
    unite = fields.Char(
        string='Unite', related='type_lubrifiant_id.unite',
        store=True, readonly=True,
    )
    quantite_videe = fields.Float(
        string='Quantite videe', digits=(8, 2),
        help='Uniquement pour les vidanges'
    )

    # Saisie en unités de conditionnement (optionnel)
    conditionnement = fields.Char(
        string='Conditionnement',
        related='type_lubrifiant_id.conditionnement',
        store=True, readonly=True
    )
    volume_conditionnement = fields.Float(
        string='Vol. par unite (L)',
        related='type_lubrifiant_id.volume_conditionnement',
        store=True, readonly=True
    )
    nb_unites = fields.Float(
        string='Nb unites',
        digits=(8, 2),
        default=0.0,
        help="Saisir le nombre de bidons/futs utilises. "
             "La quantite en litres sera calculee automatiquement. "
             "Laisser a 0 pour saisir directement en litres."
    )
    quantite = fields.Float(
        string='Quantite (L)',
        required=True, digits=(8, 2),
        help="Quantite en litres. Calculee automatiquement si nb_unites > 0."
    )

    @api.onchange('nb_unites', 'volume_conditionnement')
    def _onchange_nb_unites(self):
        """Calcule automatiquement la quantite en litres depuis le nombre d unites."""
        if self.nb_unites > 0 and self.volume_conditionnement > 0:
            self.quantite = round(self.nb_unites * self.volume_conditionnement, 2)

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
