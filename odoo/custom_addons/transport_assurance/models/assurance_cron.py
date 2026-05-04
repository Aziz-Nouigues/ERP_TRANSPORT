# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AssuranceCron(models.AbstractModel):
    """Actions planifiées pour le module assurance.

    Cron 1 (quotidien) : mise à jour états polices expirées
    Cron 2 (quotidien) : alertes d'échéance J-30 / J-15 / J-7
    Cron 3 (quotidien) : blocage exploitation si RC expirée (Tunisie)
    """
    _name = 'transport.assurance.cron'
    _description = 'Crons assurance transport'

    @api.model
    def cron_update_states(self):
        """Met à jour automatiquement l'état des polices expirées."""
        today = fields.Date.today()
        _logger.info('ASSURANCE CRON — Mise à jour états polices — %s', today)

        # ── Polices bus ──────────────────────────────────────────
        polices_bus_exp = self.env['transport.assurance.bus'].search([
            ('state', '=', 'active'),
            ('date_fin', '<', today),
        ])
        if polices_bus_exp:
            polices_bus_exp.write({'state': 'expirée'})
            _logger.info('ASSURANCE — %d polices bus passées en expirée', len(polices_bus_exp))

        polices_bus_alerte = self.env['transport.assurance.bus'].search([
            ('state', '=', 'active'),
            ('date_alerte', '<=', today),
            ('date_fin', '>=', today),
        ])
        if polices_bus_alerte:
            polices_bus_alerte.write({'state': 'alerte'})
            _logger.info('ASSURANCE — %d polices bus en alerte échéance', len(polices_bus_alerte))

        # ── Polices chauffeur ────────────────────────────────────
        polices_chf_exp = self.env['transport.assurance.chauffeur'].search([
            ('state', '=', 'active'),
            ('date_fin', '<', today),
        ])
        if polices_chf_exp:
            polices_chf_exp.write({'state': 'expirée'})
            _logger.info('ASSURANCE — %d polices chauffeur passées en expirée', len(polices_chf_exp))

        polices_chf_alerte = self.env['transport.assurance.chauffeur'].search([
            ('state', '=', 'active'),
            ('date_alerte', '<=', today),
            ('date_fin', '>=', today),
        ])
        if polices_chf_alerte:
            polices_chf_alerte.write({'state': 'alerte'})
            _logger.info('ASSURANCE — %d polices chauffeur en alerte', len(polices_chf_alerte))

    @api.model
    def cron_alertes_echeance(self):
        """Crée des activités mail.activity pour les polices proches de l'expiration.

        Jalons : J-30, J-15, J-7
        Une seule activité par police et par jalon (pas de doublons).
        """
        today = fields.Date.today()
        from dateutil.relativedelta import relativedelta

        jalons = [7, 15, 30]

        for jalon in jalons:
            date_cible = today + relativedelta(days=jalon)

            # Polices bus
            polices_bus = self.env['transport.assurance.bus'].search([
                ('state', 'in', ('active', 'alerte')),
                ('date_fin', '=', date_cible),
            ])
            for police in polices_bus:
                self._creer_activite_alerte(
                    record=police,
                    jalon=jalon,
                    message=(
                        f'Police RC/Assurance {police.type_police_id.name} du bus '
                        f'{police.vehicle_id.name} expire dans {jalon} jours '
                        f'({police.date_fin.strftime("%d/%m/%Y")}).'
                    )
                )

            # Polices chauffeur
            polices_chf = self.env['transport.assurance.chauffeur'].search([
                ('state', 'in', ('active', 'alerte')),
                ('date_fin', '=', date_cible),
            ])
            for police in polices_chf:
                self._creer_activite_alerte(
                    record=police,
                    jalon=jalon,
                    message=(
                        f'Police {police.type_police_id.name} de {police.employe_id.name} '
                        f'expire dans {jalon} jours '
                        f'({police.date_fin.strftime("%d/%m/%Y")}).'
                    )
                )

    def _creer_activite_alerte(self, record, jalon, message):
        """Crée une activité de rappel si elle n'existe pas déjà pour ce jalon."""
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False
        )
        if not activity_type:
            return
        # Éviter les doublons : chercher une activité existante avec le même résumé
        existing = record.activity_ids.filtered(
            lambda a: f'J-{jalon}' in (a.summary or '')
        )
        if existing:
            return
        record.activity_schedule(
            activity_type_id=activity_type.id,
            summary=f'Expiration assurance J-{jalon}',
            note=message,
            date_deadline=fields.Date.today(),
        )
        _logger.info('ASSURANCE ALERTE J-%d créée : %s', jalon, message[:80])

    @api.model
    def cron_bus_non_assures(self):
        """Vérifie les bus actifs sans police RC ou Voyage valide.
        Log une alerte et peut notifier le responsable.
        Cette règle est critique légalement en Tunisie.
        """
        today = fields.Date.today()
        types_obligatoires = self.env['transport.assurance.type'].search([
            ('is_obligatoire', '=', True),
            ('categorie', 'in', ['bus', 'both']),
        ])
        if not types_obligatoires:
            return

        tous_bus = self.env['fleet.vehicle'].search([('active', '=', True)])
        bus_non_assures = []

        for bus in tous_bus:
            for type_pol in types_obligatoires:
                couverture = self.env['transport.assurance.bus'].search_count([
                    ('vehicle_id', '=', bus.id),
                    ('type_police_id', '=', type_pol.id),
                    ('state', '=', 'active'),
                    ('date_fin', '>=', today),
                ])
                if not couverture:
                    bus_non_assures.append((bus.name, type_pol.name))

        if bus_non_assures:
            details = '\n'.join(
                f'  - {bus} : police {type_} manquante ou expirée'
                for bus, type_ in bus_non_assures
            )
            _logger.warning(
                'ASSURANCE CRITIQUE — Bus sans couverture obligatoire :\n%s', details
            )
            # Notifier le groupe manager assurance par email interne
            group = self.env.ref(
                'transport_assurance.group_assurance_manager',
                raise_if_not_found=False
            )
            if group:
                managers = group.users
                if managers:
                    self.env['mail.mail'].create({
                        'subject': f'⚠ ALERTE : {len(bus_non_assures)} bus sans couverture obligatoire',
                        'body_html': (
                            '<p><strong>Alerte légale critique — Assurance transport</strong></p>'
                            f'<p>{len(bus_non_assures)} bus actifs sont sans police obligatoire valide :</p>'
                            f'<pre>{details}</pre>'
                            '<p>Veuillez régulariser la situation immédiatement.</p>'
                        ),
                        'email_to': ','.join(managers.mapped('email')),
                    }).send()
