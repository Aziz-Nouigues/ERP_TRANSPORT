# -*- coding: utf-8 -*-
from odoo import models, fields, api
import datetime
import logging

_logger = logging.getLogger(__name__)

class BocCourrierPeriodique(models.Model):
    """
    Modèle de rappel automatique pour les courriers périodiques.
    Référence : Décret n°2197 du 7/10/2002 (courriers aux ministères).
    """
    _name = 'boc.courrier.periodique'
    _description = "Courrier Périodique — Modèle de rappel"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'prochaine_echeance asc, name'

    # ── IDENTIFICATION ───────────────────────────────────────────
    name = fields.Char(
        string='Désignation',
        required=True,
        translate=True,
    )
    reference = fields.Char(
        string='Référence',
        readonly=True,
        copy=False,
        default='/',
        help='Référence générée automatiquement : BOC/PER/YYYY/NNNN',
    )
    type_courrier_id = fields.Many2one(
        'boc.type.courrier',
        string='Type de courrier',
        required=True,
        domain=[('est_periodique', '=', True)],
        tracking=True,
        ondelete='restrict',
    )
    periodicite = fields.Selection(
        related='type_courrier_id.periodicite',
        string='Périodicité',
        store=True,
        readonly=True,
    )

    # ── DESTINATAIRE ─────────────────────────────────────────────
    organisme_id = fields.Many2one(
        'boc.organisme',
        string='Organisme destinataire',
        tracking=True,
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ── CALENDRIER ───────────────────────────────────────────────
    date_debut = fields.Date(
        string='Date de début de suivi',
        required=True,
        default=fields.Date.today,
    )
    derniere_echeance = fields.Date(
        string='Dernière échéance traitée',
        readonly=True,
        tracking=True,
    )
    prochaine_echeance = fields.Date(
        string='Prochaine échéance',
        compute='_compute_prochaine_echeance',
        store=True,
        tracking=True,
    )
    date_rappel = fields.Date(
        string='Date de rappel',
        compute='_compute_date_rappel',
        store=True,
    )

    # ── ÉTAT ─────────────────────────────────────────────────────
    state = fields.Selection([
        ('actif',    'Actif'),
        ('suspendu', 'Suspendu'),
        ('clos',     'Clos'),
    ], string='État', default='actif', tracking=True)

    en_attente_rappel = fields.Boolean(
        string='Rappel en attente',
        compute='_compute_en_attente_rappel',
        store=True,
    )
    en_retard = fields.Boolean(
        string='En retard',
        compute='_compute_en_attente_rappel',
        store=True,
    )

    notes = fields.Text(string='Notes / Documents attendus')

    # Lien vers les courriers arrivée générés depuis ce modèle
    arrivee_ids = fields.One2many(
        'boc.courrier.arrivee',
        'periodique_id',
        string='Courriers générés',
        readonly=True,
    )
    nb_courriers = fields.Integer(
        string='Nb courriers générés',
        compute='_compute_nb_courriers',
    )

    # ═══════════════════════════════════════════════════════════
    # ORM
    # ═══════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        """Génère automatiquement la référence BOC/PER/YYYY/NNNN à la création."""
        for vals in vals_list:
            if vals.get('reference', '/') == '/':
                vals['reference'] = (
                    self.env['ir.sequence'].next_by_code('boc.courrier.periodique') or '/'
                )
        return super().create(vals_list)

    # ═══════════════════════════════════════════════════════════
    # COMPUTE
    # ═══════════════════════════════════════════════════════════

    @api.depends('periodicite', 'derniere_echeance', 'date_debut')
    def _compute_prochaine_echeance(self):
        for rec in self:
            base = rec.derniere_echeance or rec.date_debut
            if not base or not rec.periodicite:
                rec.prochaine_echeance = False
                continue
            if rec.periodicite == 'mensuel':
                # Prochaine échéance : le 15 du mois suivant
                if base.day >= 15:
                    if base.month == 12:
                        rec.prochaine_echeance = base.replace(year=base.year + 1, month=1, day=15)
                    else:
                        rec.prochaine_echeance = base.replace(month=base.month + 1, day=15)
                else:
                    rec.prochaine_echeance = base.replace(day=15)
            elif rec.periodicite == 'semestriel':
                # Semestriel : 30 juin et 31 décembre
                if base.month < 7:
                    rec.prochaine_echeance = base.replace(month=6, day=30)
                elif base.month == 6 and base.day >= 30:
                    rec.prochaine_echeance = base.replace(month=12, day=31)
                elif base.month < 12:
                    rec.prochaine_echeance = base.replace(month=12, day=31)
                else:
                    rec.prochaine_echeance = base.replace(year=base.year + 1, month=6, day=30)
            elif rec.periodicite == 'annuel':
                # Annuel : 31 mars de l'année suivante
                if base.month < 3 or (base.month == 3 and base.day < 31):
                    rec.prochaine_echeance = base.replace(month=3, day=31)
                else:
                    rec.prochaine_echeance = base.replace(year=base.year + 1, month=3, day=31)

    @api.depends('prochaine_echeance', 'type_courrier_id.delai_rappel_periodique')
    def _compute_date_rappel(self):
        for rec in self:
            if rec.prochaine_echeance and rec.type_courrier_id:
                delai = rec.type_courrier_id.delai_rappel_periodique or 7
                rec.date_rappel = rec.prochaine_echeance - datetime.timedelta(days=delai)
            else:
                rec.date_rappel = False

    @api.depends('prochaine_echeance', 'date_rappel', 'state')
    def _compute_en_attente_rappel(self):
        today = fields.Date.today()
        for rec in self:
            if rec.state != 'actif' or not rec.prochaine_echeance:
                rec.en_attente_rappel = False
                rec.en_retard = False
                continue
            rec.en_retard = rec.prochaine_echeance < today
            rec.en_attente_rappel = (
                rec.date_rappel and rec.date_rappel <= today and not rec.en_retard
            )

    @api.depends('arrivee_ids')
    def _compute_nb_courriers(self):
        for rec in self:
            rec.nb_courriers = len(rec.arrivee_ids)

    # ═══════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════

    def action_suspendre(self):
        self.write({'state': 'suspendu'})

    def action_reactiver(self):
        self.write({'state': 'actif'})

    def action_clore(self):
        self.write({'state': 'clos'})

    def action_generer_courrier(self):
        """
        Génère un brouillon de courrier arrivée depuis ce modèle périodique.
        Ouvre le formulaire prérempli pour validation par l'agent BOC.
        """
        self.ensure_one()
        arrivee_obj = self.env['boc.courrier.arrivee']
        vals = {
            'type_arrivee': 'externe',
            'type_courrier_id': self.type_courrier_id.id,
            'sujet': self.name,
            'date_echeance': self.prochaine_echeance,
            'periodique_id': self.id,
        }
        if self.organisme_id:
            vals['organisme_id'] = self.organisme_id.id
        if self.notes:
            vals['description'] = self.notes
        new_arrivee = arrivee_obj.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'boc.courrier.arrivee',
            'res_id': new_arrivee.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_voir_courriers(self):
        """Voir tous les courriers générés depuis ce modèle."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Courriers générés',
            'res_model': 'boc.courrier.arrivee',
            'view_mode': 'list,form',
            'domain': [('periodique_id', '=', self.id)],
        }

    # ═══════════════════════════════════════════════════════════
    # CRON — Rappels automatiques
    # ═══════════════════════════════════════════════════════════

    @api.model
    def _cron_envoyer_rappels_periodiques(self):
        """
        Cron quotidien : envoie un rappel par mail/chatter pour chaque
        courrier périodique dont la date de rappel est atteinte.
        """
        today = fields.Date.today()
        rappels = self.search([
            ('state', '=', 'actif'),
            ('date_rappel', '<=', today),
            ('prochaine_echeance', '>=', today),
        ])
        for rec in rappels:
            delai = (rec.prochaine_echeance - today).days
            rec.message_post(
                body=(
                    "<strong>⏰ Rappel automatique — Courrier périodique</strong><br/>"
                    "Le courrier périodique <em>%s</em> est attendu dans "
                    "<strong>%d jour(s)</strong>.<br/>"
                    "Échéance : <strong>%s</strong><br/>"
                    "Périodicité : %s"
                ) % (
                    rec.name,
                    delai,
                    rec.prochaine_echeance.strftime('%d/%m/%Y'),
                    dict(rec._fields['periodicite'].selection).get(rec.periodicite, ''),
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                partner_ids=[rec.responsable_id.partner_id.id] if rec.responsable_id else [],
            )
            _logger.info(
                'BOC Rappel périodique envoyé : %s (échéance %s)',
                rec.name, rec.prochaine_echeance,
            )

        # Marquer aussi les retards
        retards = self.search([
            ('state', '=', 'actif'),
            ('prochaine_echeance', '<', today),
        ])
        for rec in retards:
            jours = (today - rec.prochaine_echeance).days
            rec.message_post(
                body=(
                    "<strong>🚨 RETARD — Courrier périodique en souffrance</strong><br/>"
                    "Le courrier périodique <em>%s</em> est en retard de "
                    "<strong>%d jour(s)</strong>.<br/>"
                    "Échéance dépassée : <strong>%s</strong>"
                ) % (
                    rec.name,
                    jours,
                    rec.prochaine_echeance.strftime('%d/%m/%Y'),
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                partner_ids=[rec.responsable_id.partner_id.id] if rec.responsable_id else [],
            )