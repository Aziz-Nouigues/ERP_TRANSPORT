from odoo import models, fields


class TransportEnergyType(models.Model):

    _name = 'transport.energy.type'
    _description = 'Type énergie'
    _order = 'name'

    name = fields.Char(
        string='Nom',
        required=True,
        translate=False,
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
        default='Litre',
        translate=False,
    )

    active = fields.Boolean(
        string='Actif',
        default=True,
    )

    notes = fields.Text(
        string='Notes',
        translate=False,
    )

    def _auto_init(self):
        res = super()._auto_init()
        # Convertit jsonb -> varchar si nécessaire après chaque update
        self.env.cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'transport_energy_type' AND column_name = 'name'
        """)
        row = self.env.cr.fetchone()
        if row and row[0] == 'jsonb':
            self.env.cr.execute("""
                ALTER TABLE transport_energy_type
                ALTER COLUMN name TYPE varchar
                USING (name::jsonb->>'en_US');
            """)
            self.env.cr.execute("""
                ALTER TABLE transport_energy_type
                ALTER COLUMN unite TYPE varchar
                USING (unite::jsonb->>'en_US');
            """)
        return res