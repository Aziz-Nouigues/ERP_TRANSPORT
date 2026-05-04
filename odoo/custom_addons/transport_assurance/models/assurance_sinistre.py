# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class AssuranceSinistre(models.Model):
    """Déclaration et suivi des sinistres.

    Un sinistre peut être lié à :
      - une police bus  (police_bus_id)
      - une police chauffeur (police_chauffeur_id)
    Il peut aussi référencer la tournée en cours (optionnel,
    guard runtime si transport_exploitation est installé).
    """
    _name = 'transport.assurance.sinistre'
    _description = 'Sinistre assurance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_sinistre desc, name desc'

    # ── IDENTIFICATION ───────────────────────────────────────────
    name = fields.Char(
        string='N° Sinistre',
        readonly=True, copy=False,
        default='Nouveau',
        tracking=True,
    )

    # ── POLICE CONCERNÉE ─────────────────────────────────────────
    objet_sinistre = fields.Selection([
        ('bus',      'Bus / Véhicule'),
        ('chauffeur', 'Chauffeur / Personnel'),
    ], string='Objet du sinistre', required=True, default='bus', tracking=True)

    police_bus_id = fields.Many2one(
        'transport.assurance.bus',
        string='Police bus',
        tracking=True,
        ondelete='restrict',
    )
    police_chauffeur_id = fields.Many2one(
        'transport.assurance.chauffeur',
        string='Police chauffeur',
        tracking=True,
        ondelete='restrict',
    )

    # ── CHAMPS DÉDUITS DE LA POLICE ──────────────────────────────
    compagnie_id = fields.Many2one(
        'transport.assurance.compagnie',
        string='Compagnie',
        compute='_compute_from_police',
        store=True,
        readonly=True,
    )
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Véhicule (Bus)',
        compute='_compute_from_police',
        store=True,
        tracking=True,
    )
    employe_id = fields.Many2one(
        'hr.employee',
        string='Employé / Chauffeur impliqué',
        compute='_compute_from_police',
        store=True,
        tracking=True,
    )
    type_police_id = fields.Many2one(
        'transport.assurance.type',
        string='Type de police',
        compute='_compute_from_police',
        store=True,
        readonly=True,
    )
    franchise = fields.Monetary(
        string='Franchise applicable',
        compute='_compute_from_police',
        store=True,
        currency_field='currency_id',
        readonly=True,
    )

    # ── FAIT GÉNÉRATEUR ──────────────────────────────────────────
    date_sinistre = fields.Date(
        string='Date du sinistre',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    heure_sinistre = fields.Float(
        string='Heure (h)', digits=(4, 2),
    )
    lieu = fields.Char(
        string='Lieu du sinistre',
        required=True,
        tracking=True,
    )
    gouvernorat = fields.Selection([
        ('tunis', 'Tunis'), ('ariana', 'Ariana'), ('ben_arous', 'Ben Arous'),
        ('manouba', 'La Manouba'), ('nabeul', 'Nabeul'), ('zaghouan', 'Zaghouan'),
        ('bizerte', 'Bizerte'), ('beja', 'Béja'), ('jendouba', 'Jendouba'),
        ('kef', 'Le Kef'), ('siliana', 'Siliana'), ('sousse', 'Sousse'),
        ('monastir', 'Monastir'), ('mahdia', 'Mahdia'), ('sfax', 'Sfax'),
        ('kairouan', 'Kairouan'), ('kasserine', 'Kasserine'),
        ('sidi_bouzid', 'Sidi Bouzid'), ('gabes', 'Gabès'),
        ('medenine', 'Médenine'), ('tataouine', 'Tataouine'),
        ('gafsa', 'Gafsa'), ('tozeur', 'Tozeur'), ('kebili', 'Kébili'),
    ], string='Gouvernorat')
    nature_sinistre = fields.Selection([
        ('collision',       'Collision / Accident circulation'),
        ('vol',             'Vol du véhicule'),
        ('tentative_vol',   'Tentative de vol'),
        ('incendie',        'Incendie'),
        ('bris_glace',      'Bris de glace'),
        ('catastrophe',     'Catastrophe naturelle'),
        ('vandalisme',      'Vandalisme / Dégradations'),
        ('accident_travail','Accident de travail'),
        ('maladie',         'Maladie professionnelle'),
        ('deces',           'Décès'),
        ('autre',           'Autre'),
    ], string='Nature du sinistre', required=True, tracking=True)
    description = fields.Text(
        string='Description des faits',
        required=True,
        tracking=True,
    )

    # ── LIEN EXPLOITATION (optionnel) ────────────────────────────
    tournee_id = fields.Many2one(
        'transport.exploitation.tournee',
        string='Tournée en cours',
        tracking=True,
        help='Renseignez si le sinistre s\'est produit pendant une tournée. '
             'Nécessite le module transport_exploitation.',
    )

    # ── TIERS IMPLIQUÉS ──────────────────────────────────────────
    tiers_implique = fields.Boolean(
        string='Tiers impliqué', default=False
    )
    tiers_nom = fields.Char(string='Nom du tiers')
    tiers_vehicule = fields.Char(string='Immatriculation véhicule tiers')
    tiers_assurance = fields.Char(string='Assurance du tiers')
    nb_blesses = fields.Integer(string='Nombre de blessés', default=0)
    nb_deces = fields.Integer(string='Nombre de décès', default=0)
    nb_passagers = fields.Integer(
        string='Passagers transportés',
        help='Nombre de passagers à bord au moment du sinistre.'
    )

    # ── DOCUMENTS ────────────────────────────────────────────────
    numero_pv_police = fields.Char(
        string='N° PV Police / Gendarmerie',
        tracking=True,
    )
    date_pv = fields.Date(string='Date PV')
    expertise_demandee = fields.Boolean(string='Expertise demandée')
    date_expertise = fields.Date(string='Date d\'expertise')
    expert_nom = fields.Char(string='Expert mandaté')

    # ── INDEMNISATION ────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.TND', raise_if_not_found=False)
                             or self.env.company.currency_id,
    )
    montant_reclame = fields.Monetary(
        string='Montant réclamé (TND)',
        currency_field='currency_id',
        tracking=True,
    )
    montant_accorde = fields.Monetary(
        string='Montant accordé (TND)',
        currency_field='currency_id',
        tracking=True,
    )
    franchise_appliquee = fields.Monetary(
        string='Franchise déduite',
        currency_field='currency_id',
        compute='_compute_franchise_appliquee',
        store=True,
    )
    montant_net_verse = fields.Monetary(
        string='Montant net versé',
        currency_field='currency_id',
        compute='_compute_montant_net',
        store=True,
    )
    motif_rejet = fields.Text(
        string='Motif de rejet / réduction',
        tracking=True,
    )

    # ── WORKFLOW ─────────────────────────────────────────────────
    state = fields.Selection([
        ('brouillon',   'Brouillon'),
        ('declare',     'Déclaré'),
        ('instruction', 'En instruction'),
        ('cloture',     'Clôturé'),
        ('rejete',      'Rejeté'),
    ], string='État', default='brouillon', tracking=True, required=True)

    date_declaration = fields.Date(string='Date de déclaration', tracking=True)
    date_cloture = fields.Date(string='Date de clôture', tracking=True)
    responsable_id = fields.Many2one(
        'res.users', string='Responsable suivi',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ── COMPUTE ─────────────────────────────────────────────────
    @api.depends('police_bus_id', 'police_chauffeur_id', 'objet_sinistre')
    def _compute_from_police(self):
        for rec in self:
            if rec.objet_sinistre == 'bus' and rec.police_bus_id:
                p = rec.police_bus_id
                rec.compagnie_id = p.compagnie_id
                rec.vehicle_id = p.vehicle_id
                rec.employe_id = False
                rec.type_police_id = p.type_police_id
                rec.franchise = p.franchise
            elif rec.objet_sinistre == 'chauffeur' and rec.police_chauffeur_id:
                p = rec.police_chauffeur_id
                rec.compagnie_id = p.compagnie_id
                rec.vehicle_id = False
                rec.employe_id = p.employe_id
                rec.type_police_id = p.type_police_id
                rec.franchise = p.franchise
            else:
                rec.compagnie_id = False
                rec.vehicle_id = False
                rec.employe_id = False
                rec.type_police_id = False
                rec.franchise = 0.0

    @api.depends('montant_accorde', 'franchise')
    def _compute_franchise_appliquee(self):
        for rec in self:
            if rec.montant_accorde and rec.franchise:
                rec.franchise_appliquee = min(rec.franchise, rec.montant_accorde)
            else:
                rec.franchise_appliquee = 0.0

    @api.depends('montant_accorde', 'franchise_appliquee')
    def _compute_montant_net(self):
        for rec in self:
            rec.montant_net_verse = max(
                0.0, (rec.montant_accorde or 0.0) - (rec.franchise_appliquee or 0.0)
            )

    # ── CONTRAINTES ──────────────────────────────────────────────
    @api.constrains('objet_sinistre', 'police_bus_id', 'police_chauffeur_id')
    def _check_police_required(self):
        for rec in self:
            if rec.objet_sinistre == 'bus' and not rec.police_bus_id:
                raise ValidationError(
                    'Veuillez sélectionner la police bus concernée par ce sinistre.'
                )
            if rec.objet_sinistre == 'chauffeur' and not rec.police_chauffeur_id:
                raise ValidationError(
                    'Veuillez sélectionner la police chauffeur concernée.'
                )

    @api.constrains('tournee_id')
    def _check_tournee_guard(self):
        """Guard optionnel : si transport_exploitation n'est pas installé,
        le champ tournee_id ne peut pas être renseigné (ne devrait pas
        arriver vu que le Many2one pointe vers un modèle inexistant,
        mais on sécurise par précaution).
        """
        if 'transport.exploitation.tournee' not in self.env:
            for rec in self:
                if rec.tournee_id:
                    raise ValidationError(
                        'Le module transport_exploitation n\'est pas installé. '
                        'Impossible de lier ce sinistre à une tournée.'
                    )

    # ── ACTIONS WORKFLOW ─────────────────────────────────────────
    def action_declarer(self):
        for rec in self:
            if rec.state != 'brouillon':
                raise UserError('Le sinistre est déjà déclaré.')
            if rec.name == 'Nouveau':
                rec.name = self.env['ir.sequence'].next_by_code(
                    'transport.assurance.sinistre'
                ) or 'SIN-??'
            rec.date_declaration = fields.Date.today()
            rec.state = 'declare'
            rec.message_post(
                body=f'Sinistre déclaré le {rec.date_declaration} '
                     f'— Lieu : {rec.lieu} — Nature : {dict(rec._fields["nature_sinistre"].selection).get(rec.nature_sinistre, "")}',
                subtype_xmlid='mail.mt_note',
            )

    def action_instruire(self):
        for rec in self:
            if rec.state != 'declare':
                raise UserError('Le sinistre doit être déclaré avant instruction.')
            rec.state = 'instruction'

    def action_cloturer(self):
        for rec in self:
            if rec.state not in ('declare', 'instruction'):
                raise UserError('Impossible de clôturer un sinistre dans cet état.')
            if not rec.montant_accorde and rec.montant_accorde != 0:
                raise UserError(
                    'Veuillez renseigner le montant accordé avant de clôturer.'
                )
            rec.date_cloture = fields.Date.today()
            rec.state = 'cloture'

    def action_rejeter(self):
        for rec in self:
            if rec.state not in ('declare', 'instruction'):
                raise UserError('Impossible de rejeter un sinistre dans cet état.')
            rec.state = 'rejete'

    def action_remettre_brouillon(self):
        for rec in self:
            if rec.state in ('cloture', 'rejete'):
                raise UserError(
                    'Un sinistre clôturé ou rejeté ne peut pas être remis en brouillon.'
                )
            rec.state = 'brouillon'
