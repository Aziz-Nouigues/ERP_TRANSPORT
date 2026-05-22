# -*- coding: utf-8 -*-
from odoo import models, fields, api
import requests
import logging
import re

_logger = logging.getLogger(__name__)

FASTAPI_URL = "http://localhost:8000/chat"
FASTAPI_SYNC_URL = "http://localhost:8000/sync"

PERMISSIONS = {
    "base": {
        "tables": ["fleet_vehicle","fleet_vehicle_state","transport_exploitation_tournee","transport_exploitation_ligne","transport_exploitation_agence"],
        "rapports": [],
        "stats": [],
    },
    "transport_exploitation.group_exploitation_user": {
        "tables": ["transport_exploitation_tournee","transport_exploitation_ligne","transport_exploitation_agence","transport_exploitation_feuille_route","transport_exploitation_motif","fleet_vehicle","hr_employee"],
        "rapports": ["rapport_journalier","rapport_hebdomadaire","rapport_mensuel"],
        "stats": ["tournees","bus","chauffeurs"],
    },
    "transport_exploitation.group_exploitation_manager": {
        "tables": ["transport_exploitation_tournee","transport_exploitation_ligne","transport_exploitation_agence","transport_exploitation_feuille_route","transport_exploitation_motif","fleet_vehicle","fleet_vehicle_state","hr_employee","transport_assurance_bus"],
        "rapports": ["rapport_journalier","rapport_hebdomadaire","rapport_mensuel","bilan_parc"],
        "stats": ["tournees","bus","chauffeurs","parc"],
    },
    "fleet.fleet_group_user": {
        "tables": ["fleet_vehicle","fleet_vehicle_state","fleet_vehicle_odometer","transport_assurance_bus"],
        "rapports": ["bilan_parc"],
        "stats": ["bus","parc"],
    },
    "fleet.fleet_group_manager": {
        "tables": ["fleet_vehicle","fleet_vehicle_state","fleet_vehicle_odometer","transport_assurance_bus","transport_assurance_sinistre","transport_assurance_compagnie","transport_assurance_type"],
        "rapports": ["bilan_parc","bilan_assurance"],
        "stats": ["bus","parc","assurances"],
    },
    "transport_assurance.group_assurance_user": {
        "tables": ["transport_assurance_bus","transport_assurance_chauffeur","transport_assurance_sinistre","transport_assurance_compagnie","transport_assurance_type","fleet_vehicle"],
        "rapports": ["bilan_assurance"],
        "stats": ["assurances"],
    },
    "transport_energy.group_agent_pompiste": {
        "tables": ["transport_fuel_cuve","transport_fuel_voucher","transport_fuel_station","transport_fuel_voucher_line","transport_bon_lubrifiant","transport_jaugeage","transport_stock_lubrifiant"],
        "rapports": [],
        "stats": ["carburant"],
    },
    "transport_energy.group_responsable_energie": {
        "tables": ["transport_fuel_cuve","transport_fuel_voucher","transport_fuel_station","transport_fuel_voucher_line","transport_bon_lubrifiant","transport_jaugeage","transport_stock_lubrifiant","transport_agilis_carte","transport_agilis_recharge","transport_agilis_utilisation","transport_facture_energie","transport_reception_lubrifiant"],
        "rapports": ["bilan_carburant"],
        "stats": ["carburant"],
    },
    "transport_energy.group_directeur_energie": {
        "tables": ["transport_fuel_cuve","transport_fuel_voucher","transport_fuel_station","transport_fuel_voucher_line","transport_bon_lubrifiant","transport_jaugeage","transport_stock_lubrifiant","transport_agilis_carte","transport_agilis_recharge","transport_agilis_utilisation","transport_facture_energie","transport_reception_lubrifiant","fleet_vehicle"],
        "rapports": ["bilan_carburant"],
        "stats": ["carburant","bus"],
    },
    "transport_boc.group_boc_user": {
        "tables": ["boc_courrier_arrivee","boc_courrier_depart","boc_organisme","boc_type_courrier"],
        "rapports": ["bilan_boc"],
        "stats": ["boc"],
    },
    "transport_patrimoine.group_patrimoine_user": {
        "tables": ["patrimoine_immobilisation","patrimoine_categorie","patrimoine_affectation","patrimoine_amortissement_ligne"],
        "rapports": [],
        "stats": ["patrimoine"],
    },
    "hr.group_hr_user": {
        "tables": ["hr_employee","hr_department"],
        "rapports": [],
        "stats": ["chauffeurs"],
    },
    "account.group_account_user": {
        "tables": ["account_move","account_move_line"],
        "rapports": [],
        "stats": [],
    },
    "base.group_system": {
        "tables": ["ALL"],
        "rapports": ["ALL"],
        "stats": ["ALL"],
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

    def _get_user_permissions(self):
        user = self.env.user
        allowed_tables   = set(PERMISSIONS["base"]["tables"])
        allowed_rapports = set(PERMISSIONS["base"].get("rapports", []))
        allowed_stats    = set(PERMISSIONS["base"].get("stats", []))
        for gid, perms in PERMISSIONS.items():
            if gid == "base":
                continue
            try:
                if user.has_group(gid):
                    if "ALL" in perms.get("tables", []):
                        _logger.info("Acces admin total pour %s", user.name)
                        return None, {"ALL"}, {"ALL"}, True
                    allowed_tables.update(perms.get("tables", []))
                    rp = perms.get("rapports", [])
                    if "ALL" in rp:
                        allowed_rapports = {"ALL"}
                    else:
                        allowed_rapports.update(rp)
                    st = perms.get("stats", [])
                    if "ALL" in st:
                        allowed_stats = {"ALL"}
                    else:
                        allowed_stats.update(st)
            except Exception:
                continue
        _logger.info("Acces %s : tables=%d rapports=%s stats=%s",
                     user.name, len(allowed_tables),
                     sorted(allowed_rapports), sorted(allowed_stats))
        return allowed_tables, allowed_rapports, allowed_stats, False

    def _get_user_allowed_tables(self):
        tables, _, _, _ = self._get_user_permissions()
        return tables

    def _verifier_acces_rapport(self, type_rapport, allowed_rapports):
        if "ALL" in allowed_rapports:
            return True
        return type_rapport in allowed_rapports

    def _verifier_acces_stats(self, question, allowed_stats):
        if "ALL" in allowed_stats:
            return True
        if not allowed_stats:
            _logger.info("Stats refusees : aucun module autorise pour %s", question)
            return False
        q = question.lower()
        modules_question = []
        mapping = {
            "tournees":   ["tournee", "tournée", "exploitation", "taux realisation", "taux de realisation"],
            "bus":        ["bus", "vehicule", "vehicul", "parc", "flotte", "etat bus", "etat du parc"],
            "assurances": ["assurance", "police", "sinistre"],
            "carburant":  ["carburant", "fuel", "bgi", "bge", "litre", "cuve", "consommation"],
            "boc":        ["courrier", "boc", "arrivee", "depart"],
            "chauffeurs": ["chauffeur", "conducteur", "employe"],
            "patrimoine": ["patrimoine", "immobilisation", "amortissement"],
        }
        for module, mots in mapping.items():
            if any(m in q for m in mots):
                modules_question.append(module)

        if not modules_question:
            # Question générique — autoriser seulement si l'utilisateur a des stats
            _logger.info("Stats question generique '%s' : autorise (modules=%s)", question, sorted(allowed_stats))
            return len(allowed_stats) > 0

        acces_ok = all(m in allowed_stats for m in modules_question)
        _logger.info("Verification stats: user question='%s' modules_detectes=%s allowed=%s ok=%s",
                     question, modules_question, sorted(allowed_stats), acces_ok)
        return acces_ok

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

    def ask_question(self, question=False, mode_rapport=False, mode_stats=False, **kwargs):
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
        allowed_tables, allowed_rapports, allowed_stats, is_admin_user = self._get_user_permissions()

        _mode_rapport = mode_rapport or kwargs.get("mode_rapport", False)
        _mode_stats   = mode_stats   or kwargs.get("mode_stats",   False)

        if _mode_rapport:
            if "ALL" not in allowed_rapports:
                # Aucun rapport autorisé du tout
                if not allowed_rapports:
                    return "Acces refuse : vous n'etes pas autorise a generer des rapports. Contactez votre administrateur."
                # Rapport prédéfini détecté → vérifier accès
                try:
                    from agent.agent_core import _detecter_rapport
                    type_r = _detecter_rapport(question)
                    if type_r:
                        acces_ok = self._verifier_acces_rapport(type_r, allowed_rapports)
                        _logger.info("Verification rapport: user=%s type=%s allowed=%s ok=%s",
                                     user.name, type_r, sorted(allowed_rapports), acces_ok)
                        if not acces_ok:
                            return ("Acces refuse : le rapport [" + type_r + "] "
                                    "n'est pas autorise pour votre profil. "
                                    "Contactez votre administrateur.")
                    else:
                        # Rapport libre — autorisé si l'utilisateur a au moins un rapport
                        _logger.info("Rapport libre demande par %s (rapports autorises: %s)",
                                     user.name, sorted(allowed_rapports))
                except Exception as e:
                    _logger.error("Erreur verification acces rapport: %s", e)
                    # En cas d'erreur de vérification, bloquer par sécurité
                    return "Acces refuse : impossible de verifier vos droits. Contactez votre administrateur."

        if _mode_stats and not self._verifier_acces_stats(question, allowed_stats):
            return "Acces refuse : statistiques non autorisees pour votre profil. Contactez votre administrateur."
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
                "is_admin": is_admin_user,
                "mode_rapport": _mode_rapport,
                "mode_stats": _mode_stats,
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