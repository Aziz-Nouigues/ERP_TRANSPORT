# -*- coding: utf-8 -*-
from odoo import models, fields


class AssuranceType(models.Model):
    """Types de polices d'assurance — bus et chauffeurs.

    Les types obligatoires légalement (Tunisie) déclenchent
    des contrôles automatiques à l'expiration.
    """
    _name = 'transport.assurance.type'
    _description = 'Type de police d\'assurance'
    _order = 'sequence, name'

    name = fields.Char(string='Libellé', required=True, translate=True)
    code = fields.Char(string='Code', size=20, required=True)
    sequence = fields.Integer(string='Séquence', default=10)
    active = fields.Boolean(default=True)

    # ── CATÉGORIE ────────────────────────────────────────────────
    categorie = fields.Selection([
        ('bus',      'Bus / Véhicule'),
        ('chauffeur', 'Chauffeur / Personnel'),
        ('both',     'Bus et chauffeur'),
    ], string='Catégorie', required=True, default='bus')

    # ── OBLIGATION LÉGALE ────────────────────────────────────────
    is_obligatoire = fields.Boolean(
        string='Obligatoire légalement',
        default=False,
        help='Si coché, l\'expiration de cette police sans renouvellement '
             'bloque le bus dans le module Exploitation (règle Tunisie).'
    )
    base_legale = fields.Char(
        string='Base légale',
        help='Référence réglementaire (ex : Décret n° X du JJ/MM/AAAA)'
    )
    description = fields.Text(string='Description', translate=True)
    notes = fields.Text(string='Notes internes')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Le code type police doit être unique.')
    ]

    def name_get(self):
        result = []
        for rec in self:
            label = rec.name
            if rec.is_obligatoire:
                label += ' ★'
            result.append((rec.id, label))
        return result
