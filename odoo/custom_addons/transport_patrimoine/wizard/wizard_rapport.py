# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date


class WizardRapportPatrimoine(models.TransientModel):
    """
    Wizard de génération des rapports patrimoine.
    Couvre les 15 états demandés dans le cahier des charges.
    """
    _name = 'patrimoine.wizard.rapport'
    _description = 'Rapport Patrimoine / Immobilisations'

    # ── TYPE RAPPORT ─────────────────────────────────────────────
    type_rapport = fields.Selection([
        # Tableaux d'amortissement
        ('tableau_amort',        'Tableau d\'amortissement (toutes immo)'),
        ('tableau_par_type',     'Tableau d\'amortissement par type'),
        ('tableau_par_categorie','Tableau d\'amortissement par catégorie'),
        ('tableau_par_projet',   'Tableau d\'amortissement par projet'),
        ('tableau_resume_cat',   'Résumé par catégorie'),
        ('tableau_resume_groupe','Résumé par groupe'),
        # Listes de mouvements
        ('liste_acquisitions',   'État des acquisitions de la période'),
        ('liste_cessions',       'État des cessions de la période'),
        ('liste_rebuts',         'État des mises en rebut de la période'),
        ('liste_transferts',     'Liste des transferts d\'immobilisations'),
        ('liste_distribution',   'Liste de distribution des actifs'),
        ('liste_ecarts',         'Liste des écarts d\'inventaire'),
        # Rapports de variation et synthèse
        ('variation_immo',       'Tableau de variation des immobilisations'),
        ('entierement_amortis',  'Immobilisations entièrement amorties encore en usage'),
        ('hors_usage',           'Immobilisations hors service / inutilisées'),
    ], string='Type de rapport', required=True, default='tableau_amort')

    # ── FILTRES COMMUNS ───────────────────────────────────────────
    annee = fields.Integer(
        string='Exercice',
        default=lambda self: date.today().year,
    )
    date_debut = fields.Date(
        string='Date début',
        default=lambda self: fields.Date.today().replace(day=1, month=1),
    )
    date_fin = fields.Date(
        string='Date fin',
        default=fields.Date.today,
    )
    categorie_id = fields.Many2one(
        'patrimoine.categorie',
        string='Catégorie (optionnel)',
    )
    sous_categorie_id = fields.Many2one(
        'patrimoine.sous.categorie',
        string='Sous-catégorie (optionnel)',
        domain="[('categorie_id','=',categorie_id)]",
    )
    emplacement_id = fields.Many2one(
        'patrimoine.emplacement',
        string='Emplacement (optionnel)',
    )
    methode_amort_filtre = fields.Selection([
        ('tous',      'Toutes'),
        ('lineaire',  'Linéaire'),
        ('degressif', 'Dégressif'),
        ('manuel',    'Manuel'),
    ], string='Méthode d\'amort.', default='tous')
    taux_filtre = fields.Float(
        string='Taux d\'amort. (%)',
        digits=(6, 4),
        default=0.0,
        help='0 = tous les taux',
    )
    projet_filtre = fields.Char(string='Projet / Programme')
    statut_filtre = fields.Selection([
        ('tous',        'Tous statuts'),
        ('en_service',  'En service'),
        ('hors_service','Hors service'),
        ('cede',        'Cédé'),
        ('rebut',       'Mis en rebut'),
    ], string='Statut', default='tous')

    # ── OPTIONS ──────────────────────────────────────────────────
    inclure_amortis = fields.Boolean(
        string='Inclure entièrement amortis',
        default=True,
    )
    grouper_par = fields.Selection([
        ('categorie',       'Catégorie'),
        ('sous_categorie',  'Sous-catégorie'),
        ('emplacement',     'Emplacement'),
        ('annee_acq',       'Année d\'acquisition'),
        ('methode',         'Méthode d\'amortissement'),
    ], string='Grouper par', default='categorie')

    # ═══════════════════════════════════════════════════════════
    # CONTRAINTES
    # ═══════════════════════════════════════════════════════════

    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        """Bug 10 FIX — vérifier que date_debut <= date_fin.
        Sans cette contrainte, une inversion de dates retourne silencieusement
        0 résultats sur tous les rapports de période sans avertir l'utilisateur.
        """
        for rec in self:
            if rec.date_debut and rec.date_fin and rec.date_debut > rec.date_fin:
                raise ValidationError(
                    "La date de début (%s) ne peut pas être postérieure "
                    "à la date de fin (%s)."
                    % (rec.date_debut.strftime('%d/%m/%Y'),
                       rec.date_fin.strftime('%d/%m/%Y'))
                )

    # ═══════════════════════════════════════════════════════════
    # ACTION PRINCIPALE
    # ═══════════════════════════════════════════════════════════

    def action_generer(self):
        self.ensure_one()
        refs = {
            'tableau_amort':         'transport_patrimoine.action_rapport_tableau_amortissement',
            'tableau_par_type':      'transport_patrimoine.action_rapport_tableau_par_type',
            'tableau_par_categorie': 'transport_patrimoine.action_rapport_tableau_par_categorie',
            'tableau_par_projet':    'transport_patrimoine.action_rapport_amort_par_projet',
            'tableau_resume_cat':    'transport_patrimoine.action_rapport_amort_par_sous_categorie',
            'tableau_resume_groupe': 'transport_patrimoine.action_rapport_recap_ventile',
            'liste_acquisitions':    'transport_patrimoine.action_rapport_acquisitions',
            'liste_cessions':        'transport_patrimoine.action_rapport_cessions',
            'liste_rebuts':          'transport_patrimoine.action_rapport_rebuts_periode',
            'liste_transferts':      'transport_patrimoine.action_rapport_transferts',
            'liste_distribution':    'transport_patrimoine.action_rapport_distribution',
            'liste_ecarts':          'transport_patrimoine.action_rapport_ecarts',
            'variation_immo':        'transport_patrimoine.action_rapport_variation',
            'entierement_amortis':   'transport_patrimoine.action_rapport_entierement_amortis',
            'hors_usage':            'transport_patrimoine.action_rapport_hors_usage',
        }
        return self.env.ref(refs[self.type_rapport]).report_action(self)

    # ═══════════════════════════════════════════════════════════
    # MÉTHODES DE DONNÉES (appelées depuis les templates QWeb)
    # ═══════════════════════════════════════════════════════════

    def _get_immobilisations(self, statuts=None):
        """Retourne les immobilisations selon les filtres du wizard."""
        domain = []
        if statuts:
            domain.append(('statut', 'in', statuts))
        elif self.statut_filtre != 'tous':
            domain.append(('statut', '=', self.statut_filtre))
        if self.categorie_id:
            domain.append(('categorie_id', '=', self.categorie_id.id))
        if self.sous_categorie_id:
            domain.append(('sous_categorie_id', '=', self.sous_categorie_id.id))
        if self.emplacement_id:
            domain.append(('emplacement_id', '=', self.emplacement_id.id))
        if self.methode_amort_filtre != 'tous':
            domain.append(('methode_amortissement', '=', self.methode_amort_filtre))
        if self.taux_filtre > 0:
            domain.append(('taux_amortissement', '=', self.taux_filtre))
        if self.projet_filtre:
            domain.append(('projet', 'ilike', self.projet_filtre))
        if not self.inclure_amortis:
            domain.append(('entierement_amorti', '=', False))
        return self.env['patrimoine.immobilisation'].search(domain, order='numero_inventaire')

    def _get_acquisitions(self):
        """Immobilisations acquises dans la période."""
        domain = [
            ('date_acquisition', '>=', self.date_debut),
            ('date_acquisition', '<=', self.date_fin),
        ]
        if self.categorie_id:
            domain.append(('categorie_id', '=', self.categorie_id.id))
        return self.env['patrimoine.immobilisation'].search(domain, order='date_acquisition')

    def _get_cessions(self):
        """Cessions de la période."""
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('type_sortie', '=', 'cession'),
            ('state', '=', 'comptabilise'),
        ]
        if self.categorie_id:
            domain.append(('immobilisation_id.categorie_id', '=', self.categorie_id.id))
        return self.env['patrimoine.cession'].search(domain, order='date')

    def _get_rebuts(self):
        """Rebuts de la période."""
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('type_sortie', '=', 'rebut'),
            ('state', '=', 'comptabilise'),
        ]
        if self.categorie_id:
            domain.append(('immobilisation_id.categorie_id', '=', self.categorie_id.id))
        return self.env['patrimoine.cession'].search(domain, order='date')

    def _get_recap_ventile(self):
        """
        État récapitulatif ventilé selon le critère grouper_par :
        taux d'amortissement, emplacement, année d'acquisition, méthode, catégorie.
        Retourne liste de dicts {groupe, nb, cout_brut, amort_cumule, vnc, taux_moy}.
        """
        immos = self._get_immobilisations(statuts=['en_service', 'hors_service'])
        grouper = self.grouper_par or 'categorie'
        buckets = {}

        for immo in immos:
            if grouper == 'categorie':
                key = immo.categorie_id.name if immo.categorie_id else 'Sans catégorie'
            elif grouper == 'sous_categorie':
                key = immo.sous_categorie_id.name if immo.sous_categorie_id else 'Sans sous-catégorie'
            elif grouper == 'emplacement':
                key = immo.emplacement_id.display_name if immo.emplacement_id else 'Sans emplacement'
            elif grouper == 'annee_acq':
                key = str(immo.date_acquisition.year) if immo.date_acquisition else 'Inconnue'
            elif grouper == 'methode':
                key = dict(immo._fields['methode_amortissement'].selection).get(
                    immo.methode_amortissement, immo.methode_amortissement
                )
            else:
                key = 'Autres'

            if key not in buckets:
                buckets[key] = {'groupe': key, 'nb': 0, 'cout_brut': 0.0,
                                'amort_cumule': 0.0, 'vnc': 0.0, 'taux_total': 0.0}
            b = buckets[key]
            b['nb'] += 1
            b['cout_brut'] += immo.cout_entree
            b['amort_cumule'] += immo.amortissements_cumules
            b['vnc'] += immo.valeur_nette_comptable
            b['taux_total'] += immo.taux_amortissement

        result = []
        for key in sorted(buckets):
            b = buckets[key]
            b['taux_moy'] = round(b['taux_total'] / b['nb'], 4) if b['nb'] else 0.0
            result.append(b)
        return result

    def _get_lignes_par_sous_categorie(self):
        """
        Tableau d'amortissement groupé par catégorie > sous-catégorie > immobilisation.
        Retourne structure hiérarchique pour le QWeb.
        """
        lignes = self._get_lignes_amortissement_annee()
        structure = {}
        for l in lignes:
            immo = l.immobilisation_id
            cat = immo.categorie_id.name if immo.categorie_id else 'Sans catégorie'
            scat = immo.sous_categorie_id.name if immo.sous_categorie_id else 'Sans sous-catégorie'
            structure.setdefault(cat, {})
            structure[cat].setdefault(scat, [])
            structure[cat][scat].append(l)

        result = []
        for cat_name in sorted(structure):
            cat_block = {'cat': cat_name, 'sous_cats': []}
            for scat_name in sorted(structure[cat_name]):
                ls = structure[cat_name][scat_name]
                cat_block['sous_cats'].append({
                    'scat': scat_name,
                    'lignes': ls,
                    'total_dot': sum(l.montant_amortissement for l in ls),
                    'total_cumul': sum(l.amortissements_cumules for l in ls),
                })
            result.append(cat_block)
        return result

    def _get_lignes_par_projet(self):
        """
        Tableau d'amortissement groupé par projet/programme.
        Retourne liste de dicts {projet, lignes, total_dot, total_cumul}.
        """
        immos_base = self._get_immobilisations(statuts=['en_service', 'hors_service'])
        projets = {}
        for immo in immos_base:
            proj = immo.projet or 'Sans projet'
            projets.setdefault(proj, [])
            for l in immo.ligne_amortissement_ids.filtered(lambda x: x.annee == self.annee):
                projets[proj].append(l)

        result = []
        for proj in sorted(projets):
            ls = projets[proj]
            result.append({
                'projet': proj,
                'lignes': ls,
                'total_dot': sum(l.montant_amortissement for l in ls),
                'total_cumul': sum(l.amortissements_cumules for l in ls),
                'nb_immo': len(set(l.immobilisation_id.id for l in ls)),
            })
        return result

    def _get_transferts(self):
        """Transferts de la période."""
        domain = [
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin),
            ('state', '=', 'confirme'),
        ]
        return self.env['patrimoine.mouvement'].search(domain, order='date')

    def _get_distribution(self):
        """Affectations actives."""
        domain = [('state', '=', 'active')]
        if self.emplacement_id:
            domain.append(('emplacement_id', '=', self.emplacement_id.id))
        return self.env['patrimoine.affectation'].search(domain, order='immobilisation_id')

    def _get_lignes_amortissement_annee(self):
        """Lignes d'amortissement de l'exercice."""
        domain = [
            ('annee', '=', self.annee),
        ]
        if self.categorie_id:
            domain.append(('categorie_id', '=', self.categorie_id.id))
        return self.env['patrimoine.amortissement.ligne'].search(
            domain, order='immobilisation_id, annee'
        )

    def _get_immobilisations_entierement_amorties(self):
        """Immobilisations entièrement amorties encore en service."""
        return self.env['patrimoine.immobilisation'].search([
            ('entierement_amorti', '=', True),
            ('statut', '=', 'en_service'),
        ], order='numero_inventaire')

    def _get_immobilisations_hors_usage(self):
        """Immobilisations hors service."""
        return self.env['patrimoine.immobilisation'].search([
            ('statut', '=', 'hors_service'),
        ], order='numero_inventaire')

    def _get_stats_variation(self):
        """Données pour le tableau de variation des immobilisations."""
        categories = self.env['patrimoine.categorie'].search([('actif', '=', True)])
        result = []
        for cat in categories:
            immos = self.env['patrimoine.immobilisation'].search([
                ('categorie_id', '=', cat.id),
            ])
            # Valeur début de période
            # Bug 8 FIX — guard de nullité sur date_acquisition (peut être False)
            acq_periode = immos.filtered(
                lambda i: i.date_acquisition and i.date_acquisition >= self.date_debut
                          and i.date_acquisition <= self.date_fin
            )
            sorties_periode = self.env['patrimoine.cession'].search([
                ('immobilisation_id.categorie_id', '=', cat.id),
                ('date', '>=', self.date_debut),
                ('date', '<=', self.date_fin),
                ('state', '=', 'comptabilise'),
            ])
            result.append({
                'categorie': cat.name,
                'code': cat.code,
                # Bug 8 FIX — guard de nullité sur date_acquisition
                'valeur_debut': sum(
                    i.cout_entree for i in immos
                    if i.date_acquisition and i.date_acquisition < self.date_debut
                ),
                'acquisitions': sum(i.cout_entree for i in acq_periode),
                'cessions': sum(s.cout_entree for s in sorties_periode),
                'valeur_fin': sum(i.cout_entree for i in immos if i.statut not in ('cede', 'rebut')),
                'amort_cumules': sum(i.amortissements_cumules for i in immos if i.statut not in ('cede', 'rebut')),
                'vnc': sum(i.valeur_nette_comptable for i in immos if i.statut not in ('cede', 'rebut')),
            })
        return result
