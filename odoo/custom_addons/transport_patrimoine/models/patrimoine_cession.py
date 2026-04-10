# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PatrimoineCession(models.Model):
    """
    Sortie d'une immobilisation : cession ou mise en rebut.
    Calcule et comptabilise automatiquement :
    - La dotation d'amortissement complémentaire
    - La sortie de l'actif
    - La perte ou le gain sur cession
    """
    _name = 'patrimoine.cession'
    _description = 'Cession / Sortie d\'immobilisation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(
        string='N° Sortie',
        readonly=True,
        copy=False,
        default='Nouveau',
    )
    type_sortie = fields.Selection([
        ('cession', 'Cession (vente)'),
        ('rebut',   'Mise en rebut / Destruction'),
        ('echange', 'Échange'),
        ('don',     'Don / Abandon'),
    ], string='Type de sortie', required=True, default='cession', tracking=True)

    immobilisation_id = fields.Many2one(
        'patrimoine.immobilisation',
        string='Immobilisation',
        required=True,
        ondelete='restrict',
        domain=[('statut', 'in', ('en_service', 'hors_service'))],
        tracking=True,
    )
    numero_inventaire = fields.Char(
        related='immobilisation_id.numero_inventaire',
        store=True, readonly=True,
    )
    date = fields.Date(
        string='Date de sortie',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    motif = fields.Char(string='Motif', required=True)

    # Valeurs financières
    cout_entree = fields.Float(
        string='Coût d\'entrée (DT)',
        related='immobilisation_id.cout_entree',
        store=True, readonly=True,
        digits=(15, 3),
    )
    amortissements_cumules = fields.Float(
        string='Amort. cumulés à la date (DT)',
        digits=(15, 3),
        readonly=True,
        compute='_compute_valeurs',
        store=True,
    )
    dotation_complementaire = fields.Float(
        string='Dotation complémentaire (DT)',
        digits=(15, 3),
        compute='_compute_valeurs',
        store=True,
        help='Dotation pour la période entre le dernier amortissement et la date de sortie',
    )
    vnc_sortie = fields.Float(
        string='VNC à la date de sortie (DT)',
        digits=(15, 3),
        compute='_compute_valeurs',
        store=True,
    )
    prix_cession = fields.Float(
        string='Prix de cession (DT)',
        digits=(15, 3),
        default=0.0,
    )
    plus_moins_value = fields.Float(
        string='Plus/Moins-value (DT)',
        digits=(15, 3),
        compute='_compute_plus_value',
        store=True,
    )
    type_resultat = fields.Selection([
        ('gain', 'Plus-value'),
        ('perte', 'Moins-value / Perte'),
        ('neutre', 'Neutre'),
    ], string='Résultat', compute='_compute_plus_value', store=True)

    state = fields.Selection([
        ('brouillon',  'Brouillon'),
        ('confirme',   'Confirmé'),
        ('comptabilise', 'Comptabilisé'),
        ('annule',     'Annulé'),
    ], string='État', default='brouillon', tracking=True)

    # Écritures
    move_dotation_id = fields.Many2one('account.move', string='Écriture dotation complémentaire', readonly=True)
    move_sortie_id = fields.Many2one('account.move', string='Écriture sortie actif', readonly=True)

    acheteur_id = fields.Many2one('res.partner', string='Acquéreur / Repreneur')
    notes = fields.Text(string='Observations')

    # ═══════════════════════════════════════════════════════════
    # COMPUTE
    # ═══════════════════════════════════════════════════════════

    @api.depends('immobilisation_id', 'date')
    def _compute_valeurs(self):
        for rec in self:
            immo = rec.immobilisation_id
            if not immo:
                rec.amortissements_cumules = 0.0
                rec.dotation_complementaire = 0.0
                rec.vnc_sortie = 0.0
                continue

            amort_cumule = immo.amortissements_cumules

            # Calculer la dotation complémentaire (pro-rata jours)
            dotation_comp = 0.0
            if immo.date_mise_en_service and rec.date:
                # Dernière ligne validée
                dernier_amorti = immo.ligne_amortissement_ids.filtered(
                    lambda l: l.state == 'valide'
                )
                if dernier_amorti:
                    derniere_date = max(dernier_amorti.mapped('date_fin'))
                    if rec.date > derniere_date and immo.duree_amortissement:
                        jours_periode = (rec.date - derniere_date).days
                        dotation_annuelle = immo.base_amortissable / immo.duree_amortissement
                        dotation_comp = dotation_annuelle * jours_periode / 365.0
                        dotation_comp = min(dotation_comp, immo.base_amortissable - amort_cumule)
                        dotation_comp = max(dotation_comp, 0.0)

            rec.amortissements_cumules = amort_cumule
            rec.dotation_complementaire = round(dotation_comp, 3)
            rec.vnc_sortie = max(
                immo.cout_entree - amort_cumule - dotation_comp, 0.0
            )

    @api.depends('prix_cession', 'vnc_sortie', 'type_sortie')
    def _compute_plus_value(self):
        for rec in self:
            if rec.type_sortie == 'rebut':
                rec.plus_moins_value = -rec.vnc_sortie
                rec.type_resultat = 'perte' if rec.vnc_sortie > 0 else 'neutre'
            else:
                rec.plus_moins_value = rec.prix_cession - rec.vnc_sortie
                if rec.plus_moins_value > 0.001:
                    rec.type_resultat = 'gain'
                elif rec.plus_moins_value < -0.001:
                    rec.type_resultat = 'perte'
                else:
                    rec.type_resultat = 'neutre'

    # ═══════════════════════════════════════════════════════════
    # ORM
    # ═══════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('patrimoine.cession') or 'Nouveau'
                )
        return super().create(vals_list)

    # ═══════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════

    def action_confirmer(self):
        for rec in self:
            if rec.state != 'brouillon':
                raise UserError("Seules les cessions en brouillon peuvent être confirmées.")
            rec.state = 'confirme'

    def action_comptabiliser(self):
        """Générer toutes les écritures comptables de sortie."""
        for rec in self:
            if rec.state != 'confirme':
                raise UserError("Veuillez d'abord confirmer la cession.")
            rec._comptabiliser_sortie()
            # Changer le statut de l'immobilisation
            rec.immobilisation_id.write({
                'statut': 'rebut' if rec.type_sortie == 'rebut' else 'cede',
                'date_cession': rec.date if rec.type_sortie != 'rebut' else rec.immobilisation_id.date_cession,
                'date_rebut': rec.date if rec.type_sortie == 'rebut' else rec.immobilisation_id.date_rebut,
            })
            rec.state = 'comptabilise'

    def action_annuler(self):
        for rec in self:
            if rec.state == 'comptabilise':
                raise UserError("Une cession comptabilisée ne peut pas être annulée directement. Créez une extourne.")
            # Remettre l'immobilisation en service
            if rec.immobilisation_id.statut in ('cede', 'rebut'):
                rec.immobilisation_id.statut = 'en_service'
            rec.state = 'annule'

    def _comptabiliser_sortie(self):
        """Génère les écritures comptables de la sortie."""
        self.ensure_one()
        immo = self.immobilisation_id
        cat = immo.categorie_id
        journal = immo.journal_id or self.env['account.journal'].search(
            [('type', '=', 'general')], limit=1
        )

        # B3 FIX — Vérifications préalables des comptes obligatoires
        erreurs = []
        if not journal:
            erreurs.append("Aucun journal comptable général disponible.")
        if not cat.compte_immobilisation_id:
            erreurs.append("Compte immobilisation non configuré sur la catégorie '%s'." % cat.name)
        if not cat.compte_amortissement_id:
            erreurs.append("Compte amortissements cumulés non configuré sur la catégorie '%s'." % cat.name)
        if self.type_sortie != 'rebut' and self.prix_cession > 0 and not cat.compte_cession_id:
            erreurs.append(
                "Compte produit de cession non configuré sur la catégorie '%s' "
                "(requis car prix de cession = %.3f DT)." % (cat.name, self.prix_cession)
            )
        if self.plus_moins_value < 0 and not cat.compte_perte_id:
            erreurs.append(
                "Compte perte sur cession non configuré sur la catégorie '%s' "
                "(requis car moins-value = %.3f DT)." % (cat.name, abs(self.plus_moins_value))
            )
        if self.plus_moins_value > 0 and not cat.compte_cession_id:
            erreurs.append(
                "Compte produit de cession non configuré sur la catégorie '%s' "
                "(requis car plus-value = %.3f DT)." % (cat.name, self.plus_moins_value)
            )
        if erreurs:
            raise UserError(
                "Impossible de comptabiliser la sortie — configuration incomplète :\n\n"
                + "\n".join("• " + e for e in erreurs)
            )

        # 1. Écriture dotation complémentaire
        if self.dotation_complementaire > 0 and cat.compte_dotation_id and cat.compte_amortissement_id:
            libelle_dot = 'Dotation complémentaire sortie — %s [%s]' % (immo.name, immo.numero_inventaire)
            move_dot = self.env['account.move'].create({
                'journal_id': journal.id,
                'date': self.date,
                'ref': libelle_dot,
                'line_ids': [
                    (0, 0, {'name': libelle_dot, 'account_id': cat.compte_dotation_id.id,
                            'debit': self.dotation_complementaire, 'credit': 0.0}),
                    (0, 0, {'name': libelle_dot, 'account_id': cat.compte_amortissement_id.id,
                            'debit': 0.0, 'credit': self.dotation_complementaire}),
                ],
            })
            move_dot.action_post()
            self.move_dotation_id = move_dot

        # 2. Écriture sortie actif
        libelle_sortie = '%s — %s [%s]' % (
            'Mise en rebut' if self.type_sortie == 'rebut' else 'Cession',
            immo.name, immo.numero_inventaire
        )
        amort_total = self.amortissements_cumules + self.dotation_complementaire
        lines = []

        # B3 FIX — Débit amortissements cumulés (compte 28xx) — jamais fallback sur le compte actif
        lines.append((0, 0, {
            'name': libelle_sortie,
            'account_id': cat.compte_amortissement_id.id,
            'debit': amort_total,
            'credit': 0.0,
        }))

        # Perte ou gain sur sortie
        if self.plus_moins_value < 0:
            lines.append((0, 0, {
                'name': libelle_sortie + ' — moins-value',
                'account_id': cat.compte_perte_id.id,
                'debit': abs(self.plus_moins_value),
                'credit': 0.0,
            }))
        elif self.plus_moins_value > 0:
            lines.append((0, 0, {
                'name': libelle_sortie + ' — plus-value',
                'account_id': cat.compte_cession_id.id,
                'debit': 0.0,
                'credit': self.plus_moins_value,
            }))

        # Produit de cession (prix encaissé ou à encaisser)
        if self.prix_cession > 0:
            lines.append((0, 0, {
                'name': 'Produit cession %s' % immo.numero_inventaire,
                'account_id': cat.compte_cession_id.id,
                'debit': 0.0,
                'credit': self.prix_cession,
            }))

        # Sortie de l'actif brut au coût d'entrée (crédit compte immobilisation 2xx)
        lines.append((0, 0, {
            'name': libelle_sortie,
            'account_id': cat.compte_immobilisation_id.id,
            'debit': 0.0,
            'credit': immo.cout_entree,
        }))

        move_sortie = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date,
            'ref': libelle_sortie,
            'line_ids': lines,
        })
        move_sortie.action_post()
        self.move_sortie_id = move_sortie
        _logger.info('Écriture de sortie générée : %s', move_sortie.name)
