# -*- coding: utf-8 -*-
{
    'name': 'Transport - Patrimoine & Immobilisations',
    'version': '19.0.2.2.0',
    'category': 'Transport',
    'summary': 'Gestion du patrimoine : immobilisations, amortissements, inventaire, cessions',
    'description': """
        Module Patrimoine-Immobilisations pour la gestion :
        - Fiche immobilisation (catégorie, emplacement, statut, coût)
        - Méthodes d'amortissement : linéaire, dégressif, manuel
        - Entrées : acquisition, échange, livraison à soi-même
        - Dépenses postérieures modifiant la base amortissable
        - Transferts avec historique des emplacements
        - Sorties : cession, rebut avec écritures comptables automatiques
        - Inventaire physique et gestion des écarts
        - 15+ états de restitution et tableaux d'amortissement
        - Intégration comptable complète (account.move)
        - Vues Kanban, Pivot, Graphique
        - Traductions : Français, Arabe
        - Crons automatiques : alertes amortis, inventaire annuel
    """,
    'author': 'ERP Transport',
    'depends': ['base', 'mail', 'hr', 'account', 'purchase', 'stock'],
    'license': 'LGPL-3',
    'data': [
        # Sécurité — en premier
        'security/groups.xml',
        'security/ir.model.access.csv',
        # Données de référence
        'data/sequences.xml',
        'data/patrimoine_config_data.xml',
        'data/cron.xml',
        # Vues configuration
        'views/patrimoine_config_views.xml',
        # Vues principales
        'views/patrimoine_immobilisation_views.xml',
        'views/patrimoine_kanban_views.xml',
        'views/patrimoine_mouvement_views.xml',
        'views/patrimoine_affectation_views.xml',
        'views/patrimoine_inventaire_views.xml',
        'views/patrimoine_cession_views.xml',
        'views/patrimoine_amortissement_views.xml',
        # Wizards
        'wizard/wizard_calcul_amortissement_views.xml',
        'wizard/wizard_rapport_views.xml',
        # Rapports PDF
        'reports/rapport_tableau_amortissement.xml',
        'reports/rapport_inventaire.xml',
        'reports/rapport_acquisitions.xml',
        'reports/rapport_cessions.xml',
        'reports/rapport_variation.xml',
        'reports/rapport_distribution.xml',
        'reports/rapport_manquants.xml',
        # Menu — en dernier (dépend des actions)
        'views/patrimoine_menu_views.xml',
    ],
    'demo': [
        'demo/demo_patrimoine.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
