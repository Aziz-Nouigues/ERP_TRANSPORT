# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BocTransmission(models.Model):
    """Diffusion d'un courrier arrivée aux services concernés"""
    _name = 'boc.transmission'
    _description = "Transmission / Diffusion"
    _order = 'date_transmission desc'

    # ── LIENS ───────────────────────────────────────────────────
    arrivee_id = fields.Many2one(
        'boc.courrier.arrivee',
        string='Courrier arrivée',
        required=True,
        ondelete='cascade',
    )

    # ── DESTINATAIRE INTERNE ─────────────────────────────────────
    organisme_id = fields.Many2one(
        'boc.organisme',
        string='Service / Direction destinataire',
        domain=[('type_organisme', '=', 'interne')],
    )
    destinataire_nom = fields.Char(
        string='Destinataire',
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable',
    )

    # ── INSTRUCTION ──────────────────────────────────────────────
    instruction_id = fields.Many2one(
        'boc.instruction',
        string='Instruction prédéfinie',
    )
    instruction = fields.Char(
        string='Instruction',
        translate=False,
        help='ex: Pour traitement, Pour information, Pour signature...',
    )

    # ── DATES ET ÉTAT ────────────────────────────────────────────
    date_transmission = fields.Date(
        string='Date de transmission',
        default=fields.Date.today,
        required=True,
    )
    date_echeance = fields.Date(
        string="Date d'échéance",
    )
    state = fields.Selection([
        ('en_attente', 'En attente'),
        ('transfere',  'Transféré'),
        ('accuse',     'Accusé de réception'),
        ('traite',     'Traité'),
    ], string='État', default='en_attente')

    notes = fields.Text(string='Notes', translate=False)

    # ── TYPE TRANSMISSION ────────────────────────────────────────
    # Déclaration explicite du selection nécessaire pour que les
    # filtres interne/externe fonctionnent correctement dans les vues
    type_transmission = fields.Selection(
        selection=[
            ('externe', 'Externe'),
            ('interne', 'Interne'),
        ],
        related='arrivee_id.type_arrivee',
        string='Type',
        store=True,
    )

    # ═══════════════════════════════════════════════════════════
    # ONCHANGE
    # ═══════════════════════════════════════════════════════════

    @api.onchange('instruction_id')
    def _onchange_instruction_id(self):
        if self.instruction_id:
            self.instruction = self.instruction_id.name

    @api.onchange('organisme_id')
    def _onchange_organisme_id(self):
        if self.organisme_id:
            self.destinataire_nom = self.organisme_id.name

    # ═══════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════

    def action_transferer(self):
        for rec in self:
            rec.state = 'transfere'
            # Mettre à jour le courrier parent
            if rec.arrivee_id.state == 'enregistre':
                rec.arrivee_id.state = 'diffuse'

    def action_accuser(self):
        for rec in self:
            rec.state = 'accuse'

    def action_traiter(self):
        for rec in self:
            rec.state = 'traite'