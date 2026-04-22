# -*- coding: utf-8 -*-
{
    'name': 'Fleet — État et Cause Bus',
    'version': '19.0.1.0.0',
    'category': 'Fleet',
    'summary': 'Gestion des états de véhicules avec cause, date et historique',
    'description': """
        Extension du module Fleet :
        - Ajout d'une cause obligatoire lors du changement d'état
        - Date de début de l'état en cours
        - Wizard de changement d'état rapide
        - Historique complet des changements d'état par véhicule
    """,
    'author': 'ERP Transport',
    'depends': ['fleet'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'data/fleet_etat_data.xml',
        'views/fleet_vehicle_views.xml',
        'views/wizard_changement_etat_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
