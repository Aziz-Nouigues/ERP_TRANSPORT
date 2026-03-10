from odoo import models, fields, api


class WizardRapportConsommation(models.TransientModel):
    _name = 'transport.wizard.rapport'
    _description = 'Assistant Rapport Consommation'

    # ── FILTRES COMMUNS ──────────────────────────────────────
    date_debut = fields.Date(
        string='Date debut',
        default=fields.Date.context_today
    )
    date_fin = fields.Date(
        string='Date fin',
        default=fields.Date.context_today
    )
    station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station (optionnel)'
    )
    atelier_filtre = fields.Char(
        string='Atelier / Magasin (optionnel)'
    )
    agence_filtre = fields.Char(
        string='Agence / Depot (optionnel)'
    )
    seuil_excessif = fields.Float(
        string='Seuil consommation excessive (L/100km)',
        default=35.0,
    )

    # ── TYPE RAPPORT CARBURANT ───────────────────────────────
    type_rapport_carburant = fields.Selection([
        ('recap',        'حوصلة للكمية المستهلكة - Recapitulatif'),
        ('excessif',     'Bus a consommation excessive'),
        ('par_vehicule', 'جدول توزيع السوائل حسب العربة - Distribution par vehicule'),
        ('par_station',  'جدول توزيع السوائل حسب المغازة - Distribution par station'),
        ('rotation',     'تقرير دوران السائقين - Rotation Chauffeurs'),
    ], string='Type de rapport',
       default='recap'
    )

    # ── TYPE RAPPORT LUBRIFIANT ──────────────────────────────
    type_rapport_lubrifiant = fields.Selection([
        ('lubrifiant', 'كشف استهلاك المزيتات - Consommation par vehicule'),
    ], string='Type de rapport',
       default='lubrifiant'
    )

    # garde pour compatibilite anciens rapports
    type_rapport = fields.Selection([
        ('recap',        'Recapitulatif'),
        ('excessif',     'Bus a consommation excessive'),
        ('par_vehicule', 'Distribution par vehicule'),
        ('par_station',  'Distribution par station'),
        ('lubrifiant',   'Rapport Lubrifiants'),
        ('rotation',     'Rotation Chauffeurs'),
    ], default='recap')

    # ── ACTIONS ─────────────────────────────────────────────
    def action_generer_rapport_carburant(self):
        self.ensure_one()
        refs = {
            'recap':        'transport_energy.action_rapport_recap',
            'excessif':     'transport_energy.action_rapport_excessif',
            'par_vehicule': 'transport_energy.action_rapport_par_vehicule',
            'par_station':  'transport_energy.action_rapport_par_station',
            'rotation':     'transport_energy.action_rapport_rotation_chauffeurs',
        }
        return self.env.ref(refs[self.type_rapport_carburant]).report_action(self)

    def action_generer_rapport_lubrifiant(self):
        self.ensure_one()
        return self.env.ref(
            'transport_energy.action_rapport_lubrifiant'
        ).report_action(self)

    def action_generer_rapport(self):
        self.ensure_one()
        refs = {
            'recap':        'transport_energy.action_rapport_recap',
            'excessif':     'transport_energy.action_rapport_excessif',
            'par_vehicule': 'transport_energy.action_rapport_par_vehicule',
            'par_station':  'transport_energy.action_rapport_par_station',
            'lubrifiant':   'transport_energy.action_rapport_lubrifiant',
            'rotation':     'transport_energy.action_rapport_rotation_chauffeurs',
        }
        return self.env.ref(refs[self.type_rapport]).report_action(self)

    # ── DONNÉES RÉCAPITULATIF ────────────────────────────────
    def _get_donnees_recap(self):
        domain = [('state', '=', 'done')]
        if self.date_debut:
            domain.append(('date', '>=', self.date_debut))
        if self.date_fin:
            domain.append(('date', '<=', self.date_fin))
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue
                bus_type = bus.bus_type or 'Non defini'
                if bus_type not in data:
                    data[bus_type] = {
                        'bus_type':     bus_type,
                        'nb_bons':      0,
                        'nb_vehicules': set(),
                        'total_litres': 0,
                        'total_km':     0,
                    }
                data[bus_type]['nb_bons'] += 1
                data[bus_type]['nb_vehicules'].add(bus.id)
                data[bus_type]['total_litres'] += ligne.quantity
                data[bus_type]['total_km'] += ligne.distance_estimated or 0

        result = []
        for key, val in data.items():
            total_km = val['total_km']
            total_l = val['total_litres']
            conso_moy = (total_l / total_km * 100) if total_km > 0 else 0
            result.append({
                'bus_type':     val['bus_type'],
                'nb_bons':      val['nb_bons'],
                'nb_vehicules': len(val['nb_vehicules']),
                'total_litres': round(total_l, 2),
                'total_km':     round(total_km, 2),
                'conso_moy':    round(conso_moy, 2),
            })
        return sorted(result, key=lambda x: x['total_litres'], reverse=True)

    # ── DONNÉES BUS EXCESSIFS ────────────────────────────────
    def _get_donnees_excessif(self):
        domain = [('state', '=', 'done')]
        if self.date_debut:
            domain.append(('date', '>=', self.date_debut))
        if self.date_fin:
            domain.append(('date', '<=', self.date_fin))
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
        domain = [('state', '=', 'done')]
        if self.date_debut:
            domain.append(('date', '>=', self.date_debut))
        if self.date_fin:
            domain.append(('date', '<=', self.date_fin))
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
                    }
                data[key]['nb_sorties'] += 1
                data[key]['total_litres'] += ligne.quantity
                data[key]['total_km'] += ligne.distance_estimated or 0
                if ligne.driver_code:
                    data[key]['chauffeurs'].add(ligne.driver_code)

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
            })
        return sorted(result, key=lambda x: x['total_litres'], reverse=True)

    # ── DONNÉES DISTRIBUTION PAR STATION ─────────────────────
    def _get_donnees_par_station(self):
        domain = [('state', '=', 'done')]
        if self.date_debut:
            domain.append(('date', '>=', self.date_debut))
        if self.date_fin:
            domain.append(('date', '<=', self.date_fin))
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            station = bon.station_id
            key = station.id if station else 0
            if key not in data:
                data[key] = {
                    'station_name':  station.name if station else 'Sans station',
                    'station_code':  station.code if station else '-',
                    'fuel_type':     bon.fuel_type_id.name if bon.fuel_type_id else '-',
                    'nb_bons':       0,
                    'nb_vehicules':  set(),
                    'total_litres':  0,
                    'stock_initial': station.capacity if station else 0,
                    'stock_restant': station.current_stock if station else 0,
                    'bons':          [],
                }
            data[key]['nb_bons'] += 1
            data[key]['total_litres'] += bon.total_quantity
            for ligne in bon.line_ids:
                if ligne.vehicle_id:
                    data[key]['nb_vehicules'].add(ligne.vehicle_id.id)
            data[key]['bons'].append({
                'date':      bon.date,
                'bon_name':  bon.name,
                'type':      dict(bon._fields['voucher_type'].selection).get(bon.voucher_type, '-'),
                'agent':     bon.distributor_name or '-',
                'quantite':  bon.total_quantity,
                'nb_lignes': len(bon.line_ids),
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

    # ── DONNÉES LUBRIFIANTS ──────────────────────────────────
    def _get_donnees_lubrifiant(self):
        domain = [('statut', '=', 'valide')]
        if self.date_debut:
            domain.append(('date', '>=', self.date_debut))
        if self.date_fin:
            domain.append(('date', '<=', self.date_fin))
        if self.atelier_filtre:
            domain.append(('atelier', 'ilike', self.atelier_filtre))

        bons = self.env['transport.bon.lubrifiant'].search(domain)
        data = {}
        for bon in bons:
            bus = bon.vehicule_id
            if not bus:
                continue
            for ligne in bon.ligne_ids:
                key = (bus.id, ligne.type_lubrifiant_id.id)
                if key not in data:
                    data[key] = {
                        'bus_name':        bus.name,
                        'bus_type':        bus.bus_type or '-',
                        'atelier':         bon.atelier or '-',
                        'type_lubrifiant': ligne.type_lubrifiant_id.name if ligne.type_lubrifiant_id else '-',
                        'nb_vidanges':     0,
                        'qte_vidange':     0,
                        'nb_additions':    0,
                        'qte_addition':    0,
                        'total_quantite':  0,
                        'kilometrage':     0,
                    }
                if ligne.type_operation == 'vidange':
                    data[key]['nb_vidanges'] += 1
                    data[key]['qte_vidange'] += ligne.quantite_videe or 0
                else:
                    data[key]['nb_additions'] += 1
                    data[key]['qte_addition'] += ligne.quantite
                data[key]['total_quantite'] += ligne.quantite
                if bon.kilometrage > data[key]['kilometrage']:
                    data[key]['kilometrage'] = bon.kilometrage

        result = []
        for key, val in data.items():
            result.append({
                'bus_name':        val['bus_name'],
                'bus_type':        val['bus_type'],
                'atelier':         val['atelier'],
                'type_lubrifiant': val['type_lubrifiant'],
                'nb_vidanges':     val['nb_vidanges'],
                'qte_vidange':     round(val['qte_vidange'], 2),
                'nb_additions':    val['nb_additions'],
                'qte_addition':    round(val['qte_addition'], 2),
                'total_quantite':  round(val['total_quantite'], 2),
                'kilometrage':     round(val['kilometrage'], 1),
            })
        return sorted(result, key=lambda x: x['bus_name'])

    # ── DONNÉES ROTATION CHAUFFEURS ──────────────────────────
    def _get_donnees_rotation(self):
        domain = [('state', '=', 'done')]
        if self.date_debut:
            domain.append(('date', '>=', self.date_debut))
        if self.date_fin:
            domain.append(('date', '<=', self.date_fin))

        bons = self.env['transport.fuel.voucher'].search(domain)
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue
                agence = bus.transport_agency or '-'
                if self.agence_filtre and self.agence_filtre.lower() not in agence.lower():
                    continue
                key = bus.id
                if key not in data:
                    data[key] = {
                        'bus_name':     bus.name,
                        'bus_type':     bus.bus_type or '-',
                        'agence':       agence,
                        'service_code': ligne.service_code or bus.service_code or '-',
                        'nb_sorties':   0,
                        'total_litres': 0,
                        'chauffeurs':   {},
                    }
                data[key]['nb_sorties'] += 1
                data[key]['total_litres'] += ligne.quantity
                if ligne.driver_code:
                    data[key]['chauffeurs'][ligne.driver_code] = (
                        ligne.driver_name or ligne.driver_code
                    )

        lignes = []
        for key, val in data.items():
            nb_ch = len(val['chauffeurs'])
            liste = ', '.join(
                f"{code}({nom})" if nom != code else code
                for code, nom in sorted(val['chauffeurs'].items())
            )
            lignes.append({
                'bus_name':        val['bus_name'],
                'bus_type':        val['bus_type'],
                'agence':          val['agence'],
                'service_code':    val['service_code'],
                'nb_sorties':      val['nb_sorties'],
                'nb_chauffeurs':   nb_ch,
                'total_litres':    round(val['total_litres'], 2),
                'liste_chauffeurs': liste,
            })

        lignes = sorted(lignes, key=lambda x: x['nb_chauffeurs'], reverse=True)
        return {
            'nb_bus':          len(lignes),
            'nb_plus_5':       len([l for l in lignes if l['nb_chauffeurs'] > 5]),
            'nb_plus_10':      len([l for l in lignes if l['nb_chauffeurs'] > 10]),
            'total_chauffeurs': sum(l['nb_chauffeurs'] for l in lignes),
            'lignes':          lignes,
            'bus_excessifs':   [l for l in lignes if l['nb_chauffeurs'] > 5],
        }