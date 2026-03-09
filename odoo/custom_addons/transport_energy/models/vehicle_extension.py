from odoo import models, fields, api


class FleetVehicleTransport(models.Model):
    """Extension du modèle fleet.vehicle pour le transport"""
    _inherit = 'fleet.vehicle'   # ← on ÉTEND, on ne recrée pas !

    # ── TYPE DE BUS ─────────────────────────────────────────
    bus_type = fields.Selection([
        ('standard',    'حافلة عادية نقل حضري'),
        ('double',      'حافلة مزدوجة نقل حضري'),
        ('ac_53',       'حافلة مكيفة 53'),
        ('ac_regional', 'حافلة مكيفة نقل جهوي'),
        ('service_car', 'سيارة خدمات'),
        ('other',       'Autre'),
    ], string='Type de bus', required=False)

    activity_type = fields.Selection([
        ('urban',        'Urbain (حضري)'),
        ('interurban',   'Interurbain'),
        ('regional',     'Régional (جهوي)'),
        ('admin',        'Administratif'),
    ], string='Activité')

    # ── IDENTIFICATION INTERNE ───────────────────────────────
    internal_code = fields.Char(
        string='Code interne (العربة)',
        help='Grand numéro interne ex: 15362773'
    )

    service_code = fields.Char(
        string='Code service (المصلحة)',
        help='ex: 1250, 4050, 4300...'
    )

    # ── AGENCE ──────────────────────────────────────────────
    transport_agency = fields.Char(
        string='Agence / Dépôt (لمقازة)',
        help='ex: 2 = Dépôt Tunis'
    )

    agency_code = fields.Char(
        string='Code agence',
        help='Code numérique de l\'agence'
    )

    # ── CONSOMMATION THÉORIQUE ───────────────────────────────
    theoretical_fuel_consumption = fields.Float(
        string='Conso. théorique carburant (L/100km)',
        digits=(6, 2),
        default=0.0,
        help='Norme de consommation carburant pour ce type de bus'
    )

    theoretical_oil_consumption = fields.Float(
        string='Conso. théorique lubrifiant (L/1000km)',
        digits=(6, 2),
        default=0.0,
        help='Norme de consommation huile pour ce type de bus'
    )

    # ── COMPTEUR KILOMÉTRIQUE ────────────────────────────────
    odometer_status = fields.Selection([
        ('ok',       '✅ Fonctionnel'),
        ('replaced', '🔄 Remplacé / Réparé'),
        ('broken',   '❌ En panne'),
    ], string='État du compteur',
       default='ok',
       required=True
    )

    odometer_replacement_date = fields.Date(
        string='Date remplacement compteur'
    )

    odometer_old_value = fields.Float(
        string='Ancienne valeur compteur (km)',
        digits=(12, 1),
        help='Valeur avant remplacement'
    )

    # ── CAPACITÉ RÉSERVOIR ───────────────────────────────────
    fuel_tank_capacity = fields.Float(
        string='Capacité réservoir (Litres)',
        digits=(8, 2),
        default=0.0
    )

    fuel_station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station de rattachement',
        help='Station interne habituelle de ce bus'
    )

    # ── CALCUL : DISTANCE ESTIMÉE ────────────────────────────
    @api.model
    def estimate_distance(self, fuel_quantity):
        """
        Calcule la distance estimée quand le compteur est en panne.
        Formule : Distance (km) = Quantité (L) x 100 / Conso théorique (L/100km)
        """
        if self.theoretical_fuel_consumption > 0:
            return (fuel_quantity * 100) / self.theoretical_fuel_consumption
        return 0.0