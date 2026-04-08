# -*- coding: utf-8 -*-
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class FactureEnergie(models.Model):
    """Facture STEG (electricite) ou SONEDE (eau) par site.
    Le bouton 'Chercher N-1' retrouve automatiquement la facture
    du meme site, meme type, meme mois de l'annee precedente.
    A la creation, une facture fournisseur Odoo (account.move) est
    automatiquement generee et liee via invoice_id.
    """
    _name = 'transport.facture.energie'
    _description = 'Facture energie STEG / SONEDE'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_reception desc, id desc'

    name = fields.Char(string='N Facture', required=True, tracking=True)
    type_facture = fields.Selection([
        ('steg',   'STEG (Electricite)'),
        ('sonede', 'SONEDE (Eau)'),
    ], string='Type', required=True, tracking=True)
    statut = fields.Selection([
        ('saisie',  'Saisie'),
        ('payee',   'Payee'),
        ('annulee', 'Annulee'),
    ], string='Statut', default='saisie', tracking=True)

    site = fields.Char(string='Site / Agence', required=True, translate=False)
    adresse = fields.Char(string='Adresse du compteur')
    numero_compteur = fields.Char(string='N Compteur', required=True)

    date_debut_periode = fields.Date(string='Debut periode', required=True)
    date_fin_periode = fields.Date(string='Fin periode', required=True)
    date_reception = fields.Date(string='Date reception', required=True, default=fields.Date.today)

    quantite_consommee = fields.Float(string='Quantite consommee', required=True, digits=(10, 2))
    unite_mesure = fields.Char(string='Unite', compute='_calcul_unite', store=True)
    montant = fields.Float(string='Montant (TND)', required=True, digits=(10, 3))

    # Comparaison N-1 (peut etre remplie manuellement ou via bouton auto)
    consommation_n1 = fields.Float(string='Consommation N-1', digits=(10, 2))
    montant_n1 = fields.Float(string='Montant N-1 (TND)', digits=(10, 3))
    ecart_consommation = fields.Float(
        string='Ecart consommation',
        digits=(10, 2),
        compute='_calcul_ecart',
        store=True
    )
    ecart_pourcentage = fields.Float(
        string='Ecart (%)',
        digits=(5, 2),
        compute='_calcul_ecart',
        store=True
    )
    notes = fields.Text(string='Notes', translate=False)

    # Lien vers la facture comptable Odoo (account.move)
    invoice_id = fields.Many2one(
        'account.move',
        string='Facture comptable',
        readonly=True,
        copy=False,
        ondelete='set null',
        help="Facture fournisseur generee automatiquement dans la comptabilite Odoo."
    )
    invoice_state = fields.Selection(
        related='invoice_id.state',
        string='Etat comptable',
        readonly=True,
    )

    # Lien BOC bureau d'ordre (optionnel)
    boc_arrivee_id = fields.Many2one(
        'boc.courrier.arrivee',
        string='Courrier BOC associe',
        domain=[('type_courrier_id.name', 'ilike', 'facture')],
    )
    boc_reference = fields.Char(
        string='Ref BOC',
        related='boc_arrivee_id.name',
        store=True, readonly=True
    )

    # ── SYNCHRONISATION COMPTABILITE ─────────────────────────────

    def _get_or_create_partner(self, type_facture):
        """Retrouve ou cree le partenaire fournisseur STEG ou SONEDE."""
        name = 'STEG' if type_facture == 'steg' else 'SONEDE'
        partner = self.env['res.partner'].search(
            [('name', 'ilike', name), ('supplier_rank', '>', 0)], limit=1
        )
        if not partner:
            partner = self.env['res.partner'].search(
                [('name', 'ilike', name)], limit=1
            )
        if not partner:
            partner = self.env['res.partner'].create({
                'name': name,
                'supplier_rank': 1,
                'company_type': 'company',
            })
        return partner

    def _get_vendor_bill_journal(self):
        """Retrouve le journal Achats (type purchase)."""
        journal = self.env['account.journal'].search(
            [('type', '=', 'purchase'), ('company_id', '=', self.env.company.id)],
            limit=1
        )
        if not journal:
            raise ValidationError(
                "Aucun journal de type 'Achats' trouve dans la comptabilite. "
                "Veuillez en configurer un avant de creer une facture energie."
            )
        return journal

    def _build_invoice_vals(self):
        """Construit le dictionnaire de valeurs pour account.move."""
        self.ensure_one()
        partner = self._get_or_create_partner(self.type_facture)
        journal = self._get_vendor_bill_journal()
        label = (
            f"[{self.type_facture.upper()}] {self.name} — "
            f"{self.site} ({self.date_debut_periode} / {self.date_fin_periode})"
        )
        # Compte de charge par defaut : on cherche un compte 6xx, sinon None
        # Note: Odoo 19 utilise company_ids (Many2many) au lieu de company_id
        # Note: Odoo 19 a supprime le champ 'deprecated' de account.account
        account = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'expense_direct_cost']),
            ('company_ids', 'in', [self.env.company.id]),
        ], limit=1)
        line_vals = {
            'name': label,
            'quantity': self.quantite_consommee,
            'price_unit': self.montant / self.quantite_consommee if self.quantite_consommee else self.montant,
        }
        if account:
            line_vals['account_id'] = account.id
        return {
            'move_type': 'in_invoice',
            'ref': self.name,
            'partner_id': partner.id,
            'journal_id': journal.id,
            'invoice_date': self.date_reception,
            'invoice_date_due': self.date_reception,
            'narration': (
                f"Facture {self.type_facture.upper()} — Site : {self.site}\n"
                f"Compteur : {self.numero_compteur}\n"
                f"Periode : {self.date_debut_periode} au {self.date_fin_periode}\n"
                f"Consommation : {self.quantite_consommee} {self.unite_mesure}"
            ),
            'invoice_line_ids': [(0, 0, line_vals)],
        }

    def _sync_to_account_invoice(self):
        """Cree ou met a jour la facture comptable liee."""
        self.ensure_one()
        if not self.invoice_id:
            # Creation
            invoice = self.env['account.move'].sudo().create(self._build_invoice_vals())
            self.sudo().write({'invoice_id': invoice.id})
            self.message_post(
                body=f"Facture comptable creee automatiquement : <a href='/odoo/accounting/vendor-bills/{invoice.id}'>{invoice.name or 'Brouillon'}</a>"
            )
        else:
            # Mise a jour si encore en brouillon
            if self.invoice_id.state == 'draft':
                vals = self._build_invoice_vals()
                # On reecrit les lignes
                self.invoice_id.sudo().write({
                    'ref': vals['ref'],
                    'invoice_date': vals['invoice_date'],
                    'narration': vals['narration'],
                    'invoice_line_ids': [(5, 0, 0)] + [(0, 0, l[2]) for l in vals['invoice_line_ids']],
                })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._sync_to_account_invoice()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Re-synchronise si les champs financiers changent et facture encore en brouillon
        sync_triggers = {'montant', 'quantite_consommee', 'date_reception',
                         'date_debut_periode', 'date_fin_periode', 'site', 'name'}
        if sync_triggers & set(vals.keys()):
            for rec in self:
                if rec.invoice_id and rec.invoice_id.state == 'draft':
                    rec._sync_to_account_invoice()
        return res

    def action_open_invoice(self):
        """Ouvre la facture comptable Odoo liee."""
        self.ensure_one()
        if not self.invoice_id:
            raise ValidationError("Aucune facture comptable liee.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facture comptable',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── ACTIONS METIER ────────────────────────────────────────────

    @api.depends('type_facture')
    @api.constrains('date_debut_periode', 'date_fin_periode')
    def _verifier_periode(self):
        for facture in self:
            if (facture.date_debut_periode and facture.date_fin_periode
                    and facture.date_fin_periode < facture.date_debut_periode):
                raise ValidationError(
                    "La date de fin de periode ne peut pas etre anterieure "
                    "a la date de debut."
                )

    def _calcul_unite(self):
        for f in self:
            f.unite_mesure = 'kWh' if f.type_facture == 'steg' else 'm3' if f.type_facture == 'sonede' else ''

    @api.depends('quantite_consommee', 'consommation_n1')
    def _calcul_ecart(self):
        for f in self:
            f.ecart_consommation = f.quantite_consommee - f.consommation_n1
            if f.consommation_n1 > 0:
                f.ecart_pourcentage = round(f.ecart_consommation / f.consommation_n1 * 100, 2)
            else:
                f.ecart_pourcentage = 0.0

    def action_chercher_n1(self):
        """Recherche automatique de la facture N-1 pour ce site."""
        for facture in self:
            if not (facture.site and facture.type_facture and facture.date_debut_periode):
                continue
            date_n1 = facture.date_debut_periode - relativedelta(years=1)
            facture_n1 = self.search([
                ('site', '=', facture.site),
                ('type_facture', '=', facture.type_facture),
                ('date_debut_periode', '>=', date_n1.replace(day=1)),
                ('date_debut_periode', '<=', date_n1.replace(day=28)),
                ('id', '!=', facture.id),
                ('statut', '!=', 'annulee'),
            ], limit=1)
            if facture_n1:
                facture.write({
                    'consommation_n1': facture_n1.quantite_consommee,
                    'montant_n1': facture_n1.montant,
                })
            else:
                raise ValidationError(
                    f"Aucune facture N-1 trouvee pour le site '{facture.site}' "
                    f"({facture.type_facture.upper()}) en {date_n1.strftime('%B %Y')}."
                )

    def action_payer(self):
        """Marque la facture energie comme payee et confirme la facture comptable."""
        for rec in self:
            rec.write({'statut': 'payee'})
            if rec.invoice_id and rec.invoice_id.state == 'draft':
                rec.invoice_id.sudo().action_post()

    def action_annuler(self):
        """Annule la facture energie et la facture comptable si encore en brouillon."""
        for rec in self:
            rec.write({'statut': 'annulee'})
            if rec.invoice_id and rec.invoice_id.state == 'draft':
                rec.invoice_id.sudo().button_cancel()

    @api.constrains('date_debut_periode', 'date_fin_periode')
    def _verifier_dates(self):
        for f in self:
            if f.date_debut_periode and f.date_fin_periode:
                if f.date_fin_periode < f.date_debut_periode:
                    raise ValidationError("La date de fin doit etre apres la date de debut.")
