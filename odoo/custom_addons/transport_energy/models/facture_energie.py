from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class FactureEnergie(models.Model):
    """Facture STEG ou SONEDE par site"""
    _name = 'transport.facture.energie'
    _description = 'Facture Énergie (STEG/SONEDE)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_reception desc, id desc'

    # ── IDENTIFICATION ───────────────────────────────────────
    name = fields.Char(
        string='N° Facture',
        required=True,
        tracking=True
    )

    type_facture = fields.Selection([
        ('steg',   '⚡ STEG (Électricité)'),
        ('sonede', '💧 SONEDE (Eau)'),
    ], string='Type', required=True, tracking=True)

    statut = fields.Selection([
        ('saisie',  'Saisie'),
        ('payee',   'Payée'),
        ('annulee', 'Annulée'),
    ], string='Statut', default='saisie', tracking=True)

    # ── SITE ────────────────────────────────────────────────
    site = fields.Char(
        string='Site / Agence',
        required=True
    )

    adresse = fields.Char(string='Adresse du compteur')

    numero_compteur = fields.Char(
        string='N° Compteur',
        required=True
    )

    # ── PÉRIODE ─────────────────────────────────────────────
    date_debut_periode = fields.Date(
        string='Début période',
        required=True
    )

    date_fin_periode = fields.Date(
        string='Fin période',
        required=True
    )

    date_reception = fields.Date(
        string='Date réception',
        required=True,
        default=fields.Date.today
    )

    # ── CONSOMMATION ────────────────────────────────────────
    quantite_consommee = fields.Float(
        string='Quantité consommée',
        required=True,
        digits=(10, 2)
    )

    unite_mesure = fields.Char(
        string='Unité',
        compute='_calcul_unite',
        store=True
    )

    montant = fields.Float(
        string='Montant (TND)',
        required=True,
        digits=(10, 3)
    )

    # ── COMPARAISON N-1 (saisie manuelle) ───────────────────
    consommation_n1 = fields.Float(
        string='Consommation N-1',
        digits=(10, 2)
    )

    montant_n1 = fields.Float(
        string='Montant N-1 (TND)',
        digits=(10, 3)
    )

    ecart_consommation = fields.Float(
        string='Écart consommation',
        digits=(10, 2),
        compute='_calcul_ecart',
        store=True
    )

    ecart_pourcentage = fields.Float(
        string='Écart (%)',
        digits=(5, 2),
        compute='_calcul_ecart',
        store=True
    )

    notes = fields.Text(string='Notes')

    # ── CALCULS ─────────────────────────────────────────────
    @api.depends('type_facture')
    def _calcul_unite(self):
        for facture in self:
            if facture.type_facture == 'steg':
                facture.unite_mesure = 'kWh'
            elif facture.type_facture == 'sonede':
                facture.unite_mesure = 'm³'
            else:
                facture.unite_mesure = ''

    @api.depends('quantite_consommee', 'consommation_n1')
    def _calcul_ecart(self):
        for facture in self:
            facture.ecart_consommation = (
                facture.quantite_consommee - facture.consommation_n1
            )
            if facture.consommation_n1 > 0:
                facture.ecart_pourcentage = (
                    facture.ecart_consommation /
                    facture.consommation_n1 * 100
                )
            else:
                facture.ecart_pourcentage = 0

    # ── BOUTON : Chercher N-1 automatiquement ───────────────
    def action_chercher_n1(self):
        """Cherche et remplit automatiquement les données N-1"""
        for facture in self:
            if not (facture.site and facture.type_facture and
                    facture.date_debut_periode):
                continue

            date_n1 = facture.date_debut_periode - relativedelta(years=1)

            facture_n1 = self.search([
                ('site', '=', facture.site),
                ('type_facture', '=', facture.type_facture),
                ('date_debut_periode', '>=', date_n1.replace(day=1)),
                ('date_debut_periode', '<=', date_n1.replace(day=28)),
                ('id', '!=', facture.id),
            ], limit=1)

            if facture_n1:
                facture.write({
                    'consommation_n1': facture_n1.quantite_consommee,
                    'montant_n1': facture_n1.montant,
                })

    @api.constrains('date_debut_periode', 'date_fin_periode')
    def _verifier_dates(self):
        for facture in self:
            if (facture.date_debut_periode and
                    facture.date_fin_periode and
                    facture.date_fin_periode < facture.date_debut_periode):
                raise ValidationError(
                    "La date de fin doit être après la date de début !"
                )

    # ── WORKFLOW ────────────────────────────────────────────
    def action_payer(self):
        self.write({'statut': 'payee'})

    def action_annuler(self):
        self.write({'statut': 'annulee'})