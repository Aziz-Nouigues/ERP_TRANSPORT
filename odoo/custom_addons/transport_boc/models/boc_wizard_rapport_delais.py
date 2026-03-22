# -*- coding: utf-8 -*-
from odoo import models, fields, api
import datetime


class BocWizardRapportDelais(models.TransientModel):
    """Wizard de génération des rapports de suivi des délais BOC"""
    _name = 'boc.wizard.rapport.delais'
    _description = 'Rapport Délais de Traitement BOC'

    # ── FILTRES ──────────────────────────────────────────────────
    date_debut = fields.Date(
        string='Date début',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_fin = fields.Date(
        string='Date fin',
        required=True,
        default=fields.Date.today,
    )
    type_arrivee = fields.Selection([
        ('externe', 'Externe'),
        ('interne', 'Interne'),
    ], string='Type arrivée', help='Laisser vide pour tous')

    type_rapport = fields.Selection([
        ('echus',   'Courriers échus (sans suite)'),
        ('depasse', 'Courriers traités hors délai'),
        ('delais',  'Édition des délais de traitement'),
    ], string='Type de rapport', required=True, default='delais')

    # ═══════════════════════════════════════════════════════════
    # ACTIONS — GÉNÉRATION PDF
    # ═══════════════════════════════════════════════════════════

    def action_generer_rapport(self):
        self.ensure_one()
        refs = {
            'echus':   'transport_boc.action_rapport_boc_echus',
            'depasse': 'transport_boc.action_rapport_boc_depasse',
            'delais':  'transport_boc.action_rapport_boc_delais',
        }
        return self.env.ref(refs[self.type_rapport]).report_action(self)

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — RAPPORT 1 : COURRIERS ÉCHUS
    # Courriers sans suite dont la date d'échéance est dépassée
    # ═══════════════════════════════════════════════════════════

    def _get_courriers_echus(self):
        today = fields.Date.today()
        domain = [
            ('date_echeance', '>=', self.date_debut),
            ('date_echeance', '<=', self.date_fin),
            ('date_echeance', '<', today),
            ('state', 'not in', ('traite', 'classe')),
            ('necessite_reponse', '=', True),
            ('reponse_fournie', '=', False),
        ]
        if self.type_arrivee:
            domain.append(('type_arrivee', '=', self.type_arrivee))

        courriers = self.env['boc.courrier.arrivee'].search(
            domain, order='date_echeance asc'
        )

        result = []
        for c in courriers:
            jours = (today - c.date_echeance).days
            result.append({
                'name':         c.name,
                'date_arrivee': c.date_arrivee.strftime('%d/%m/%Y %H:%M') if c.date_arrivee else '-',
                'type_courrier': c.type_courrier_id.name or '-',
                'expediteur':   c.organisme_id.name or c.expediteur_nom or '-',
                'sujet':        c.sujet or '-',
                'date_echeance': c.date_echeance.strftime('%d/%m/%Y') if c.date_echeance else '-',
                'jours_depasses': jours,
                'state':        dict(c._fields['state'].selection).get(c.state, c.state),
            })
        return result

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — RAPPORT 2 : COURRIERS TRAITÉS HORS DÉLAI
    # Courriers traités mais la réponse est arrivée après l'échéance
    # ═══════════════════════════════════════════════════════════

    def _get_courriers_depasse_delai(self):
        domain = [
            ('date_arrivee', '>=', datetime.datetime.combine(self.date_debut, datetime.time.min)),
            ('date_arrivee', '<=', datetime.datetime.combine(self.date_fin, datetime.time.max)),
            ('state', 'in', ('traite', 'classe')),
            ('reponse_fournie', '=', True),
            ('date_echeance', '!=', False),
            ('date_reponse', '!=', False),
        ]
        if self.type_arrivee:
            domain.append(('type_arrivee', '=', self.type_arrivee))

        courriers = self.env['boc.courrier.arrivee'].search(
            domain, order='date_arrivee asc'
        )

        result = []
        for c in courriers:
            if not c.date_reponse or not c.date_echeance:
                continue
            if c.date_reponse <= c.date_echeance:
                continue
            jours = (c.date_reponse - c.date_echeance).days
            result.append({
                'name':          c.name,
                'date_arrivee':  c.date_arrivee.strftime('%d/%m/%Y') if c.date_arrivee else '-',
                'type_courrier': c.type_courrier_id.name or '-',
                'expediteur':    c.organisme_id.name or c.expediteur_nom or '-',
                'sujet':         c.sujet or '-',
                'date_echeance': c.date_echeance.strftime('%d/%m/%Y'),
                'date_reponse':  c.date_reponse.strftime('%d/%m/%Y'),
                'jours_depasses': jours,
            })
        return result

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — RAPPORT 3 : ÉDITION DES DÉLAIS DE TRAITEMENT
    # Tous les courriers avec leur délai calculé
    # ═══════════════════════════════════════════════════════════

    def _get_delais_traitement(self):
        today = fields.Date.today()
        domain = [
            ('date_arrivee', '>=', datetime.datetime.combine(self.date_debut, datetime.time.min)),
            ('date_arrivee', '<=', datetime.datetime.combine(self.date_fin, datetime.time.max)),
            ('date_echeance', '!=', False),
        ]
        if self.type_arrivee:
            domain.append(('type_arrivee', '=', self.type_arrivee))

        courriers = self.env['boc.courrier.arrivee'].search(
            domain, order='date_arrivee asc'
        )

        result = []
        for c in courriers:
            date_arr = c.date_arrivee.date() if c.date_arrivee else None

            # Calcul délai réel (si traité) ou délai en cours
            if c.date_reponse and date_arr:
                delai = (c.date_reponse - date_arr).days
            elif date_arr:
                delai = (today - date_arr).days
            else:
                delai = 0

            # Statut du délai
            if c.state in ('traite', 'classe') and c.date_reponse and c.date_echeance:
                if c.date_reponse <= c.date_echeance:
                    statut = 'dans_delai'
                else:
                    statut = 'hors_delai'
            elif c.date_echeance and c.date_echeance < today and c.state not in ('traite', 'classe'):
                statut = 'echu'
            elif c.state in ('traite', 'classe'):
                statut = 'dans_delai'
            else:
                statut = 'en_cours'

            result.append({
                'name':          c.name,
                'date_arrivee':  c.date_arrivee.strftime('%d/%m/%Y') if c.date_arrivee else '-',
                'expediteur':    c.organisme_id.name or c.expediteur_nom or '-',
                'sujet':         c.sujet or '-',
                'date_echeance': c.date_echeance.strftime('%d/%m/%Y') if c.date_echeance else '-',
                'date_reponse':  c.date_reponse.strftime('%d/%m/%Y') if c.date_reponse else '-',
                'delai_jours':   delai,
                'statut_delai':  statut,
            })
        return result

    # ═══════════════════════════════════════════════════════════
    # STATISTIQUES GLOBALES pour le rapport 3
    # ═══════════════════════════════════════════════════════════

    def _get_stats_delais(self):
        courriers = self._get_delais_traitement()
        total = len(courriers)
        echus = len([c for c in courriers if c['statut_delai'] == 'echu'])
        hors_delai = len([c for c in courriers if c['statut_delai'] == 'hors_delai'])
        dans_delai = len([c for c in courriers if c['statut_delai'] == 'dans_delai'])
        delais = [c['delai_jours'] for c in courriers if c['delai_jours'] > 0]
        delai_moyen = round(sum(delais) / len(delais), 1) if delais else 0
        return {
            'total':       total,
            'echus':       echus,
            'hors_delai':  hors_delai,
            'dans_delai':  dans_delai,
            'delai_moyen': delai_moyen,
        }