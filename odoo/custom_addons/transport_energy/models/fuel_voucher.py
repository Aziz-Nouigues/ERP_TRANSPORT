# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


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
    time_end   = fields.Float(string='Heure fin',   default=17.0)

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
    agency_sub_code  = fields.Char(string='Code secondaire agence')
    pump_counter_start = fields.Float(string='Compteur pompe debut', digits=(12, 0))
    pump_counter_end   = fields.Float(string='Compteur pompe fin',   digits=(12, 0))
    remaining_stock    = fields.Float(string='Stock restant estime (L)', digits=(10, 2))

    # ── CHAMPS BGE ────────────────────────────────────────────────
    station_externe      = fields.Char(string='Station externe (nom)', translate=True)
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

    notes   = fields.Text(string='Notes', translate=False)
    line_ids = fields.One2many(
        'transport.fuel.voucher.line', 'voucher_id',
        string='Lignes de ravitaillement'
    )

    @api.depends('line_ids.quantity', 'line_ids.unit_price')
    def _compute_totals(self):
        for rec in self:
            rec.total_quantity = sum(l.quantity for l in rec.line_ids)
            rec.total_cost     = sum(l.subtotal  for l in rec.line_ids)

    @api.onchange('cuve_id')
    def _onchange_cuve(self):
        if self.cuve_id:
            self.pump_counter_start = self.cuve_id.pump_counter_current
            self.remaining_stock    = self.cuve_id.current_stock

    @api.onchange('voucher_type')
    def _onchange_voucher_type(self):
        if self.voucher_type == 'internal':
            self.station_externe       = False
            self.station_externe_ville = False
            self.payment_mode          = False
            self.agilis_card_id        = False
            self.ticket_reference      = False
            self.fuel_type_bge_id      = False
        else:
            self.cuve_id            = False
            self.pump_counter_start = 0
            self.pump_counter_end   = 0
            self.remaining_stock    = 0

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
            lignes_sans_qte = rec.line_ids.filtered(lambda l: l.quantity <= 0)
            if lignes_sans_qte:
                noms = ', '.join(l.vehicle_id.name or '?' for l in lignes_sans_qte)
                raise ValidationError(
                    f"Quantité manquante sur les lignes : {noms}. "
                    f"Veuillez saisir ou confirmer la quantité suggérée."
                )
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
                if rec.pump_counter_end > 0:
                    rec.cuve_id.write({'pump_counter_current': rec.pump_counter_end})

            elif rec.voucher_type == 'external' and rec.payment_mode == 'agilis':
                if not rec.agilis_card_id:
                    raise ValidationError("Mode paiement AGILIS : selectionner une carte AGILIS.")
                if rec.agilis_card_id.statut != 'active':
                    raise ValidationError(
                        f"La carte {rec.agilis_card_id.name} est {rec.agilis_card_id.statut}."
                    )
                if rec.agilis_card_id.solde_actuel < rec.total_cost:
                    raise ValidationError(
                        f"Solde insuffisant sur la carte {rec.agilis_card_id.name} : "
                        f"solde {rec.agilis_card_id.solde_actuel:.3f} TND, "
                        f"montant requis {rec.total_cost:.3f} TND."
                    )
                fuel_type = rec.fuel_type_bge_id or rec.fuel_type_id
                self.env['transport.agilis.utilisation'].create({
                    'carte_id':       rec.agilis_card_id.id,
                    'voucher_id':     rec.id,
                    'date':           fields.Datetime.now(),
                    'station_externe': rec.station_externe or '',
                    'chauffeur': ', '.join(
                        l.driver_name for l in rec.line_ids if l.driver_name
                    ) or '',
                    'fuel_type_id': fuel_type.id if fuel_type else False,
                    'quantite':     rec.total_quantity,
                    'prix_unitaire': (rec.total_cost / rec.total_quantity)
                        if rec.total_quantity > 0 else 0.0,
                })

            rec.write({'state': 'done'})

            # ── Étape 5 : création relevés fleet.vehicle.odometer ───────
            # Un relevé par ligne de ravitaillement ayant un compteur renseigné.
            # Permet à P1 de trouver un historique fiable pour les prochains bons.
            for line in rec.line_ids:
                if line.vehicle_id and line.odometer_value > 0 and line.odometer_status != 'broken':
                    self.env['fleet.vehicle.odometer'].create({
                        'vehicle_id': line.vehicle_id.id,
                        'value':      line.odometer_value,
                        'date':       rec.date,
                        'name': (
                            f"Ravitaillement {rec.name} — {line.driver_name or line.vehicle_id.name}"
                        ),
                    })

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise ValidationError(
                    "Impossible d'annuler un bon valide. "
                    "Utiliser 'Annuler (directeur)' pour restituer le stock."
                )
            rec.write({'state': 'cancelled'})

    def action_cancel_done(self):
        for rec in self:
            if rec.state != 'done':
                raise ValidationError("Ce bon n'est pas dans l'etat 'Valide'.")
            if rec.voucher_type == 'internal' and rec.cuve_id:
                rec.cuve_id._add_stock(rec.total_quantity)
                rec.message_post(
                    body=(
                        f"Annulation BGI — Stock restitue : "
                        f"+{rec.total_quantity:.0f} L sur {rec.cuve_id.display_name}"
                    ),
                    message_type='notification'
                )
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
                raise ValidationError(
                    "Compteur fin ne peut pas etre inferieur au compteur debut."
                )

    @api.constrains('agilis_card_id', 'payment_mode')
    def _check_agilis_card(self):
        for rec in self:
            if rec.voucher_type == 'external' and rec.payment_mode == 'agilis':
                if not rec.agilis_card_id:
                    raise ValidationError(
                        "Mode paiement AGILIS : une carte AGILIS doit etre selectionnee."
                    )


# ══════════════════════════════════════════════════════════════════════════════
#  LIGNE DE RAVITAILLEMENT — avec intégration Exploitation
# ══════════════════════════════════════════════════════════════════════════════
class TransportFuelVoucherLine(models.Model):
    """Ligne de ravitaillement — 1 ligne = 1 bus ravitaille.

    Distance estimée — 3 sources par ordre de priorité :
    ┌─────────────────────────────────────────────────────────────────┐
    │ P1 : Delta compteur odometer (fleet.vehicle.odometer)           │
    │      Créé auto par Exploitation à la clôture de tournée         │
    │      → Source la plus fiable, toujours utilisée en premier      │
    │                                                                 │
    │ P2 : Tournées Exploitation réalisées (transport.exploitation.   │
    │      tournee) entre le dernier ravitaillement et aujourd'hui    │
    │      → Somme des km_realise sur la période                      │
    │                                                                 │
    │ P3 : Estimation carburant (fallback)                            │
    │      Distance = Quantité × 100 / Conso théorique (L/100km)     │
    │      → Utilisé si compteur en panne ET pas de tournées          │
    └─────────────────────────────────────────────────────────────────┘
    """
    _name = 'transport.fuel.voucher.line'
    _description = 'Ligne de bon de carburant'
    _order = 'time asc'

    voucher_id = fields.Many2one(
        'transport.fuel.voucher', string='Bon de carburant',
        required=True, ondelete='cascade'
    )
    time        = fields.Float(string='Heure', default=8.0)
    vehicle_id  = fields.Many2one('fleet.vehicle', string='Bus / Vehicule', required=True)
    service_code = fields.Char(string='Code service',  translate=False)
    driver_code  = fields.Char(string='Code chauffeur', translate=False)
    driver_name  = fields.Char(string='Nom chauffeur',  translate=True)

    odometer_value  = fields.Float(string='Compteur bus (km)', digits=(12, 0))
    odometer_status = fields.Selection(
        related='vehicle_id.odometer_status',
        string='Etat compteur', readonly=True
    )

    # ── Distance estimée + source ──────────────────────────────────
    distance_estimated = fields.Float(
        string='Distance estimee (km)',
        compute='_compute_distance', store=True, digits=(10, 1)
    )
    source_distance = fields.Selection([
        ('odometer',   'Compteur km (periodes)'),
        ('tournees',   'Tournees exploitation'),
        ('estimation', 'Estimation carburant'),
        ('aucune',     'Non calculee'),
    ], string='Source distance', compute='_compute_distance',
       store=True, readonly=True,
       help='Indique quelle source a ete utilisee pour calculer la distance.'
    )

    # ── Quantité suggérée (lecture seule) ─────────────────────────
    quantite_suggeree = fields.Float(
        string='Quantite suggeree (L)',
        compute='_compute_distance', store=True, digits=(10, 2),
        readonly=True,
        help='Calculee depuis la distance estimee et la conso theorique du vehicule.'
    )

    # ── Tournées liées (champs calculés sans stockage SQL) ────────
    nb_tournees = fields.Integer(
        string='Nb tournees', compute='_compute_tournees_liees', store=False
    )
    km_tournees = fields.Float(
        string='Km tournees (total)', compute='_compute_tournees_liees',
        store=False, digits=(10, 1),
        help='Somme des km realises sur les tournees apres le dernier ravitaillement.'
    )

    # ── Carburant ─────────────────────────────────────────────────
    quantity   = fields.Float(string='Quantite (L)',         required=True, digits=(10, 2))
    unit_price = fields.Float(string='Prix unitaire (TND/L)', digits=(10, 3))
    subtotal   = fields.Float(
        string='Montant (TND)', compute='_compute_subtotal',
        store=True, digits=(12, 3)
    )

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = round(line.quantity * line.unit_price, 3)

    # ── Helpers ────────────────────────────────────────────────────
    def _get_date_dernier_ravitaillement(self):
        """Retourne la date du dernier bon VALIDÉ pour ce bus avant le bon courant.
        Utilisé pour borner la recherche des tournées (P2).
        """
        self.ensure_one()
        domain = [
            ('state', '=', 'done'),
            ('line_ids.vehicle_id', '=', self.vehicle_id.id),
        ]
        if self.voucher_id:
            domain += [
                ('id',   '!=', self.voucher_id.id),
                ('date', '<',  self.voucher_id.date),   # < strict : exclut le jour même
            ]
        dernier = self.env['transport.fuel.voucher'].search(domain, order='date desc', limit=1)
        return dernier.date if dernier else False

    def _get_tournees_apres_dernier_ravitaillement(self):
        """Tournées réalisées par ce bus APRÈS le dernier ravitaillement
        et jusqu'à la date du bon courant (incluse).
        - Filtre par vehicle_id : chaque bus ne voit que ses propres tournées.
        - Exclut le double comptage : si ce bus a déjà une autre ligne sur le
          même bon, on ne retourne rien (une seule ligne par bus par bon).
        Retourne un recordset vide si le module Exploitation n'est pas installé.
        """
        self.ensure_one()
        if 'transport.exploitation.tournee' not in self.env:
            return self.env['transport.fuel.voucher.line'].browse()

        # Un bus ne doit avoir qu'une seule ligne par bon.
        # Si une autre ligne du même bon concerne déjà ce bus → pas de tournées.
        if self.voucher_id:
            doublon = self.voucher_id.line_ids.filtered(
                lambda l: l.vehicle_id.id == self.vehicle_id.id
                and l.id != (self._origin.id or False)
                and l.id != self.id
            )
            if doublon:
                return self.env['transport.exploitation.tournee'].browse()

        Tournee = self.env['transport.exploitation.tournee']
        date_fin = self.voucher_id.date if self.voucher_id else fields.Date.today()
        domain = [
            ('vehicle_id', '=', self.vehicle_id.id),
            ('state',      '=', 'realise'),
            ('date',       '<=', date_fin),
            ('km_realise', '>',  0),
        ]
        date_debut = self._get_date_dernier_ravitaillement()
        if date_debut:
            domain.append(('date', '>', date_debut))
        try:
            return Tournee.search(domain, order='date asc')
        except Exception:
            _logger.warning("fuel_voucher: lecture tournees impossible", exc_info=True)
            return Tournee.browse()

    def _km_odometer_cumules(self):
        """P1 — Cumul des km odometer depuis le dernier ravitaillement.

        Logique :
          - On cherche toutes les lignes validées de ce bus dont odometer_value
            est compris entre le dernier relevé du précédent bon validé (exclu)
            et le relevé actuel (inclus).
          - On trie par odometer_value croissant et on somme les deltas consécutifs.
          - Cela gère correctement les ravitaillements intermédiaires et les
            compteurs remplacés (odometer_status = 'replaced').
        """
        self.ensure_one()
        v = self.vehicle_id

        # Relevé du dernier bon validé pour ce bus (borne basse)
        domain_prev_bon = [
            ('vehicle_id',       '=', v.id),
            ('odometer_value',   '>', 0),
            ('voucher_id.state', '=', 'done'),
        ] + ([('id', '!=', self.id)] if self.id else [])
        if self.odometer_value > 0:
            domain_prev_bon.append(('odometer_value', '<', self.odometer_value))

        prev_line = self.env['transport.fuel.voucher.line'].search(
            domain_prev_bon, order='odometer_value desc', limit=1)
        borne_basse = prev_line.odometer_value if prev_line.exists() else 0.0

        if borne_basse <= 0 or self.odometer_value <= borne_basse:
            return 0.0

        # Toutes les lignes validées du bus dans la fenêtre ]borne_basse, odometer_value_actuel]
        lignes_fenetre = self.env['transport.fuel.voucher.line'].search([
            ('vehicle_id',       '=', v.id),
            ('odometer_value',   '>',  borne_basse),
            ('odometer_value',   '<=', self.odometer_value),
            ('voucher_id.state', '=',  'done'),
        ] + ([('id', '!=', self.id)] if self.id else []),
        order='odometer_value asc')

        # Calcul des deltas consécutifs entre les relevés de la fenêtre
        # Le premier delta est depuis borne_basse, puis entre chaque paire.
        valeurs = [borne_basse] + list(lignes_fenetre.mapped('odometer_value')) + [self.odometer_value]
        km_total = round(sum(
            max(valeurs[i+1] - valeurs[i], 0)
            for i in range(len(valeurs) - 1)
        ), 1)
        return km_total

    # ── Compute tournées liées (affichage info) ────────────────────
    @api.depends('vehicle_id', 'voucher_id.date', 'voucher_id.state')
    def _compute_tournees_liees(self):
        for line in self:
            if not line.vehicle_id:
                line.nb_tournees = 0
                line.km_tournees = 0.0
                continue
            tournees = line._get_tournees_apres_dernier_ravitaillement()
            line.nb_tournees = len(tournees)
            line.km_tournees = round(sum(tournees.mapped('km_realise')), 1) if tournees else 0.0

    # ── Helper : consommation effective ───────────────────────────
    def _get_conso_effective(self):
        """Retourne la consommation effective (L/100km) à utiliser pour ce bus.

        Priorité :
          1. Conso réelle calculée depuis le dernier bon validé de ce bus
             qui possède à la fois une distance_estimated et une quantity.
             → litres_distribués × 100 / km_parcourus
          2. Conso théorique Fleet (theoretical_fuel_consumption) comme fallback.
          3. 0.0 si aucune donnée disponible.
        """
        self.ensure_one()
        v = self.vehicle_id
        if not v:
            return 0.0

        dernier_ligne = self.env['transport.fuel.voucher.line'].search([
            ('vehicle_id',         '=', v.id),
            ('distance_estimated', '>', 0),
            ('quantity',           '>', 0),
            ('voucher_id.state',   '=', 'done'),
        ] + ([('id', '!=', self.id)] if self.id else []),
        order='id desc', limit=1)

        if dernier_ligne.exists():
            conso_reelle = round(
                dernier_ligne.quantity * 100 / dernier_ligne.distance_estimated, 2
            )
            if conso_reelle > 0:
                _logger.debug(
                    "Bus %s — conso réelle : %.2f L/100km (bon %s, %.1f L / %.1f km)",
                    v.name, conso_reelle,
                    dernier_ligne.voucher_id.name,
                    dernier_ligne.quantity,
                    dernier_ligne.distance_estimated,
                )
                return conso_reelle

        return v.theoretical_fuel_consumption or 0.0

    # ── Compute distance + quantité suggérée ──────────────────────
    @api.depends(
        'quantity', 'vehicle_id', 'odometer_value',
        'vehicle_id.odometer_status',
        'vehicle_id.theoretical_fuel_consumption',
        'voucher_id.date', 'voucher_id.state'
    )
    def _compute_distance(self):
        """Calcule distance_estimated, source_distance et quantite_suggeree.

        P1 — Compteur OK : cumul des deltas odometer depuis le dernier ravitaillement.
             quantite_suggeree = km × conso_effective / 100

        P2 — Compteur en panne : somme km_realise des tournées après dernier ravit.
             quantite_suggeree = km_tournees × conso_effective / 100

        P2b — Pas de tournées : moyenne pondérée sur 5 périodes historiques (filtre IQR).
             quantite_suggeree = km_moy × conso_effective / 100

        P3 — Fallback : km estimés depuis la quantité saisie et la conso effective.
             quantite_suggeree = 0 (on part de la quantité, pas l'inverse)

        Dans tous les cas, conso_effective = conso réelle historique si dispo,
        sinon conso théorique Fleet.
        """
        for line in self:
            if not line.vehicle_id:
                line.distance_estimated  = 0.0
                line.source_distance     = 'aucune'
                line.quantite_suggeree   = 0.0
                continue

            conso = line._get_conso_effective()

            # ── P1 : Compteur OK — cumul deltas odometer ────────────────
            if line.vehicle_id.odometer_status != 'broken' and line.odometer_value > 0:
                km = line._km_odometer_cumules()
                if km > 0:
                    line.distance_estimated = km
                    line.source_distance    = 'odometer'
                    line.quantite_suggeree  = round(km * conso / 100, 2) if conso > 0 else 0.0
                    _logger.debug(
                        "Ligne %s — P1 odometer : %.1f km → %.2f L suggérés (%.2f L/100km)",
                        line.id, km, line.quantite_suggeree, conso
                    )
                    continue

            # ── P2 : Compteur en panne — tournées après dernier ravit. ──
            tournees = line._get_tournees_apres_dernier_ravitaillement()
            if tournees:
                km_total = round(sum(tournees.mapped('km_realise')), 1)
                if km_total > 0:
                    line.distance_estimated = km_total
                    line.source_distance    = 'tournees'
                    line.quantite_suggeree  = round(km_total * conso / 100, 2) if conso > 0 else 0.0
                    _logger.debug(
                        "Ligne %s — P2 tournees (%d) : %.1f km → %.2f L suggérés (%.2f L/100km)",
                        line.id, len(tournees), km_total, line.quantite_suggeree, conso
                    )
                    continue

            # ── P2b : Estimation historique intelligente (5 périodes) ───
            # Récupère les 5 dernières lignes validées de ce bus avec
            # distance_estimated > 0. Filtre les aberrantes (IQR), puis
            # calcule une moyenne pondérée (période récente = poids 2×).
            historique = self.env['transport.fuel.voucher.line'].search([
                ('vehicle_id',         '=', line.vehicle_id.id),
                ('distance_estimated', '>', 0),
                ('quantity',           '>', 0),
                ('voucher_id.state',   '=', 'done'),
            ] + ([('id', '!=', line.id)] if line.id else []),
            order='id desc', limit=5)

            if historique:
                distances = list(historique.mapped('distance_estimated'))

                # ── Filtre IQR (exclut pannes longues, grèves, etc.) ────
                if len(distances) >= 4:
                    tri = sorted(distances)
                    n = len(tri)
                    q1 = tri[n // 4]
                    q3 = tri[(3 * n) // 4]
                    iqr = q3 - q1
                    borne_basse = q1 - 1.5 * iqr
                    borne_haute = q3 + 1.5 * iqr
                    distances_filtrees = [d for d in distances if borne_basse <= d <= borne_haute]
                    # Garder au moins 2 valeurs, sinon revenir à l'original
                    if len(distances_filtrees) >= 2:
                        distances = distances_filtrees

                # ── Moyenne pondérée (récent = poids 2, anciens = poids 1) ─
                # distances est trié du plus récent au plus ancien (order desc)
                poids  = [2] + [1] * (len(distances) - 1)
                km_moy = round(
                    sum(d * p for d, p in zip(distances, poids)) / sum(poids), 1
                )

                if km_moy > 0:
                    line.distance_estimated = km_moy
                    line.source_distance    = 'estimation'
                    line.quantite_suggeree  = round(km_moy * conso / 100, 2) if conso > 0 else 0.0
                    _logger.debug(
                        "Ligne %s — P2b historique (%d périodes, filtre IQR) : "
                        "%.1f km moy pondérée → %.2f L suggérés (%.2f L/100km)",
                        line.id, len(distances), km_moy, line.quantite_suggeree, conso
                    )
                    continue

            # ── P3 : Estimation depuis quantité saisie + conso effective ─
            if conso > 0 and line.quantity > 0:
                km_estime = round(line.quantity * 100 / conso, 1)
                line.distance_estimated = km_estime
                line.source_distance    = 'estimation'
                line.quantite_suggeree  = 0.0
                _logger.debug(
                    "Ligne %s — P3 estimation : %.1f km (%.1f L / %.2f L/100km)",
                    line.id, km_estime, line.quantity, conso
                )
                continue

            # Aucune source
            line.distance_estimated = 0.0
            line.source_distance    = 'aucune'
            line.quantite_suggeree  = 0.0

    # ── onchange vehicle : pré-remplir compteur + quantité ────────
    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Pré-remplit :
        - le compteur km depuis le dernier relevé Fleet
        - la quantité distribuée depuis la quantite_suggeree calculée
          (uniquement si la quantité n'a pas encore été saisie)
        """
        if not self.vehicle_id:
            return

        # Pré-remplir compteur odometer
        dernier = self.env['fleet.vehicle.odometer'].search(
            [('vehicle_id', '=', self.vehicle_id.id)],
            order='date desc, id desc', limit=1
        )
        if dernier and not self.odometer_value:
            self.odometer_value = dernier.value

        # Déclencher le compute manuellement pour avoir quantite_suggeree à jour
        self._compute_distance()

        # Pré-remplir quantity si suggestion disponible et quantity pas encore saisie
        if self.quantite_suggeree > 0 and not self.quantity:
            self.quantity = self.quantite_suggeree

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(
                    "La quantite distribuee ne peut pas etre negative."
                )