import io
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class WizardRapportConsommation(models.TransientModel):
    _name = 'transport.wizard.rapport'
    _description = 'Assistant Rapport Consommation'

    # ── FILTRES COMMUNS ──────────────────────────────────────
    date_debut = fields.Date(string='Date debut', default=fields.Date.context_today)
    date_fin = fields.Date(string='Date fin', default=fields.Date.context_today)
    station_id = fields.Many2one('transport.fuel.station', string='Station (optionnel)')
    atelier_filtre = fields.Char(string='Atelier / Magasin (optionnel)')
    agence_filtre = fields.Char(string='Agence / Depot (optionnel)')
    seuil_excessif = fields.Float(string='Seuil consommation excessive (L/100km)', default=35.0)

    # ── TYPE RAPPORT CARBURANT ───────────────────────────────
    type_rapport_carburant = fields.Selection([
        ('recap',        'حوصلة للكمية المستهلكة - Recapitulatif'),
        ('excessif',     'Bus a consommation excessive'),
        ('par_vehicule', 'جدول توزيع السوائل حسب العربة - Distribution par vehicule'),
        ('par_station',  'جدول توزيع السوائل حسب المغازة - Distribution par station'),
        ('rotation',     'تقرير دوران السائقين - Rotation Chauffeurs'),
    ], string='Type de rapport', default='recap')

    # ── TYPE RAPPORT LUBRIFIANT ──────────────────────────────
    type_rapport_lubrifiant = fields.Selection([
        ('lubrifiant', 'كشف استهلاك المزيتات - Consommation par vehicule'),
    ], string='Type de rapport', default='lubrifiant')

    type_rapport = fields.Selection([
        ('recap', 'Recapitulatif'),
        ('excessif', 'Bus a consommation excessive'),
        ('par_vehicule', 'Distribution par vehicule'),
        ('par_station', 'Distribution par station'),
        ('lubrifiant', 'Rapport Lubrifiants'),
        ('rotation', 'Rotation Chauffeurs'),
    ], default='recap')

    # ── HELPER XLSX ──────────────────────────────────────────
    def _make_xlsx_response(self, filename, callback):
        """Cree un fichier Excel et retourne l'action de telechargement"""
        if not xlsxwriter:
            raise UserError("Le module xlsxwriter n'est pas installe !")
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formats communs
        fmt_title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#1a5276', 'font_color': 'white'})
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#2e86c1', 'font_color': 'white', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        fmt_data = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        fmt_data_left = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
        fmt_total = workbook.add_format({'bold': True, 'bg_color': '#d5e8d4', 'border': 1, 'align': 'center'})
        fmt_red = workbook.add_format({'border': 1, 'align': 'center', 'font_color': 'red', 'bold': True})
        fmt_green = workbook.add_format({'border': 1, 'align': 'center', 'font_color': 'green', 'bold': True})
        fmt_orange = workbook.add_format({'border': 1, 'align': 'center', 'font_color': '#e67e22', 'bold': True})

        formats = {
            'title': fmt_title,
            'header': fmt_header,
            'data': fmt_data,
            'data_left': fmt_data_left,
            'total': fmt_total,
            'red': fmt_red,
            'green': fmt_green,
            'orange': fmt_orange,
        }

        callback(workbook, formats)
        workbook.close()
        output.seek(0)
        xlsx_data = base64.b64encode(output.read()).decode()

        # Sauvegarder dans attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ── ACTIONS PDF ─────────────────────────────────────────
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
        return self.env.ref('transport_energy.action_rapport_lubrifiant').report_action(self)

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

    # ── EXPORT EXCEL CARBURANT ───────────────────────────────
    def action_export_excel_carburant(self):
        self.ensure_one()
        typ = self.type_rapport_carburant
        if typ == 'recap':
            return self._export_recap()
        elif typ == 'excessif':
            return self._export_excessif()
        elif typ == 'par_vehicule':
            return self._export_par_vehicule()
        elif typ == 'par_station':
            return self._export_par_station()
        elif typ == 'rotation':
            return self._export_rotation()

    # ── EXPORT EXCEL LUBRIFIANT ──────────────────────────────
    def action_export_excel_lubrifiant(self):
        self.ensure_one()
        return self._export_lubrifiant()

    # ── EXPORT RECAPITULATIF ─────────────────────────────────
    def _export_recap(self):
        def build(workbook, f):
            ws = workbook.add_worksheet('Recapitulatif')
            ws.set_column(0, 0, 30)
            ws.set_column(1, 5, 18)
            ws.merge_range('A1:F1', 'Recapitulatif Consommation Carburant', f['title'])
            ws.merge_range('A2:F2', f'Du {self.date_debut} au {self.date_fin}', f['data'])
            headers = ['Type de Bus', 'Nb Bons', 'Nb Vehicules', 'Total Litres (L)', 'Total KM', 'Conso Moyenne (L/100)']
            for col, h in enumerate(headers):
                ws.write(3, col, h, f['header'])
            lignes = self._get_donnees_recap()
            for row, l in enumerate(lignes, 4):
                ws.write(row, 0, l['bus_type'], f['data_left'])
                ws.write(row, 1, l['nb_bons'], f['data'])
                ws.write(row, 2, l['nb_vehicules'], f['data'])
                ws.write(row, 3, l['total_litres'], f['data'])
                ws.write(row, 4, l['total_km'], f['data'])
                ws.write(row, 5, l['conso_moy'], f['data'])
            r = len(lignes) + 4
            ws.write(r, 0, 'TOTAL', f['total'])
            ws.write(r, 3, sum(l['total_litres'] for l in lignes), f['total'])
            ws.write(r, 4, sum(l['total_km'] for l in lignes), f['total'])
        return self._make_xlsx_response(f'Recapitulatif_{self.date_debut}_{self.date_fin}.xlsx', build)

    # ── EXPORT BUS EXCESSIFS ─────────────────────────────────
    def _export_excessif(self):
        def build(workbook, f):
            ws = workbook.add_worksheet('Bus Excessifs')
            ws.set_column(0, 0, 30)
            ws.set_column(1, 7, 18)
            ws.merge_range('A1:H1', 'Bus a Consommation Excessive', f['title'])
            ws.merge_range('A2:H2', f'Du {self.date_debut} au {self.date_fin} | Seuil: {self.seuil_excessif} L/100km', f['data'])
            headers = ['Bus', 'Type', 'Nb Sorties', 'Total Litres', 'Total KM', 'Conso Theorique', 'Conso Reelle', 'Ecart']
            for col, h in enumerate(headers):
                ws.write(3, col, h, f['header'])
            lignes = self._get_donnees_excessif()
            for row, l in enumerate(lignes, 4):
                ws.write(row, 0, l['bus_name'], f['data_left'])
                ws.write(row, 1, l['bus_type'], f['data'])
                ws.write(row, 2, l['nb_sorties'], f['data'])
                ws.write(row, 3, l['total_litres'], f['data'])
                ws.write(row, 4, l['total_km'], f['data'])
                ws.write(row, 5, l['conso_theorique'], f['data'])
                ws.write(row, 6, l['conso_reelle'], f['red'])
                ws.write(row, 7, l['ecart'], f['red'])
        return self._make_xlsx_response(f'BusExcessifs_{self.date_debut}_{self.date_fin}.xlsx', build)

    # ── EXPORT DISTRIBUTION PAR VEHICULE ────────────────────
    def _export_par_vehicule(self):
        def build(workbook, f):
            ws = workbook.add_worksheet('Distribution Vehicule')
            ws.set_column(0, 0, 30)
            ws.set_column(1, 10, 18)
            ws.merge_range('A1:K1', 'Distribution Carburant par Vehicule', f['title'])
            ws.merge_range('A2:K2', f'Du {self.date_debut} au {self.date_fin}', f['data'])
            headers = ['Bus', 'Type', 'Code Interne', 'Service', 'Nb Sorties', 'Nb Chauffeurs', 'Total Litres', 'Total KM', 'Conso Theorique', 'Conso Reelle', 'Ecart']
            for col, h in enumerate(headers):
                ws.write(3, col, h, f['header'])
            lignes = self._get_donnees_par_vehicule()
            for row, l in enumerate(lignes, 4):
                ws.write(row, 0, l['bus_name'], f['data_left'])
                ws.write(row, 1, l['bus_type'], f['data'])
                ws.write(row, 2, l['code_interne'], f['data'])
                ws.write(row, 3, l['service_code'], f['data'])
                ws.write(row, 4, l['nb_sorties'], f['data'])
                ws.write(row, 5, l['nb_chauffeurs'], f['data'])
                ws.write(row, 6, l['total_litres'], f['data'])
                ws.write(row, 7, l['total_km'], f['data'])
                ws.write(row, 8, l['conso_theorique'], f['data'])
                ws.write(row, 9, l['conso_reelle'], f['data'])
                ecart_fmt = f['red'] if l['ecart'] > 5 else f['green'] if l['ecart'] < 0 else f['data']
                ws.write(row, 10, l['ecart'], ecart_fmt)
            r = len(lignes) + 4
            ws.write(r, 0, 'TOTAL', f['total'])
            ws.write(r, 6, round(sum(l['total_litres'] for l in lignes), 2), f['total'])
        return self._make_xlsx_response(f'DistributionVehicule_{self.date_debut}_{self.date_fin}.xlsx', build)

    # ── EXPORT DISTRIBUTION PAR STATION ─────────────────────
    def _export_par_station(self):
        def build(workbook, f):
            ws = workbook.add_worksheet('Distribution Station')
            ws.set_column(0, 0, 25)
            ws.set_column(1, 7, 18)
            ws.merge_range('A1:H1', 'Distribution Carburant par Station', f['title'])
            ws.merge_range('A2:H2', f'Du {self.date_debut} au {self.date_fin}', f['data'])
            headers = ['Station', 'Code', 'Type Carburant', 'Nb Bons', 'Nb Vehicules', 'Total Litres', 'Stock Initial', 'Stock Restant']
            for col, h in enumerate(headers):
                ws.write(3, col, h, f['header'])
            stations = self._get_donnees_par_station()
            row = 4
            for s in stations:
                ws.write(row, 0, s['station_name'], f['data_left'])
                ws.write(row, 1, s['station_code'], f['data'])
                ws.write(row, 2, s['fuel_type'], f['data'])
                ws.write(row, 3, s['nb_bons'], f['data'])
                ws.write(row, 4, s['nb_vehicules'], f['data'])
                ws.write(row, 5, s['total_litres'], f['data'])
                ws.write(row, 6, s['stock_initial'], f['data'])
                ws.write(row, 7, s['stock_restant'], f['data'])
                row += 1
                # Detail bons
                ws2_name = s['station_name'][:25]
                ws2 = workbook.add_worksheet(f'Detail_{ws2_name}')
                ws2.set_column(0, 5, 18)
                detail_headers = ['Date', 'Bon', 'Type', 'Agent', 'Nb Vehicules', 'Quantite (L)']
                for col, h in enumerate(detail_headers):
                    ws2.write(0, col, h, f['header'])
                for r2, bon in enumerate(s['bons'], 1):
                    ws2.write(r2, 0, str(bon['date']), f['data'])
                    ws2.write(r2, 1, bon['bon_name'], f['data'])
                    ws2.write(r2, 2, bon['type'], f['data'])
                    ws2.write(r2, 3, bon['agent'], f['data'])
                    ws2.write(r2, 4, bon['nb_lignes'], f['data'])
                    ws2.write(r2, 5, bon['quantite'], f['data'])
        return self._make_xlsx_response(f'DistributionStation_{self.date_debut}_{self.date_fin}.xlsx', build)

    # ── EXPORT ROTATION CHAUFFEURS ───────────────────────────
    def _export_rotation(self):
        def build(workbook, f):
            ws = workbook.add_worksheet('Rotation Chauffeurs')
            ws.set_column(0, 0, 30)
            ws.set_column(1, 6, 18)
            ws.set_column(7, 7, 50)
            ws.merge_range('A1:H1', 'Rapport Rotation des Chauffeurs', f['title'])
            ws.merge_range('A2:H2', f'Du {self.date_debut} au {self.date_fin}', f['data'])
            headers = ['Bus', 'Type', 'Agence', 'Service', 'Nb Sorties', 'Nb Chauffeurs', 'Total Litres', 'Liste Chauffeurs']
            for col, h in enumerate(headers):
                ws.write(3, col, h, f['header'])
            donnees = self._get_donnees_rotation()
            for row, l in enumerate(donnees['lignes'], 4):
                ws.write(row, 0, l['bus_name'], f['data_left'])
                ws.write(row, 1, l['bus_type'], f['data'])
                ws.write(row, 2, l['agence'], f['data'])
                ws.write(row, 3, l['service_code'], f['data'])
                ws.write(row, 4, l['nb_sorties'], f['data'])
                nb_fmt = f['red'] if l['nb_chauffeurs'] > 10 else f['orange'] if l['nb_chauffeurs'] > 5 else f['green']
                ws.write(row, 5, l['nb_chauffeurs'], nb_fmt)
                ws.write(row, 6, l['total_litres'], f['data'])
                ws.write(row, 7, l['liste_chauffeurs'], f['data_left'])
        return self._make_xlsx_response(f'RotationChauffeurs_{self.date_debut}_{self.date_fin}.xlsx', build)

    # ── EXPORT LUBRIFIANTS ───────────────────────────────────
    def _export_lubrifiant(self):
        def build(workbook, f):
            ws = workbook.add_worksheet('Lubrifiants')
            ws.set_column(0, 0, 30)
            ws.set_column(1, 9, 18)
            ws.merge_range('A1:J1', 'Rapport Consommation Lubrifiants', f['title'])
            ws.merge_range('A2:J2', f'Du {self.date_debut} au {self.date_fin}', f['data'])
            headers = ['Bus', 'Type', 'Atelier', 'Lubrifiant', 'Nb Vidanges', 'Qte Vidange (L)', 'Nb Additions', 'Qte Addition (L)', 'Total (L)', 'Kilometrage']
            for col, h in enumerate(headers):
                ws.write(3, col, h, f['header'])
            lignes = self._get_donnees_lubrifiant()
            for row, l in enumerate(lignes, 4):
                ws.write(row, 0, l['bus_name'], f['data_left'])
                ws.write(row, 1, l['bus_type'], f['data'])
                ws.write(row, 2, l['atelier'], f['data'])
                ws.write(row, 3, l['type_lubrifiant'], f['data'])
                ws.write(row, 4, l['nb_vidanges'], f['data'])
                ws.write(row, 5, l['qte_vidange'], f['data'])
                ws.write(row, 6, l['nb_additions'], f['data'])
                ws.write(row, 7, l['qte_addition'], f['data'])
                ws.write(row, 8, l['total_quantite'], f['data'])
                ws.write(row, 9, l['kilometrage'], f['data'])
            r = len(lignes) + 4
            ws.write(r, 0, 'TOTAL', f['total'])
            ws.write(r, 8, round(sum(l['total_quantite'] for l in lignes), 2), f['total'])
        return self._make_xlsx_response(f'Lubrifiants_{self.date_debut}_{self.date_fin}.xlsx', build)

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
                    data[bus_type] = {'bus_type': bus_type, 'nb_bons': 0, 'nb_vehicules': set(), 'total_litres': 0, 'total_km': 0}
                data[bus_type]['nb_bons'] += 1
                data[bus_type]['nb_vehicules'].add(bus.id)
                data[bus_type]['total_litres'] += ligne.quantity
                data[bus_type]['total_km'] += ligne.distance_estimated or 0
        result = []
        for key, val in data.items():
            total_km = val['total_km']
            total_l = val['total_litres']
            conso_moy = (total_l / total_km * 100) if total_km > 0 else 0
            result.append({'bus_type': val['bus_type'], 'nb_bons': val['nb_bons'], 'nb_vehicules': len(val['nb_vehicules']), 'total_litres': round(total_l, 2), 'total_km': round(total_km, 2), 'conso_moy': round(conso_moy, 2)})
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
                    data[key] = {'bus_name': bus.name, 'bus_type': bus.bus_type or '-', 'conso_theorique': bus.theoretical_fuel_consumption or 0, 'total_litres': 0, 'total_km': 0, 'nb_sorties': 0}
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
                result.append({'bus_name': val['bus_name'], 'bus_type': val['bus_type'], 'nb_sorties': val['nb_sorties'], 'total_litres': round(total_l, 2), 'total_km': round(total_km, 2), 'conso_theorique': round(val['conso_theorique'], 2), 'conso_reelle': round(conso_reelle, 2), 'ecart': round(ecart, 2)})
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
                    data[key] = {'bus_name': bus.name, 'bus_type': bus.bus_type or '-', 'code_interne': bus.license_plate or '-', 'service_code': ligne.service_code or '-', 'conso_theorique': bus.theoretical_fuel_consumption or 0, 'nb_sorties': 0, 'chauffeurs': set(), 'total_litres': 0, 'total_km': 0}
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
            result.append({'bus_name': val['bus_name'], 'bus_type': val['bus_type'], 'code_interne': val['code_interne'], 'service_code': val['service_code'], 'nb_sorties': val['nb_sorties'], 'nb_chauffeurs': len(val['chauffeurs']), 'total_litres': round(total_l, 2), 'total_km': round(total_km, 2), 'conso_theorique': round(conso_theorique, 2), 'conso_reelle': round(conso_reelle, 2), 'ecart': round(ecart, 2)})
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
                data[key] = {'station_name': station.name if station else 'Sans station', 'station_code': station.code if station else '-', 'fuel_type': bon.fuel_type_id.name if bon.fuel_type_id else '-', 'nb_bons': 0, 'nb_vehicules': set(), 'total_litres': 0, 'stock_initial': station.capacity if station else 0, 'stock_restant': station.current_stock if station else 0, 'bons': []}
            data[key]['nb_bons'] += 1
            data[key]['total_litres'] += bon.total_quantity
            for ligne in bon.line_ids:
                if ligne.vehicle_id:
                    data[key]['nb_vehicules'].add(ligne.vehicle_id.id)
            data[key]['bons'].append({'date': bon.date, 'bon_name': bon.name, 'type': dict(bon._fields['voucher_type'].selection).get(bon.voucher_type, '-'), 'agent': bon.distributor_name or '-', 'quantite': bon.total_quantity, 'nb_lignes': len(bon.line_ids)})
        result = []
        for key, val in data.items():
            result.append({'station_name': val['station_name'], 'station_code': val['station_code'], 'fuel_type': val['fuel_type'], 'nb_bons': val['nb_bons'], 'nb_vehicules': len(val['nb_vehicules']), 'total_litres': round(val['total_litres'], 2), 'stock_initial': val['stock_initial'], 'stock_restant': val['stock_restant'], 'bons': sorted(val['bons'], key=lambda x: x['date'])})
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
                    data[key] = {'bus_name': bus.name, 'bus_type': bus.bus_type or '-', 'atelier': bon.atelier or '-', 'type_lubrifiant': ligne.type_lubrifiant_id.name if ligne.type_lubrifiant_id else '-', 'nb_vidanges': 0, 'qte_vidange': 0, 'nb_additions': 0, 'qte_addition': 0, 'total_quantite': 0, 'kilometrage': 0}
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
            result.append({'bus_name': val['bus_name'], 'bus_type': val['bus_type'], 'atelier': val['atelier'], 'type_lubrifiant': val['type_lubrifiant'], 'nb_vidanges': val['nb_vidanges'], 'qte_vidange': round(val['qte_vidange'], 2), 'nb_additions': val['nb_additions'], 'qte_addition': round(val['qte_addition'], 2), 'total_quantite': round(val['total_quantite'], 2), 'kilometrage': round(val['kilometrage'], 1)})
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
                    data[key] = {'bus_name': bus.name, 'bus_type': bus.bus_type or '-', 'agence': agence, 'service_code': ligne.service_code or bus.service_code or '-', 'nb_sorties': 0, 'total_litres': 0, 'chauffeurs': {}}
                data[key]['nb_sorties'] += 1
                data[key]['total_litres'] += ligne.quantity
                if ligne.driver_code:
                    data[key]['chauffeurs'][ligne.driver_code] = ligne.driver_name or ligne.driver_code
        lignes = []
        for key, val in data.items():
            nb_ch = len(val['chauffeurs'])
            liste = ', '.join(f"{code}({nom})" if nom != code else code for code, nom in sorted(val['chauffeurs'].items()))
            lignes.append({'bus_name': val['bus_name'], 'bus_type': val['bus_type'], 'agence': val['agence'], 'service_code': val['service_code'], 'nb_sorties': val['nb_sorties'], 'nb_chauffeurs': nb_ch, 'total_litres': round(val['total_litres'], 2), 'liste_chauffeurs': liste})
        lignes = sorted(lignes, key=lambda x: x['nb_chauffeurs'], reverse=True)
        return {'nb_bus': len(lignes), 'nb_plus_5': len([l for l in lignes if l['nb_chauffeurs'] > 5]), 'nb_plus_10': len([l for l in lignes if l['nb_chauffeurs'] > 10]), 'total_chauffeurs': sum(l['nb_chauffeurs'] for l in lignes), 'lignes': lignes, 'bus_excessifs': [l for l in lignes if l['nb_chauffeurs'] > 5]}