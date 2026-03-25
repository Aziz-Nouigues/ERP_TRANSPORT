from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Jaugeage(models.Model):
    """Opération de jaugeage des cuves carburant"""
    _name = 'transport.jaugeage'
    _description = 'Jaugeage des cuves'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # ── IDENTIFICATION ───────────────────────────────────────
    name = fields.Char(
        string='N° Jaugeage',
        required=True,
        copy=False,
        readonly=True,
        default='Nouveau',
        translate=False,
    )

    statut = fields.Selection([
        ('brouillon',   'Brouillon'),
        ('confirme',    'Confirmé'),
        ('approuve',    'Approuvé'),
        ('annule',      'Annulé'),
    ], string='Statut', default='brouillon', tracking=True)

    # ── DATE & RESPONSABLE ───────────────────────────────────
    date = fields.Datetime(
        string='Date & Heure',
        required=True,
        default=fields.Datetime.now
    )

    responsable = fields.Char(
        string='Responsable',
        required=True,
        translate=True,
    )

    # ── STATION ─────────────────────────────────────────────
    station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station / Cuve',
        required=True,
        tracking=True
    )

    # ── NIVEAUX ─────────────────────────────────────────────
    stock_theorique = fields.Float(
        string='Stock théorique ERP (L)',
        digits=(10, 2),
        compute='_calcul_stock_theorique',
        store=True
    )

    niveau_mesure = fields.Float(
        string='Niveau mesuré réel (L)',
        required=True,
        digits=(10, 2)
    )

    # ── ÉCART ───────────────────────────────────────────────
    ecart = fields.Float(
        string='Écart (L)',
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

    niveau_alerte = fields.Selection([
        ('normal',      'Normal (< 1%)'),
        ('attention',   'Attention (1-3%)'),
        ('critique',    'Critique (> 3%)'),
    ], string='Niveau alerte',
       compute='_calcul_ecart',
       store=True
    )

    # ── JUSTIFICATION ───────────────────────────────────────
    justification = fields.Text(
        string='Justification de l\'écart',
        translate=False,
    )

    ajustement_stock = fields.Boolean(
        string='Ajuster le stock ?',
        default=False
    )

    notes = fields.Text(string='Notes', translate=False)

    # ── CALCULS ─────────────────────────────────────────────
    @api.depends('station_id')
    def _calcul_stock_theorique(self):
        for jaugeage in self:
            if jaugeage.station_id:
                jaugeage.stock_theorique = (
                    jaugeage.station_id.current_stock
                )
            else:
                jaugeage.stock_theorique = 0

    @api.depends('stock_theorique', 'niveau_mesure')
    def _calcul_ecart(self):
        for jaugeage in self:
            jaugeage.ecart = (
                jaugeage.stock_theorique - jaugeage.niveau_mesure
            )

            if jaugeage.stock_theorique > 0:
                pct = abs(jaugeage.ecart) / jaugeage.stock_theorique * 100
                jaugeage.ecart_pourcentage = round(pct, 2)
            else:
                jaugeage.ecart_pourcentage = 0

            # Niveau d'alerte selon les règles du CDC
            pct = jaugeage.ecart_pourcentage
            if pct < 1:
                jaugeage.niveau_alerte = 'normal'
            elif pct <= 3:
                jaugeage.niveau_alerte = 'attention'
            else:
                jaugeage.niveau_alerte = 'critique'

    # ── WORKFLOW ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code(
                        'transport.jaugeage'
                    ) or 'Nouveau'
                )
        return super().create(vals_list)

    def action_confirmer(self):
        for jaugeage in self:
            if jaugeage.niveau_alerte == 'critique':
                # Alerte automatique si écart > 3%
                jaugeage.message_post(
                    body=f"🔴 ALERTE : Écart critique de "
                         f"{jaugeage.ecart_pourcentage:.2f}% "
                         f"détecté ! Investigation obligatoire.",
                    message_type='notification'
                )
            jaugeage.write({'statut': 'confirme'})

    def action_approuver(self):
        for jaugeage in self:
            if jaugeage.niveau_alerte != 'normal':
                if not jaugeage.justification:
                    raise ValidationError(
                        "Une justification est obligatoire "
                        "pour les écarts supérieurs à 1% !"
                    )
            # Ajuster le stock si demandé
            if jaugeage.ajustement_stock and jaugeage.station_id:
                jaugeage.station_id.write({
                    'current_stock': jaugeage.niveau_mesure
                })
                jaugeage.message_post(
                    body=f"✅ Stock ajusté de "
                         f"{jaugeage.stock_theorique:.2f} L "
                         f"à {jaugeage.niveau_mesure:.2f} L",
                    message_type='notification'
                )
            jaugeage.write({'statut': 'approuve'})

    def action_annuler(self):
        for jaugeage in self:
            if jaugeage.statut == 'approuve':
                raise ValidationError(
                    "Impossible d'annuler un jaugeage approuvé !"
                )
            jaugeage.write({'statut': 'annule'})

    def action_brouillon(self):
        self.write({'statut': 'brouillon'})

    # ── CONTRAINTES ─────────────────────────────────────────
    @api.constrains('niveau_mesure')
    def _verifier_niveau(self):
        for jaugeage in self:
            if jaugeage.niveau_mesure < 0:
                raise ValidationError(
                    "Le niveau mesuré ne peut pas être négatif !"
                )