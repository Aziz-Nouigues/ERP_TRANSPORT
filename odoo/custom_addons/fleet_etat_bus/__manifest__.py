# -*- coding: utf-8 -*-
{
    'name': 'Fleet — Parc Véhicules Transport',
    'version': '19.0.3.0.0',
    'category': 'Fleet',
    'summary': 'Menu centralisé dans Fleet : état, compteur, historique de chaque bus',
    'author': 'ERP Transport',
    'depends': ['fleet', 'transport_energy'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'data/fleet_etat_data.xml',
        'views/fleet_vehicle_views.xml',
        'views/wizard_changement_etat_views.xml',
        'views/fleet_parc_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
