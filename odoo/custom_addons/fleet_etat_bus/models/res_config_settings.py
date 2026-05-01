# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    """Paramètres de configuration du module fleet_etat_bus.
    Accessibles via Parc auto > Configuration > Paramètres.
    """
    _inherit = 'res.config.settings'

    # Alerte automatique si un bus reste indisponible trop longtemps
    fleet_alerte_immobilisation_jours = fields.Integer(
        string='Alerte immobilisation après (jours)',
        default=7,
        config_parameter='fleet_etat_bus.alerte_immobilisation_jours',
        help='Nombre de jours d\'immobilisation d\'un bus avant de déclencher une alerte '
             'dans le chatter du véhicule. Mettre 0 pour désactiver.'
    )

    # Exiger un motif lors de tout retour en service
    fleet_motif_retour_service_obligatoire = fields.Boolean(
        string='Motif obligatoire au retour en service',
        default=True,
        config_parameter='fleet_etat_bus.motif_retour_service_obligatoire',
        help='Si activé, le wizard de changement d\'état exige un motif détaillé '
             'lors du passage à l\'état "En service".'
    )

    # Rapport PDF auto-imprimé à chaque changement d'état
    fleet_impression_auto_changement = fields.Boolean(
        string='Imprimer fiche à chaque changement d\'état',
        default=False,
        config_parameter='fleet_etat_bus.impression_auto_changement',
        help='Si activé, la fiche état PDF est générée automatiquement '
             'à chaque confirmation du wizard de changement d\'état.'
    )
