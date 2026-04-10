# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class WizardCalculAmortissement(models.TransientModel):
    """
    Wizard de calcul et comptabilisation périodique des dotations.
    Permet de comptabiliser toutes les dotations d'une période donnée
    pour toutes les immobilisations ou une catégorie spécifique.
    """
    _name = 'patrimoine.wizard.calcul.amortissement'
    _description = 'Calcul des dotations aux amortissements'

    # ── FILTRES ──────────────────────────────────────────────────
    annee = fields.Integer(
        string='Exercice comptable',
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    date_arrete = fields.Date(
        string='Date d\'arrêté',
        required=True,
        default=fields.Date.today,
        help='Date de comptabilisation des dotations',
    )
    categorie_id = fields.Many2one(
        'patrimoine.categorie',
        string='Catégorie (optionnel)',
        help='Laisser vide pour traiter toutes les catégories',
    )
    methode_filtre = fields.Selection([
        ('tous',      'Toutes les méthodes'),
        ('lineaire',  'Linéaire uniquement'),
        ('degressif', 'Dégressif uniquement'),
        ('manuel',    'Manuel uniquement'),
    ], string='Méthode', default='tous')

    # ── MODE ─────────────────────────────────────────────────────
    mode = fields.Selection([
        ('simulation', 'Simulation (sans comptabilisation)'),
        ('validation', 'Validation avec comptabilisation'),
    ], string='Mode', required=True, default='simulation')

    # ── RÉSULTATS SIMULATION ─────────────────────────────────────
    nb_lignes = fields.Integer(string='Lignes trouvées', readonly=True)
    montant_total = fields.Float(string='Total dotations (DT)', digits=(15, 3), readonly=True)
    simulation_faite = fields.Boolean(default=False)

    # ═══════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════

    def action_simuler(self):
        """Calculer le total des dotations sans comptabiliser."""
        self.ensure_one()
        lignes = self._get_lignes_a_valider()
        self.nb_lignes = len(lignes)
        self.montant_total = sum(lignes.mapped('montant_amortissement'))
        self.simulation_faite = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_valider(self):
        """Comptabiliser toutes les dotations de la période."""
        self.ensure_one()
        lignes = self._get_lignes_a_valider()
        if not lignes:
            raise UserError(
                "Aucune ligne d'amortissement prévisionnelle trouvée pour "
                "l'exercice %d avec les filtres sélectionnés." % self.annee
            )
        nb = 0
        montant = 0.0
        for ligne in lignes:
            try:
                ligne.action_valider()
                nb += 1
                montant += ligne.montant_amortissement
            except Exception as e:
                _logger.error('Erreur comptabilisation ligne %s : %s', ligne.id, str(e))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Dotations comptabilisées',
                'message': '%d dotations comptabilisées pour un total de %.3f DT.' % (nb, montant),
                'type': 'success',
                'sticky': True,
            }
        }

    def _get_lignes_a_valider(self):
        """Retourne les lignes d'amortissement prévisionnelles de la période.

        A2 FIX — On filtre désormais sur date_fin <= date_arrete (et non sur annee seul)
        pour ne comptabiliser que les dotations réellement échues à la date d'arrêté.
        Cela évite de comptabiliser des dotations futures lors d'un arrêté intermédiaire
        (ex : arrêté au 30/06 ne doit pas valider la dotation dont date_fin = 31/12).
        """
        domain = [
            ('annee', '=', self.annee),
            ('state', '=', 'brouillon'),
            ('date_fin', '<=', self.date_arrete),          # A2 FIX — respect de la date d'arrêté
            ('immobilisation_id.statut', 'in', ('en_service', 'hors_service')),
        ]
        if self.categorie_id:
            domain.append(('categorie_id', '=', self.categorie_id.id))
        if self.methode_filtre != 'tous':
            domain.append(('immobilisation_id.methode_amortissement', '=', self.methode_filtre))

        return self.env['patrimoine.amortissement.ligne'].search(domain)
