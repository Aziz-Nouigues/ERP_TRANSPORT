from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TransportFuelStation(models.Model):
    _name = 'transport.fuel.station'
    _description = 'Station de pompage carburant'
    _order = 'name'

    # ── IDENTIFICATION ──────────────────────────────────────
    name = fields.Char(
        string='Nom de la station',
        required=True
    )

    code = fields.Char(
        string='Code station',
        required=True
    )

    pump_number = fields.Char(
        string='N° Pompe (الفرعي)',
        help='Numéro de la pompe dans la station'
    )

    # ── TYPE ────────────────────────────────────────────────
    station_type = fields.Selection([
        ('internal', 'Interne (société)'),
        ('external', 'Externe'),
    ], string='Type', required=True, default='internal')

    # ── LOCALISATION ────────────────────────────────────────
    agency_id = fields.Many2one(
        'res.partner',
        string='Agence / Dépôt (لمقازة)',
        help='Agence ou dépôt où se trouve cette station'
    )

    address = fields.Char(string='Adresse')

    # ── COMPTEUR POMPE ──────────────────────────────────────
    pump_counter_start = fields.Float(
        string='Compteur pompe début (بداية عداد المضخة)',
        digits=(12, 0),
        default=0
    )

    pump_counter_current = fields.Float(
        string='Compteur pompe actuel',
        digits=(12, 0),
        default=0
    )

    # ── STOCK ───────────────────────────────────────────────
    fuel_type_id = fields.Many2one(
        'transport.energy.type',
        string='Type de carburant',
        domain="[('category', '=', 'fuel')]"
    )

    capacity = fields.Float(
        string='Capacité cuve (Litres)',
        digits=(10, 2)
    )

    current_stock = fields.Float(
        string='Stock actuel (Litres)',
        digits=(10, 2)
    )

    min_stock_alert = fields.Float(
        string='Seuil alerte stock (Litres)',
        digits=(10, 2),
        default=500
    )

    # ── ÉTAT ────────────────────────────────────────────────
    active = fields.Boolean(
        string='Active',
        default=True
    )

    notes = fields.Text(string='Notes')

    # ── CALCUL ──────────────────────────────────────────────
    stock_percentage = fields.Float(
        string='Niveau stock (%)',
        compute='_compute_stock_percentage',
        store=True
    )

    stock_status = fields.Selection([
        ('ok',      '✅ Normal'),
        ('low',     '⚠️ Bas'),
        ('critical','🔴 Critique'),
    ], string='État stock',
       compute='_compute_stock_percentage',
       store=True
    )

    @api.depends('current_stock', 'capacity', 'min_stock_alert')
    def _compute_stock_percentage(self):
        for rec in self:
            if rec.capacity > 0:
                pct = (rec.current_stock / rec.capacity) * 100
                rec.stock_percentage = round(pct, 1)
            else:
                rec.stock_percentage = 0

            # Statut selon le seuil d'alerte
            if rec.current_stock <= 0:
                rec.stock_status = 'critical'
            elif rec.current_stock <= rec.min_stock_alert:
                rec.stock_status = 'low'
            else:
                rec.stock_status = 'ok'

    @api.constrains('current_stock', 'capacity')
    def _check_stock(self):
        for rec in self:
            if rec.current_stock < 0:
                raise ValidationError(
                    "Le stock ne peut pas être négatif !"
                )
            if rec.capacity > 0 and rec.current_stock > rec.capacity:
                raise ValidationError(
                    "Le stock actuel dépasse la capacité de la cuve !"
                )