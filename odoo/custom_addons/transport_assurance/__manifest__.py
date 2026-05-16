# -*- coding: utf-8 -*-
{
    'name': 'Transport - Assurance',
    'version': '19.0.2.0.0',
    'category': 'Transport',
    'summary': 'Gestion des polices d\'assurance bus et chauffeurs — Blocage tournée si non assuré',
    'description': """
        Module Assurance pour le transport terrestre tunisien.
        - Polices bus : RC (obligatoire), Voyage (obligatoire), Tous risques, Incendie/vol
        - Polices chauffeurs : AT/CNAM, Vie groupe, RC pro, Complémentaire santé
        - Gestion des sinistres avec workflow complet
        - Règles Tunisie : visite technique RC, blocage bus non assuré
        - NOUVEAU : Bus sans assurance valide = bloqué dans l'Exploitation
        - Alertes automatiques J-30 / J-15 / J-7
        - 4 rapports PDF
    """,
    'author': 'ERP Transport',
    'license': 'LGPL-3',
    'depends': [
        'fleet',
        'fleet_etat_bus',
        'transport_exploitation',
        'hr',
        'account',
        'mail',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/assurance_type_data.xml',
        'data/cron.xml',
        'views/assurance_config_views.xml',
        'views/assurance_bus_views.xml',
        'views/assurance_chauffeur_views.xml',
        'views/assurance_sinistre_views.xml',
        'wizard/wizard_renouvellement_views.xml',
        'wizard/wizard_rapport_views.xml',
        'reports/rapport_polices_actives.xml',
        'reports/rapport_echeancier.xml',
        'reports/rapport_sinistres.xml',
        'reports/rapport_bus_non_assures.xml',
        'views/assurance_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
