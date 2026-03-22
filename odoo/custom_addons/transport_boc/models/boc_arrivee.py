# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class BocCourrierArrivee(models.Model):
    """Courrier Arrivée — interne et externe"""
    _name = 'boc.courrier.arrivee'
    _description = "Courrier Arrivée"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_arrivee desc, name desc'

    # ── IDENTIFICATION ──────────────────────────────────────────
    name = fields.Char(
        string='Numéro d\'ordre',
        readonly=True,
        copy=False,
        default='Nouveau',
    )
    annee_exercice = fields.Char(
        string='Année d\'exercice',
        default=lambda self: str(fields.Date.today().year),
    )

    # ── TYPE ET NATURE ───────────────────────────────────────────
    type_arrivee = fields.Selection([
        ('externe', 'Externe'),
        ('interne', 'Interne'),
    ], string='Type d\'arrivée', required=True, default='externe',
       tracking=True)

    type_courrier_id = fields.Many2one(
        'boc.type.courrier',
        string='Nature du courrier',
        required=True,
        tracking=True,
    )

    # ── DATES ────────────────────────────────────────────────────
    date_arrivee = fields.Datetime(
        string='Date / Heure d\'arrivée',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    date_courrier = fields.Date(
        string='Date du courrier',
        tracking=True,
    )
    date_echeance = fields.Date(
        string='Date d\'échéance',
        tracking=True,
        help='Date limite de traitement/réponse',
    )
    date_rappel = fields.Date(
        string='Date de rappel',
        compute='_compute_date_rappel',
        store=True,
        help='Rappel automatique à mi-délai',
    )

    # ── EXPÉDITEUR ───────────────────────────────────────────────
    organisme_id = fields.Many2one(
        'boc.organisme',
        string='Expéditeur',
        tracking=True,
    )
    expediteur_nom = fields.Char(
        string='Nom expéditeur',
        translate=True,
        help='Si l\'expéditeur n\'est pas dans la liste des organismes',
    )
    reference_expediteur = fields.Char(
        string='Référence expéditeur',
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
    annotation_id = fields.Many2one(
        'boc.annotation',
        string='Annotation',
    )

    # ── POUR LES FACTURES ────────────────────────────────────────
    est_facture = fields.Boolean(
        string='C\'est une facture',
        compute='_compute_est_facture',
        store=True,
    )
    reference_facture = fields.Char(
        string='Référence facture',
    )
    montant_facture = fields.Float(
        string='Montant facture (DT)',
        digits=(12, 3),
    )
    fournisseur = fields.Char(
        string='Fournisseur',
    )

    # ── ÉTAT ─────────────────────────────────────────────────────
    state = fields.Selection([
        ('brouillon',  'Brouillon'),
        ('enregistre', 'Enregistré'),
        ('diffuse',    'Diffusé'),
        ('traite',     'Traité'),
        ('classe',     'Classé'),
    ], string='État', default='brouillon', tracking=True)

    necessite_reponse = fields.Boolean(
        string='Nécessite une réponse',
        default=False,
        tracking=True,
    )
    reponse_fournie = fields.Boolean(
        string='Réponse fournie',
        default=False,
        tracking=True,
    )
    date_reponse = fields.Date(
        string='Date de réponse',
    )
    depart_reponse_id = fields.Many2one(
        'boc.courrier.depart',
        string='Courrier départ (réponse)',
    )

    # ── DIFFUSION ────────────────────────────────────────────────
    transmission_ids = fields.One2many(
        'boc.transmission',
        'arrivee_id',
        string='Diffusions',
    )
    nb_transmissions = fields.Integer(
        string='Nb diffusions',
        compute='_compute_nb_transmissions',
    )


    # ── PIÈCES JOINTES (géré par mail.thread) ────────────────────
    # Les PJ sont accessibles via le chatter standard d'Odoo

    # ── GED (Gestion Électronique des Documents) ─────────────────
    # Intégration avec une GED externe open source (Alfresco, Mayan EDMS, Nextcloud…)
    # La mise en place de la GED ne fait pas partie du présent marché.
    # Ces champs permettent le lien entre le courrier et le document archivé dans la GED.
    ged_document_ref = fields.Char(
        string='Référence GED',
        copy=False,
        help='Identifiant / référence du document dans la GED externe',
    )
    ged_url = fields.Char(
        string='Lien GED',
        copy=False,
        help='URL direct vers le document archivé dans la GED externe',
    )
    ged_archive_date = fields.Date(
        string='Date archivage GED',
        copy=False,
        readonly=True,
        help='Date à laquelle le document a été archivé dans la GED',
    )
    ged_archive_status = fields.Selection([
        ('non_archive', 'Non archivé'),
        ('archive',     'Archivé'),
        ('restaure',    'Restauré'),
    ], string='Statut GED',
       default='non_archive',
       copy=False,
       tracking=True,
    )

    def action_ouvrir_ged(self):
        """Ouvrir le document dans la GED externe"""
        self.ensure_one()
        if not self.ged_url:
            raise ValidationError(
                "Aucun lien GED n'est renseigné pour ce courrier.\n"
                "Veuillez d'abord archiver le document dans la GED et renseigner le lien."
            )
        return {
            'type': 'ir.actions.act_url',
            'url': self.ged_url,
            'target': 'new',
        }

    def action_marquer_archive_ged(self):
        """Marquer le courrier comme archivé dans la GED"""
        for rec in self:
            if not rec.ged_document_ref:
                raise ValidationError(
                    "Veuillez renseigner la référence GED avant de marquer comme archivé."
                )
            rec.write({
                'ged_archive_status': 'archive',
                'ged_archive_date': fields.Date.today(),
            })

    def action_restaurer_ged(self):
        """Marquer le document comme restauré depuis la GED"""
        for rec in self:
            rec.write({'ged_archive_status': 'restaure'})

    # ── ALERTES ──────────────────────────────────────────────────
    en_retard = fields.Boolean(
        string='En retard',
        compute='_compute_en_retard',
        store=True,
    )
    jours_restants = fields.Integer(
        string='Jours restants',
        compute='_compute_en_retard',
        store=True,
    )

    # ═══════════════════════════════════════════════════════════
    # COMPUTE METHODS
    # ═══════════════════════════════════════════════════════════

    @api.depends('type_courrier_id')
    def _compute_est_facture(self):
        for rec in self:
            rec.est_facture = (
                rec.type_courrier_id and
                'facture' in (rec.type_courrier_id.name or '').lower()
            )

    @api.depends('date_arrivee', 'date_echeance')
    def _compute_date_rappel(self):
        """Rappel à mi-délai entre date arrivée et date échéance"""
        for rec in self:
            if rec.date_arrivee and rec.date_echeance:
                date_arr = rec.date_arrivee.date()
                date_ech = rec.date_echeance
                delta = (date_ech - date_arr).days
                rec.date_rappel = date_arr + \
                    __import__('datetime').timedelta(days=delta // 2)
            else:
                rec.date_rappel = False

    @api.depends('date_echeance', 'state')
    def _compute_en_retard(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_echeance and rec.state not in ('traite', 'classe'):
                delta = (rec.date_echeance - today).days
                rec.jours_restants = delta
                rec.en_retard = delta < 0
            else:
                rec.jours_restants = 0
                rec.en_retard = False

    @api.depends('transmission_ids')
    def _compute_nb_transmissions(self):
        for rec in self:
            rec.nb_transmissions = len(rec.transmission_ids)

    # ═══════════════════════════════════════════════════════════
    # ONCHANGE
    # ═══════════════════════════════════════════════════════════

    @api.onchange('sujet_id')
    def _onchange_sujet_id(self):
        if self.sujet_id:
            self.sujet = self.sujet_id.name

    # ═══════════════════════════════════════════════════════════
    # CONTRAINTES
    # ═══════════════════════════════════════════════════════════

    @api.constrains('date_courrier', 'date_arrivee')
    def _check_date_courrier(self):
        """La date du courrier ne doit pas être postérieure à la date d'arrivée"""
        for rec in self:
            if rec.date_courrier and rec.date_arrivee:
                if rec.date_courrier > rec.date_arrivee.date():
                    raise ValidationError(
                        "La date du courrier (%s) ne peut pas être "
                        "postérieure à la date d'arrivée (%s)."
                        % (rec.date_courrier, rec.date_arrivee.date())
                    )

    @api.constrains('reference_facture', 'fournisseur', 'montant_facture')
    def _check_doublon_facture(self):
        """Alerte si une facture identique existe déjà"""
        for rec in self:
            if not rec.est_facture or not rec.reference_facture:
                continue
            doublon = self.search([
                ('reference_facture', '=', rec.reference_facture),
                ('fournisseur', '=', rec.fournisseur),
                ('id', '!=', rec.id),
            ], limit=1)
            if doublon:
                raise ValidationError(
                    "⚠️ Doublon détecté !\n"
                    "Une facture avec la référence '%s' du fournisseur '%s' "
                    "existe déjà (N° %s).\n"
                    "Risque de double facturation !"
                    % (rec.reference_facture, rec.fournisseur, doublon.name)
                )

    # ═══════════════════════════════════════════════════════════
    # ACTIONS WORKFLOW
    # ═══════════════════════════════════════════════════════════

    def action_enregistrer(self):
        """Enregistrement officiel — génère le numéro d'ordre"""
        for rec in self:
            if rec.name == 'Nouveau':
                rec.name = self.env['ir.sequence'].next_by_code(
                    'boc.courrier.arrivee'
                )
            rec.state = 'enregistre'

    def action_diffuser(self):
        """Marquer comme diffusé aux services"""
        for rec in self:
            rec.state = 'diffuse'

    def action_traiter(self):
        """Marquer comme traité"""
        for rec in self:
            rec.state = 'traite'
            rec.reponse_fournie = True
            rec.date_reponse = fields.Date.today()

    def action_classer(self):
        """Archiver / Classer le courrier"""
        for rec in self:
            rec.state = 'classe'

    def action_reset(self):
        """Remettre en brouillon"""
        for rec in self:
            rec.state = 'brouillon'