from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TransportFuelVoucher(models.Model):
    """En-tête du Bon de Ravitaillement Carburant (BGI/BGE)"""
    _name = 'transport.fuel.voucher'
    _description = 'Bon de Gasoil Interne/Externe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # ── IDENTIFICATION ───────────────────────────────────────
    name = fields.Char(
        string='N° du Bon',
        required=True,
        copy=False,
        readonly=True,
        default='Nouveau'
    )

    voucher_type = fields.Selection([
        ('internal', 'Interne (BGI)'),
        ('external', 'Externe (BGE)'),
    ], string='Type', required=True,
       default='internal', tracking=True)

    state = fields.Selection([
        ('draft',     'Brouillon'),
        ('confirmed', 'Confirmé'),
        ('done',      'Validé'),
        ('cancelled', 'Annulé'),
    ], string='Statut', default='draft', tracking=True)

    # ── DATE ────────────────────────────────────────────────
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today
    )

    time_start = fields.Float(
        string='Heure début (بداية العمل)',
        default=7.0
    )

    time_end = fields.Float(
        string='Heure fin (نهاية العمل)',
        default=17.0
    )

    # ── STATION ─────────────────────────────────────────────
    station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station / Pompe',
        required=True,
        tracking=True
    )

    # FIX ODOO 19 : domain en STRING et non en liste Python
    fuel_type_id = fields.Many2one(
        'transport.energy.type',
        string='Type de carburant',
        required=True,
        domain="[('category', '=', 'fuel')]"
    )

    # ── AGENT DISTRIBUTEUR ──────────────────────────────────
    distributor_code = fields.Char(
        string='Code agent distributeur (العون الموزع)'
    )

    distributor_name = fields.Char(
        string='Nom agent distributeur'
    )

    agency_main_code = fields.Char(
        string='Code principal (التدرج الرئيسي)'
    )

    agency_sub_code = fields.Char(
        string='Code secondaire (الفرعي)'
    )

    # ── COMPTEUR POMPE ───────────────────────────────────────
    pump_counter_start = fields.Float(
        string='Compteur pompe début (بداية عداد المضخة)',
        digits=(12, 0)
    )

    pump_counter_end = fields.Float(
        string='Compteur pompe fin (نهاية عداد المضخة)',
        digits=(12, 0)
    )

    # ── QUANTITÉS ───────────────────────────────────────────
    total_quantity = fields.Float(
        string='Quantité totale distribuée (L)',
        compute='_compute_totals',
        store=True,
        digits=(10, 2)
    )

    remaining_stock = fields.Float(
        string='Stock restant (الكمية المتبقية)',
        digits=(10, 2)
    )

    # ── VALIDATION ──────────────────────────────────────────
    is_validated = fields.Boolean(
        string='Validé (مصادق)',
        default=False
    )

    notes = fields.Text(string='Notes / Observations')

    # ── LIGNES ──────────────────────────────────────────────
    line_ids = fields.One2many(
        'transport.fuel.voucher.line',
        'voucher_id',
        string='Lignes de ravitaillement'
    )

    # ── CALCULS ─────────────────────────────────────────────
    @api.depends('line_ids.quantity')
    def _compute_totals(self):
        for rec in self:
            rec.total_quantity = sum(
                line.quantity for line in rec.line_ids
            )

    @api.onchange('station_id')
    def _onchange_station(self):
        """Remplir automatiquement les infos de la station"""
        if self.station_id:
            self.fuel_type_id = self.station_id.fuel_type_id
            self.pump_counter_start = self.station_id.pump_counter_current
            self.remaining_stock = self.station_id.current_stock

    # ── ACTIONS WORKFLOW ────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                if vals.get('voucher_type') == 'external':
                    seq = 'transport.fuel.voucher.external'
                else:
                    seq = 'transport.fuel.voucher.internal'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq) or 'Nouveau'
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(
                    "Impossible de confirmer un bon sans lignes de ravitaillement !"
                )
            rec.write({'state': 'confirmed'})

    def action_validate(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise ValidationError(
                    "Le bon doit être confirmé avant validation !"
                )
            if rec.station_id:
                new_stock = rec.station_id.current_stock - rec.total_quantity
                if new_stock < 0:
                    raise ValidationError(
                        f"Stock insuffisant ! Stock actuel : "
                        f"{rec.station_id.current_stock} L, "
                        f"Quantité demandée : {rec.total_quantity} L"
                    )
                rec.station_id.write({
                    'current_stock': new_stock,
                    'pump_counter_current': rec.pump_counter_end
                })
            rec.write({
                'state': 'done',
                'is_validated': True
            })

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise ValidationError(
                    "Impossible d'annuler un bon déjà validé !"
                )
            rec.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ── CONTRAINTES ─────────────────────────────────────────
    @api.constrains('pump_counter_start', 'pump_counter_end')
    def _check_pump_counters(self):
        for rec in self:
            if (rec.pump_counter_end > 0 and
                    rec.pump_counter_start > 0 and
                    rec.pump_counter_end < rec.pump_counter_start):
                raise ValidationError(
                    "Le compteur fin ne peut pas être inférieur au compteur début !"
                )


class TransportFuelVoucherLine(models.Model):
    """Ligne de ravitaillement — 1 ligne = 1 bus"""
    _name = 'transport.fuel.voucher.line'
    _description = 'Ligne de bon de carburant'
    _order = 'time asc'

    voucher_id = fields.Many2one(
        'transport.fuel.voucher',
        string='Bon de carburant',
        required=True,
        ondelete='cascade'
    )

    # ── HEURE ───────────────────────────────────────────────
    time = fields.Float(
        string='Heure (التوقيت)',
        default=8.0
    )

    # ── VÉHICULE ────────────────────────────────────────────
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Bus (العربة)',
        required=True
    )

    service_code = fields.Char(
        string='Code service (المصلحة)',
    )

    # ── CHAUFFEUR ───────────────────────────────────────────
    driver_code = fields.Char(
        string='Code chauffeur (المعرف)'
    )

    driver_name = fields.Char(
        string='Nom chauffeur (إسم السائق)'
    )

    # ── COMPTEUR BUS ────────────────────────────────────────
    odometer_value = fields.Float(
        string='Compteur bus (عداد العربة)',
        digits=(12, 0)
    )

    odometer_status = fields.Selection(
        related='vehicle_id.odometer_status',
        string='État compteur',
        readonly=True
    )

    distance_estimated = fields.Float(
        string='Distance estimée (km)',
        compute='_compute_distance',
        store=True,
        digits=(10, 1)
    )

    # ── CARBURANT ───────────────────────────────────────────
    quantity = fields.Float(
        string='Quantité distribuée (L)',
        required=True,
        digits=(10, 2)
    )

    # ── CALCUL DISTANCE ESTIMÉE ─────────────────────────────
    @api.depends('quantity', 'vehicle_id', 'odometer_status')
    def _compute_distance(self):
        for line in self:
            if (line.odometer_status == 'broken' and
                    line.vehicle_id and
                    line.vehicle_id.theoretical_fuel_consumption > 0):
                conso = line.vehicle_id.theoretical_fuel_consumption
                line.distance_estimated = (line.quantity * 100) / conso
            else:
                line.distance_estimated = 0.0

    # ── CONTRAINTES ─────────────────────────────────────────
    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(
                    "La quantité doit être supérieure à 0 !"
                )