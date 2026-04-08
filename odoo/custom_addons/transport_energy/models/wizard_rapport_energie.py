# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date


class WizardRapportEnergie(models.TransientModel):
    _name = 'transport.wizard.rapport.energie'
    _description = 'Wizard Rapport Energie STEG/SONEDE'

    annee = fields.Integer(
        string='Annee',
        required=True,
        default=lambda self: date.today().year
    )

    # CORRECTION : 3 types de rapports logiquement distincts
    # - steg     : rapport STEG uniquement, unité kWh, comparaison N/N-1
    # - sonede   : rapport SONEDE uniquement, unité m³, comparaison N/N-1
    # - synthese : synthèse financière globale (montants TND), STEG + SONEDE
    #              séparés en deux sections — jamais mélangés dans une même colonne
    type_rapport = fields.Selection([
        ('steg',     'Rapport STEG (Electricite — kWh)'),
        ('sonede',   'Rapport SONEDE (Eau — m³)'),
        ('synthese', 'Synthese financiere STEG + SONEDE (TND)'),
    ], string='Type de rapport', required=True, default='steg',
       help=(
           "STEG : rapport détaillé électricité en kWh.\n"
           "SONEDE : rapport détaillé eau en m³.\n"
           "Synthèse : vue financière globale en TND — les deux types "
           "sont présentés séparément, jamais additionnés."
       )
    )

    site_filtre = fields.Char(string='Site / Agence (optionnel)')

    def action_generer(self):
        self.ensure_one()
        return self.env.ref(
            'transport_energy.action_rapport_energie_pdf'
        ).report_action(self)

    def _get_donnees(self):
        """Retourne les données selon le type de rapport choisi."""
        self.ensure_one()
        if self.type_rapport == 'synthese':
            return self._get_donnees_synthese()
        else:
            return self._get_donnees_detail(self.type_rapport)

    def _get_donnees_detail(self, type_energie):
        """Rapport détaillé pour UN seul type : STEG ou SONEDE.
        Unité cohérente sur tout le rapport (kWh ou m³).
        Comparaison N / N-1 par facture et par site.
        """
        unite = 'kWh' if type_energie == 'steg' else 'm³'
        type_label = 'STEG' if type_energie == 'steg' else 'SONEDE'

        domain = [
            ('type_facture', '=', type_energie),
            ('date_debut_periode', '>=', date(self.annee, 1, 1)),
            ('date_debut_periode', '<=', date(self.annee, 12, 31)),
            ('statut', '!=', 'annulee'),
        ]
        if self.site_filtre:
            domain.append(('site', 'ilike', self.site_filtre))

        factures = self.env['transport.facture.energie'].search(
            domain, order='site, date_debut_periode'
        )

        lignes = []
        par_site = {}
        total_n = total_n1 = total_montant_n = total_montant_n1 = 0

        for f in factures:
            ecart = round(f.ecart_consommation, 2)
            ecart_pct = round(f.ecart_pourcentage, 1)

            lignes.append({
                'site':       f.site,
                'compteur':   f.numero_compteur,
                'type':       type_label,
                'unite':      unite,
                'periode':    f'{f.date_debut_periode} — {f.date_fin_periode}',
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

            if f.site not in par_site:
                par_site[f.site] = {'site': f.site, 'total_n': 0, 'total_n1': 0,
                                     'montant_n': 0, 'montant_n1': 0}
            par_site[f.site]['total_n'] += f.quantite_consommee
            par_site[f.site]['total_n1'] += f.consommation_n1
            par_site[f.site]['montant_n'] += f.montant
            par_site[f.site]['montant_n1'] += f.montant_n1

        par_site_list = []
        for key, val in par_site.items():
            ecart = round(val['total_n'] - val['total_n1'], 2)
            ecart_pct = round(
                (ecart / val['total_n1'] * 100) if val['total_n1'] > 0 else 0, 1
            )
            par_site_list.append({
                'site':       val['site'],
                'total_n':    round(val['total_n'], 2),
                'total_n1':   round(val['total_n1'], 2),
                'montant_n':  round(val['montant_n'], 3),
                'montant_n1': round(val['montant_n1'], 3),
                'ecart':      ecart,
                'ecart_pct':  ecart_pct,
            })

        total_ecart = round(total_n - total_n1, 2)
        ecart_pct_global = round(
            (total_ecart / total_n1 * 100) if total_n1 > 0 else 0, 1
        )

        return {
            'mode':             'detail',
            'type_label':       type_label,
            'unite':            unite,
            'nb_factures':      len(factures),
            'lignes':           lignes,
            'par_site':         sorted(par_site_list, key=lambda x: x['site']),
            'total_n':          round(total_n, 2),
            'total_n1':         round(total_n1, 2),
            'total_montant_n':  round(total_montant_n, 3),
            'total_montant_n1': round(total_montant_n1, 3),
            'total_ecart':      total_ecart,
            'ecart_pct':        ecart_pct_global,
        }

    def _get_donnees_synthese(self):
        """Synthèse financière globale : STEG et SONEDE présentés séparément.
        Unité commune = TND (montants).
        Les quantités (kWh vs m³) sont affichées dans leur section respective,
        jamais additionnées ensemble.
        """
        domain_base = [
            ('date_debut_periode', '>=', date(self.annee, 1, 1)),
            ('date_debut_periode', '<=', date(self.annee, 12, 31)),
            ('statut', '!=', 'annulee'),
        ]
        if self.site_filtre:
            domain_base.append(('site', 'ilike', self.site_filtre))

        steg_data = self._get_donnees_detail('steg')
        sonede_data = self._get_donnees_detail('sonede')

        # Tous les sites uniques
        sites_steg = {l['site'] for l in steg_data['lignes']}
        sites_sonede = {l['site'] for l in sonede_data['lignes']}
        tous_sites = sorted(sites_steg | sites_sonede)

        # Synthèse par site : montants TND uniquement (unité commune)
        par_site = {}
        for site in tous_sites:
            par_site[site] = {
                'site':             site,
                'steg_montant_n':   0,
                'steg_montant_n1':  0,
                'steg_qte_n':       0,
                'sonede_montant_n': 0,
                'sonede_montant_n1':0,
                'sonede_qte_n':     0,
                'total_n':          0,
                'total_n1':         0,
            }

        for ligne in steg_data['lignes']:
            s = par_site[ligne['site']]
            s['steg_montant_n']  += ligne['montant_n']
            s['steg_montant_n1'] += ligne['montant_n1']
            s['steg_qte_n']      += ligne['qte_n']

        for ligne in sonede_data['lignes']:
            s = par_site[ligne['site']]
            s['sonede_montant_n']  += ligne['montant_n']
            s['sonede_montant_n1'] += ligne['montant_n1']
            s['sonede_qte_n']      += ligne['qte_n']

        synthese_par_site = []
        for site, val in par_site.items():
            total_n  = round(val['steg_montant_n']  + val['sonede_montant_n'],  3)
            total_n1 = round(val['steg_montant_n1'] + val['sonede_montant_n1'], 3)
            ecart = round(total_n - total_n1, 3)
            ecart_pct = round((ecart / total_n1 * 100) if total_n1 > 0 else 0, 1)
            synthese_par_site.append({
                'site':              site,
                'steg_montant_n':    round(val['steg_montant_n'],   3),
                'steg_montant_n1':   round(val['steg_montant_n1'],  3),
                'steg_qte_n':        round(val['steg_qte_n'],       2),
                'sonede_montant_n':  round(val['sonede_montant_n'],  3),
                'sonede_montant_n1': round(val['sonede_montant_n1'], 3),
                'sonede_qte_n':      round(val['sonede_qte_n'],      2),
                'total_n':           total_n,
                'total_n1':          total_n1,
                'ecart':             ecart,
                'ecart_pct':         ecart_pct,
            })

        total_steg_n   = steg_data['total_montant_n']
        total_steg_n1  = steg_data['total_montant_n1']
        total_sonede_n  = sonede_data['total_montant_n']
        total_sonede_n1 = sonede_data['total_montant_n1']
        total_n  = round(total_steg_n  + total_sonede_n,  3)
        total_n1 = round(total_steg_n1 + total_sonede_n1, 3)
        ecart_global = round(total_n - total_n1, 3)
        ecart_pct_global = round(
            (ecart_global / total_n1 * 100) if total_n1 > 0 else 0, 1
        )

        return {
            'mode':              'synthese',
            'type_label':        'STEG + SONEDE',
            'unite':             'TND',
            'nb_factures':       steg_data['nb_factures'] + sonede_data['nb_factures'],
            'steg':              steg_data,
            'sonede':            sonede_data,
            'par_site':          synthese_par_site,
            'total_steg_n':      round(total_steg_n,  3),
            'total_steg_n1':     round(total_steg_n1, 3),
            'total_sonede_n':    round(total_sonede_n,  3),
            'total_sonede_n1':   round(total_sonede_n1, 3),
            'total_n':           total_n,
            'total_n1':          total_n1,
            'ecart_global':      ecart_global,
            'ecart_pct':         ecart_pct_global,
        }
