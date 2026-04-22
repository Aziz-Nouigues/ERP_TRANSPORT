# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PatrimoineAmortissementLigne(models.Model):
    """Ligne du tableau d'amortissement d'une immobilisation."""
    _name = 'patrimoine.amortissement.ligne'
    _description = 'Ligne d\'amortissement'
    _order = 'immobilisation_id, annee, date_debut'

    immobilisation_id = fields.Many2one(
        'patrimoine.immobilisation',
        string='Immobilisation',
        required=True,
        ondelete='cascade',
    )
    categorie_id = fields.Many2one(
        'patrimoine.categorie',
        string='Catégorie',
        related='immobilisation_id.categorie_id',
        store=True,
        readonly=True,
    )
    annee = fields.Integer(string='Exercice', required=True)
    date_debut = fields.Date(string='Début période', required=True)
    date_fin = fields.Date(string='Fin période', required=True)
    taux_applique = fields.Float(string='Taux appliqué (%)', digits=(6, 4))
    montant_amortissement = fields.Float(
        string='Dotation (DT)',
        digits=(15, 3),
        required=True,
    )
    amortissements_cumules = fields.Float(
        string='Amort. cumulés (DT)',
        digits=(15, 3),
    )
    valeur_nette = fields.Float(
        string='VNC (DT)',
        digits=(15, 3),
    )
    state = fields.Selection([
        ('brouillon', 'Prévisionnel'),
        ('valide',    'Comptabilisé'),
        ('annule',    'Annulé'),
    ], string='État', default='brouillon', required=True)

    # Lien écriture comptable
    move_id = fields.Many2one(
        'account.move',
        string='Écriture comptable',
        readonly=True,
        copy=False,
    )

    notes = fields.Char(string='Remarques')

    # ═══════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════

    def action_valider(self):
        """Comptabiliser la dotation d'amortissement."""
        for rec in self:
            if rec.state != 'brouillon':
                raise UserError("Seules les lignes prévisionnelles peuvent être comptabilisées.")
            if rec.montant_amortissement <= 0:
                raise UserError("Le montant de la dotation doit être positif.")
            rec._generer_ecriture_dotation()
            rec.state = 'valide'

    def action_annuler(self):
        """Annuler une dotation comptabilisée par extourne comptable."""
        for rec in self:
            if rec.state != 'valide':
                raise UserError("Seules les lignes comptabilisées peuvent être annulées.")
            # Bug 6 FIX — générer une extourne propre plutôt que button_cancel/button_draft
            # qui laisse l'écriture originale orpheline en brouillon sans contrepartie.
            if rec.move_id and rec.move_id.state == 'posted':
                extourne = rec.move_id._reverse_moves(
                    default_values_list=[{
                        'ref': 'Extourne — %s' % (rec.move_id.ref or rec.move_id.name),
                        'date': rec.move_id.date,
                    }]
                )
                extourne.action_post()
            rec.state = 'annule'

    def _generer_ecriture_dotation(self):
        """Génère l'écriture de dotation aux amortissements."""
        self.ensure_one()
        immo = self.immobilisation_id
        cat = immo.categorie_id

        if not cat.compte_dotation_id or not cat.compte_amortissement_id:
            _logger.warning(
                'Comptes dotation/amortissement non configurés pour la catégorie %s', cat.name
            )
            return

        journal = immo.journal_id or self.env['account.journal'].search(
            [('type', '=', 'general')], limit=1
        )
        if not journal:
            return

        libelle = 'Dotation amort. %s — %s [%s]' % (
            self.annee, immo.name, immo.numero_inventaire
        )
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date_fin,
            'ref': libelle,
            'line_ids': [
                (0, 0, {
                    'name': libelle,
                    'account_id': cat.compte_dotation_id.id,
                    'debit': self.montant_amortissement,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': libelle,
                    'account_id': cat.compte_amortissement_id.id,
                    'debit': 0.0,
                    'credit': self.montant_amortissement,
                }),
            ],
        })
        move.action_post()
        self.move_id = move.id


class PatrimoineDepreciation(models.Model):
    """
    Dépréciation de valeur d'une immobilisation (perte de valeur exceptionnelle).
    Impact comptable et modification de la base amortissable.
    """
    _name = 'patrimoine.depreciation'
    _description = 'Dépréciation d\'immobilisation'
    _inherit = ['mail.thread']
    _order = 'date desc'

    immobilisation_id = fields.Many2one(
        'patrimoine.immobilisation',
        string='Immobilisation',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Date de dépréciation',
        required=True,
        default=fields.Date.today,
    )
    montant = fields.Float(
        string='Montant dépréciation (DT)',
        required=True,
        digits=(15, 3),
    )
    motif = fields.Char(string='Motif de dépréciation', required=True)
    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('valide',    'Validé'),
        ('annule',    'Annulé'),
    ], string='État', default='brouillon', tracking=True)
    move_id = fields.Many2one('account.move', string='Écriture', readonly=True, copy=False)

    @api.constrains('montant')
    def _check_montant(self):
        for rec in self:
            if rec.montant <= 0:
                raise ValidationError("Le montant de dépréciation doit être positif.")

    def action_valider(self):
        for rec in self:
            cat = rec.immobilisation_id.categorie_id
            if cat.compte_depreciation_id:
                journal = rec.immobilisation_id.journal_id or self.env['account.journal'].search(
                    [('type', '=', 'general')], limit=1
                )
                if journal:
                    libelle = 'Dépréciation — %s [%s]' % (
                        rec.immobilisation_id.name, rec.immobilisation_id.numero_inventaire
                    )
                    # Bug 9 FIX — la contrepartie d'une dépréciation est le compte de provision
                    # pour dépréciation (compte_provision_depreciation_id, ex: 29xx), et NON le compte
                    # d'amortissement cumulé (28xx). Ce sont deux mécanismes comptables distincts :
                    # amortissement = dépréciation irréversible planifiée (28xx)
                    # dépréciation = perte de valeur exceptionnelle réversible (29xx)
                    # Écriture : Débit 68xx (charge dépréciation) / Crédit 29xx (provision)
                    compte_provision = cat.compte_provision_depreciation_id or cat.compte_amortissement_id
                    move = self.env['account.move'].create({
                        'journal_id': journal.id,
                        'date': rec.date,
                        'ref': libelle,
                        'line_ids': [
                            (0, 0, {'name': libelle, 'account_id': cat.compte_depreciation_id.id,
                                    'debit': rec.montant, 'credit': 0.0}),
                            (0, 0, {'name': libelle,
                                    'account_id': compte_provision.id,
                                    'debit': 0.0, 'credit': rec.montant}),
                        ],
                    })
                    move.action_post()
                    rec.move_id = move.id
            rec.state = 'valide'


class PatrimoineDepensePosterieure(models.Model):
    """
    Dépense postérieure activée qui augmente la base amortissable de l'immobilisation.
    Ex: grosse réparation, amélioration, extension.
    """
    _name = 'patrimoine.depense.posterieure'
    _description = 'Dépense postérieure activée'
    _inherit = ['mail.thread']
    _order = 'date desc'

    immobilisation_id = fields.Many2one(
        'patrimoine.immobilisation',
        string='Immobilisation',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Désignation', required=True)
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
    )
    montant = fields.Float(
        string='Montant (DT)',
        required=True,
        digits=(15, 3),
    )
    nature = fields.Selection([
        ('grosse_reparation', 'Grosse réparation'),
        ('amelioration',      'Amélioration / Extension'),
        ('remplacement',      'Remplacement de composant'),
        ('autre',             'Autre'),
    ], string='Nature', required=True, default='grosse_reparation')
    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('valide',    'Validé'),
    ], string='État', default='brouillon', tracking=True)
    facture_id = fields.Many2one('account.move', string='Facture rattachée')
    notes = fields.Text(string='Notes')

    def action_valider(self):
        for rec in self:
            rec.state = 'valide'
            # Recalculer le tableau d'amortissement
            rec.immobilisation_id.action_generer_tableau_amortissement()
