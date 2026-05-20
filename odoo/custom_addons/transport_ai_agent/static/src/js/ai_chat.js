import { Component, useState, onPatched, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const AGENT_URL = "http://localhost:8000";

// ── Liste des rapports disponibles ──────────────────────────────────────────
const RAPPORTS = [
    {
        id: "rapport_journalier",
        label: "📋 Rapport journalier d'exploitation",
        description: "Tournées du jour, km, écarts, annulations",
        categorie: "Exploitation",
    },
    {
        id: "rapport_hebdomadaire",
        label: "📋 Rapport hebdomadaire d'exploitation",
        description: "Bilan 7 jours : tournées, chauffeurs, lignes",
        categorie: "Exploitation",
    },
    {
        id: "rapport_mensuel",
        label: "📋 Rapport mensuel d'exploitation",
        description: "Bilan du mois : km, recettes, top chauffeurs",
        categorie: "Exploitation",
    },
    {
        id: "bilan_parc",
        label: "🚌 Synthèse état du parc bus",
        description: "État de chaque bus, assurances, km du mois",
        categorie: "Parc",
    },
    {
        id: "bilan_assurance",
        label: "🛡️ Bilan mensuel assurance et sinistres",
        description: "Polices actives, sinistres, expirations à 30j",
        categorie: "Assurance",
    },
    {
        id: "bilan_carburant",
        label: "⛽ Rapport mensuel consommation carburant",
        description: "BGI/BGE, litres par bus, coût total",
        categorie: "Carburant",
    },
    {
        id: "bilan_boc",
        label: "📬 Synthèse courrier BOC",
        description: "Courriers reçus, en attente, en retard",
        categorie: "BOC",
    },
];

class AiChatInterface extends Component {
    static template = "transport_ai_agent.ChatInterface";
    static props = { ...standardFieldProps };

    setup() {
        this.orm          = useService("orm");
        this.notification = useService("notification");
        this.RAPPORTS     = RAPPORTS;

        this.state = useState({
            // Mode : "chat" ou "rapport"
            mode: "chat",

            // Chat
            messages: [],
            question: "",
            loading: false,
            history: [],
            currentId: this.props.record.resId || null,

            // Rapport
            rapportSelectionne: null,
            rapportTexte: "",
            rapportDetectionMsg: "",
            rapportLoading: false,
            rapportResultat: null,
            rapportErreur: null,

            // User
            userInitials: "??",
            userName: "Chargement...",
            userId: null,
        });

        onWillStart(async () => {
            await this.loadUserInfo();
            await this.loadHistory();
            if (this.state.currentId) {
                await this.loadMessages();
            }
        });

        onPatched(() => this.scrollToBottom());
    }

    // ── Mode switch ──────────────────────────────────────────────────────────

    setMode(mode) {
        this.state.mode = mode;
    }

    // ── Rapport ──────────────────────────────────────────────────────────────

    selectRapport(id) {
        this.state.rapportSelectionne  = id;
        this.state.rapportTexte        = "";
        this.state.rapportDetectionMsg = "";
        this.state.rapportResultat     = null;
        this.state.rapportErreur       = null;
    }

    onRapportTexteInput(ev) {
        this.state.rapportTexte        = ev.target.value;
        this.state.rapportDetectionMsg = "";
        this.state.rapportErreur       = null;
    }

    onRapportTexteKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.envoyerTexteRapport();
        }
    }

    // ── Envoi texte → agent avec instruction "génère un rapport PDF" ─────────

    async envoyerTexteRapport() {
        const texte = this.state.rapportTexte.trim();
        if (!texte || this.state.rapportLoading) return;

        this.state.rapportLoading      = true;
        this.state.rapportResultat     = null;
        this.state.rapportErreur       = null;
        this.state.rapportDetectionMsg = "⏳ Génération du rapport en cours...";

        try {
            if (!this.state.currentId) await this.newConversation();

            const result = await this.orm.call(
                "transport.ai.conversation",
                "ask_question",
                [[this.state.currentId]],
                { question: texte, mode_rapport: true }
            );

            let raw     = "";
            let pdf_url = null;

            if (result && typeof result === "object") {
                raw     = result.reponse || result.content || result.texte || "";
                pdf_url = result.pdf_url || null;
            } else if (typeof result === "string") {
                raw = result;
                // Odoo retourne parfois le texte brut avec PDF_URL dedans
                const parsed0 = this._parseContent(raw);
                if (parsed0.pdf_url) {
                    pdf_url = parsed0.pdf_url;
                    raw     = parsed0.content;
                }
            }

            const parsed = this._parseContent(raw);
            if (!pdf_url && parsed.pdf_url) {
                pdf_url = parsed.pdf_url;
                raw     = parsed.content;
            }

            if (pdf_url) {
                // Extraire le type depuis l'URL (rapport prédéfini ou libre)
                const m1 = pdf_url.match(/\/rapport\/([^/]+)\/pdf/);
                const m2 = pdf_url.match(/\/rapports\/fichiers\/([^/]+\.pdf)/);
                const tid = m1 ? m1[1] : null;
                const nom = m2 ? m2[1] : null;
                const rpt = tid ? RAPPORTS.find(r => r.id === tid) : null;

                this.state.rapportResultat = {
                    label:   rpt ? rpt.label : "Rapport personnalisé",
                    pdf_url,
                    texte:   raw,
                    nom_fichier: nom || (tid ? `${tid}_${this._dateStr()}.pdf` : "rapport.pdf"),
                };
                if (tid) this.state.rapportSelectionne = tid;
                this.state.rapportDetectionMsg = "";
                this.notification.add("Rapport généré !", { type: "success" });
            } else {
                // L'agent n'a pas trouvé de rapport correspondant
                this.state.rapportDetectionMsg = "";
                this.state.rapportErreur = raw || "Aucun rapport trouvé pour cette demande. Essayez : \"données sur les bus\", \"assurances\", \"carburant\"...";
            }

        } catch (e) {
            console.error("Erreur rapport:", e);
            this.state.rapportDetectionMsg = "";
            this.state.rapportErreur = "Erreur de connexion à l'agent IA.";
        } finally {
            this.state.rapportLoading = false;
        }
    }

    getRapportLabel(id) {
        const r = RAPPORTS.find(r => r.id === id);
        return r ? r.label : id;
    }

    async genererRapport() {
        const id = this.state.rapportDetecte || this.state.rapportSelectionne;
        if (!id || this.state.rapportLoading) return;

        this.state.rapportLoading = true;
        this.state.rapportResultat = null;
        this.state.rapportErreur   = null;

        try {
            const res = await fetch(`${AGENT_URL}/rapport/${id}/pdf`, {
                method: "GET",
                headers: { "Accept": "application/json" },
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `Erreur HTTP ${res.status}`);
            }

            const data = await res.json();
            const pdf_url = data.pdf_url || `${AGENT_URL}/rapport/${id}/pdf`;
            const label   = this.getRapportLabel(id);

            this.state.rapportResultat = {
                label,
                pdf_url,
                texte: data.texte || `Rapport ${label} généré avec succès.`,
            };

            this.notification.add("Rapport généré avec succès !", { type: "success" });

        } catch (e) {
            // Fallback : si l'API ne retourne pas JSON, construire l'URL directement
            const pdf_url = `${AGENT_URL}/rapport/${id}/pdf`;
            const label   = this.getRapportLabel(id);
            this.state.rapportResultat = {
                label,
                pdf_url,
                texte: `Rapport ${label} prêt.`,
            };
        } finally {
            this.state.rapportLoading = false;
        }
    }

    ouvrirRapportPDF() {
        if (this.state.rapportResultat?.pdf_url) {
            // Ouvrir inline dans un nouvel onglet
            window.open(this.state.rapportResultat.pdf_url, "_blank");
        }
    }

    async telechargerRapportPDF() {
        const r = this.state.rapportResultat;
        if (!r?.pdf_url) return;
        const nom = r.nom_fichier ||
            `${this.state.rapportSelectionne || "rapport"}_${this._dateStr()}.pdf`;
        // Ajouter ?dl=true pour forcer le téléchargement
        const url_dl = r.pdf_url.includes("?") ? r.pdf_url + "&dl=true" : r.pdf_url + "?dl=true";
        await this.telechargerPDF(url_dl, nom);
    }

    _dateStr() {
        return new Date().toISOString().slice(0, 10);
    }

    // ── User info ────────────────────────────────────────────────────────────

    async loadUserInfo() {
        try {
            const res = await fetch("/web/session/get_session_info", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} }),
            });
            const data = await res.json();
            if (data.result) {
                const userName = data.result.name || data.result.partner_display_name || "Utilisateur";
                const parts = userName.trim().split(" ");
                const initials = parts.length >= 2
                    ? (parts[0][0] + parts[1][0]).toUpperCase()
                    : userName.substring(0, 2).toUpperCase();
                this.state.userName     = userName;
                this.state.userInitials = initials;
                this.state.userId       = data.result.uid || null;
            }
        } catch (e) {
            this.state.userName     = "Utilisateur";
            this.state.userInitials = "UT";
        }
    }

    // ── Historique conversations ─────────────────────────────────────────────

    async loadHistory() {
        try {
            const domain = this.state.userId ? [["create_uid", "=", this.state.userId]] : [];
            const convs  = await this.orm.searchRead(
                "transport.ai.conversation",
                domain,
                ["id", "name", "create_date", "message_ids"],
                { order: "create_date desc", limit: 30 }
            );
            this.state.history = convs
                .filter(c => c.message_ids.length > 0 && c.name !== "Nouvelle conversation")
                .map(c => ({
                    id:   c.id,
                    name: c.name,
                    date: this._formatDate(c.create_date),
                }));
        } catch (e) {
            console.error("Erreur chargement historique:", e);
        }
    }

    async loadMessages() {
        try {
            const messages = await this.orm.searchRead(
                "transport.ai.message",
                [["conversation_id", "=", this.state.currentId]],
                ["content", "message_type", "create_date"],
                { order: "create_date asc" }
            );
            this.state.messages = messages.map(m => {
                const parsed = this._parseContent(m.content || "");
                return {
                    id:      m.id,
                    content: parsed.content,
                    pdf_url: parsed.pdf_url,
                    type:    m.message_type,
                    time:    this._formatTime(m.create_date),
                };
            });
        } catch (e) {
            console.error("Erreur chargement messages:", e);
        }
    }

    async newConversation() {
        try {
            const id = await this.orm.create(
                "transport.ai.conversation",
                [{ name: "Nouvelle conversation" }]
            );
            this.state.currentId = id;
            this.state.messages  = [];
            await this.loadHistory();
        } catch (e) {
            console.error("Erreur nouvelle conversation:", e);
        }
    }

    async loadConversation(id) {
        this.state.currentId = id;
        this.state.messages  = [];
        await this.loadMessages();
    }

    // ── Parsing ──────────────────────────────────────────────────────────────

    _parseContent(content) {
        const pdfMatch = content.match(/PDF_URL:(http\S+)/);
        if (pdfMatch) {
            const pdf_url = pdfMatch[1].trim();
            const texte   = content.replace(/\nPDF_URL:http\S+/, "").trim();
            return { content: texte, pdf_url };
        }
        return { content, pdf_url: null };
    }

    // ── PDF helpers ──────────────────────────────────────────────────────────

    ouvrirPDF(pdf_url) {
        // Ouvre inline dans un nouvel onglet
        window.open(pdf_url, "_blank");
    }

    async telechargerPDF(pdf_url, nomFichier) {
        // Ajouter ?dl=true si c'est une URL FastAPI
        const url = pdf_url.includes("localhost:8000") && !pdf_url.includes("?dl")
            ? (pdf_url.includes("?") ? pdf_url + "&dl=true" : pdf_url + "?dl=true")
            : pdf_url;
        try {
            const r    = await fetch(url);
            if (!r.ok) throw new Error(`Erreur ${r.status}`);
            const blob = await r.blob();
            const a    = Object.assign(document.createElement("a"), {
                href:     URL.createObjectURL(blob),
                download: nomFichier || "rapport.pdf",
            });
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);
            this.notification.add("PDF téléchargé avec succès.", { type: "success" });
        } catch (e) {
            this.notification.add(`Erreur téléchargement : ${e.message}`, { type: "danger" });
        }
    }

    _getNomFichier(pdf_url) {
        const m = pdf_url.match(/\/rapport\/([^/]+)\/pdf/);
        if (m) return `${m[1]}_${this._dateStr()}.pdf`;
        return "rapport.pdf";
    }

    // ── Envoi question (mode chat) ────────────────────────────────────────────

    async sendQuestion() {
        const question = this.state.question.trim();
        if (!question || this.state.loading) return;

        if (!this.state.currentId) await this.newConversation();

        this.state.messages.push({
            id:      Date.now(),
            content: question,
            pdf_url: null,
            type:    "user",
            time:    this._now(),
        });

        this.state.question = "";
        this.state.loading  = true;

        const textarea = document.querySelector(".ai_textarea");
        if (textarea) textarea.style.height = "auto";

        try {
            const result = await this.orm.call(
                "transport.ai.conversation",
                "ask_question",
                [[this.state.currentId]],
                { question }
            );

            let raw     = "";
            let pdf_url = null;

            if (result && typeof result === "object") {
                raw     = result.reponse || result.content || result.texte || "";
                pdf_url = result.pdf_url || null;
            } else if (typeof result === "string" && result.trim()) {
                raw = result;
            } else {
                raw = "Aucune réponse reçue.";
            }

            const parsed = this._parseContent(raw);
            if (!pdf_url && parsed.pdf_url) {
                pdf_url = parsed.pdf_url;
                raw     = parsed.content;
            }

            this.state.messages.push({
                id:      Date.now() + 1,
                content: raw || "Aucune réponse reçue.",
                pdf_url,
                type:    "agent",
                time:    this._now(),
            });

            await this.loadHistory();

        } catch (e) {
            console.error("Erreur sendQuestion:", e);
            this.state.messages.push({
                id:      Date.now() + 1,
                content: "Erreur de connexion à l'agent IA.",
                pdf_url: null,
                type:    "agent",
                time:    this._now(),
            });
            this.notification.add("Erreur agent IA", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async askSuggestion(question) {
        this.state.question = question;
        await this.sendQuestion();
    }

    // ── Utilitaires ──────────────────────────────────────────────────────────

    onInput(ev) {
        this.state.question      = ev.target.value;
        ev.target.style.height   = "auto";
        ev.target.style.height   = Math.min(ev.target.scrollHeight, 140) + "px";
    }

    onKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendQuestion();
        }
    }

    scrollToBottom() {
        const el = document.getElementById("ai_messages_list");
        if (el) el.scrollTop = el.scrollHeight;
    }

    _formatTime(dateStr) {
        if (!dateStr) return "";
        return new Date(dateStr).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    }

    _formatDate(dateStr) {
        if (!dateStr) return "";
        const d    = new Date(dateStr);
        const now  = new Date();
        const diff = Math.floor((now - d) / (1000 * 60 * 60 * 24));
        if (diff === 0) return "Aujourd'hui";
        if (diff === 1) return "Hier";
        if (diff < 7)   return `Il y a ${diff} jours`;
        return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
    }

    _now() {
        return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    }
}

registry.category("fields").add("ai_chat_messages", {
    component: AiChatInterface,
    supportedTypes: ["one2many"],
});