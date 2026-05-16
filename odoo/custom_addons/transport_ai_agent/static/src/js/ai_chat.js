/** @odoo-module **/

import { Component, useState, onPatched, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

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
            this.state.messages = messages.map((m) => ({
                id: m.id,
                content: m.content || "",
                type: m.message_type,
                time: this._formatTime(m.create_date),
            }));
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

    async sendQuestion() {
        const question = this.state.question.trim();
        if (!question || this.state.loading) return;

        if (!this.state.currentId) {
            await this.newConversation();
        }

        this.state.messages.push({
            id: Date.now(),
            content: question,
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

            console.log("Réponse agent:", result, typeof result);

            const content = (typeof result === "string" && result.trim())
                ? result
                : "Aucune réponse reçue.";

            this.state.messages.push({
                id: Date.now() + 1,
                content: content,
                type: "agent",
                time: this._now(),
            });

            await this.loadHistory();

        } catch (e) {
            console.error("Erreur sendQuestion:", e);
            this.state.messages.push({
                id: Date.now() + 1,
                content: "Erreur de connexion à l'agent IA.",
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