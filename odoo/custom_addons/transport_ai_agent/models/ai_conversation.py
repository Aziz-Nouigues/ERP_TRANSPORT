# -*- coding: utf-8 -*-
from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

FASTAPI_URL = "http://localhost:8000/chat"
FASTAPI_SYNC_URL = "http://localhost:8000/sync"

PERMISSIONS = {
    'base': {
        'tables': [
            'transport_exploitation_tournee',
            'transport_exploitation_ligne',
            'transport_fuel_voucher',
            'transport_fuel_cuve',
            'transport_fuel_station',
            'transport_boc_arrivee',
            'transport_boc_depart',
            'fleet_vehicle',
            'fleet_etat_bus_historique',
            'transport_assurance_bus',
            'transport_assurance_chauffeur',
            'transport_assurance_sinistre',
        ],
    },
    'transport_patrimoine.group_patrimoine_user': {
        'tables': ['transport_patrimoine_immobilisation'],
    },
    'transport_energy.group_agent_pompiste': {
        'tables': [
            'transport_fuel_cuve',
            'transport_fuel_voucher',
            'transport_fuel_station',
            'transport_fuel_voucher_line',
            'transport_bon_lubrifiant',
            'transport_jaugeage',
            'transport_stock_lubrifiant',
        ],
    },
    'transport_energy.group_responsable_energie': {
        'tables': [
            'transport_fuel_cuve',
            'transport_fuel_voucher',
            'transport_fuel_station',
            'transport_fuel_voucher_line',
            'transport_bon_lubrifiant',
            'transport_jaugeage',
            'transport_stock_lubrifiant',
            'transport_agilis_carte',
            'transport_agilis_recharge',
            'transport_agilis_utilisation',
            'transport_facture_energie',
            'transport_reception_lubrifiant',
        ],
    },
    'transport_energy.group_directeur_energie': {
        'tables': [
            'transport_fuel_cuve',
            'transport_fuel_voucher',
            'transport_fuel_station',
            'transport_fuel_voucher_line',
            'transport_bon_lubrifiant',
            'transport_jaugeage',
            'transport_stock_lubrifiant',
            'transport_agilis_carte',
            'transport_agilis_recharge',
            'transport_agilis_utilisation',
            'transport_facture_energie',
            'transport_reception_lubrifiant',
        ],
    },
    'account.group_account_user': {
        'tables': ['account_move', 'account_move_line'],
    },
    'hr.group_hr_user': {
        'tables': ['hr_employee', 'hr_department'],
    },
    'base.group_system': {
        'tables': ['ALL'],
    },
}

MOTS_CLES_PROTEGES = {
    'hr': [
        'employe', 'employee', 'salarie',
        'staff', 'personnel', 'ressource humaine',
    ],
    'account': [
        'facture', 'invoice',
        'paiement', 'payment', 'avoir',
        'journal', 'bilan',
    ],
    'res_partner': [
        'fournisseur', 'supplier',
    ],
}

MOTS_TRANSPORT_AUTORISES = [
    'cuve', 'carburant', 'bgi', 'bge', 'tournee', 'tournée',
    'bus', 'assurance', 'police', 'patrimoine', 'immobilisation',
    'boc', 'courrier', 'lubrifiant', 'ravitaillement', 'agilis',
    'ligne', 'parc', 'vehicule', 'véhicule', 'stock carburant',
    'km', 'kilometrage', 'kilométrage', 'chauffeur', 'conducteur',
    'litre', 'pompe', 'station', 'cuve',
]


class AiConversation(models.Model):
    _name = 'transport.ai.conversation'
    _description = 'Conversation Agent IA Transport'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        readonly=True,
        default='Nouvelle conversation'
    )
    user_id = fields.Many2one(
        'res.users',
        string='Utilisateur',
        default=lambda self: self.env.user.id,
        readonly=True,
        required=True,
    )
    message_ids = fields.One2many(
        'transport.ai.message',
        'conversation_id',
        string='Messages'
    )
    active = fields.Boolean(default=True)
    create_date = fields.Datetime(
        string='Date creation',
        readonly=True
    )

    @api.model
    def get_current_user_info(self):
        user = self.env.user
        name = user.name or user.login or "Utilisateur"
        parts = name.strip().split(" ")
        initials = (
            (parts[0][0] + parts[1][0]).upper()
            if len(parts) >= 2
            else name[:2].upper()
        )
        return {
            "id": user.id,
            "name": name,
            "initials": initials,
            "login": user.login,
        }

    def _get_user_allowed_tables(self):
        user = self.env.user
        allowed = set()
        allowed.update(PERMISSIONS['base']['tables'])

        for group_xml_id, perms in PERMISSIONS.items():
            if group_xml_id == 'base':
                continue
            try:
                if user.has_group(group_xml_id):
                    tables = perms.get('tables', [])
                    if 'ALL' in tables:
                        return None
                    allowed.update(tables)
            except Exception:
                continue

        _logger.info(f"Tables autorisees pour {user.name} : {sorted(list(allowed))}")
        return allowed

    def ask_question(self, question=False, **kwargs):
        self.ensure_one()

        if not question:
            question = kwargs.get('question', '')
        if not question:
            return "Veuillez poser une question."

        # Recupere l'ID via SQL pur pour eviter ARRAY[]
        self.env.cr.execute(
            "SELECT id, name, user_id FROM transport_ai_conversation "
            "WHERE id = ANY(%s) LIMIT 1",
            (list(self._ids),)
        )
        row = self.env.cr.fetchone()
        if not row:
            return "Erreur : conversation non trouvee."

        conv_id = row[0]
        conv_name = row[1]
        conv_user_id = row[2]

        _logger.info(f"ask_question - id={conv_id} user={self.env.user.name} question={question}")

        if conv_user_id and conv_user_id != self.env.user.id:
            return "Vous ne pouvez pas acceder a la conversation d'un autre utilisateur."

        user = self.env.user
        allowed_tables = self._get_user_allowed_tables()
        session_id = f"odoo_user_{user.id}_conv_{conv_id}"

        # Sauvegarde message utilisateur via SQL
        self.env.cr.execute(
            """
            INSERT INTO transport_ai_message
                (conversation_id, content, message_type,
                 create_date, write_date, create_uid, write_uid)
            VALUES (%s, %s, %s,
                    NOW() AT TIME ZONE 'UTC',
                    NOW() AT TIME ZONE 'UTC',
                    %s, %s)
            """,
            (conv_id, question, 'user', user.id, user.id)
        )

        # Appel FastAPI
        try:
            payload = {
                "question": question,
                "session_id": session_id,
                "user_id": user.id,
                "user_name": user.name,
                "allowed_tables": (
                    list(allowed_tables) if allowed_tables else ["ALL"]
                ),
                "is_admin": allowed_tables is None,
            }
            response = requests.post(
                FASTAPI_URL,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            reponse_text = data.get("reponse", "Aucune reponse recue.")
            _logger.info(f"Reponse FastAPI : {reponse_text[:100]}")

        except requests.exceptions.ConnectionError:
            reponse_text = "Erreur : L'agent IA n'est pas accessible. Verifiez que FastAPI tourne sur le port 8000."
        except requests.exceptions.Timeout:
            reponse_text = "Erreur : Timeout - l'agent met trop de temps a repondre."
        except Exception as e:
            reponse_text = f"Erreur : {str(e)}"
            _logger.error(f"Erreur agent IA : {str(e)}", exc_info=True)

        # Sauvegarde reponse agent via SQL
        self.env.cr.execute(
            """
            INSERT INTO transport_ai_message
                (conversation_id, content, message_type,
                 create_date, write_date, create_uid, write_uid)
            VALUES (%s, %s, %s,
                    NOW() AT TIME ZONE 'UTC',
                    NOW() AT TIME ZONE 'UTC',
                    %s, %s)
            """,
            (conv_id, reponse_text, 'agent', user.id, user.id)
        )

        # Mise a jour nom conversation
        if conv_name == 'Nouvelle conversation':
            nouveau_nom = question[:50] + ('...' if len(question) > 50 else '')
            self.env.cr.execute(
                "UPDATE transport_ai_conversation SET name = %s WHERE id = %s",
                (nouveau_nom, conv_id)
            )

        return reponse_text


class AiMessage(models.Model):
    _name = 'transport.ai.message'
    _description = 'Message conversation IA'
    _order = 'create_date asc'

    conversation_id = fields.Many2one(
        'transport.ai.conversation',
        string='Conversation',
        ondelete='cascade'
    )
    content = fields.Text(string='Contenu', required=True)
    message_type = fields.Selection([
        ('user', 'Utilisateur'),
        ('agent', 'Agent IA'),
    ], string='Type', required=True)
    create_date = fields.Datetime(string='Date', readonly=True)


class AiChromaSyncCron(models.Model):
    _name = 'transport.ai.chroma.cron'
    _description = 'Cron synchronisation ChromaDB'

    @api.model
    def _sync_all_changes(self):
        import requests as req
        from datetime import datetime, timedelta

        depuis = datetime.now() - timedelta(minutes=6)
        depuis_str = depuis.strftime('%Y-%m-%d %H:%M:%S')
        synced = 0

        # Tournees
        try:
            tournees = self.env[
                'transport.exploitation.tournee'
            ].search([('write_date', '>=', depuis_str)])
            for t in tournees:
                doc = (
                    f"Tournee {t.name} du {t.date} "
                    f"etat: {t.state} "
                    f"ligne: {t.ligne_id.name if t.ligne_id else 'N/A'} "
                    f"bus: {t.vehicle_id.name if t.vehicle_id else 'N/A'} "
                    f"km prevu: {t.km_prevu} "
                    f"km realise: {t.km_realise}"
                )
                req.post(FASTAPI_SYNC_URL, json={
                    "model": "transport.exploitation.tournee",
                    "record_id": t.id,
                    "operation": "upsert",
                    "document": doc
                }, timeout=10)
                synced += 1
        except Exception as e:
            _logger.warning(f"Sync tournees: {e}")

        # Assurances
        try:
            assurances = self.env[
                'transport.assurance.bus'
            ].search([('write_date', '>=', depuis_str)])
            for a in assurances:
                doc = (
                    f"Police {a.numero_police} "
                    f"bus: {a.vehicle_id.name if a.vehicle_id else 'N/A'} "
                    f"fin: {a.date_fin} "
                    f"obligatoire: {'oui' if a.is_obligatoire else 'non'} "
                    f"etat: {a.state}"
                )
                req.post(FASTAPI_SYNC_URL, json={
                    "model": "transport.assurance.bus",
                    "record_id": a.id,
                    "operation": "upsert",
                    "document": doc
                }, timeout=10)
                synced += 1
        except Exception as e:
            _logger.warning(f"Sync assurances: {e}")

        # Carburant
        try:
            vouchers = self.env[
                'transport.fuel.voucher'
            ].search([('write_date', '>=', depuis_str)])
            for v in vouchers:
                doc = (
                    f"Bon {v.name} type: {v.voucher_type} "
                    f"date: {v.date} "
                    f"quantite: {v.total_quantity} L "
                    f"etat: {v.state}"
                )
                req.post(FASTAPI_SYNC_URL, json={
                    "model": "transport.fuel.voucher",
                    "record_id": v.id,
                    "operation": "upsert",
                    "document": doc
                }, timeout=10)
                synced += 1
        except Exception as e:
            _logger.warning(f"Sync carburant: {e}")

        # Patrimoine
        try:
            immobilisations = self.env[
                'patrimoine.immobilisation'
            ].search([('write_date', '>=', depuis_str)])
            for i in immobilisations:
                doc = (
                    f"Immobilisation {i.name} "
                    f"statut: {i.statut} "
                    f"fin amortissement: {i.fin_amortissement}"
                )
                req.post(FASTAPI_SYNC_URL, json={
                    "model": "patrimoine.immobilisation",
                    "record_id": i.id,
                    "operation": "upsert",
                    "document": doc
                }, timeout=10)
                synced += 1
        except Exception as e:
            _logger.warning(f"Sync patrimoine: {e}")

        # BOC
        try:
            arrivees = self.env[
                'boc.courrier.arrivee'
            ].search([('write_date', '>=', depuis_str)])
            for b in arrivees:
                doc = (
                    f"Courrier BOC arrivee {b.name} "
                    f"objet: {b.objet} etat: {b.state}"
                )
                req.post(FASTAPI_SYNC_URL, json={
                    "model": "boc.courrier.arrivee",
                    "record_id": b.id,
                    "operation": "upsert",
                    "document": doc
                }, timeout=10)
                synced += 1
        except Exception as e:
            _logger.warning(f"Sync BOC: {e}")

        _logger.info(f"ChromaDB cron - {synced} documents synchronises")
        return True