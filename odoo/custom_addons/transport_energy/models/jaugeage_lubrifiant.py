# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class StockLubrifiantMagasin(models.Model):
    """Stock theorique lubrifiant par atelier/magasin et type.
    Mis a jour uniquement par les bons lubrifiant valides et les jaugeages approuves.
    Un enregistrement = un type de lubrifiant dans un magasin donne.
    """
    _name = 'transport.stock.lubrifiant'
    _description = 'Stock lubrifiant magasin'
    _order = 'atelier, type_lubrifiant_id'
    _rec_name = 'display_name'

    atelier = fields.Char(
        string='Atelier / Magasin',
        required=True,
        translate=True,
        index=True,
    )
    agence = fields.Char(string='Agence / Depot', translate=True)
    type_lubrifiant_id = fields.Many2one(
        'transport.energy.type',
        string='Type de lubrifiant',
        required=True,
        domain="[('category','=','lubrifiant')]",
    )
    unite = fields.Char(
        string='Unite',
        related='type_lubrifiant_id.unite',
        store=True,
        readonly=True,
    )
    stock_actuel = fields.Float(
        string='Stock actuel (L)',
        digits=(10, 2),
        default=0.0,
        readonly=True,
        help="Stock en litres. Mis a jour par les bons lubrifiant et les jaugeages approuves.",
    )
    nb_unites_actuel = fields.Float(
        string='Stock actuel (unites)',
        digits=(10, 2),
        compute='_compute_nb_unites',
        store=True,
        help="Stock converti en unites de conditionnement (bidons, futs...). "
             "Affiche 0 si pas de conditionnement defini sur le type de lubrifiant."
    )
    stock_minimum = fields.Float(
        string='Seuil alerte stock (L)',
        digits=(10, 2),
        default=20.0,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    display_name = fields.Char(
        string='Designation',
        compute='_compute_display_name',
        store=True,
    )
    stock_status = fields.Selection([
        ('ok',       'Normal'),
        ('low',      'Bas'),
        ('critical', 'Critique'),
    ], string='Etat stock', compute='_compute_stock_status', store=True)

    @api.depends('atelier', 'type_lubrifiant_id')
    def _compute_display_name(self):
        for rec in self:
            lub = rec.type_lubrifiant_id.name or ''
            rec.display_name = f"{rec.atelier} — {lub}" if rec.atelier else lub

    @api.depends('stock_actuel', 'stock_minimum')
    def _compute_stock_status(self):
        for rec in self:
            if rec.stock_actuel <= 0:
                rec.stock_status = 'critical'
            elif rec.stock_actuel <= rec.stock_minimum:
                rec.stock_status = 'low'
            else:
                rec.stock_status = 'ok'

    @api.depends('stock_actuel', 'type_lubrifiant_id', 'type_lubrifiant_id.volume_conditionnement')
    def _compute_nb_unites(self):
        for rec in self:
            vol = rec.type_lubrifiant_id.volume_conditionnement if rec.type_lubrifiant_id else 0
            if vol > 0:
                rec.nb_unites_actuel = round(rec.stock_actuel / vol, 2)
            else:
                rec.nb_unites_actuel = 0.0

    def action_initialiser_stock(self):
        """Ouvre un wizard pour saisir le stock initial (directeur uniquement)."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Initialiser le stock',
            'res_model': 'transport.wizard.init.stock.lubrifiant',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_stock_lubrifiant_id': self.id},
        }

    def _add_stock(self, qty):
        """Credite le stock (appele par bon.lubrifiant a la validation)."""
        self.ensure_one()
        self.write({'stock_actuel': self.stock_actuel + qty})

    def _consume_stock(self, qty):
        """Debite le stock (appele par bon.lubrifiant a la validation)."""
        self.ensure_one()
        new = self.stock_actuel - qty
        if new < 0:
            raise ValidationError(
                f"Stock insuffisant en {self.atelier} "
                f"({self.type_lubrifiant_id.name}) : "
                f"disponible {self.stock_actuel:.2f} L, demande {qty:.2f} L."
            )
        self.write({'stock_actuel': new})

    _sql_constraints = [
        ('unique_atelier_type', 'unique(atelier, type_lubrifiant_id)',
         'Un seul enregistrement de stock par atelier et type de lubrifiant.'),
    ]


class JaugeageLubrifiant(models.Model):
    """Jaugeage physique des stocks de lubrifiants en magasin/atelier.
    Equivalent du jaugeage carburant (transport.jaugeage) mais pour
    les huiles, fluides et autres lubrifiants stockes en magasin.

    Flux :
        Brouillon → Confirme → Approuve
                       └→ Annule

    A l'approbation, si ajustement_stock=True, le stock du magasin
    (transport.stock.lubrifiant) est mis a jour avec le niveau mesure.
    Cette ecriture ne peut etre faite que par le directeur.
    """
    _name = 'transport.jaugeage.lubrifiant'
    _description = 'Jaugeage lubrifiant magasin'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # ── IDENTIFICATION ──────────────────────────────────────────
    name = fields.Char(
        string='N Jaugeage',
        required=True, copy=False, readonly=True,
        default='Nouveau', translate=False,
    )
    statut = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme',  'Confirme'),
        ('approuve',  'Approuve'),
        ('annule',    'Annule'),
    ], string='Statut', default='brouillon', tracking=True)

    # ── LOCALISATION ─────────────────────────────────────────────
    date = fields.Datetime(
        string='Date et heure',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    responsable = fields.Char(
        string='Responsable',
        required=True,
        translate=True,
    )
    atelier = fields.Char(
        string='Atelier / Magasin',
        required=True,
        translate=True,
        tracking=True,
    )
    agence = fields.Char(string='Agence / Depot', translate=True)

    # ── LUBRIFIANT ────────────────────────────────────────────────
    stock_lubrifiant_id = fields.Many2one(
        'transport.stock.lubrifiant',
        string='Stock lubrifiant (magasin)',
        required=True,
        tracking=True,
        domain="[('atelier','=',atelier)]",
        help="Selectionnez le type de lubrifiant a jauger dans cet atelier.",
    )
    type_lubrifiant_id = fields.Many2one(
        'transport.energy.type',
        string='Type lubrifiant',
        related='stock_lubrifiant_id.type_lubrifiant_id',
        store=True,
        readonly=True,
    )
    unite = fields.Char(
        string='Unite',
        related='stock_lubrifiant_id.unite',
        store=True,
        readonly=True,
    )

    # ── NIVEAUX ───────────────────────────────────────────────────
    stock_theorique = fields.Float(
        string='Stock theorique ERP (L)',
        digits=(10, 2),
        readonly=True,
        help="Snapshot du stock ERP au moment de la confirmation du jaugeage.",
    )
    niveau_mesure = fields.Float(
        string='Niveau mesure reel (L)',
        required=True,
        digits=(10, 2),
    )
    ecart = fields.Float(
        string='Ecart (L)',
        digits=(10, 2),
        compute='_calcul_ecart',
        store=True,
        help="Positif = surplus physique, Negatif = manque.",
    )
    ecart_pourcentage = fields.Float(
        string='Ecart (%)',
        digits=(5, 2),
        compute='_calcul_ecart',
        store=True,
    )
    niveau_alerte = fields.Selection([
        ('normal',    'Normal (< 1%)'),
        ('attention', 'Attention (1 a 3%)'),
        ('critique',  'Critique (> 3%)'),
    ], string='Niveau alerte', compute='_calcul_ecart', store=True)

    # ── AJUSTEMENT ────────────────────────────────────────────────
    ajustement_stock = fields.Boolean(
        string='Ajuster le stock ?',
        default=False,
        help=(
            "Si coche, le stock du magasin sera mis a jour avec le niveau "
            "mesure lors de l'approbation (directeur uniquement)."
        ),
    )
    justification = fields.Text(
        string='Justification de l ecart',
        translate=False,
    )
    notes = fields.Text(string='Notes', translate=False)

    # ── CALCULS ───────────────────────────────────────────────────
    @api.depends('stock_theorique', 'niveau_mesure')
    def _calcul_ecart(self):
        for rec in self:
            rec.ecart = rec.stock_theorique - rec.niveau_mesure
            if rec.stock_theorique > 0:
                pct = abs(rec.ecart) / rec.stock_theorique * 100
                rec.ecart_pourcentage = round(pct, 2)
            else:
                rec.ecart_pourcentage = 0.0
            pct = rec.ecart_pourcentage
            if pct < 1:
                rec.niveau_alerte = 'normal'
            elif pct <= 3:
                rec.niveau_alerte = 'attention'
            else:
                rec.niveau_alerte = 'critique'

    # ── onchange : pre-remplir atelier depuis le stock selectionne ──
    @api.onchange('stock_lubrifiant_id')
    def _onchange_stock_lubrifiant(self):
        if self.stock_lubrifiant_id:
            self.atelier = self.stock_lubrifiant_id.atelier
            self.agence  = self.stock_lubrifiant_id.agence

    # ── SEQUENCE ─────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code(
                        'transport.jaugeage.lubrifiant'
                    ) or 'Nouveau'
                )
            # Pre-remplir stock_theorique a la creation (valeur indicative)
            if not vals.get('stock_theorique') and vals.get('stock_lubrifiant_id'):
                stock = self.env['transport.stock.lubrifiant'].browse(
                    vals['stock_lubrifiant_id']
                )
                vals['stock_theorique'] = stock.stock_actuel
        return super().create(vals_list)

    # ── WORKFLOW ─────────────────────────────────────────────────
    def action_confirmer(self):
        """FIX : Snapshot du stock theorique au moment de la confirmation."""
        for rec in self:
            # Capturer le stock reel au moment exact de la confirmation
            stock_snapshot = (
                rec.stock_lubrifiant_id.stock_actuel
                if rec.stock_lubrifiant_id else 0.0
            )
            if rec.niveau_alerte == 'critique':
                rec.message_post(
                    body=(
                        f"ALERTE CRITIQUE : ecart de "
                        f"{rec.ecart_pourcentage:.2f}% detecte sur "
                        f"{rec.type_lubrifiant_id.name} — {rec.atelier}. "
                        f"Investigation obligatoire avant approbation."
                    ),
                    message_type='notification',
                )
            rec.write({
                'statut': 'confirme',
                'stock_theorique': stock_snapshot,  # Snapshot fixe
            })

    def action_approuver(self):
        for rec in self:
            if rec.statut != 'confirme':
                raise ValidationError(
                    "Le jaugeage doit etre confirme avant approbation."
                )
            if rec.niveau_alerte != 'normal' and not rec.justification:
                raise ValidationError(
                    "Une justification est obligatoire pour tout ecart superieur a 1%."
                )
            if rec.ajustement_stock and rec.stock_lubrifiant_id:
                ancien = rec.stock_lubrifiant_id.stock_actuel
                # Ecriture directe autorisee uniquement ici, par le directeur
                rec.stock_lubrifiant_id.with_context(
                    force_stock_write=True
                ).write({'stock_actuel': rec.niveau_mesure})
                rec.message_post(
                    body=(
                        f"Stock ajuste ({rec.type_lubrifiant_id.name} — "
                        f"{rec.atelier}) : "
                        f"{ancien:.2f} L → {rec.niveau_mesure:.2f} L"
                    ),
                    message_type='notification',
                )
            rec.write({'statut': 'approuve'})

    def action_annuler(self):
        for rec in self:
            if rec.statut == 'approuve':
                raise ValidationError(
                    "Impossible d'annuler un jaugeage approuve. "
                    "Contacter le directeur."
                )
            rec.write({'statut': 'annule'})

    def action_brouillon(self):
        self.write({'statut': 'brouillon'})

    # ── CONTRAINTES ───────────────────────────────────────────────
    @api.constrains('niveau_mesure')
    def _verifier_niveau(self):
        for rec in self:
            if rec.niveau_mesure < 0:
                raise ValidationError(
                    "Le niveau mesure ne peut pas etre negatif."
                )


class WizardInitStockLubrifiant(models.TransientModel):
    """Wizard pour initialiser ou ajuster manuellement le stock lubrifiant.
    Accessible uniquement au directeur. Crée une trace dans le chatter.
    Supporte la saisie en litres OU en unités de conditionnement (bidons, fûts...).
    """
    _name = 'transport.wizard.init.stock.lubrifiant'
    _description = 'Initialisation stock lubrifiant'

    stock_lubrifiant_id = fields.Many2one(
        'transport.stock.lubrifiant',
        string='Stock lubrifiant',
        required=True, readonly=True
    )
    type_lubrifiant_id = fields.Many2one(
        'transport.energy.type',
        string='Type lubrifiant',
        related='stock_lubrifiant_id.type_lubrifiant_id',
        readonly=True
    )
    atelier = fields.Char(
        string='Atelier',
        related='stock_lubrifiant_id.atelier',
        readonly=True
    )
    stock_actuel = fields.Float(
        string='Stock actuel (L)',
        related='stock_lubrifiant_id.stock_actuel',
        readonly=True
    )

    # Mode de saisie
    mode_saisie = fields.Selection([
        ('litres', 'En litres'),
        ('unites', 'En unités de conditionnement (bidons, fûts...)'),
    ], string='Saisir en', default='litres', required=True)

    # Saisie en litres
    quantite_litres = fields.Float(
        string='Quantité (L)',
        digits=(10, 2),
        default=0.0
    )

    # Saisie en unités de conditionnement
    nb_unites = fields.Float(
        string='Nombre d\'unités',
        digits=(10, 2),
        default=0.0,
        help="Nombre de bidons, fûts, cartouches..."
    )
    volume_unitaire = fields.Float(
        string='Volume par unité (L)',
        related='type_lubrifiant_id.volume_conditionnement',
        readonly=True
    )
    conditionnement = fields.Char(
        string='Type conditionnement',
        related='type_lubrifiant_id.conditionnement',
        readonly=True
    )
    quantite_calculee = fields.Float(
        string='Quantité calculée (L)',
        compute='_compute_quantite_calculee',
        digits=(10, 2)
    )

    motif = fields.Text(
        string='Motif',
        required=True,
        help="Justification de la modification (stock initial, correction, ...)"
    )

    @api.depends('mode_saisie', 'quantite_litres', 'nb_unites', 'volume_unitaire')
    def _compute_quantite_calculee(self):
        for rec in self:
            if rec.mode_saisie == 'litres':
                rec.quantite_calculee = rec.quantite_litres
            elif rec.volume_unitaire > 0:
                # Conditionnement configuré : nb_unites × volume
                rec.quantite_calculee = round(rec.nb_unites * rec.volume_unitaire, 2)
            else:
                # Pas de conditionnement : nb_unites = litres directement
                rec.quantite_calculee = rec.nb_unites

    @api.onchange('mode_saisie')
    def _onchange_mode_saisie(self):
        self.quantite_litres = 0.0
        self.nb_unites = 0.0

    def action_valider(self):
        self.ensure_one()
        stock = self.stock_lubrifiant_id
        quantite = self.quantite_calculee

        if quantite <= 0:
            if self.mode_saisie == 'unites' and self.volume_unitaire <= 0:
                raise ValidationError(
                    "Le type de lubrifiant '%s' n'a pas de conditionnement configure "
                    "(volume par unite = 0). "
                    "Configurez le conditionnement dans Configuration > Types d'energie, "
                    "ou choisissez le mode 'En litres'." % (
                        self.type_lubrifiant_id.name or ''
                    )
                )
            raise ValidationError("La quantite doit etre superieure a 0.")

        ancien = stock.stock_actuel
        stock.write({'stock_actuel': quantite})

        # Message chatter détaillé
        if self.mode_saisie == 'unites' and self.conditionnement and self.volume_unitaire > 0:
            detail = (
                f"{self.nb_unites:.0f} {self.conditionnement}(s) "
                f"× {self.volume_unitaire:.2f} L = {quantite:.2f} L"
            )
        else:
            detail = f"{quantite:.2f} L"

        # Log de la modification dans odoo.log
        import logging
        logging.getLogger(__name__).info(
            "Stock lubrifiant [%s] ajuste par %s : %.2f L -> %.2f L. %s. Motif: %s",
            stock.display_name, self.env.user.name, ancien, quantite, detail, self.motif
        )
        return {'type': 'ir.actions.act_window_close'}
