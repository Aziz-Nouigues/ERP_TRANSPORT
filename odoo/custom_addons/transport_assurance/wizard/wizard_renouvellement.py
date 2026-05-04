# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class WizardRenouvellement(models.TransientModel):
    """Wizard de renouvellement d'une police d'assurance bus ou chauffeur.
    Crée une nouvelle police en copiant l'ancienne avec les nouvelles dates
    et lie les deux polices (police_precedente_id / police_suivante_id).
    """
    _name = 'transport.assurance.wizard.renouvellement'
    _description = 'Wizard renouvellement police assurance'

    # ── CONTEXTE ─────────────────────────────────────────────────
    police_bus_id = fields.Many2one(
        'transport.assurance.bus', string='Police bus à renouveler'
    )
    police_chauffeur_id = fields.Many2one(
        'transport.assurance.chauffeur', string='Police chauffeur à renouveler'
    )
    type_renouvellement = fields.Selection([
        ('bus',      'Police bus'),
        ('chauffeur', 'Police chauffeur'),
    ], string='Type', compute='_compute_type', store=True)

    # ── VÉHICULE / EMPLOYÉ (déduit) ──────────────────────────────
    vehicle_id = fields.Many2one('fleet.vehicle', string='Bus')
    employe_id = fields.Many2one('hr.employee', string='Chauffeur / Employé')
    type_police_id = fields.Many2one('transport.assurance.type', string='Type de police')
    compagnie_id = fields.Many2one(
        'transport.assurance.compagnie', string='Compagnie', required=True
    )

    # ── NOUVELLES CONDITIONS ──────────────────────────────────────
    date_debut = fields.Date(string='Nouvelle date de début', required=True)
    date_fin = fields.Date(string='Nouvelle date de fin', required=True)
    prime_annuelle = fields.Monetary(
        string='Prime annuelle (TND)',
        currency_field='currency_id',
    )
    franchise = fields.Monetary(
        string='Franchise (TND)',
        currency_field='currency_id',
    )
    plafond_garantie = fields.Monetary(
        string='Plafond garantie (TND)',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.TND', raise_if_not_found=False)
                             or self.env.company.currency_id,
    )

    # ── VISITE TECHNIQUE (pour RC) ───────────────────────────────
    date_visite_technique = fields.Date(
        string='Date visite technique',
        help='Obligatoire pour le renouvellement RC (règle Tunisie).'
    )
    notes = fields.Text(string='Notes / Conditions particulières')

    @api.depends('police_bus_id', 'police_chauffeur_id')
    def _compute_type(self):
        for rec in self:
            if rec.police_bus_id:
                rec.type_renouvellement = 'bus'
            elif rec.police_chauffeur_id:
                rec.type_renouvellement = 'chauffeur'
            else:
                rec.type_renouvellement = False

    @api.onchange('police_bus_id')
    def _onchange_police_bus(self):
        if self.police_bus_id:
            p = self.police_bus_id
            from dateutil.relativedelta import relativedelta
            self.date_debut = p.date_fin + relativedelta(days=1) if p.date_fin else fields.Date.today()
            self.date_fin = self.date_debut + relativedelta(years=1) if self.date_debut else False
            self.prime_annuelle = p.prime_annuelle
            self.franchise = p.franchise
            self.plafond_garantie = p.plafond_garantie

    @api.onchange('police_chauffeur_id')
    def _onchange_police_chauffeur(self):
        if self.police_chauffeur_id:
            p = self.police_chauffeur_id
            from dateutil.relativedelta import relativedelta
            self.date_debut = p.date_fin + relativedelta(days=1) if p.date_fin else fields.Date.today()
            self.date_fin = self.date_debut + relativedelta(years=1) if self.date_debut else False
            self.prime_annuelle = p.prime_annuelle
            self.franchise = p.franchise

    def action_confirmer(self):
        self.ensure_one()
        if self.type_renouvellement == 'bus':
            return self._renouveler_bus()
        elif self.type_renouvellement == 'chauffeur':
            return self._renouveler_chauffeur()
        raise UserError('Type de renouvellement non déterminé.')

    def _renouveler_bus(self):
        ancienne = self.police_bus_id
        # Vérification visite technique pour RC
        if (ancienne.type_police_id and ancienne.type_police_id.code == 'RC'
                and not self.date_visite_technique):
            raise UserError(
                'La date de visite technique est obligatoire pour le '
                'renouvellement d\'une police RC (règle Tunisie).'
            )
        nouvelle = self.env['transport.assurance.bus'].create({
            'vehicle_id': ancienne.vehicle_id.id,
            'type_police_id': ancienne.type_police_id.id,
            'compagnie_id': self.compagnie_id.id,
            'date_debut': self.date_debut,
            'date_fin': self.date_fin,
            'prime_annuelle': self.prime_annuelle,
            'franchise': self.franchise,
            'plafond_garantie': self.plafond_garantie,
            'date_visite_technique': self.date_visite_technique,
            'police_precedente_id': ancienne.id,
            'notes': self.notes,
            'state': 'brouillon',
        })
        ancienne.police_suivante_id = nouvelle.id
        if ancienne.state == 'active':
            ancienne.state = 'expirée'
        nouvelle.action_activer()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'transport.assurance.bus',
            'res_id': nouvelle.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _renouveler_chauffeur(self):
        ancienne = self.police_chauffeur_id
        nouvelle = self.env['transport.assurance.chauffeur'].create({
            'employe_id': ancienne.employe_id.id,
            'type_police_id': ancienne.type_police_id.id,
            'compagnie_id': self.compagnie_id.id,
            'date_debut': self.date_debut,
            'date_fin': self.date_fin,
            'prime_annuelle': self.prime_annuelle,
            'franchise': self.franchise,
            'capital_assure': ancienne.capital_assure,
            'beneficiaire': ancienne.beneficiaire,
            'lien_beneficiaire': ancienne.lien_beneficiaire,
            'notes': self.notes,
            'state': 'brouillon',
        })
        if ancienne.state == 'active':
            ancienne.state = 'expirée'
        nouvelle.action_activer()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'transport.assurance.chauffeur',
            'res_id': nouvelle.id,
            'view_mode': 'form',
            'target': 'current',
        }