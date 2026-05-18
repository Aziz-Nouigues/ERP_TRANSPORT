# -*- coding: utf-8 -*-
from odoo import models, fields, api
import requests
import logging
import re

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
    'hr': ['employe', 'employee', 'salarie', 'staff', 'personnel'],
    'account': ['facture', 'invoice', 'paiement', 'payment', 'avoir', 'journal', 'bilan'],
    'res_partner': ['fournisseur', 'supplier'],
}

MOTS_TRANSPORT_AUTORISES = [
    'cuve', 'carburant', 'bgi', 'bge', 'tournee', 'tournée',
    'bus', 'assurance', 'police', 'patrimoine', 'immobilisation',
    'boc', 'courrier', 'lubrifiant', 'ravitaillement', 'agilis',
    'ligne', 'parc', 'vehicule', 'véhicule', 'stock carburant',
    'km', 'kilometrage', 'kilométrage', 'chauffeur', 'conducteur',
    'litre', 'pompe', 'station',
]


class AiConversation(models.Model):
    _name = 'transport.ai.conversation'
    _description = 'Conversation Agent IA Transport'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(string='Reference', readonly=True, default='Nouvelle conversation')
    user_id = fields.Many2one('res.users', string='Utilisateur',
                              default=lambda self: self.env.user.id,
                              readonly=True, required=True)
    message_ids = fields.One2many('transport.ai.message', 'conversation_id', string='Messages')
    active = fields.Boolean(default=True)
    create_date = fields.Datetime(string='Date creation', readonly=True)

    @api.model
    def get_current_user_info(self):
        user = self.env.user
        name = user.name or user.login or "Utilisateur"
        parts = name.strip().split(" ")
        initials = ((parts[0][0] + parts[1][0]).upper()
                    if len(parts) >= 2 else name[:2].upper())
        return {"id": user.id, "name": name, "initials": initials, "login": user.login}

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

    def _parse_pdf_url(self, reponse_text):
        """
        Extrait le pdf_url depuis la réponse de l'agent.
        Format : "...texte...\nPDF_URL:http://localhost:8000/rapport/xxx/pdf"
        Retourne (texte_propre, pdf_url)
        """
        m = re.search(r'PDF_URL:(http\S+)', reponse_text)
        if m:
            pdf_url = m.group(1).strip()
            texte_propre = re.sub(r'\nPDF_URL:http\S+', '', reponse_text).strip()
            return texte_propre, pdf_url
        return reponse_text, None

    def ask_question(self, question=False, **kwargs):
        self.ensure_one()

        if not question:
            question = kwargs.get('question', '')
        if not question:
            return "Veuillez poser une question."

        self.env.cr.execute(
            "SELECT id, name, user_id FROM transport_ai_conversation "
            "WHERE id = ANY(%s) LIMIT 1",
            (list(self._ids),)
        )
        row = self.env.cr.fetchone()
        if not row:
            return "Erreur : conversation non trouvee."

        conv_id, conv_name, conv_user_id = row
        _logger.info(f"ask_question - id={conv_id} user={self.env.user.name} question={question}")

        if conv_user_id and conv_user_id != self.env.user.id:
            return "Vous ne pouvez pas acceder a la conversation d'un autre utilisateur."

        user = self.env.user
        allowed_tables = self._get_user_allowed_tables()
        session_id = f"odoo_user_{user.id}_conv_{conv_id}"

        # Sauvegarde message utilisateur
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
        pdf_url = None
        try:
            payload = {
                "question": question,
                "session_id": session_id,
                "user_id": user.id,
                "user_name": user.name,
                "allowed_tables": list(allowed_tables) if allowed_tables else ["ALL"],
                "is_admin": allowed_tables is None,
            }
            response = requests.post(FASTAPI_URL, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()

            reponse_brute = data.get("reponse", "Aucune reponse recue.")

            # ── Extraire pdf_url si présent ──────────────────────────────────
            # 1. Depuis le champ pdf_url de la réponse FastAPI
            if data.get("pdf_url"):
                pdf_url = data["pdf_url"]
                reponse_text = reponse_brute
            else:
                # 2. Depuis le texte (format PDF_URL:http://...)
                reponse_text, pdf_url = self._parse_pdf_url(reponse_brute)

            _logger.info(f"Reponse: {reponse_text[:100]} | pdf_url: {pdf_url}")

        except requests.exceptions.ConnectionError:
            reponse_text = "Erreur : L'agent IA n'est pas accessible."
            pdf_url = None
        except requests.exceptions.Timeout:
            reponse_text = "Erreur : Timeout - l'agent met trop de temps a repondre."
            pdf_url = None
        except Exception as e:
            reponse_text = f"Erreur : {str(e)}"
            pdf_url = None
            _logger.error(f"Erreur agent IA : {str(e)}", exc_info=True)

        # Sauvegarde réponse agent (texte propre sans PDF_URL:)
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

        # Mise à jour nom conversation
        if conv_name == 'Nouvelle conversation':
            nouveau_nom = question[:50] + ('...' if len(question) > 50 else '')
            self.env.cr.execute(
                "UPDATE transport_ai_conversation SET name = %s WHERE id = %s",
                (nouveau_nom, conv_id)
            )

        # ── Retourner un dict si pdf_url présent, sinon le texte seul ────────
        if pdf_url:
            return {"content": reponse_text, "pdf_url": pdf_url}
        return reponse_text


class AiMessage(models.Model):
    _name = 'transport.ai.message'
    _description = 'Message conversation IA'
    _order = 'create_date asc'

    conversation_id = fields.Many2one('transport.ai.conversation',
                                      string='Conversation', ondelete='cascade')
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

        modeles = [
            ('transport.exploitation.tournee', lambda t:
             f"Tournee {t.name} du {t.date} etat: {t.state} "
             f"ligne: {t.ligne_id.name if t.ligne_id else 'N/A'} "
             f"bus: {t.vehicle_id.name if t.vehicle_id else 'N/A'} "
             f"km prevu: {t.km_prevu} km realise: {t.km_realise}"),
            ('transport.assurance.bus', lambda a:
             f"Police {a.numero_police} bus: {a.vehicle_id.name if a.vehicle_id else 'N/A'} "
             f"fin: {a.date_fin} etat: {a.state}"),
            ('transport.fuel.voucher', lambda v:
             f"Bon {v.name} type: {v.voucher_type} date: {v.date} "
             f"quantite: {v.total_quantity} L etat: {v.state}"),
            ('patrimoine.immobilisation', lambda i:
             f"Immobilisation {i.name} statut: {i.statut}"),
            ('boc.courrier.arrivee', lambda b:
             f"Courrier BOC arrivee {b.name} etat: {b.state}"),
        ]

        for modele, doc_fn in modeles:
            try:
                records = self.env[modele].search([('write_date', '>=', depuis_str)])
                for r in records:
                    req.post(FASTAPI_SYNC_URL, json={
                        "model": modele,
                        "record_id": r.id,
                        "operation": "upsert",
                        "document": doc_fn(r)
                    }, timeout=10)
                    synced += 1
            except Exception as e:
                _logger.warning(f"Sync {modele}: {e}")

        _logger.info(f"ChromaDB cron - {synced} documents synchronises")
        return True