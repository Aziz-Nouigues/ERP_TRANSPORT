# -*- coding: utf-8 -*-
from odoo import models, fields, api


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

    # Unité de mesure de base (toujours en litres pour les liquides)
    unite = fields.Char(
        string='Unite de mesure (base)',
        default='Litre',
        translate=False,
        help="Unite de stockage et de calcul. Toujours en Litre pour les lubrifiants."
    )

    # Conditionnement physique (bidon, fut, cartouche, ...)
    # Si renseigné, le stock peut être saisi en unités de conditionnement
    conditionnement = fields.Char(
        string='Conditionnement',
        translate=False,
        help="Unité physique de conditionnement. Ex: Bidon, Fut, Cartouche. "
             "Laisser vide si vendu au litre directement."
    )
    volume_conditionnement = fields.Float(
        string='Volume par unité (L)',
        digits=(8, 2),
        default=0.0,
        help="Volume en litres contenu dans une unité de conditionnement. "
             "Ex: 1 Bidon = 10 L → saisir 10. "
             "Si 0 ou vide, pas de conditionnement géré."
    )

    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes', translate=False)

    @property
    def has_conditionnement(self):
        """Retourne True si ce type a un conditionnement défini."""
        return bool(self.conditionnement and self.volume_conditionnement > 0)

    def litres_vers_unites(self, litres):
        """Convertit des litres en nombre d'unités de conditionnement."""
        self.ensure_one()
        if self.has_conditionnement:
            return litres / self.volume_conditionnement
        return litres

    def unites_vers_litres(self, unites):
        """Convertit des unités de conditionnement en litres."""
        self.ensure_one()
        if self.has_conditionnement:
            return unites * self.volume_conditionnement
        return unites
