# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BocCourrierDepart(models.Model):
    """Courrier Départ — tout ce qui sort de l'entreprise"""
    _name = 'boc.courrier.depart'
    _description = "Courrier Départ"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_depart desc, name desc'

    # ── IDENTIFICATION ──────────────────────────────────────────
    name = fields.Char(
        string='Numéro d\'ordre',
        readonly=True,
        copy=False,
        default='Nouveau',
    )

    # ── TYPE ET NATURE ───────────────────────────────────────────
    type_depart = fields.Selection([
        ('externe', 'Externe'),
        ('interne', 'Interne'),
    ], string='Type de départ', required=True, default='externe',
       tracking=True)

    type_courrier_id = fields.Many2one(
        'boc.type.courrier',
        string='Nature du courrier',
        required=True,
        tracking=True,
    )

    support = fields.Selection([
        ('papier',       'Lettre papier'),
        ('electronique', 'Lettre électronique'),
        ('cd',           'CD'),
        ('lettre_fermee','Lettre fermée'),
        ('carte_geo',    'Carte géographique'),
        ('autre',        'Autre'),
    ], string='Support / Format', default='papier', required=True)

    # ── DATES ────────────────────────────────────────────────────
    date_depart = fields.Date(
        string='Date de départ',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )

    # ── DESTINATAIRE ─────────────────────────────────────────────
    organisme_id = fields.Many2one(
        'boc.organisme',
        string='Destinataire',
        tracking=True,
    )
    destinataire_nom = fields.Char(
        string='Nom destinataire',
        translate=True,
        help='Si le destinataire n\'est pas dans la liste des organismes',
    )

    # ── CONTENU ──────────────────────────────────────────────────
    sujet_id = fields.Many2one(
        'boc.sujet',
        string='Sujet prédéfini',
    )
    sujet = fields.Char(
        string='Objet / Sujet',
        required=True,
        translate=False,
        tracking=True,
    )
    description = fields.Text(
        string='Description / Remarques',
    )
    reference_interne = fields.Char(
        string='Référence interne',
    )

    # ── LIEN AVEC COURRIER ARRIVÉE (réponse) ─────────────────────
    arrivee_id = fields.Many2one(
        'boc.courrier.arrivee',
        string='En réponse à',
        help='Courrier arrivée auquel ce départ répond',
    )

    # ── ÉTAT ─────────────────────────────────────────────────────
    state = fields.Selection([
        ('brouillon',  'Brouillon'),
        ('enregistre', 'Enregistré'),
        ('envoye',     'Envoyé'),
        ('classe',     'Classé'),
    ], string='État', default='brouillon', tracking=True)

    # ── EXPÉDITEUR INTERNE ───────────────────────────────────────
    service_expediteur = fields.Char(
        string='Service expéditeur',
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
    )

    # ═══════════════════════════════════════════════════════════
    # ONCHANGE
    # ═══════════════════════════════════════════════════════════

    @api.onchange('sujet_id')
    def _onchange_sujet_id(self):
        if self.sujet_id:
            self.sujet = self.sujet_id.name

    @api.onchange('arrivee_id')
    def _onchange_arrivee_id(self):
        """Pré-remplir le sujet depuis le courrier arrivée"""
        if self.arrivee_id and not self.sujet:
            self.sujet = "RE: " + (self.arrivee_id.sujet or '')

    # ═══════════════════════════════════════════════════════════
    # ACTIONS WORKFLOW
    # ═══════════════════════════════════════════════════════════

    def action_enregistrer(self):
        """Enregistrement officiel — génère le numéro d'ordre"""
        for rec in self:
            if rec.name == 'Nouveau':
                rec.name = self.env['ir.sequence'].next_by_code(
                    'boc.courrier.depart'
                )
            rec.state = 'enregistre'
            # Si lié à un courrier arrivée, le marquer comme traité
            if rec.arrivee_id and rec.arrivee_id.state == 'diffuse':
                rec.arrivee_id.depart_reponse_id = rec.id

    def action_envoyer(self):
        """Marquer comme envoyé"""
        for rec in self:
            rec.state = 'envoye'

    def action_classer(self):
        """Archiver / Classer"""
        for rec in self:
            rec.state = 'classe'

    def action_reset(self):
        for rec in self:
            rec.state = 'brouillon'