import { Component, useState, onPatched, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const AGENT_URL = "http://localhost:8000";

class AiChatInterface extends Component {
    static template = "transport_ai_agent.ChatInterface";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            messages: [],
            question: "",
            loading: false,
            userInitials: "??",
            userName: "Chargement...",
            userId: null,
            history: [],
            currentId: this.props.record.resId || null,
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

    async loadUserInfo() {
        try {
            const res = await fetch("/web/session/get_session_info", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {},
                }),
            });
            const data = await res.json();
            if (data.result) {
                const userName = data.result.name ||
                                 data.result.partner_display_name ||
                                 "Utilisateur";
                const parts = userName.trim().split(" ");
                const initials = parts.length >= 2
                    ? (parts[0][0] + parts[1][0]).toUpperCase()
                    : userName.substring(0, 2).toUpperCase();
                this.state.userName = userName;
                this.state.userInitials = initials;
                this.state.userId = data.result.uid || null;
            }
        } catch (e) {
            this.state.userName = "Utilisateur";
            this.state.userInitials = "UT";
        }
    }

    async loadHistory() {
        try {
            const domain = this.state.userId
                ? [["create_uid", "=", this.state.userId]]
                : [];
            const convs = await this.orm.searchRead(
                "transport.ai.conversation",
                domain,
                ["id", "name", "create_date", "message_ids"],
                { order: "create_date desc", limit: 30 }
            );
            this.state.history = convs
                .filter(c =>
                    c.message_ids.length > 0 &&
                    c.name !== "Nouvelle conversation"
                )
                .map(c => ({
                    id: c.id,
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
            this.state.messages = messages.map((m) => {
                const parsed = this._parseContent(m.content || "");
                return {
                    id: m.id,
                    content: parsed.content,
                    pdf_url: parsed.pdf_url,
                    type: m.message_type,
                    time: this._formatTime(m.create_date),
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
            this.state.messages = [];
            await this.loadHistory();
        } catch (e) {
            console.error("Erreur nouvelle conversation:", e);
        }
    }

    async loadConversation(id) {
        this.state.currentId = id;
        this.state.messages = [];
        await this.loadMessages();
    }

    // ── Parsing de la réponse agent ──────────────────────────────────────────

    _parseContent(content) {
        // Détecter PDF_URL: dans la réponse
        const pdfMatch = content.match(/PDF_URL:(http\S+)/);
        if (pdfMatch) {
            const pdf_url = pdfMatch[1].trim();
            // Nettoyer le texte en retirant la ligne PDF_URL:
            const texte = content.replace(/\nPDF_URL:http\S+/, "").trim();
            return { content: texte, pdf_url };
        }
        return { content, pdf_url: null };
    }

    // ── Téléchargement PDF ───────────────────────────────────────────────────

    ouvrirPDF(pdf_url) {
        // Ouvrir le PDF dans un nouvel onglet
        window.open(pdf_url, "_blank");
    }

    async telechargerPDF(pdf_url, nomFichier) {
        try {
            const r = await fetch(pdf_url);
            if (!r.ok) throw new Error(`Erreur ${r.status}`);
            const blob = await r.blob();
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement("a");
            a.href     = url;
            a.download = nomFichier || "rapport.pdf";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this.notification.add("PDF téléchargé avec succès.", { type: "success" });
        } catch(e) {
            this.notification.add(`Erreur téléchargement : ${e.message}`, { type: "danger" });
        }
    }

    _getNomFichier(pdf_url) {
        // Extraire le type de rapport depuis l'URL
        const m = pdf_url.match(/\/rapport\/([^/]+)\/pdf/);
        if (m) return `${m[1]}_${new Date().toISOString().slice(0,10)}.pdf`;
        return "rapport.pdf";
    }

    // ── Formatage ────────────────────────────────────────────────────────────

    _formatTime(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    _formatDate(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now - d) / (1000 * 60 * 60 * 24));
        if (diff === 0) return "Aujourd'hui";
        if (diff === 1) return "Hier";
        if (diff < 7) return `Il y a ${diff} jours`;
        return d.toLocaleDateString("fr-FR", {
            day: "2-digit",
            month: "short",
        });
    }

    _now() {
        return new Date().toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    onInput(ev) {
        this.state.question = ev.target.value;
        ev.target.style.height = "auto";
        ev.target.style.height =
            Math.min(ev.target.scrollHeight, 140) + "px";
    }

    onKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendQuestion();
        }
    }

    async askSuggestion(question) {
        this.state.question = question;
        await this.sendQuestion();
    }

    // ── Envoi question ───────────────────────────────────────────────────────

    async sendQuestion() {
        const question = this.state.question.trim();
        if (!question || this.state.loading) return;

        if (!this.state.currentId) {
            await this.newConversation();
        }

        this.state.messages.push({
            id: Date.now(),
            content: question,
            pdf_url: null,
            type: "user",
            time: this._now(),
        });

        this.state.question = "";
        this.state.loading = true;

        const textarea = document.querySelector(".ai_textarea");
        if (textarea) textarea.style.height = "auto";

        try {
            const result = await this.orm.call(
                "transport.ai.conversation",
                "ask_question",
                [[this.state.currentId]],
                { question: question }
            );

            // ask_question retourne soit un dict {reponse, pdf_url}
            // soit un string (ancienne version)
            let raw = "";
            let pdf_url = null;

            if (result && typeof result === "object") {
                // Nouveau format : dict avec reponse + pdf_url
                raw     = result.reponse || result.content || "";
                pdf_url = result.pdf_url || null;
            } else if (typeof result === "string" && result.trim()) {
                // Ancien format : string pur
                raw = result;
            } else {
                raw = "Aucune réponse reçue.";
            }

            // Parser aussi le texte pour détecter PDF_URL: inline (fallback)
            const parsed = this._parseContent(raw);
            if (!pdf_url && parsed.pdf_url) {
                pdf_url = parsed.pdf_url;
                raw     = parsed.content;
            }

            this.state.messages.push({
                id: Date.now() + 1,
                content: raw || "Aucune réponse reçue.",
                pdf_url: pdf_url,
                type: "agent",
                time: this._now(),
            });

            await this.loadHistory();

        } catch (e) {
            console.error("Erreur sendQuestion:", e);
            this.state.messages.push({
                id: Date.now() + 1,
                content: "Erreur de connexion à l'agent IA.",
                pdf_url: null,
                type: "agent",
                time: this._now(),
            });
            this.notification.add("Erreur agent IA", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    scrollToBottom() {
        const el = document.getElementById("ai_messages_list");
        if (el) el.scrollTop = el.scrollHeight;
    }
}

registry.category("fields").add("ai_chat_messages", {
    component: AiChatInterface,
    supportedTypes: ["one2many"],
});