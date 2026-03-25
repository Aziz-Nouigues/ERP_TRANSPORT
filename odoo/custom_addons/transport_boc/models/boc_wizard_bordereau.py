# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BocWizardBordereau(models.TransientModel):
    """Wizard de génération des bordereaux de transmission BOC"""
    _name = 'boc.wizard.bordereau'
    _description = 'Bordereaux de Transmission BOC'

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

    type_bordereau = fields.Selection([
        ('interne_transfere',     'Courriers internes transférés'),
        ('interne_non_transfere', 'Courriers internes non transférés'),
        ('externe_transfere',     'Courriers externes transférés'),
        ('externe_non_transfere', 'Courriers externes non transférés'),
        ('rappel_echeance',       'Courriers nécessitant une action (rappel mi-délai)'),
    ], string='Type de bordereau', required=True,
       default='interne_transfere')

    # ═══════════════════════════════════════════════════════════
    # ACTION — GÉNÉRATION PDF
    # ═══════════════════════════════════════════════════════════

    def action_generer_bordereau(self):
        self.ensure_one()
        refs = {
            'interne_transfere':     'transport_boc.action_bordereau_interne_transfere',
            'interne_non_transfere': 'transport_boc.action_bordereau_interne_non_transfere',
            'externe_transfere':     'transport_boc.action_bordereau_externe_transfere',
            'externe_non_transfere': 'transport_boc.action_bordereau_externe_non_transfere',
            'rappel_echeance':       'transport_boc.action_bordereau_rappel_echeance',
        }
        return self.env.ref(refs[self.type_bordereau]).report_action(self)

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — TRANSMISSIONS INTERNES TRANSFÉRÉES
    # ═══════════════════════════════════════════════════════════

    def _get_transmissions_internes_transferees(self):
        """Courriers internes dont au moins une transmission est transférée/traitée"""
        domain = [
            ('date_transmission', '>=', self.date_debut),
            ('date_transmission', '<=', self.date_fin),
            ('type_transmission', '=', 'interne'),
            ('state', 'in', ('transfere', 'accuse', 'traite')),
        ]
        transmissions = self.env['boc.transmission'].search(
            domain, order='date_transmission asc'
        )
        return self._format_transmissions(transmissions)

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — TRANSMISSIONS INTERNES NON TRANSFÉRÉES
    # ═══════════════════════════════════════════════════════════

    def _get_transmissions_internes_non_transferees(self):
        """Courriers internes en attente (non encore transférés)"""
        domain = [
            ('date_transmission', '>=', self.date_debut),
            ('date_transmission', '<=', self.date_fin),
            ('type_transmission', '=', 'interne'),
            ('state', '=', 'en_attente'),
        ]
        transmissions = self.env['boc.transmission'].search(
            domain, order='date_transmission asc'
        )
        return self._format_transmissions(transmissions)

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — TRANSMISSIONS EXTERNES TRANSFÉRÉES
    # ═══════════════════════════════════════════════════════════

    def _get_transmissions_externes_transferees(self):
        """Courriers externes dont la diffusion est transférée/traitée"""
        domain = [
            ('date_transmission', '>=', self.date_debut),
            ('date_transmission', '<=', self.date_fin),
            ('type_transmission', '=', 'externe'),
            ('state', 'in', ('transfere', 'accuse', 'traite')),
        ]
        transmissions = self.env['boc.transmission'].search(
            domain, order='date_transmission asc'
        )
        return self._format_transmissions(transmissions)

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — TRANSMISSIONS EXTERNES NON TRANSFÉRÉES
    # ═══════════════════════════════════════════════════════════

    def _get_transmissions_externes_non_transferees(self):
        """Courriers externes en attente"""
        domain = [
            ('date_transmission', '>=', self.date_debut),
            ('date_transmission', '<=', self.date_fin),
            ('type_transmission', '=', 'externe'),
            ('state', '=', 'en_attente'),
        ]
        transmissions = self.env['boc.transmission'].search(
            domain, order='date_transmission asc'
        )
        return self._format_transmissions(transmissions)

    # ═══════════════════════════════════════════════════════════
    # DONNÉES — COURRIERS NÉCESSITANT UNE ACTION (RAPPEL MI-DÉLAI)
    # ═══════════════════════════════════════════════════════════

    def _get_courriers_rappel_echeance(self):
        """
        Courriers arrivée :
        - qui nécessitent une réponse
        - non encore traités/classés
        - dont la date de rappel (mi-délai) est dans la période sélectionnée
          OU dont la date d'échéance est dans les 7 prochains jours
        """
        today = fields.Date.today()
        domain = [
            ('necessite_reponse', '=', True),
            ('reponse_fournie', '=', False),
            ('state', 'not in', ('traite', 'classe')),
            ('date_echeance', '!=', False),
            ('date_arrivee', '>=',
             fields.Datetime.from_string('%s 00:00:00' % self.date_debut)),
            ('date_arrivee', '<=',
             fields.Datetime.from_string('%s 23:59:59' % self.date_fin)),
        ]
        courriers = self.env['boc.courrier.arrivee'].search(
            domain, order='date_echeance asc'
        )

        result = []
        for c in courriers:
            jours_restants = (c.date_echeance - today).days
            # Statut rappel
            if jours_restants < 0:
                statut = 'En retard'
                alerte = 'danger'
            elif jours_restants <= 3:
                statut = 'Urgent (%d j)' % jours_restants
                alerte = 'warning'
            else:
                statut = '%d jour(s) restant(s)' % jours_restants
                alerte = 'info'

            result.append({
                'name':            c.name,
                'date_arrivee':    c.date_arrivee.strftime('%d/%m/%Y') if c.date_arrivee else '-',
                'expediteur':      c.organisme_id.name or c.expediteur_nom or '-',
                'sujet':           c.sujet or '-',
                'type_courrier':   c.type_courrier_id.name or '-',
                'date_echeance':   c.date_echeance.strftime('%d/%m/%Y'),
                'date_rappel':     c.date_rappel.strftime('%d/%m/%Y') if c.date_rappel else '-',
                'jours_restants':  jours_restants,
                'statut':          statut,
                'alerte':          alerte,
                'state':           dict(c._fields['state'].selection).get(c.state, c.state),
            })
        return result

    # ═══════════════════════════════════════════════════════════
    # HELPER — FORMATAGE DES TRANSMISSIONS
    # ═══════════════════════════════════════════════════════════

    def _format_transmissions(self, transmissions):
        state_labels = {
            'en_attente': 'En attente',
            'transfere':  'Transféré',
            'accuse':     'Accusé de réception',
            'traite':     'Traité',
        }
        result = []
        for t in transmissions:
            result.append({
                'arrivee_num':      t.arrivee_id.name or '-',
                'arrivee_date':     t.arrivee_id.date_arrivee.strftime('%d/%m/%Y %H:%M')
                                    if t.arrivee_id.date_arrivee else '-',
                'arrivee_sujet':    t.arrivee_id.sujet or '-',
                'expediteur':       t.arrivee_id.organisme_id.name
                                    or t.arrivee_id.expediteur_nom or '-',
                'type_courrier':    t.arrivee_id.type_courrier_id.name or '-',
                'destinataire':     t.organisme_id.name or t.destinataire_nom or '-',
                'responsable':      t.responsable_id.name or '-',
                'instruction':      t.instruction or '-',
                'date_transmission': t.date_transmission.strftime('%d/%m/%Y')
                                    if t.date_transmission else '-',
                'date_echeance':    t.date_echeance.strftime('%d/%m/%Y')
                                    if t.date_echeance else '-',
                'state':            state_labels.get(t.state, t.state),
                'notes':            t.notes or '',
            })
        return result