# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TransportFuelStation(models.Model):
    """Station de pompage — lieu physique.
    Contient une ou plusieurs cuves (transport.fuel.cuve).
    N'a plus de stock propre : le stock est sur chaque cuve.
    """
    _name = 'transport.fuel.station'
    _description = 'Station de pompage carburant'
    _order = 'name'

    name = fields.Char(string='Nom de la station', required=True, translate=True)
    code = fields.Char(string='Code station', required=True)
    agency_id = fields.Many2one('res.partner', string='Agence / Depot')
    address = fields.Char(string='Adresse', translate=True)
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes', translate=False)

    cuve_ids = fields.One2many(
        'transport.fuel.cuve', 'station_id',
        string='Cuves'
    )
    nb_cuves = fields.Integer(
        string='Nb cuves',
        compute='_compute_nb_cuves',
        store=True
    )

    @api.depends('cuve_ids')
    def _compute_nb_cuves(self):
        for rec in self:
            rec.nb_cuves = len(rec.cuve_ids)


class TransportFuelCuve(models.Model):
    """Cuve individuelle dans une station.
    Chaque cuve a son propre type de carburant, son stock,
    sa capacite et son compteur de pompe.
    C'est la cuve — et non la station — qui est referencee
    par supply.order, fuel.voucher et jaugeage.
    """
    _name = 'transport.fuel.cuve'
    _description = 'Cuve carburant (station de pompage)'
    _order = 'station_id, fuel_type_id'
    _rec_name = 'display_name'

    display_name = fields.Char(
        string='Designation',
        compute='_compute_display_name',
        store=True
    )
    station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station',
        required=True,
        ondelete='cascade'
    )
    fuel_type_id = fields.Many2one(
        'transport.energy.type',
        string='Type de carburant',
        required=True,
        domain="[('category','=','fuel')]"
    )
    pump_number = fields.Char(string='N Pompe')
    capacity = fields.Float(string='Capacite (L)', digits=(10, 2))
    current_stock = fields.Float(
        string='Stock actuel (L)',
        digits=(10, 2),
        readonly=True,
        help="Mis a jour par les receptions citerne et les jaugeages approuves uniquement."
    )
    min_stock_alert = fields.Float(
        string='Seuil alerte (L)',
        digits=(10, 2),
        default=500
    )
    pump_counter_start = fields.Float(
        string='Compteur initial',
        digits=(12, 0),
        default=0
    )
    pump_counter_current = fields.Float(
        string='Compteur actuel',
        digits=(12, 0),
        default=0
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes', translate=False)

    stock_percentage = fields.Float(
        string='Niveau (%)',
        compute='_compute_stock_status',
        store=True
    )
    stock_status = fields.Selection([
        ('ok',       'Normal'),
        ('low',      'Bas'),
        ('critical', 'Critique'),
    ], string='Etat stock', compute='_compute_stock_status', store=True)

    @api.depends('station_id', 'fuel_type_id', 'pump_number')
    def _compute_display_name(self):
        for rec in self:
            station = rec.station_id.name or ''
            fuel = rec.fuel_type_id.name or ''
            pump = f' — Pompe {rec.pump_number}' if rec.pump_number else ''
            rec.display_name = f"{station} / {fuel}{pump}"

    @api.depends('current_stock', 'capacity', 'min_stock_alert')
    def _compute_stock_status(self):
        for rec in self:
            if rec.capacity > 0:
                rec.stock_percentage = round(rec.current_stock / rec.capacity * 100, 1)
            else:
                rec.stock_percentage = 0.0
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
                raise ValidationError("Le stock ne peut pas etre negatif.")
            if rec.capacity > 0 and rec.current_stock > rec.capacity:
                raise ValidationError("Le stock depasse la capacite de la cuve.")

    @api.constrains('station_id', 'fuel_type_id')
    def _check_unique_fuel_per_station(self):
        for rec in self:
            duplicate = self.search([
                ('station_id', '=', rec.station_id.id),
                ('fuel_type_id', '=', rec.fuel_type_id.id),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    f"La station '{rec.station_id.name}' a deja une cuve "
                    f"'{rec.fuel_type_id.name}'. "
                    f"Une seule cuve par type de carburant par station."
                )

    def _add_stock(self, qty):
        """Credite le stock (appele par supply.order a la validation)."""
        self.ensure_one()
        new = self.current_stock + qty
        if self.capacity > 0 and new > self.capacity:
            raise ValidationError(
                f"Reception impossible : stock apres reception ({new:.0f} L) "
                f"depasse la capacite ({self.capacity:.0f} L)."
            )
        self.write({'current_stock': new})

    def _consume_stock(self, qty):
        """Debite le stock (appele par fuel.voucher a la validation)."""
        self.ensure_one()
        new = self.current_stock - qty
        if new < 0:
            raise ValidationError(
                f"Stock insuffisant ({self.fuel_type_id.name}) : "
                f"disponible {self.current_stock:.0f} L, "
                f"demande {qty:.0f} L."
            )
        self.write({'current_stock': new})
