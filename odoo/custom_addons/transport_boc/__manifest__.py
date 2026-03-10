# -*- coding: utf-8 -*-
{
    'name': "Transport - Bureau d'Ordre",
    'version': '19.0.1.0.0',
    'category': 'Transport',
    'summary': "Gestion du courrier arrivee et depart - Bureau d'Ordre",
    'description': """
        Module Bureau d'Ordre (BOC) pour la gestion du courrier :
        - Courrier Arrivee (interne et externe)
        - Courrier Depart
        - Diffusion aux services
        - Suivi des delais et alertes
        - Rapports et editions
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
        'views/boc_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}