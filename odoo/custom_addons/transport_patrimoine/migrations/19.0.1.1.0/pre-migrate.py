# -*- coding: utf-8 -*-
"""
Migration 19.0.1.1.0 — Corrections workflow patrimoine
=======================================================
- B2 : correction double soustraction valeur_residuelle (pas de migration SQL nécessaire,
       les lignes brouillon seront recalculées automatiquement)
- A4 : suppression du statut 'inventorie' — mise à jour des enregistrements résiduels
       vers 'en_service' (aucun enregistrement ne devrait exister, le statut n'était
       jamais assigné, mais on sécurise la migration)
- B1 : ajout colonne compte_contrepartie_id sur patrimoine_categorie (Odoo ORM le crée
       automatiquement, rien à faire ici)
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # A4 — Purge du statut 'inventorie' jamais assigné
    cr.execute("""
        SELECT COUNT(*) FROM patrimoine_immobilisation
        WHERE statut = 'inventorie'
    """)
    nb = cr.fetchone()[0]
    if nb:
        _logger.warning(
            'Migration patrimoine 1.1.0 : %d immobilisation(s) avec statut '
            '"inventorie" trouvée(s) — remise en "en_service".', nb
        )
        cr.execute("""
            UPDATE patrimoine_immobilisation
            SET statut = 'en_service'
            WHERE statut = 'inventorie'
        """)
    else:
        _logger.info(
            'Migration patrimoine 1.1.0 : aucune immobilisation avec statut "inventorie" — OK.'
        )

    # B2 — Supprimer les lignes d'amortissement brouillon pour forcer un recalcul propre
    # (les lignes validées sont conservées)
    cr.execute("""
        SELECT COUNT(*) FROM patrimoine_amortissement_ligne WHERE state = 'brouillon'
    """)
    nb_lignes = cr.fetchone()[0]
    if nb_lignes:
        _logger.info(
            'Migration patrimoine 1.1.0 : suppression de %d ligne(s) d\'amortissement '
            'brouillon pour recalcul avec la base corrigée (B2).', nb_lignes
        )
        cr.execute("""
            DELETE FROM patrimoine_amortissement_ligne WHERE state = 'brouillon'
        """)
    _logger.info('Migration patrimoine 1.1.0 terminée.')
