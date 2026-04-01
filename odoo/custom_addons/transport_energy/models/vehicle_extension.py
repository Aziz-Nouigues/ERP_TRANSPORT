# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FleetVehicleTransport(models.Model):
    _inherit = 'fleet.vehicle'

    bus_type = fields.Selection([
        ('standard',    'Autobus standard urbain'),
        ('double',      'Autobus articule urbain'),
        ('ac_53',       'Autobus climatise 53 places'),
        ('ac_regional', 'Autobus climatise regional'),
        ('service_car', 'Voiture de service'),
        ('other',       'Autre'),
    ], string='Type de bus')

    activity_type = fields.Selection([
        ('urban',      'Urbain'),
        ('interurban', 'Interurbain'),
        ('regional',   'Regional'),
        ('admin',      'Administratif'),
    ], string='Activite')

    internal_code = fields.Char(
        string='Code interne',
        translate=False,
        help='Grand numero interne ex: 15362773'
    )
    service_code = fields.Char(
        string='Code service',
        translate=False,
        help='ex: 1250, 4050'
    )
    transport_agency = fields.Char(string='Agence / Depot', translate=False)
    agency_code = fields.Char(string='Code agence', translate=False)

    theoretical_fuel_consumption = fields.Float(
        string='Conso. theorique carburant (L/100km)',
        digits=(6, 2),
        default=0.0
    )
    theoretical_oil_consumption = fields.Float(
        string='Conso. theorique lubrifiant (L/1000km)',
        digits=(6, 2),
        default=0.0
    )
    fuel_tank_capacity = fields.Float(
        string='Capacite reservoir (L)',
        digits=(8, 2),
        default=0.0
    )
    fuel_station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station de rattachement'
    )

    odometer_status = fields.Selection([
        ('ok',       'Fonctionnel'),
        ('replaced', 'Remplace / Repare'),
        ('broken',   'En panne'),
    ], string='Etat du compteur', default='ok', required=True)
    odometer_replacement_date = fields.Date(string='Date remplacement compteur')
    odometer_old_value = fields.Float(
        string='Ancienne valeur compteur (km)',
        digits=(12, 1)
    )

    def estimate_distance_from_fuel(self, fuel_quantity):
        """Distance estimee quand compteur en panne.
        Distance (km) = quantite (L) * 100 / conso_theorique (L/100km)
        """
        self.ensure_one()
        if self.theoretical_fuel_consumption > 0:
            return round((fuel_quantity * 100) / self.theoretical_fuel_consumption, 1)
        return 0.0
