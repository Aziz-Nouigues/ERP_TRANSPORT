# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Jaugeage(models.Model):
    """Jaugeage physique d'une cuve carburant.
    Compare le stock theorique ERP avec le niveau physiquement mesure.
    FIX : stock_theorique capture en snapshot au moment de action_confirmer()
    pour eviter le decalage si des BGI sont saisis entre la creation et l'approbation.
    """
    _name = 'transport.jaugeage'
    _description = 'Jaugeage des cuves carburant'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N Jaugeage', required=True, copy=False,
        readonly=True, default='Nouveau', translate=False
    )
    statut = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme',  'Confirme'),
        ('approuve',  'Approuve'),
        ('annule',    'Annule'),
    ], string='Statut', default='brouillon', tracking=True)

    date = fields.Datetime(string='Date et heure', required=True, default=fields.Datetime.now)
    responsable = fields.Char(string='Responsable', required=True, translate=True)

    cuve_id = fields.Many2one('transport.fuel.cuve', string='Cuve',
                               required=True, tracking=True)
    station_id = fields.Many2one(
        'transport.fuel.station', string='Station',
        related='cuve_id.station_id', store=True, readonly=True
    )
    fuel_type_id = fields.Many2one(
        'transport.energy.type', string='Type carburant',
        related='cuve_id.fuel_type_id', store=True, readonly=True
    )

    # FIX : stock_theorique est maintenant un champ simple (Float) non calculé.
    # Il est rempli comme snapshot au moment de action_confirmer().
    # Ceci évite le décalage si des BGI sont saisis entre création et approbation.
    stock_theorique = fields.Float(
        string='Stock theorique ERP (L)', digits=(10, 2), readonly=True,
        help="Snapshot du stock ERP au moment de la confirmation du jaugeage."
    )
    niveau_mesure = fields.Float(
        string='Niveau mesure reel (L)', required=True, digits=(10, 2)
    )
    ecart = fields.Float(
        string='Ecart (L)', digits=(10, 2),
        compute='_calcul_ecart', store=True
    )
    ecart_pourcentage = fields.Float(
        string='Ecart (%)', digits=(5, 2),
        compute='_calcul_ecart', store=True
    )
    niveau_alerte = fields.Selection([
        ('normal',    'Normal (< 1%)'),
        ('attention', 'Attention (1 a 3%)'),
        ('critique',  'Critique (> 3%)'),
    ], string='Niveau alerte', compute='_calcul_ecart', store=True)

    ajustement_stock = fields.Boolean(
        string='Ajuster le stock ?', default=False,
        help="Si coche, le stock de la cuve sera mis a jour avec le niveau mesure a l'approbation."
    )
    justification = fields.Text(string='Justification de l ecart', translate=False)
    notes = fields.Text(string='Notes', translate=False)

    @api.depends('stock_theorique', 'niveau_mesure')
    def _calcul_ecart(self):
        for jaugeage in self:
            jaugeage.ecart = jaugeage.stock_theorique - jaugeage.niveau_mesure
            if jaugeage.stock_theorique > 0:
                pct = abs(jaugeage.ecart) / jaugeage.stock_theorique * 100
                jaugeage.ecart_pourcentage = round(pct, 2)
            else:
                jaugeage.ecart_pourcentage = 0.0
            pct = jaugeage.ecart_pourcentage
            if pct < 1:
                jaugeage.niveau_alerte = 'normal'
            elif pct <= 3:
                jaugeage.niveau_alerte = 'attention'
            else:
                jaugeage.niveau_alerte = 'critique'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'transport.jaugeage'
                ) or 'Nouveau'
            # Pré-remplir stock_theorique à la création (valeur indicative)
            if not vals.get('stock_theorique') and vals.get('cuve_id'):
                cuve = self.env['transport.fuel.cuve'].browse(vals['cuve_id'])
                vals['stock_theorique'] = cuve.current_stock
        return super().create(vals_list)

    def action_confirmer(self):
        """FIX : Snapshot du stock théorique au moment de la confirmation."""
        for jaugeage in self:
            # Capturer le stock réel au moment exact de la confirmation
            stock_snapshot = jaugeage.cuve_id.current_stock if jaugeage.cuve_id else 0.0
            if jaugeage.niveau_alerte == 'critique':
                jaugeage.message_post(
                    body=(
                        f"ALERTE CRITIQUE : ecart de "
                        f"{jaugeage.ecart_pourcentage:.2f}% detecte sur "
                        f"{jaugeage.cuve_id.display_name}. "
                        f"Investigation obligatoire."
                    ),
                    message_type='notification'
                )
            jaugeage.write({
                'statut': 'confirme',
                'stock_theorique': stock_snapshot,  # Snapshot fixe
            })

    def action_approuver(self):
        for jaugeage in self:
            if jaugeage.statut != 'confirme':
                raise ValidationError("Le jaugeage doit etre confirme avant approbation.")
            if jaugeage.niveau_alerte != 'normal' and not jaugeage.justification:
                raise ValidationError(
                    "Une justification est obligatoire pour les ecarts superieurs a 1%."
                )
            if jaugeage.ajustement_stock and jaugeage.cuve_id:
                # Vérifier que le niveau mesuré ne dépasse pas la capacité
                if (jaugeage.cuve_id.capacity > 0
                        and jaugeage.niveau_mesure > jaugeage.cuve_id.capacity):
                    raise ValidationError(
                        f"Le niveau mesure ({jaugeage.niveau_mesure:.0f} L) "
                        f"depasse la capacite de la cuve ({jaugeage.cuve_id.capacity:.0f} L)."
                    )
                ancien = jaugeage.cuve_id.current_stock
                jaugeage.cuve_id.write({'current_stock': jaugeage.niveau_mesure})
                jaugeage.message_post(
                    body=(
                        f"Stock ajuste ({jaugeage.cuve_id.display_name}) : "
                        f"{ancien:.2f} L → {jaugeage.niveau_mesure:.2f} L"
                    ),
                    message_type='notification'
                )
            jaugeage.write({'statut': 'approuve'})

    def action_annuler(self):
        for jaugeage in self:
            if jaugeage.statut == 'approuve':
                raise ValidationError("Impossible d'annuler un jaugeage approuve.")
            jaugeage.write({'statut': 'annule'})

    def action_brouillon(self):
        self.write({'statut': 'brouillon'})

    @api.constrains('niveau_mesure')
    def _verifier_niveau(self):
        for jaugeage in self:
            if jaugeage.niveau_mesure < 0:
                raise ValidationError("Le niveau mesure ne peut pas etre negatif.")
