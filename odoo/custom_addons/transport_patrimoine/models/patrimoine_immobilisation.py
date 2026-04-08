# -*- coding: utf-8 -*-
import datetime
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PatrimoineImmobilisation(models.Model):
    """Fiche individuelle d'immobilisation — cœur du module patrimoine."""
    _name = 'patrimoine.immobilisation'
    _description = 'Immobilisation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'numero_inventaire, name'

    # ── IDENTIFICATION ───────────────────────────────────────────
    name = fields.Char(
        string='Désignation',
        required=True,
        translate=True,
        tracking=True,
    )
    numero_inventaire = fields.Char(
        string='N° Inventaire',
        readonly=True,
        copy=False,
        default='Nouveau',
        tracking=True,
    )
    reference = fields.Char(
        string='Référence interne',
        tracking=True,
    )
    numero_serie = fields.Char(string='N° Série / Immatriculation')
    marque = fields.Char(string='Marque / Modèle')
    description = fields.Text(string='Description complémentaire')

    # ── CLASSIFICATION ───────────────────────────────────────────
    categorie_id = fields.Many2one(
        'patrimoine.categorie',
        string='Catégorie',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    sous_categorie_id = fields.Many2one(
        'patrimoine.sous.categorie',
        string='Sous-catégorie',
        domain="[('categorie_id','=',categorie_id)]",
        tracking=True,
        ondelete='restrict',
    )

    # ── TYPE D'ENTRÉE ────────────────────────────────────────────
    type_entree = fields.Selection([
        ('acquisition',   'Acquisition'),
        ('echange',       'Échange'),
        ('livraison_soi', 'Livraison à soi-même'),
        ('don',           'Don / Subvention'),
        ('apport',        'Apport en nature'),
    ], string='Mode d\'entrée', required=True, default='acquisition', tracking=True)

    # ── STATUT ───────────────────────────────────────────────────
    statut = fields.Selection([
        ('en_cours',     'En cours'),
        ('en_service',   'En service'),
        ('hors_service', 'Hors service'),
        ('cede',         'Cédé'),
        ('rebut',        'Mis en rebut'),
        ('inventorie',   'Inventorié'),
    ], string='Statut', default='en_cours', tracking=True, required=True)

    # ── DATES ────────────────────────────────────────────────────
    date_acquisition = fields.Date(
        string='Date d\'acquisition',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    date_mise_en_service = fields.Date(
        string='Date de mise en service',
        tracking=True,
    )
    date_hors_service = fields.Date(
        string='Date de mise hors service',
        tracking=True,
    )
    motif_hors_service = fields.Char(
        string='Motif hors exploitation',
    )
    date_cession = fields.Date(string='Date de cession', tracking=True)
    date_rebut = fields.Date(string='Date de rebut', tracking=True)
    fin_amortissement = fields.Date(
        string='Fin d\'amortissement prévue',
        compute='_compute_fin_amortissement',
        store=True,
    )

    # ── EMPLACEMENT ──────────────────────────────────────────────
    emplacement_id = fields.Many2one(
        'patrimoine.emplacement',
        string='Emplacement actuel',
        tracking=True,
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable / Affectataire',
        tracking=True,
        default=lambda self: self.env.user,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Département affectataire',
        related='emplacement_id.department_id',
        store=True,
        readonly=True,
    )
    quantite = fields.Float(
        string='Quantité',
        default=1.0,
        digits=(10, 2),
        help='Nombre d\'unités pour cet actif',
    )
    quantite_distribuee = fields.Float(
        string='Quantité distribuée',
        compute='_compute_quantites',
        store=True,
        digits=(10, 2),
    )
    quantite_non_distribuee = fields.Float(
        string='Quantité non distribuée',
        compute='_compute_quantites',
        store=True,
        digits=(10, 2),
    )

    # ── VALEURS FINANCIÈRES ───────────────────────────────────────
    cout_acquisition = fields.Float(
        string='Coût d\'acquisition (DT)',
        digits=(15, 3),
        required=True,
        tracking=True,
    )
    frais_accessoires = fields.Float(
        string='Frais accessoires (DT)',
        digits=(15, 3),
        help='Frais de transport, installation, montage...',
    )
    depenses_posterieures = fields.Float(
        string='Dépenses postérieures (DT)',
        digits=(15, 3),
        compute='_compute_depenses_posterieures',
        store=True,
        help='Total des dépenses postérieures activées',
    )
    cout_entree = fields.Float(
        string='Coût d\'entrée total (DT)',
        digits=(15, 3),
        compute='_compute_cout_entree',
        store=True,
    )
    valeur_residuelle = fields.Float(
        string='Valeur résiduelle (DT)',
        digits=(15, 3),
        default=0.0,
        tracking=True,
    )
    base_amortissable = fields.Float(
        string='Base amortissable (DT)',
        digits=(15, 3),
        compute='_compute_base_amortissable',
        store=True,
    )
    valeur_nette_comptable = fields.Float(
        string='VNC (DT)',
        digits=(15, 3),
        compute='_compute_vnc',
        store=True,
    )
    amortissements_cumules = fields.Float(
        string='Amortissements cumulés (DT)',
        digits=(15, 3),
        compute='_compute_vnc',
        store=True,
    )
    depreciation_cumule = fields.Float(
        string='Dépréciations cumulées (DT)',
        digits=(15, 3),
        compute='_compute_vnc',
        store=True,
    )

    # ── AMORTISSEMENT ────────────────────────────────────────────
    methode_amortissement = fields.Selection([
        ('lineaire',  'Linéaire'),
        ('degressif', 'Dégressif'),
        ('manuel',    'Manuel'),
    ], string='Méthode d\'amortissement',
       default='lineaire',
       required=True,
       tracking=True,
    )
    duree_amortissement = fields.Integer(
        string='Durée d\'amortissement (années)',
        default=5,
        required=True,
        tracking=True,
    )
    taux_amortissement = fields.Float(
        string='Taux d\'amortissement (%)',
        digits=(6, 4),
        compute='_compute_taux',
        store=True,
    )
    coefficient_degressif = fields.Float(
        string='Coefficient dégressif',
        default=1.5,
        digits=(4, 2),
    )
    amortissement_en_cours = fields.Boolean(
        string='Amortissement démarré',
        compute='_compute_amort_en_cours',
        store=True,
    )
    entierement_amorti = fields.Boolean(
        string='Entièrement amorti',
        compute='_compute_amort_en_cours',
        store=True,
    )

    # ── LIGNES D'AMORTISSEMENT ────────────────────────────────────
    ligne_amortissement_ids = fields.One2many(
        'patrimoine.amortissement.ligne',
        'immobilisation_id',
        string='Tableau d\'amortissement',
    )
    depreciation_ids = fields.One2many(
        'patrimoine.depreciation',
        'immobilisation_id',
        string='Dépréciations',
    )
    depense_posterieure_ids = fields.One2many(
        'patrimoine.depense.posterieure',
        'immobilisation_id',
        string='Dépenses postérieures',
    )

    # ── MOUVEMENTS & AFFECTATIONS ─────────────────────────────────
    mouvement_ids = fields.One2many(
        'patrimoine.mouvement',
        'immobilisation_id',
        string='Historique des transferts',
    )
    affectation_ids = fields.One2many(
        'patrimoine.affectation',
        'immobilisation_id',
        string='Affectations / Distribution',
    )

    # ── COMPTABILITÉ ──────────────────────────────────────────────
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal comptable',
        domain=[('type', 'in', ['general', 'purchase'])],
    )
    move_entree_id = fields.Many2one(
        'account.move',
        string='Écriture d\'entrée',
        readonly=True,
        copy=False,
    )

    # ── PIÈCES JOINTES & DOCUMENTS ───────────────────────────────
    facture_achat_ids = fields.Many2many(
        'account.move',
        'patrimoine_immo_facture_rel',
        'immobilisation_id',
        'move_id',
        string='Factures rattachées',
        domain=[('move_type', 'in', ['in_invoice', 'in_refund'])],
    )
    fournisseur_id = fields.Many2one('res.partner', string='Fournisseur')
    bon_commande_ref = fields.Char(string='N° Bon de commande')
    facture_ref = fields.Char(string='N° Facture d\'achat')

    # ── PROJET (pour rapports par projet) ─────────────────────────
    projet = fields.Char(string='Projet / Programme', translate=True)
    annee_budget = fields.Char(
        string='Année budgétaire',
        default=lambda self: str(fields.Date.today().year),
    )

    # ═══════════════════════════════════════════════════════════
    # COMPUTE METHODS
    # ═══════════════════════════════════════════════════════════

    @api.depends('depense_posterieure_ids.montant', 'depense_posterieure_ids.state')
    def _compute_depenses_posterieures(self):
        for rec in self:
            rec.depenses_posterieures = sum(
                d.montant for d in rec.depense_posterieure_ids
                if d.state == 'valide'
            )

    @api.depends('cout_acquisition', 'frais_accessoires', 'depenses_posterieures')
    def _compute_cout_entree(self):
        for rec in self:
            rec.cout_entree = (
                rec.cout_acquisition + rec.frais_accessoires + rec.depenses_posterieures
            )

    @api.depends('cout_entree', 'valeur_residuelle')
    def _compute_base_amortissable(self):
        for rec in self:
            rec.base_amortissable = max(
                rec.cout_entree - rec.valeur_residuelle, 0.0
            )

    @api.depends('duree_amortissement', 'methode_amortissement', 'coefficient_degressif')
    def _compute_taux(self):
        for rec in self:
            if rec.duree_amortissement and rec.duree_amortissement > 0:
                taux_lin = 100.0 / rec.duree_amortissement
                if rec.methode_amortissement == 'degressif':
                    rec.taux_amortissement = taux_lin * rec.coefficient_degressif
                else:
                    rec.taux_amortissement = taux_lin
            else:
                rec.taux_amortissement = 0.0

    @api.depends('date_mise_en_service', 'duree_amortissement')
    def _compute_fin_amortissement(self):
        for rec in self:
            if rec.date_mise_en_service and rec.duree_amortissement:
                rec.fin_amortissement = rec.date_mise_en_service.replace(
                    year=rec.date_mise_en_service.year + rec.duree_amortissement
                )
            else:
                rec.fin_amortissement = False

    @api.depends('ligne_amortissement_ids.montant_amortissement', 'ligne_amortissement_ids.state',
                 'depreciation_ids.montant', 'depreciation_ids.state',
                 'cout_entree')
    def _compute_vnc(self):
        for rec in self:
            amort_cumule = sum(
                l.montant_amortissement for l in rec.ligne_amortissement_ids
                if l.state == 'valide'
            )
            deprec_cumule = sum(
                d.montant for d in rec.depreciation_ids
                if d.state == 'valide'
            )
            rec.amortissements_cumules = amort_cumule
            rec.depreciation_cumule = deprec_cumule
            rec.valeur_nette_comptable = rec.cout_entree - amort_cumule - deprec_cumule

    @api.depends('ligne_amortissement_ids.state', 'base_amortissable', 'amortissements_cumules')
    def _compute_amort_en_cours(self):
        for rec in self:
            rec.amortissement_en_cours = bool(
                rec.ligne_amortissement_ids.filtered(lambda l: l.state == 'valide')
            )
            rec.entierement_amorti = (
                rec.base_amortissable > 0 and
                rec.amortissements_cumules >= rec.base_amortissable - 0.001
            )

    @api.depends('affectation_ids.quantite', 'affectation_ids.state')
    def _compute_quantites(self):
        for rec in self:
            distribuee = sum(
                a.quantite for a in rec.affectation_ids
                if a.state == 'active'
            )
            rec.quantite_distribuee = distribuee
            rec.quantite_non_distribuee = max(rec.quantite - distribuee, 0.0)

    # ═══════════════════════════════════════════════════════════
    # ONCHANGE
    # ═══════════════════════════════════════════════════════════

    @api.onchange('categorie_id')
    def _onchange_categorie_id(self):
        """Pré-remplir la méthode et la durée depuis la catégorie"""
        if self.categorie_id:
            self.methode_amortissement = self.categorie_id.methode_amortissement or 'lineaire'
            self.duree_amortissement = self.categorie_id.duree_amortissement or 5
            self.coefficient_degressif = self.categorie_id.taux_degressif or 1.5
            self.sous_categorie_id = False

    @api.onchange('sous_categorie_id')
    def _onchange_sous_categorie_id(self):
        """Surcharger avec les paramètres de la sous-catégorie si renseignés"""
        sc = self.sous_categorie_id
        if sc and sc.methode_amortissement != 'herite':
            self.methode_amortissement = sc.methode_amortissement
        if sc and sc.duree_amortissement > 0:
            self.duree_amortissement = sc.duree_amortissement

    # ═══════════════════════════════════════════════════════════
    # CONTRAINTES
    # ═══════════════════════════════════════════════════════════

    @api.constrains('date_mise_en_service', 'date_acquisition')
    def _check_dates(self):
        for rec in self:
            if rec.date_mise_en_service and rec.date_acquisition:
                if rec.date_mise_en_service < rec.date_acquisition:
                    raise ValidationError(
                        "La date de mise en service ne peut pas être antérieure "
                        "à la date d'acquisition."
                    )

    @api.constrains('cout_acquisition')
    def _check_cout(self):
        for rec in self:
            if rec.cout_acquisition < 0:
                raise ValidationError("Le coût d'acquisition ne peut pas être négatif.")

    @api.constrains('duree_amortissement')
    def _check_duree(self):
        for rec in self:
            if rec.duree_amortissement <= 0:
                raise ValidationError("La durée d'amortissement doit être supérieure à 0.")

    # ═══════════════════════════════════════════════════════════
    # ORM
    # ═══════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('numero_inventaire', 'Nouveau') == 'Nouveau':
                vals['numero_inventaire'] = (
                    self.env['ir.sequence'].next_by_code('patrimoine.immobilisation') or 'Nouveau'
                )
        return super().create(vals_list)

    # ═══════════════════════════════════════════════════════════
    # ACTIONS WORKFLOW
    # ═══════════════════════════════════════════════════════════

    def action_mettre_en_service(self):
        """Passer en statut 'En service' et générer l'écriture comptable d'entrée."""
        for rec in self:
            if rec.statut not in ('en_cours',):
                raise UserError("Seules les immobilisations 'En cours' peuvent être mises en service.")
            if not rec.date_mise_en_service:
                rec.date_mise_en_service = fields.Date.today()
            rec.statut = 'en_service'
            # Générer l'écriture comptable d'entrée
            rec._generer_ecriture_entree()

    def action_mettre_hors_service(self):
        """Passer en statut 'Hors service'."""
        for rec in self:
            if rec.statut not in ('en_service',):
                raise UserError("Seules les immobilisations 'En service' peuvent être mises hors service.")
            rec.statut = 'hors_service'
            if not rec.date_hors_service:
                rec.date_hors_service = fields.Date.today()

    def action_reset_en_service(self):
        """Remettre en service."""
        for rec in self:
            rec.statut = 'en_service'
            rec.date_hors_service = False
            rec.motif_hors_service = False

    def action_voir_tableau_amortissement(self):
        """Ouvrir le tableau d'amortissement."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tableau d\'amortissement — %s' % self.name,
            'res_model': 'patrimoine.amortissement.ligne',
            'view_mode': 'list,form',
            'domain': [('immobilisation_id', '=', self.id)],
            'context': {'default_immobilisation_id': self.id},
        }

    def action_generer_tableau_amortissement(self):
        """Générer ou recalculer le tableau d'amortissement prévisionnel."""
        self.ensure_one()
        if not self.date_mise_en_service:
            raise UserError("Veuillez renseigner la date de mise en service avant de générer le tableau d'amortissement.")
        # Supprimer les lignes brouillon existantes
        self.ligne_amortissement_ids.filtered(lambda l: l.state == 'brouillon').unlink()
        # Générer les nouvelles lignes
        self._generer_lignes_amortissement()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tableau d\'amortissement',
            'res_model': 'patrimoine.amortissement.ligne',
            'view_mode': 'list',
            'domain': [('immobilisation_id', '=', self.id)],
        }

    def action_voir_mouvements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historique des transferts',
            'res_model': 'patrimoine.mouvement',
            'view_mode': 'list,form',
            'domain': [('immobilisation_id', '=', self.id)],
        }

    # ═══════════════════════════════════════════════════════════
    # CALCUL DES LIGNES D'AMORTISSEMENT
    # ═══════════════════════════════════════════════════════════

    def _generer_lignes_amortissement(self):
        """
        Génère le tableau d'amortissement complet selon la méthode choisie.
        - Linéaire : dotation = base_restante / annees_restantes (recalcul après dépense postérieure)
        - Dégressif : taux dégressif sur VNC restante, bascule linéaire quand plus avantageux
        - Manuel : lignes vides à remplir manuellement
        """
        self.ensure_one()
        if not self.date_mise_en_service or not self.base_amortissable:
            return

        base = self.base_amortissable
        duree = self.duree_amortissement
        date_debut = self.date_mise_en_service

        # Lignes déjà validées — on les respecte et on reprend à partir de là
        lignes_validees = self.ligne_amortissement_ids.filtered(
            lambda l: l.state == 'valide'
        ).sorted('annee')

        deja_amorti = sum(l.montant_amortissement for l in lignes_validees)

        # CORRECTION : calculer l'index de départ à partir de la dernière année validée
        # et non pas du nombre de lignes (qui peut être incorrect si des lignes ont été annulées)
        if lignes_validees:
            derniere_annee_validee = max(lignes_validees.mapped('annee'))
            annee_en_cours = derniere_annee_validee - date_debut.year + 1
        else:
            annee_en_cours = 0

        # Sécurité : ne pas dépasser la durée totale
        annee_en_cours = min(annee_en_cours, duree)

        # Base restante réelle à amortir sur les années restantes
        # On soustrait aussi la valeur résiduelle pour ne pas l'amortir
        base_restante = base - deja_amorti - self.valeur_residuelle
        annees_restantes = duree - annee_en_cours

        if base_restante <= 0.001 or annees_restantes <= 0:
            return

        if self.methode_amortissement == 'lineaire':
            self._generer_lineaire(
                base, duree, date_debut, annee_en_cours,
                deja_amorti, base_restante, annees_restantes
            )
        elif self.methode_amortissement == 'degressif':
            self._generer_degressif(
                base, duree, date_debut, annee_en_cours,
                deja_amorti, base_restante, annees_restantes
            )
        elif self.methode_amortissement == 'manuel':
            self._generer_manuel(duree, date_debut, annee_en_cours)

    def _generer_lineaire(self, base, duree, date_debut, annee_start, cumul_start,
                          base_restante=None, annees_restantes=None):
        """
        Génère les lignes pour la méthode linéaire.
        Après une dépense postérieure, base_restante et annees_restantes sont recalculés
        pour répartir correctement le solde restant sur les années restantes.
        """
        Ligne = self.env['patrimoine.amortissement.ligne']

        if base_restante is None:
            base_restante = base - self.valeur_residuelle
        if annees_restantes is None:
            annees_restantes = duree - annee_start

        # Dotation annuelle = base restante / années restantes
        dotation_annuelle = base_restante / annees_restantes if annees_restantes else 0
        # Taux réel basé sur la dotation recalculée
        taux_affiche = (dotation_annuelle / base * 100) if base else 0

        cumul = cumul_start
        nb_lignes_restantes = annees_restantes
        ligne_num = 0
        for i in range(annee_start, duree):
            annee = date_debut.year + i
            ligne_num += 1

            # Pro-rata première année si début n'est pas le 01/01
            if i == 0 and date_debut.month > 1:
                jours_restants = (datetime.date(annee + 1, 1, 1) - date_debut).days
                jours_annee = (datetime.date(annee + 1, 1, 1) - datetime.date(annee, 1, 1)).days
                montant = dotation_annuelle * (jours_restants / jours_annee)
            else:
                montant = dotation_annuelle

            # Dernière ligne : solder exactement pour éviter les écarts d'arrondi
            if ligne_num == nb_lignes_restantes:
                montant = base - self.valeur_residuelle - cumul
            else:
                montant = min(montant, base - self.valeur_residuelle - cumul)

            if montant <= 0.001:
                break

            cumul += montant
            vnc = self.cout_entree - cumul
            Ligne.create({
                'immobilisation_id': self.id,
                'annee': annee,
                'date_debut': datetime.date(annee, 1, 1) if i > 0 else date_debut,
                'date_fin': datetime.date(annee, 12, 31),
                'taux_applique': taux_affiche,
                'montant_amortissement': round(montant, 3),
                'amortissements_cumules': round(cumul, 3),
                'valeur_nette': round(vnc, 3),
                'state': 'brouillon',
            })

    def _generer_degressif(self, base, duree, date_debut, annee_start, cumul_start,
                           base_restante=None, annees_restantes=None):
        """
        Génère les lignes pour la méthode dégressive.
        Bascule vers linéaire lorsque la dotation dégressive < dotation linéaire restante.
        """
        Ligne = self.env['patrimoine.amortissement.ligne']
        taux_degressif = (100.0 / duree) * self.coefficient_degressif / 100.0

        # base_restante = VNC restante après lignes validées (sans valeur résiduelle)
        vnc_restant = base_restante if base_restante is not None else (base - self.valeur_residuelle - cumul_start)
        cumul = cumul_start
        nb_annees_restantes = annees_restantes if annees_restantes is not None else (duree - annee_start)

        for idx, i in enumerate(range(annee_start, duree)):
            annee = date_debut.year + i
            annees_restantes_local = nb_annees_restantes - idx

            # Calcul dégressif sur VNC restante
            montant_degressif = vnc_restant * taux_degressif
            # Calcul linéaire sur le restant (bascule quand plus avantageux)
            montant_lineaire = vnc_restant / annees_restantes_local if annees_restantes_local else vnc_restant

            montant = max(montant_degressif, montant_lineaire)

            # Dernière ligne : solder exactement
            if idx == nb_annees_restantes - 1:
                montant = vnc_restant
            else:
                montant = min(montant, vnc_restant)

            if montant <= 0.001:
                break

            cumul += montant
            vnc_restant -= montant

            Ligne.create({
                'immobilisation_id': self.id,
                'annee': annee,
                'date_debut': datetime.date(annee, 1, 1) if i > 0 else date_debut,
                'date_fin': datetime.date(annee, 12, 31),
                'taux_applique': taux_degressif * 100,
                'montant_amortissement': round(montant, 3),
                'amortissements_cumules': round(cumul, 3),
                'valeur_nette': round(self.cout_entree - cumul, 3),
                'state': 'brouillon',
            })

    def _generer_manuel(self, duree, date_debut, annee_start):
        """Génère des lignes vides pour saisie manuelle."""
        Ligne = self.env['patrimoine.amortissement.ligne']
        for i in range(annee_start, duree):
            annee = date_debut.year + i
            Ligne.create({
                'immobilisation_id': self.id,
                'annee': annee,
                'date_debut': datetime.date(annee, 1, 1) if i > 0 else date_debut,
                'date_fin': datetime.date(annee, 12, 31),
                'taux_applique': 0.0,
                'montant_amortissement': 0.0,
                'amortissements_cumules': 0.0,
                'valeur_nette': self.cout_entree,
                'state': 'brouillon',
            })

    # ═══════════════════════════════════════════════════════════
    # GÉNÉRATION D'ÉCRITURES COMPTABLES
    # ═══════════════════════════════════════════════════════════

    def _generer_ecriture_entree(self):
        """Génère l'écriture comptable de mise en service de l'immobilisation."""
        self.ensure_one()
        cat = self.categorie_id
        if not cat.compte_immobilisation_id:
            _logger.warning(
                'Pas de compte immobilisation sur la catégorie %s — écriture non générée.', cat.name
            )
            return

        journal = self.journal_id or self.env['account.journal'].search(
            [('type', '=', 'general')], limit=1
        )
        if not journal:
            return

        move_vals = {
            'journal_id': journal.id,
            'date': self.date_mise_en_service or fields.Date.today(),
            'ref': 'Entrée immo — %s [%s]' % (self.name, self.numero_inventaire),
            'line_ids': [
                (0, 0, {
                    'name': '%s — %s' % (self.numero_inventaire, self.name),
                    'account_id': cat.compte_immobilisation_id.id,
                    'debit': self.cout_entree,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Contrepartie entrée immo %s' % self.numero_inventaire,
                    'account_id': (
                        self.facture_achat_ids[:1].invoice_line_ids[:1].account_id.id
                        if self.facture_achat_ids else cat.compte_immobilisation_id.id
                    ),
                    'debit': 0.0,
                    'credit': self.cout_entree,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_entree_id = move.id
        _logger.info('Écriture d\'entrée générée : %s pour immo %s', move.name, self.numero_inventaire)

    # ═══════════════════════════════════════════════════════════
    # MÉTHODES CRON
    # ═══════════════════════════════════════════════════════════

    @api.model
    def _cron_generer_tableaux_amortissement(self):
        """Cron mensuel : génère les lignes prévisionnelles manquantes."""
        immobilisations = self.search([
            ('statut', 'in', ['en_service', 'hors_service']),
            ('date_mise_en_service', '!=', False),
            ('base_amortissable', '>', 0),
            ('entierement_amorti', '=', False),
        ])
        for immo in immobilisations:
            try:
                immo._generer_lignes_amortissement()
            except Exception as e:
                _logger.error(
                    'Erreur génération tableau amort. immo %s : %s',
                    immo.numero_inventaire, str(e)
                )
        _logger.info(
            'Patrimoine — Tableau amort. traité pour %d immobilisation(s).',
            len(immobilisations)
        )

    @api.model
    def _cron_alerte_entierement_amortis(self):
        """Cron mensuel : notifie les responsables des immos entièrement amorties en service."""
        amortis = self.search([
            ('entierement_amorti', '=', True),
            ('statut', '=', 'en_service'),
        ])
        for immo in amortis:
            immo.message_post(
                body=(
                    "<strong>Immobilisation entièrement amortie</strong><br/>"
                    "L'immobilisation <em>%s</em> [%s] est entièrement amortie "
                    "mais reste en service.<br/>"
                    "Coût brut : %.3f DT — VNC : 0.000 DT"
                ) % (immo.name, immo.numero_inventaire, immo.cout_entree),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                partner_ids=[immo.responsable_id.partner_id.id] if immo.responsable_id else [],
            )
        _logger.info(
            'Patrimoine — Alerte envoyée pour %d immo(s) entièrement amorties en service.',
            len(amortis)
        )