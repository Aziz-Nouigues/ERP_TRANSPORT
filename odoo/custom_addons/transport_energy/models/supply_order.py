# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TransportSupplyOrder(models.Model):
    """Commande et reception de carburant citerne vers une cuve interne.
    C'est le seul chemin autorise pour crediter le stock d'une cuve.
    A la validation, le stock de la cuve est incremente via _add_stock().
    """
    _name = 'transport.supply.order'
    _description = 'Approvisionnement citerne — cuve interne'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N Reference',
        required=True, copy=False, readonly=True,
        default='Nouveau', translate=False
    )
    state = fields.Selection([
        ('draft',     'Brouillon'),
        ('confirmed', 'Commande confirmee'),
        ('received',  'Citerne recue'),
        ('validated', 'Valide'),
        ('cancelled', 'Annule'),
    ], string='Statut', default='draft', tracking=True)

    date = fields.Date(string='Date commande', required=True, default=fields.Date.today)
    date_reception = fields.Date(string='Date reception prevue')
    date_received = fields.Date(string='Date reception reelle')

    cuve_id = fields.Many2one(
        'transport.fuel.cuve',
        string='Cuve',
        required=True,
        tracking=True
    )
    station_id = fields.Many2one(
        'transport.fuel.station',
        string='Station',
        related='cuve_id.station_id',
        store=True,
        readonly=True
    )
    fuel_type_id = fields.Many2one(
        'transport.energy.type',
        string='Type carburant',
        related='cuve_id.fuel_type_id',
        store=True,
        readonly=True
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
        required=True
    )
    quantity_ordered = fields.Float(
        string='Quantite commandee (L)',
        required=True,
        digits=(10, 2)
    )
    quantity_received = fields.Float(
        string='Quantite recue (L)',
        digits=(10, 2)
    )
    unit_price = fields.Float(
        string='Prix unitaire (TND/L)',
        digits=(10, 3)
    )
    total_cost = fields.Float(
        string='Cout total (TND)',
        compute='_compute_total',
        store=True,
        digits=(12, 3)
    )
    delivery_note = fields.Char(string='N bon livraison', translate=False)
    notes = fields.Text(string='Notes', translate=False)

    stock_before = fields.Float(
        string='Stock avant reception (L)',
        digits=(10, 2),
        readonly=True
    )
    stock_after = fields.Float(
        string='Stock apres reception (L)',
        digits=(10, 2),
        readonly=True,
        compute='_compute_stock_after',
        store=True
    )

    @api.depends('quantity_received', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total_cost = round(rec.quantity_received * rec.unit_price, 3)

    @api.depends('stock_before', 'quantity_received')
    def _compute_stock_after(self):
        for rec in self:
            rec.stock_after = rec.stock_before + rec.quantity_received

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'transport.supply.order'
                ) or 'Nouveau'
        return super().create(vals_list)

    def _reopen_form(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('transport_energy.action_supply_order')
        action.update({
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        })
        return action

    def action_confirm(self):
        for rec in self:
            if rec.quantity_ordered <= 0:
                raise ValidationError("La quantite commandee doit etre positive.")
            rec.write({'state': 'confirmed'})
        return self._reopen_form()

    def action_receive(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise ValidationError("La commande doit etre confirmee avant reception.")
            if rec.quantity_received <= 0:
                raise ValidationError("Saisir la quantite reellement recue.")
            rec.write({
                'state': 'received',
                'date_received': fields.Date.today(),
                'stock_before': rec.cuve_id.current_stock,
            })

    def action_validate(self):
        for rec in self:
            if rec.state != 'received':
                raise ValidationError("Enregistrer la reception avant de valider.")
            rec.cuve_id._add_stock(rec.quantity_received)
            rec.write({'state': 'validated'})
            rec.message_post(
                body=(
                    f"Stock cuve mis a jour : "
                    f"{rec.stock_before:.0f} L → "
                    f"{rec.cuve_id.current_stock:.0f} L "
                    f"(+{rec.quantity_received:.0f} L)"
                ),
                message_type='notification'
            )
        return self._reopen_form()

    def action_cancel(self):
        for rec in self:
            if rec.state == 'validated':
                raise ValidationError("Impossible d'annuler un approvisionnement deja valide.")
            rec.write({'state': 'cancelled'})
        return self._reopen_form()

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return self._reopen_form()

    @api.constrains('quantity_ordered', 'quantity_received')
    def _check_quantities(self):
        for rec in self:
            if rec.quantity_ordered <= 0:
                raise ValidationError("Quantite commandee doit etre > 0.")
            if rec.quantity_received < 0:
                raise ValidationError("Quantite recue ne peut pas etre negative.")
