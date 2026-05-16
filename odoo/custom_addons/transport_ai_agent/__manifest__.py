{
    'name': 'Transport IA Agent',
    'version': '19.0.1.0.0',
    'category': 'Transport',
    'summary': 'Agent IA conversationnel pour ERP Transport Terrestre',
    'description': """
        Module d'intégration de l'agent IA dans l'ERP Transport.
        Permet aux utilisateurs de poser des questions en français
        directement depuis l'interface Odoo.
    """,
    'author': 'ERP Transport Tunisie',
    'depends': ['base', 'web', 'mail',
            'fleet_etat_bus',
            'transport_exploitation',
            'transport_assurance',
            'transport_energy',
            'transport_patrimoine',
            'transport_boc'],
    'data': [
        'security/ir.model.access.csv',
        'views/ai_chat_views.xml',
        'views/ai_chat_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'transport_ai_agent/static/src/css/ai_chat.css',
            'transport_ai_agent/static/src/xml/ai_chat.xml',
            'transport_ai_agent/static/src/js/ai_chat.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}