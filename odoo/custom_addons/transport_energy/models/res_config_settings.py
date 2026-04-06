# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    """Configuration admin pour le module Transport Energie.
    Accès réservé au Directeur Energie (groupe admin).
    """
    _inherit = 'res.config.settings'

    # ── Rechargement cartes AGILIS ──────────────────────────────────────────
    agilis_montant_max_recharge = fields.Float(
        string='Plafond de rechargement AGILIS (TND)',
        config_parameter='transport_energy.agilis_montant_max_recharge',
        digits=(10, 3),
        help="Montant maximum autorisé par rechargement de carte AGILIS. "
             "Mettre 0 pour désactiver le contrôle.",
    )
    agilis_approbation_obligatoire = fields.Boolean(
        string='Approbation obligatoire pour les rechargements',
        config_parameter='transport_energy.agilis_approbation_obligatoire',
        help="Si activé, chaque rechargement doit être validé par un Responsable "
             "avant d'être pris en compte dans le solde.",
    )
    agilis_solde_minimum_defaut = fields.Float(
        string='Solde minimum par défaut (TND)',
        config_parameter='transport_energy.agilis_solde_minimum_defaut',
        digits=(10, 3),
        help="Valeur par défaut du seuil d'alerte de solde lors de la création "
             "d'une nouvelle carte AGILIS.",
    )
