# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ReceptionLubrifiant(models.Model):
    """Reception de lubrifiant en magasin/atelier.
    C'est le seul chemin autorise pour crediter le stock lubrifiant.
    A la validation, le stock du magasin est incremente via _add_stock().
    Equivalent de transport.supply.order pour le carburant.
    """
    _name = 'transport.reception.lubrifiant'
    _description = 'Reception lubrifiant magasin'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N Reference', required=True, copy=False,
        readonly=True, default='Nouveau', translate=False
    )
    state = fields.Selection([
        ('draft',     'Brouillon'),
        ('confirmed', 'Confirme'),
        ('validated', 'Valide'),
        ('cancelled', 'Annule'),
    ], string='Statut', default='draft', tracking=True)

    date = fields.Date(string='Date reception', required=True, default=fields.Date.today)
    atelier = fields.Char(string='Atelier / Magasin', required=True, tracking=True)
    agence = fields.Char(string='Agence / Depot')
    fournisseur_id = fields.Many2one('res.partner', string='Fournisseur')
    bon_livraison = fields.Char(string='N Bon de livraison')
    notes = fields.Text(string='Notes')

    ligne_ids = fields.One2many(
        'transport.reception.lubrifiant.ligne', 'reception_id',
        string='Lubrifiants recus'
    )

    total_cout = fields.Float(
        string='Cout total (TND)', compute='_compute_total',
        store=True, digits=(12, 3)
    )

    @api.depends('ligne_ids.sous_total')
    def _compute_total(self):
        for rec in self:
            rec.total_cout = sum(l.sous_total for l in rec.ligne_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'transport.reception.lubrifiant'
                ) or 'Nouveau'
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.ligne_ids:
                raise ValidationError("Impossible de confirmer sans lignes.")
            rec.write({'state': 'confirmed'})

    def action_validate(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise ValidationError("La reception doit etre confirmee avant validation.")
            for ligne in rec.ligne_ids:
                # Retrouver ou créer le stock magasin
                stock = self.env['transport.stock.lubrifiant'].search([
                    ('atelier', '=', rec.atelier),
                    ('type_lubrifiant_id', '=', ligne.type_lubrifiant_id.id),
                ], limit=1)
                if not stock:
                    stock = self.env['transport.stock.lubrifiant'].create({
                        'atelier': rec.atelier,
                        'agence': rec.agence or '',
                        'type_lubrifiant_id': ligne.type_lubrifiant_id.id,
                        'stock_actuel': 0.0,
                    })
                # Créditer le stock en litres
                stock._add_stock(ligne.quantite_litres)
                stock.message_post(
                    body=(
                        f"Reception {rec.name} validee : "
                        f"+{ligne.quantite_litres:.2f} L "
                        f"({ligne.nb_unites:.0f} {ligne.conditionnement or 'unite(s)'}). "
                        f"Stock : {stock.stock_actuel:.2f} L"
                    ),
                    message_type='notification'
                )
            rec.write({'state': 'validated'})
            rec.message_post(
                body=f"Reception validee — {len(rec.ligne_ids)} ligne(s) creditees.",
                message_type='notification'
            )

    def action_cancel(self):
        for rec in self:
            if rec.state == 'validated':
                raise ValidationError(
                    "Impossible d'annuler une reception validee. "
                    "Contacter le directeur."
                )
            rec.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})


class ReceptionLubrifiantLigne(models.Model):
    """Ligne de reception lubrifiant.
    Saisie en unites de conditionnement (bidons, futs) OU en litres.
    Le stock est toujours credite en litres.
    """
    _name = 'transport.reception.lubrifiant.ligne'
    _description = 'Ligne reception lubrifiant'

    reception_id = fields.Many2one(
        'transport.reception.lubrifiant', string='Reception',
        required=True, ondelete='cascade'
    )
    type_lubrifiant_id = fields.Many2one(
        'transport.energy.type', string='Type lubrifiant',
        required=True, domain="[('category','=','lubrifiant')]"
    )
    unite = fields.Char(
        string='Unite', related='type_lubrifiant_id.unite',
        store=True, readonly=True
    )
    conditionnement = fields.Char(
        string='Conditionnement',
        related='type_lubrifiant_id.conditionnement',
        store=True, readonly=True
    )
    volume_conditionnement = fields.Float(
        string='Vol/unite (L)',
        related='type_lubrifiant_id.volume_conditionnement',
        store=True, readonly=True
    )

    # Saisie : en unités OU en litres directement
    nb_unites = fields.Float(
        string='Nb unites reçues',
        digits=(10, 2), default=0.0,
        help="Nombre de bidons/futs recus. Laisser 0 pour saisir en litres."
    )
    quantite_litres = fields.Float(
        string='Quantite (L)',
        digits=(10, 2), required=True,
        help="Quantite en litres. Calculee automatiquement si nb_unites > 0."
    )
    prix_unitaire = fields.Float(
        string='Prix unitaire (TND/L)', digits=(10, 3)
    )
    sous_total = fields.Float(
        string='Sous-total (TND)', compute='_compute_sous_total',
        store=True, digits=(12, 3)
    )

    @api.depends('quantite_litres', 'prix_unitaire')
    def _compute_sous_total(self):
        for l in self:
            l.sous_total = round(l.quantite_litres * l.prix_unitaire, 3)

    @api.onchange('nb_unites', 'volume_conditionnement')
    def _onchange_nb_unites(self):
        if self.nb_unites > 0 and self.volume_conditionnement > 0:
            self.quantite_litres = round(self.nb_unites * self.volume_conditionnement, 2)

    @api.constrains('quantite_litres')
    def _check_quantite(self):
        for l in self:
            if l.quantite_litres <= 0:
                raise ValidationError("La quantite doit etre superieure a 0.")
