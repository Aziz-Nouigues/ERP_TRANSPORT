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
        ('recap',     'حوصلة للكمية المستهلكة - Récapitulatif'),
        ('excessif',  'Bus à consommation excessive'),
    ], string='Type de rapport',
       required=True,
       default='recap'
    )

    seuil_excessif = fields.Float(
        string='Seuil consommation excessive (L/100km)',
        default=35.0,
        help="Un bus est considéré excessif si sa consommation "
             "dépasse ce seuil"
    )

    # ── ACTIONS ─────────────────────────────────────────────
    def action_generer_rapport(self):
        """Génère le rapport selon le type choisi"""
        self.ensure_one()

        if self.type_rapport == 'recap':
            return self.env.ref(
                'transport_energy.action_rapport_recap'
            ).report_action(self)
        else:
            return self.env.ref(
                'transport_energy.action_rapport_excessif'
            ).report_action(self)

    def _get_donnees_recap(self):
        """Calcule les données pour le rapport récapitulatif"""
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'done'),

        ]
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)

        # Grouper par type de bus
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue

                bus_type = bus.bus_type or 'Non défini'
                service = ligne.service_code or '-'

                key = bus_type
                if key not in data:
                    data[key] = {
                        'bus_type':      bus_type,
                        'nb_bons':       0,
                        'nb_vehicules':  set(),
                        'total_litres':  0,
                        'total_km':      0,
                    }

                data[key]['nb_bons'] += 1
                data[key]['nb_vehicules'].add(bus.id)
                data[key]['total_litres'] += ligne.quantity
                data[key]['total_km'] += ligne.distance_estimated or 0

        # Convertir sets en counts + calculer moyenne
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

    def _get_donnees_excessif(self):
        """Calcule les bus à consommation excessive"""
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'done'),

        ]
        if self.station_id:
            domain.append(('station_id', '=', self.station_id.id))

        bons = self.env['transport.fuel.voucher'].search(domain)

        # Grouper par véhicule
        data = {}
        for bon in bons:
            for ligne in bon.line_ids:
                bus = ligne.vehicle_id
                if not bus:
                    continue

                key = bus.id
                if key not in data:
                    data[key] = {
                        'vehicle':          bus,
                        'bus_name':         bus.name,
                        'bus_type':         bus.bus_type or '-',
                        'conso_theorique':  bus.theoretical_fuel_consumption or 0,
                        'total_litres':     0,
                        'total_km':         0,
                        'nb_sorties':       0,
                    }

                data[key]['total_litres'] += ligne.quantity
                data[key]['total_km'] += ligne.distance_estimated or 0
                data[key]['nb_sorties'] += 1

        # Calculer consommation réelle et filtrer excessifs
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