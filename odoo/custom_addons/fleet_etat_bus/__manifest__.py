# -*- coding: utf-8 -*-
{
    'name': 'Fleet — Parc Véhicules Transport Terrestre',
    'version': '19.0.4.1.0',
    'category': 'Fleet',
    'summary': 'Gestion avancée des états, historique, Kanban et rapport PDF pour le parc bus',
    'description': """
        Module de personnalisation du module Fleet standard d'Odoo 19
        pour la gestion du parc de véhicules de transport terrestre.

        Fonctionnalités :
        - Suivi des états (En service, En panne, En maintenance, Hors service, Réformé)
        - Historique complet avec cause, priorité, durée et responsable
        - Wizard de changement d'état avec alerte tournées impactées
        - Vue Kanban du parc regroupée par état
        - Rapport PDF "Fiche état véhicule" avec historique et signature
        - Tags (étiquettes) sur les véhicules
        - Page Paramètres dédiée (seuils d'alerte, règles d'impression)
        - Hook post-installation : initialise l'historique des véhicules existants

        Correctifs v4.1.0 :
        - state_duree_jours : store=True (tri/filtre SQL opérationnel)
        - nb_historique : depends sur sous-champ .id (recalcul correct)
        - Guard sur transport.exploitation.tournee (module optionnel)
        - Suppression de la redondance "Changements d'état" dans la fiche
        - Restructuration de la fiche : bandeaux d'alerte + sections ordonnées
    """,
    'author': 'ERP Transport',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'fleet',
        'transport_energy',
        # 'transport_exploitation',  # Optionnel — décommentez si installé
        # Le wizard utilise 'transport.exploitation.tournee' avec un guard
        # runtime (if 'transport.exploitation.tournee' in self.env) pour
        # ne pas bloquer l'installation si ce module est absent.
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/fleet_etat_data.xml',
        'views/fleet_vehicle_views.xml',
        'views/fleet_kanban_view.xml',
        'views/wizard_changement_etat_views.xml',
        'views/res_config_settings_views.xml',
        'views/fleet_parc_menus.xml',
        'views/fleet_vehicle_assurance_views.xml',
        'reports/report_fleet_etat_vehicle.xml',
    ],
    'assets': {},
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
