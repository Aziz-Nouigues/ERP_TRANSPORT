from odoo import models, fields, api
from datetime import date


class WizardRapportEnergie(models.TransientModel):
    _name = 'transport.wizard.rapport.energie'
    _description = 'Wizard Rapport Energie STEG/SONEDE'

    annee = fields.Integer(
        string='Annee',
        required=True,
        default=lambda self: date.today().year
    )

    type_energie = fields.Selection([
        ('steg',   'STEG - Electricite'),
        ('sonede', 'SONEDE - Eau'),
        ('tous',   'STEG + SONEDE'),
    ], string='Type', required=True, default='tous')

    site_filtre = fields.Char(
        string='Site / Agence (optionnel)'
    )

    def action_generer(self):
        self.ensure_one()
        return self.env.ref(
            'transport_energy.action_rapport_energie_pdf'
        ).report_action(self)

    def _get_donnees(self):
        domain = []
        if self.type_energie != 'tous':
            domain.append(('type_facture', '=', self.type_energie))
        if self.site_filtre:
            domain.append(('site', 'ilike', self.site_filtre))

        # Factures de l'annee N
        domain_n = domain + [
            ('date_debut_periode', '>=', date(self.annee, 1, 1)),
            ('date_debut_periode', '<=', date(self.annee, 12, 31)),
            ('statut', '!=', 'annulee'),
        ]
        factures = self.env['transport.facture.energie'].search(
            domain_n, order='site, date_debut_periode'
        )

        lignes = []
        total_n = 0
        total_n1 = 0
        total_montant_n = 0
        total_montant_n1 = 0

        # Grouper par site pour la section comparaison
        par_site = {}

        for f in factures:
            type_label = 'STEG' if f.type_facture == 'steg' else 'SONEDE'
            unite = 'kWh' if f.type_facture == 'steg' else 'm3'
            ecart = round(f.ecart_consommation, 2)
            ecart_pct = round(f.ecart_pourcentage, 1)

            lignes.append({
                'site':       f.site,
                'compteur':   f.numero_compteur,
                'type':       type_label,
                'unite':      unite,
                'periode':    f'{f.date_debut_periode} / {f.date_fin_periode}',
                'qte_n':      round(f.quantite_consommee, 2),
                'montant_n':  round(f.montant, 3),
                'qte_n1':     round(f.consommation_n1, 2),
                'montant_n1': round(f.montant_n1, 3),
                'ecart':      ecart,
                'ecart_pct':  ecart_pct,
            })

            total_n += f.quantite_consommee
            total_n1 += f.consommation_n1
            total_montant_n += f.montant
            total_montant_n1 += f.montant_n1

            # Agreger par site
            site_key = f'{f.site}_{f.type_facture}'
            if site_key not in par_site:
                par_site[site_key] = {
                    'site':    f'{f.site} ({type_label})',
                    'total_n':  0,
                    'total_n1': 0,
                }
            par_site[site_key]['total_n'] += f.quantite_consommee
            par_site[site_key]['total_n1'] += f.consommation_n1

        # Calculer ecarts par site
        par_site_list = []
        for key, val in par_site.items():
            ecart = round(val['total_n'] - val['total_n1'], 2)
            ecart_pct = round(
                (ecart / val['total_n1'] * 100) if val['total_n1'] > 0 else 0, 1
            )
            par_site_list.append({
                'site':     val['site'],
                'total_n':  round(val['total_n'], 2),
                'total_n1': round(val['total_n1'], 2),
                'ecart':    ecart,
                'ecart_pct': ecart_pct,
            })

        total_ecart = round(total_n - total_n1, 2)
        ecart_pct_global = round(
            (total_ecart / total_n1 * 100) if total_n1 > 0 else 0, 1
        )

        # Unite globale
        if self.type_energie == 'steg':
            unite = 'kWh'
        elif self.type_energie == 'sonede':
            unite = 'm3'
        else:
            unite = 'kWh/m3'

        return {
            'nb_factures':     len(factures),
            'unite':           unite,
            'lignes':          lignes,
            'par_site':        sorted(par_site_list, key=lambda x: x['site']),
            'total_n':         round(total_n, 2),
            'total_n1':        round(total_n1, 2),
            'total_montant_n':  round(total_montant_n, 3),
            'total_montant_n1': round(total_montant_n1, 3),
            'total_ecart':     total_ecart,
            'ecart_pct':       ecart_pct_global,
        }