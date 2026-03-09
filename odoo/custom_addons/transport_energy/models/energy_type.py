from odoo import models, fields


class TransportEnergyType(models.Model):

    _name = 'transport.energy.type'
    _description = 'Type énergie'
    _order = 'name'

    name = fields.Char(
        string='Nom',
        required=True
    )

    category = fields.Selection([
        ('fuel',  'Carburant'),
        ('lubrifiant', 'Lubrifiant'),
        ('autre',      'Autre'),
    ],
        string='Catégorie',
        required=True,

    )

    unite = fields.Char(
        string='Unité de mesure',
        default='Litre'
    )

    actif = fields.Boolean(
        string='Actif',
        default=True
    )

    notes = fields.Text(
        string='Notes'
    )