from odoo import models, fields, api


class WizardRapportConsommation(models.TransientModel):
    """Wizard pour générer les rapports de consommation"""
    _name = 'transport.wizard.rapport'
    _description = 'Assistant Rapport Consommation'

    # ── FILTRES ─────────────────────────────────────────────
    date_debut = fields.Date(
        string='Date début',
        required=True,
        default=fields.Date.context_today
    )

    date_fin = fields.Date(
        string='Date fin',
        required=True,
        default=fields.Date.context_today
    )

    station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station (optionnel)'
    )

    type_rapport = fields.Selection([
        ('recap',        'حوصلة للكمية المستهلكة - Récapitulatif'),
        ('excessif',     'Bus à consommation excessive'),
        ('par_vehicule', 'جدول توزيع السوائل حسب العربة - Distribution par véhicule'),
        ('par_station',  'جدول توزيع السوائل حسب المغّازة - Distribution par station'),
    ], string='Type de rapport',
       required=True,
       default='recap'
    )

    seuil_excessif = fields.Float(
        string='Seuil consommation excessive (L/100km)',
        default=35.0,
    )

    # ── ACTIONS ─────────────────────────────────────────────
    def action_generer_rapport(self):
        self.ensure_one()
        if self.type_rapport == 'recap':
            return self.env.ref(
                'transport_energy.action_rapport_recap'
            ).report_action(self)
        elif self.type_rapport == 'excessif':
            return self.env.ref(
                'transport_energy.action_rapport_excessif'
            ).report_action(self)
        elif self.type_rapport == 'par_vehicule':
            return self.env.ref(
                'transport_energy.action_rapport_par_vehicule'
            ).report_action(self)
        elif self.type_rapport == 'par_station':
            return self.env.ref(
                'transport_energy.action_rapport_par_station'
            ).report_action(self)

    # ── DONNÉES RÉCAPITULATIF ────────────────────────────────
    def _get_donnees_recap(self):
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'done'),
        ]
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue
                bus_type = bus.bus_type or 'Non défini'
                key = bus_type
                if key not in data:
                    data[key] = {
                        'bus_type':     bus_type,
                        'nb_bons':      0,
                        'nb_vehicules': set(),
                        'total_litres': 0,
                        'total_km':     0,
                    }
                data[key]['nb_bons'] += 1
                data[key]['nb_vehicules'].add(bus.id)
                data[key]['total_litres'] += ligne.quantity
                data[key]['total_km'] += ligne.distance_estimated or 0

        result = []
        for key, val in data.items():
            nb_v = len(val['nb_vehicules'])
            total_km = val['total_km']
            total_l = val['total_litres']
            conso_moy = (total_l / total_km * 100) if total_km > 0 else 0
            result.append({
                'bus_type':     val['bus_type'],
                'nb_bons':      val['nb_bons'],
                'nb_vehicules': nb_v,
                'total_litres': round(total_l, 2),
                'total_km':     round(total_km, 2),
                'conso_moy':    round(conso_moy, 2),
            })
        return sorted(result, key=lambda x: x['total_litres'], reverse=True)

    # ── DONNÉES BUS EXCESSIFS ────────────────────────────────
    def _get_donnees_excessif(self):
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'done'),
        ]
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue
                key = bus.id
                if key not in data:
                    data[key] = {
                        'vehicle':         bus,
                        'bus_name':        bus.name,
                        'bus_type':        bus.bus_type or '-',
                        'conso_theorique': bus.theoretical_fuel_consumption or 0,
                        'total_litres':    0,
                        'total_km':        0,
                        'nb_sorties':      0,
                    }
                data[key]['total_litres'] += ligne.quantity
                data[key]['total_km'] += ligne.distance_estimated or 0
                data[key]['nb_sorties'] += 1

        result = []
        for key, val in data.items():
            total_km = val['total_km']
            total_l = val['total_litres']
            conso_reelle = (total_l / total_km * 100) if total_km > 0 else 0
            if conso_reelle > self.seuil_excessif:
                ecart = conso_reelle - val['conso_theorique']
                result.append({
                    'bus_name':        val['bus_name'],
                    'bus_type':        val['bus_type'],
                    'nb_sorties':      val['nb_sorties'],
                    'total_litres':    round(total_l, 2),
                    'total_km':        round(total_km, 2),
                    'conso_theorique': round(val['conso_theorique'], 2),
                    'conso_reelle':    round(conso_reelle, 2),
                    'ecart':           round(ecart, 2),
                })
        return sorted(result, key=lambda x: x['conso_reelle'], reverse=True)

    # ── DONNÉES DISTRIBUTION PAR VÉHICULE ────────────────────
    def _get_donnees_par_vehicule(self):
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'done'),
        ]
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue
                key = bus.id
                if key not in data:
                    data[key] = {
                        'bus_name':        bus.name,
                        'bus_type':        bus.bus_type or '-',
                        'code_interne':    bus.license_plate or '-',
                        'service_code':    ligne.service_code or '-',
                        'conso_theorique': bus.theoretical_fuel_consumption or 0,
                        'nb_sorties':      0,
                        'chauffeurs':      set(),
                        'total_litres':    0,
                        'total_km':        0,
                        'details':         [],
                    }
                data[key]['nb_sorties'] += 1
                data[key]['total_litres'] += ligne.quantity
                data[key]['total_km'] += ligne.distance_estimated or 0
                if ligne.driver_code:
                    data[key]['chauffeurs'].add(ligne.driver_code)
                data[key]['details'].append({
                    'date':          bon.date,
                    'bon_name':      bon.name,
                    'station':       bon.station_id.name if bon.station_id else '-',
                    'driver_code':   ligne.driver_code or '-',
                    'driver_name':   ligne.driver_name or '-',
                    'odometer':      ligne.odometer_value,
                    'quantity':      ligne.quantity,
                    'distance_est':  ligne.distance_estimated or 0,
                })

        result = []
        for key, val in data.items():
            total_km = val['total_km']
            total_l = val['total_litres']
            conso_reelle = (total_l / total_km * 100) if total_km > 0 else 0
            conso_theorique = val['conso_theorique']
            ecart = conso_reelle - conso_theorique if conso_theorique > 0 else 0
            result.append({
                'bus_name':        val['bus_name'],
                'bus_type':        val['bus_type'],
                'code_interne':    val['code_interne'],
                'service_code':    val['service_code'],
                'nb_sorties':      val['nb_sorties'],
                'nb_chauffeurs':   len(val['chauffeurs']),
                'total_litres':    round(total_l, 2),
                'total_km':        round(total_km, 2),
                'conso_theorique': round(conso_theorique, 2),
                'conso_reelle':    round(conso_reelle, 2),
                'ecart':           round(ecart, 2),
                'details':         sorted(val['details'], key=lambda x: x['date']),
            })
        return sorted(result, key=lambda x: x['total_litres'], reverse=True)

    # ── DONNÉES DISTRIBUTION PAR STATION ─────────────────────
    def _get_donnees_par_station(self):
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'done'),
        ]
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            station = bon.station_id
            key = station.id if station else 0
            if key not in data:
                data[key] = {
                    'station_name':   station.name if station else 'Sans station',
                    'station_code':   station.code if station else '-',
                    'fuel_type':      bon.fuel_type_id.name if bon.fuel_type_id else '-',
                    'nb_bons':        0,
                    'nb_vehicules':   set(),
                    'total_litres':   0,
                    'stock_initial':  station.capacity if station else 0,
                    'stock_restant':  station.current_stock if station else 0,
                    'bons':           [],
                }
            data[key]['nb_bons'] += 1
            data[key]['total_litres'] += bon.total_quantity
            for ligne in bon.line_ids:
                if ligne.vehicle_id:
                    data[key]['nb_vehicules'].add(ligne.vehicle_id.id)
            data[key]['bons'].append({
                'date':       bon.date,
                'bon_name':   bon.name,
                'type':       dict(bon._fields['voucher_type'].selection).get(bon.voucher_type, '-'),
                'agent':      bon.distributor_name or '-',
                'quantite':   bon.total_quantity,
                'nb_lignes':  len(bon.line_ids),
            })

        result = []
        for key, val in data.items():
            result.append({
                'station_name':  val['station_name'],
                'station_code':  val['station_code'],
                'fuel_type':     val['fuel_type'],
                'nb_bons':       val['nb_bons'],
                'nb_vehicules':  len(val['nb_vehicules']),
                'total_litres':  round(val['total_litres'], 2),
                'stock_initial': val['stock_initial'],
                'stock_restant': val['stock_restant'],
                'bons':          sorted(val['bons'], key=lambda x: x['date']),
            })
        return sorted(result, key=lambda x: x['total_litres'], reverse=True)
