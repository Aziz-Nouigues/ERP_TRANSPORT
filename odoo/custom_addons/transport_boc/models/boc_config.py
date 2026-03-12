# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BocTypeCourrier(models.Model):
    """Types de courrier : Facture, Lettre, Appel d'offre, ..."""
    _name = 'boc.type.courrier'
    _description = "Type de Courrier"
    _order = 'name'

    name = fields.Char(
        string='Type de courrier',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
    )
    actif = fields.Boolean(
        string='Actif',
        default=True,
    )
    notes = fields.Text(
        string='Notes',
    )


class BocOrganisme(models.Model):
    """Organismes internes et externes (expéditeurs / destinataires)"""
    _name = 'boc.organisme'
    _description = "Organisme"
    _order = 'name'

    name = fields.Char(
        string='Nom organisme',
        required=True,
        translate=True,
    )
    type_organisme = fields.Selection([
        ('interne', 'Interne'),
        ('externe', 'Externe'),
    ], string='Type', required=True, default='externe')

    code = fields.Char(string='Code')
    adresse = fields.Text(string='Adresse')
    telephone = fields.Char(string='Téléphone')
    email = fields.Char(string='Email')
    actif = fields.Boolean(string='Actif', default=True)

    # Pour les organismes internes : lien avec direction/service
    direction = fields.Char(string='Direction')
    service = fields.Char(string='Service')
    section = fields.Char(string='Section')


class BocSujet(models.Model):
    """Sujets prédéfinis pour les courriers"""
    _name = 'boc.sujet'
    _description = "Sujet Prédéfini"
    _order = 'name'

    name = fields.Char(string='Sujet', required=True, translate=True)
    actif = fields.Boolean(string='Actif', default=True)


class BocInstruction(models.Model):
    """Instructions prédéfinies pour la diffusion"""
    _name = 'boc.instruction'
    _description = "Instruction Prédéfinie"
    _order = 'name'

    name = fields.Char(string='Instruction', required=True, translate=True)
    # ex: "Pour traitement", "Pour information", "Pour signature", "Pour avis"
    actif = fields.Boolean(string='Actif', default=True)


class BocAnnotation(models.Model):
    """Annotations prédéfinies"""
    _name = 'boc.annotation'
    _description = "Annotation Prédéfinie"
    _order = 'name'

    name = fields.Char(string='Annotation', required=True, translate=True)
    actif = fields.Boolean(string='Actif', default=True)