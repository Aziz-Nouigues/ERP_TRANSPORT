# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class PatrimoineInventaire(models.Model):
    """
    Session d'inventaire physique des immobilisations.
    Permet de constater les écarts et d'effectuer les ajustements nécessaires.
    """
    _name = 'patrimoine.inventaire'
    _description = 'Inventaire des immobilisations'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(
        string='N° Inventaire',
        readonly=True,
        copy=False,
        default='Nouveau',
    )
    date = fields.Date(
        string='Date d\'inventaire',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    date_debut = fields.Date(string='Début de la campagne')
    date_fin = fields.Date(string='Fin de la campagne')
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable inventaire',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    state = fields.Selection([
        ('ouvert',   'Ouvert'),
        ('en_cours', 'En cours'),
        ('cloture',  'Clôturé'),
        ('valide',   'Validé'),
    ], string='État', default='ouvert', tracking=True)

    # Filtres
    site_filtre = fields.Char(string='Site filtré')
    categorie_filtre_id = fields.Many2one('patrimoine.categorie', string='Catégorie filtrée')

    ligne_ids = fields.One2many(
        'patrimoine.inventaire.ligne',
        'inventaire_id',
        string='Lignes d\'inventaire',
    )

    # Statistiques
    nb_immobilisations = fields.Integer(
        string='Nb immobilisations recensées',
        compute='_compute_stats',
    )
    nb_retrouvees = fields.Integer(
        string='Retrouvées',
        compute='_compute_stats',
    )
    nb_manquantes = fields.Integer(
        string='Manquantes',
        compute='_compute_stats',
    )
    nb_ecarts = fields.Integer(
        string='Avec écart',
        compute='_compute_stats',
    )

    notes = fields.Text(string='Observations générales')

    @api.depends('ligne_ids.etat_constate')
    def _compute_stats(self):
        for rec in self:
            lignes = rec.ligne_ids
            rec.nb_immobilisations = len(lignes)
            rec.nb_retrouvees = len(lignes.filtered(lambda l: l.etat_constate == 'retrouve'))
            rec.nb_manquantes = len(lignes.filtered(lambda l: l.etat_constate == 'manquant'))
            rec.nb_ecarts = len(lignes.filtered(lambda l: l.ecart_quantite != 0))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('patrimoine.inventaire') or 'Nouveau'
                )
        return super().create(vals_list)

    def action_charger_immobilisations(self):
        """Charger toutes les immobilisations actives dans les lignes d'inventaire."""
        self.ensure_one()
        if self.state == 'valide':
            raise UserError("Impossible de modifier un inventaire validé.")

        domain = [('statut', 'in', ('en_service', 'hors_service'))]
        if self.categorie_filtre_id:
            domain.append(('categorie_id', '=', self.categorie_filtre_id.id))
        if self.site_filtre:
            domain.append(('emplacement_id.site', 'ilike', self.site_filtre))

        immobilisations = self.env['patrimoine.immobilisation'].search(domain)

        # Supprimer les lignes existantes non validées
        self.ligne_ids.filtered(lambda l: not l.inventorie).unlink()

        lignes_a_creer = []
        immo_existantes = self.ligne_ids.mapped('immobilisation_id').ids
        for immo in immobilisations:
            if immo.id not in immo_existantes:
                lignes_a_creer.append({
                    'inventaire_id': self.id,
                    'immobilisation_id': immo.id,
                    'quantite_theorique': immo.quantite,
                    'quantite_constatee': 0.0,
                    'etat_constate': 'non_inventorie',
                })
        if lignes_a_creer:
            self.env['patrimoine.inventaire.ligne'].create(lignes_a_creer)
        self.state = 'en_cours'

    def action_valider(self):
        """Valider l'inventaire et appliquer les ajustements."""
        self.ensure_one()
        # Sortir les immobilisations non retrouvées
        lignes_manquantes = self.ligne_ids.filtered(lambda l: l.etat_constate == 'manquant')
        for ligne in lignes_manquantes:
            ligne.immobilisation_id.write({
                'statut': 'rebut',
                'date_rebut': fields.Date.today(),
            })
            ligne.immobilisation_id.message_post(
                body="Mise en rebut suite inventaire %s — immobilisation non retrouvée." % self.name,
                message_type='comment',
            )
        self.state = 'valide'

    def action_imprimer_bordereau(self):
        return self.env.ref(
            'transport_patrimoine.action_rapport_bordereau_inventaire'
        ).report_action(self)

    def action_imprimer_ecarts(self):
        return self.env.ref(
            'transport_patrimoine.action_rapport_bordereau_ecarts'
        ).report_action(self)


class PatrimoineInventaireLigne(models.Model):
    """Ligne d'une session d'inventaire."""
    _name = 'patrimoine.inventaire.ligne'
    _description = 'Ligne d\'inventaire'
    _order = 'inventaire_id, immobilisation_id'

    inventaire_id = fields.Many2one(
        'patrimoine.inventaire',
        string='Inventaire',
        required=True,
        ondelete='cascade',
    )
    immobilisation_id = fields.Many2one(
        'patrimoine.immobilisation',
        string='Immobilisation',
        required=True,
        ondelete='restrict',
    )
    numero_inventaire = fields.Char(
        related='immobilisation_id.numero_inventaire',
        store=True, readonly=True,
    )
    categorie_id = fields.Many2one(
        related='immobilisation_id.categorie_id',
        store=True, readonly=True,
    )
    emplacement_id = fields.Many2one(
        related='immobilisation_id.emplacement_id',
        store=True, readonly=True,
    )

    quantite_theorique = fields.Float(
        string='Qté théorique',
        digits=(10, 2),
        readonly=True,
    )
    quantite_constatee = fields.Float(
        string='Qté constatée',
        digits=(10, 2),
        default=0.0,
    )
    ecart_quantite = fields.Float(
        string='Écart',
        digits=(10, 2),
        compute='_compute_ecart',
        store=True,
    )
    etat_constate = fields.Selection([
        ('non_inventorie', 'Non inventorié'),
        ('retrouve',       'Retrouvé'),
        ('manquant',       'Manquant'),
        ('deteriore',      'Détérioré'),
        ('excedent',       'En excédent'),
    ], string='État constaté', default='non_inventorie', required=True)

    inventorie = fields.Boolean(string='Inventorié', default=False)
    observateurs = fields.Char(string='Observateurs / Signataires')
    remarques = fields.Char(string='Remarques')

    @api.depends('quantite_theorique', 'quantite_constatee')
    def _compute_ecart(self):
        for rec in self:
            rec.ecart_quantite = rec.quantite_constatee - rec.quantite_theorique

    def action_marquer_retrouve(self):
        for rec in self:
            rec.write({
                'etat_constate': 'retrouve',
                'quantite_constatee': rec.quantite_theorique,
                'inventorie': True,
            })

    def action_marquer_manquant(self):
        for rec in self:
            rec.write({
                'etat_constate': 'manquant',
                'quantite_constatee': 0.0,
                'inventorie': True,
            })


class PatrimoineInventaireCron(models.Model):
    """Extension du modèle inventaire pour les méthodes cron."""
    _inherit = 'patrimoine.inventaire'

    @api.model
    def _cron_rappel_inventaire_annuel(self):
        """Cron mensuel : alerte si aucun inventaire validé depuis 12 mois."""
        import datetime
        today = fields.Date.today()
        un_an = today - datetime.timedelta(days=365)
        dernier = self.search([
            ('state', '=', 'valide'),
            ('date', '>=', un_an),
        ], limit=1, order='date desc')
        if not dernier:
            _logger.warning(
                'Patrimoine — Aucun inventaire physique validé depuis 12 mois !'
            )