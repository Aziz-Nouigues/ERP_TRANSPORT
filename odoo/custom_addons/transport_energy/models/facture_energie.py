# -*- coding: utf-8 -*-
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class FactureEnergie(models.Model):
    """Facture STEG (electricite) ou SONEDE (eau) par site.
    Le bouton 'Chercher N-1' retrouve automatiquement la facture
    du meme site, meme type, meme mois de l'annee precedente.
    """
    _name = 'transport.facture.energie'
    _description = 'Facture energie STEG / SONEDE'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_reception desc, id desc'

    name = fields.Char(string='N Facture', required=True, tracking=True)
    type_facture = fields.Selection([
        ('steg',   'STEG (Electricite)'),
        ('sonede', 'SONEDE (Eau)'),
    ], string='Type', required=True, tracking=True)
    statut = fields.Selection([
        ('saisie',  'Saisie'),
        ('payee',   'Payee'),
        ('annulee', 'Annulee'),
    ], string='Statut', default='saisie', tracking=True)

    site = fields.Char(string='Site / Agence', required=True, translate=False)
    adresse = fields.Char(string='Adresse du compteur')
    numero_compteur = fields.Char(string='N Compteur', required=True)

    date_debut_periode = fields.Date(string='Debut periode', required=True)
    date_fin_periode = fields.Date(string='Fin periode', required=True)
    date_reception = fields.Date(string='Date reception', required=True, default=fields.Date.today)

    quantite_consommee = fields.Float(string='Quantite consommee', required=True, digits=(10, 2))
    unite_mesure = fields.Char(string='Unite', compute='_calcul_unite', store=True)
    montant = fields.Float(string='Montant (TND)', required=True, digits=(10, 3))

    # Comparaison N-1 (peut etre remplie manuellement ou via bouton auto)
    consommation_n1 = fields.Float(string='Consommation N-1', digits=(10, 2))
    montant_n1 = fields.Float(string='Montant N-1 (TND)', digits=(10, 3))
    ecart_consommation = fields.Float(
        string='Ecart consommation',
        digits=(10, 2),
        compute='_calcul_ecart',
        store=True
    )
    ecart_pourcentage = fields.Float(
        string='Ecart (%)',
        digits=(5, 2),
        compute='_calcul_ecart',
        store=True
    )
    notes = fields.Text(string='Notes', translate=False)

    # Lien BOC bureau d'ordre (optionnel)
    boc_arrivee_id = fields.Many2one(
        'boc.courrier.arrivee',
        string='Courrier BOC associe',
        domain=[('type_courrier_id.name', 'ilike', 'facture')],
    )
    boc_reference = fields.Char(
        string='Ref BOC',
        related='boc_arrivee_id.name',
        store=True, readonly=True
    )

    @api.depends('type_facture')
    def _calcul_unite(self):
        for f in self:
            f.unite_mesure = 'kWh' if f.type_facture == 'steg' else 'm3' if f.type_facture == 'sonede' else ''

    @api.depends('quantite_consommee', 'consommation_n1')
    def _calcul_ecart(self):
        for f in self:
            f.ecart_consommation = f.quantite_consommee - f.consommation_n1
            if f.consommation_n1 > 0:
                f.ecart_pourcentage = round(f.ecart_consommation / f.consommation_n1 * 100, 2)
            else:
                f.ecart_pourcentage = 0.0

    def action_chercher_n1(self):
        """Recherche automatique de la facture N-1 pour ce site."""
        for facture in self:
            if not (facture.site and facture.type_facture and facture.date_debut_periode):
                continue
            date_n1 = facture.date_debut_periode - relativedelta(years=1)
            facture_n1 = self.search([
                ('site', '=', facture.site),
                ('type_facture', '=', facture.type_facture),
                ('date_debut_periode', '>=', date_n1.replace(day=1)),
                ('date_debut_periode', '<=', date_n1.replace(day=28)),
                ('id', '!=', facture.id),
                ('statut', '!=', 'annulee'),
            ], limit=1)
            if facture_n1:
                facture.write({
                    'consommation_n1': facture_n1.quantite_consommee,
                    'montant_n1': facture_n1.montant,
                })
            else:
                raise ValidationError(
                    f"Aucune facture N-1 trouvee pour le site '{facture.site}' "
                    f"({facture.type_facture.upper()}) en {date_n1.strftime('%B %Y')}."
                )

    def action_payer(self):
        self.write({'statut': 'payee'})

    def action_annuler(self):
        self.write({'statut': 'annulee'})

    @api.constrains('date_debut_periode', 'date_fin_periode')
    def _verifier_dates(self):
        for f in self:
            if f.date_debut_periode and f.date_fin_periode:
                if f.date_fin_periode < f.date_debut_periode:
                    raise ValidationError("La date de fin doit etre apres la date de debut.")
