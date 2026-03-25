# -*- coding: utf-8 -*-
{
    'name': 'Transport - Bureau d\'Ordre',
    'version': '19.0.1.0.0',
    'category': 'Transport',
    'summary': 'Gestion du courrier arrivée et départ - Bureau d\'Ordre',
    'description': """
        Module Bureau d'Ordre (BOC) pour la gestion du courrier :
        - Courrier Arrivée (interne et externe)
        - Courrier Départ
        - Diffusion aux services
        - Suivi des délais et alertes
        - Rapports et éditions
    """,
    'author': 'ERP Transport',
    'depends': ['base', 'mail', 'hr'],
    'license': 'LGPL-3',
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/boc_config_views.xml',
        'views/boc_arrivee_views.xml',
        'views/boc_depart_views.xml',
        'views/boc_transmission_views.xml',
        'reports/rapport_boc.xml',
        'reports/rapport_boc_bordereau.xml',
        'reports/boc_wizard_rapport_delais_views.xml',
        'views/boc_menu_views.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}