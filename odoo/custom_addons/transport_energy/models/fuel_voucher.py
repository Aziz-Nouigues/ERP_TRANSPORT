# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TransportFuelVoucher(models.Model):
    """Bon de ravitaillement carburant.
    - BGI (interne) : cuve interne, compteur pompe, lignes bus.
    - BGE (externe) : station externe libre, mode paiement, lien AGILIS optionnel.
    A la validation BGI : debite current_stock de la cuve.
    A la validation BGE AGILIS : cree automatiquement 1 transport.agilis.utilisation par bon.
    """
    _name = 'transport.fuel.voucher'
    _description = 'Bon de ravitaillement carburant (BGI / BGE)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='N du Bon', required=True, copy=False,
        readonly=True, default='Nouveau', translate=False
    )
    voucher_type = fields.Selection([
        ('internal', 'Interne (BGI)'),
        ('external', 'Externe (BGE)'),
    ], string='Type', required=True, default='internal', tracking=True)

    state = fields.Selection([
        ('draft',     'Brouillon'),
        ('confirmed', 'Confirme'),
        ('done',      'Valide'),
        ('cancelled', 'Annule'),
    ], string='Statut', default='draft', tracking=True)

    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    time_start = fields.Float(string='Heure debut', default=7.0)
    time_end = fields.Float(string='Heure fin', default=17.0)

    # ── CHAMPS BGI ────────────────────────────────────────────────
    cuve_id = fields.Many2one('transport.fuel.cuve', string='Cuve / Pompe')
    station_id = fields.Many2one(
        'transport.fuel.station', string='Station',
        related='cuve_id.station_id', store=True, readonly=True
    )
    fuel_type_id = fields.Many2one(
        'transport.energy.type', string='Type carburant',
        related='cuve_id.fuel_type_id', store=True, readonly=True
    )
    distributor_code = fields.Char(string='Code agent distributeur', translate=False)
    distributor_name = fields.Char(string='Nom agent distributeur', translate=True)
    agency_main_code = fields.Char(string='Code principal agence')
    agency_sub_code = fields.Char(string='Code secondaire agence')
    pump_counter_start = fields.Float(string='Compteur pompe debut', digits=(12, 0))
    pump_counter_end = fields.Float(string='Compteur pompe fin', digits=(12, 0))
    remaining_stock = fields.Float(string='Stock restant estime (L)', digits=(10, 2))

    # ── CHAMPS BGE ────────────────────────────────────────────────
    station_externe = fields.Char(string='Station externe (nom)', translate=True)
    station_externe_ville = fields.Char(string='Ville / Adresse', translate=True)
    fuel_type_bge_id = fields.Many2one(
        'transport.energy.type', string='Type carburant (BGE)',
        domain="[('category','=','fuel')]"
    )
    payment_mode = fields.Selection([
        ('cash',   'Especes'),
        ('agilis', 'Carte AGILIS'),
        ('credit', 'Credit fournisseur'),
    ], string='Mode de paiement')
    agilis_card_id = fields.Many2one(
        'transport.agilis.carte', string='Carte AGILIS',
        domain="[('statut','=','active')]"
    )
    ticket_reference = fields.Char(string='N ticket / recu externe', translate=False)

    # ── TOTAUX ────────────────────────────────────────────────────
    total_quantity = fields.Float(
        string='Quantite totale (L)', compute='_compute_totals',
        store=True, digits=(10, 2)
    )
    total_cost = fields.Float(
        string='Cout total (TND)', compute='_compute_totals',
        store=True, digits=(12, 3)
    )

    notes = fields.Text(string='Notes', translate=False)
    line_ids = fields.One2many(
        'transport.fuel.voucher.line', 'voucher_id',
        string='Lignes de ravitaillement'
    )

    @api.depends('line_ids.quantity', 'line_ids.unit_price')
    def _compute_totals(self):
        for rec in self:
            rec.total_quantity = sum(l.quantity for l in rec.line_ids)
            rec.total_cost = sum(l.subtotal for l in rec.line_ids)

    @api.onchange('cuve_id')
    def _onchange_cuve(self):
        if self.cuve_id:
            self.pump_counter_start = self.cuve_id.pump_counter_current
            self.remaining_stock = self.cuve_id.current_stock

    @api.onchange('voucher_type')
    def _onchange_voucher_type(self):
        if self.voucher_type == 'internal':
            self.station_externe = False
            self.station_externe_ville = False
            self.payment_mode = False
            self.agilis_card_id = False
            self.ticket_reference = False
            self.fuel_type_bge_id = False
        else:
            self.cuve_id = False
            self.pump_counter_start = 0
            self.pump_counter_end = 0
            self.remaining_stock = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                seq = ('transport.fuel.voucher.external'
                       if vals.get('voucher_type') == 'external'
                       else 'transport.fuel.voucher.internal')
                vals['name'] = self.env['ir.sequence'].next_by_code(seq) or 'Nouveau'
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError("Impossible de confirmer un bon sans lignes.")
            if rec.voucher_type == 'internal' and not rec.cuve_id:
                raise ValidationError("Selectionner une cuve pour un BGI.")
            if rec.voucher_type == 'external' and not rec.station_externe:
                raise ValidationError("Saisir le nom de la station externe pour un BGE.")
            if rec.voucher_type == 'external' and not rec.payment_mode:
                raise ValidationError("Selectionner un mode de paiement pour un BGE.")
            rec.write({'state': 'confirmed'})

    def action_validate(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise ValidationError("Le bon doit etre confirme avant validation.")

            if rec.voucher_type == 'internal' and rec.cuve_id:
                if rec.cuve_id.current_stock < rec.total_quantity:
                    raise ValidationError(
                        f"Stock insuffisant ({rec.cuve_id.fuel_type_id.name}) : "
                        f"disponible {rec.cuve_id.current_stock:.0f} L, "
                        f"demande {rec.total_quantity:.0f} L."
                    )
                rec.cuve_id._consume_stock(rec.total_quantity)
                # FIX : mettre à jour compteur uniquement si pump_counter_end > 0
                if rec.pump_counter_end > 0:
                    rec.cuve_id.write({'pump_counter_current': rec.pump_counter_end})

            elif rec.voucher_type == 'external' and rec.payment_mode == 'agilis':
                if not rec.agilis_card_id:
                    raise ValidationError("Mode paiement AGILIS : selectionner une carte AGILIS.")
                if rec.agilis_card_id.statut != 'active':
                    raise ValidationError(
                        f"La carte {rec.agilis_card_id.name} est {rec.agilis_card_id.statut}."
                    )
                # FIX : vérifier solde suffisant avant utilisation
                if rec.agilis_card_id.solde_actuel < rec.total_cost:
                    raise ValidationError(
                        f"Solde insuffisant sur la carte {rec.agilis_card_id.name} : "
                        f"solde {rec.agilis_card_id.solde_actuel:.3f} TND, "
                        f"montant requis {rec.total_cost:.3f} TND."
                    )
                fuel_type = rec.fuel_type_bge_id or rec.fuel_type_id
                # FIX : créer UNE SEULE utilisation par bon (pas par ligne)
                # pour éviter le double débit de la carte AGILIS
                self.env['transport.agilis.utilisation'].create({
                    'carte_id': rec.agilis_card_id.id,
                    'voucher_id': rec.id,
                    'date': fields.Datetime.now(),
                    'station_externe': rec.station_externe or '',
                    'chauffeur': ', '.join(
                        l.driver_name for l in rec.line_ids if l.driver_name
                    ) or '',
                    'fuel_type_id': fuel_type.id if fuel_type else False,
                    'quantite': rec.total_quantity,
                    'prix_unitaire': (rec.total_cost / rec.total_quantity)
                        if rec.total_quantity > 0 else 0.0,
                })

            rec.write({'state': 'done'})

    def action_cancel(self):
        """Annulation uniquement pour les bons non validés."""
        for rec in self:
            if rec.state == 'done':
                raise ValidationError(
                    "Impossible d'annuler un bon valide. "
                    "Utiliser 'Annuler (directeur)' pour restituer le stock."
                )
            rec.write({'state': 'cancelled'})

    def action_cancel_done(self):
        """FIX : Annulation d'un bon validé avec restitution du stock (directeur)."""
        for rec in self:
            if rec.state != 'done':
                raise ValidationError("Ce bon n'est pas dans l'etat 'Valide'.")
            # Restituer le stock cuve si BGI
            if rec.voucher_type == 'internal' and rec.cuve_id:
                rec.cuve_id._add_stock(rec.total_quantity)
                rec.message_post(
                    body=(
                        f"Annulation BGI — Stock restitue : "
                        f"+{rec.total_quantity:.0f} L sur {rec.cuve_id.display_name}"
                    ),
                    message_type='notification'
                )
            # Supprimer l'utilisation AGILIS liée si BGE AGILIS
            if rec.voucher_type == 'external' and rec.payment_mode == 'agilis':
                utilisations = self.env['transport.agilis.utilisation'].search([
                    ('voucher_id', '=', rec.id)
                ])
                utilisations.unlink()
                rec.message_post(
                    body="Annulation BGE AGILIS — Utilisation carte supprimee.",
                    message_type='notification'
                )
            rec.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    @api.constrains('pump_counter_start', 'pump_counter_end')
    def _check_pump_counters(self):
        for rec in self:
            if (rec.voucher_type == 'internal'
                    and rec.pump_counter_end > 0
                    and rec.pump_counter_start > 0
                    and rec.pump_counter_end < rec.pump_counter_start):
                raise ValidationError("Compteur fin ne peut pas etre inferieur au compteur debut.")

    @api.constrains('agilis_card_id', 'payment_mode')
    def _check_agilis_card(self):
        for rec in self:
            if rec.voucher_type == 'external' and rec.payment_mode == 'agilis':
                if not rec.agilis_card_id:
                    raise ValidationError("Mode paiement AGILIS : une carte AGILIS doit etre selectionnee.")


class TransportFuelVoucherLine(models.Model):
    """Ligne de ravitaillement — 1 ligne = 1 bus ravitaille."""
    _name = 'transport.fuel.voucher.line'
    _description = 'Ligne de bon de carburant'
    _order = 'time asc'

    voucher_id = fields.Many2one(
        'transport.fuel.voucher', string='Bon de carburant',
        required=True, ondelete='cascade'
    )
    time = fields.Float(string='Heure', default=8.0)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Bus / Vehicule', required=True)
    service_code = fields.Char(string='Code service', translate=False)
    driver_code = fields.Char(string='Code chauffeur', translate=False)
    driver_name = fields.Char(string='Nom chauffeur', translate=True)

    odometer_value = fields.Float(string='Compteur bus (km)', digits=(12, 0))
    odometer_status = fields.Selection(
        related='vehicle_id.odometer_status',
        string='Etat compteur', readonly=True
    )
    distance_estimated = fields.Float(
        string='Distance estimee (km)',
        compute='_compute_distance', store=True, digits=(10, 1)
    )

    quantity = fields.Float(string='Quantite (L)', required=True, digits=(10, 2))
    unit_price = fields.Float(string='Prix unitaire (TND/L)', digits=(10, 3))
    subtotal = fields.Float(
        string='Montant (TND)', compute='_compute_subtotal',
        store=True, digits=(12, 3)
    )

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = round(line.quantity * line.unit_price, 3)

    @api.depends('quantity', 'vehicle_id', 'odometer_status')
    def _compute_distance(self):
        """Calcule la distance estimée uniquement si le compteur est en panne.
        Si le compteur est fonctionnel, la distance réelle est calculée
        via delta odometer_value dans les rapports (_get_donnees_excessif etc.)
        """
        for line in self:
            if (line.odometer_status == 'broken'
                    and line.vehicle_id
                    and line.vehicle_id.theoretical_fuel_consumption > 0):
                line.distance_estimated = line.vehicle_id.estimate_distance_from_fuel(
                    line.quantity
                )
            else:
                line.distance_estimated = 0.0

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("La quantite distribuee doit etre superieure a 0.")
