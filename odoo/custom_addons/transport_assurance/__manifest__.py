# -*- coding: utf-8 -*-
{
    'name': 'Transport - Assurance',
    'version': '19.0.1.0.0',
    'category': 'Transport',
    'summary': 'Gestion des polices d\'assurance bus et chauffeurs, sinistres, alertes Tunisie',
    'description': """
        Module Assurance pour le transport terrestre tunisien.

        Fonctionnalités :
        - Référentiel compagnies d'assurance et types de polices
        - Polices bus (hérite fleet.vehicle.log.contract) :
            RC, Tous risques, Voyage/passagers, Incendie/vol
        - Polices chauffeurs (hr.employee) :
            AT/CNAM, Vie groupe, RC pro, Complémentaire santé
        - Gestion des sinistres avec workflow complet
        - Règles métier Tunisie :
            * RC + Voyage obligatoires pour tout bus en service
            * Vérification visite technique avant renouvellement RC
            * Blocage automatique du bus dans l'Exploitation si RC expirée
        - Alertes automatiques d'échéance (J-30 / J-15 / J-7)
        - Rapport « Bus non assurés » — alerte légale critique
        - 6 états PDF : polices actives, échéancier, coût, sinistres,
          taux sinistralité, bus non assurés
    """,
    'author': 'ERP Transport',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'fleet',
        'fleet_etat_bus',       # fleet.vehicle étendu + états bus
        'transport_patrimoine',  # patrimoine.immobilisation
        'hr',
        'account',
        'mail',
        # transport_exploitation est optionnel :
        # le module s'installe sans lui.
        # Les contraintes liées à l'exploitation utilisent
        # un guard runtime (if 'transport.exploitation.tournee' in self.env).
    ],
    'data': [
        # ── Sécurité (en premier) ──
        'security/groups.xml',
        'security/ir.model.access.csv',
        # ── Données de référence ──
        'data/sequences.xml',
        'data/assurance_type_data.xml',
        'data/cron.xml',
        # ── Configuration ──
        'views/assurance_config_views.xml',
        # ── Vues principales ──
        'views/assurance_compagnie_views.xml',
        'views/assurance_bus_views.xml',
        'views/assurance_chauffeur_views.xml',
        'views/assurance_sinistre_views.xml',
        # ── Wizards ──
        'wizard/wizard_renouvellement_views.xml',
        'wizard/wizard_rapport_views.xml',
        # ── Rapports PDF ──
        'reports/rapport_polices_actives.xml',
        'reports/rapport_echeancier.xml',
        'reports/rapport_sinistres.xml',
        'reports/rapport_bus_non_assures.xml',
        # ── Menus (en dernier) ──
        'views/assurance_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
