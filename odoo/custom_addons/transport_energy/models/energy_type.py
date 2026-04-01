# -*- coding: utf-8 -*-
from odoo import models, fields


class TransportEnergyType(models.Model):
    _name = 'transport.energy.type'
    _description = 'Type energie (carburant, lubrifiant, autre)'
    _order = 'category, name'

    name = fields.Char(string='Nom', required=True, translate=False)
    category = fields.Selection([
        ('fuel',       'Carburant'),
        ('lubrifiant', 'Lubrifiant'),
        ('autre',      'Autre'),
    ], string='Categorie', required=True)
    unite = fields.Char(string='Unite de mesure', default='Litre', translate=False)
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes', translate=False)
