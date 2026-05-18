/** @odoo-module **/
/**
 * transport_ai_agent/static/src/components/chatbot_widget.js
 * Widget chatbot avec boutons de téléchargement PDF — Niveau 3
 */

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const AGENT_URL = "http://localhost:8000";

// Rapports disponibles avec labels et icônes
const RAPPORTS = [
    { id: "rapport_journalier",   label: "📊 Rapport Journalier",     description: "Tournées du jour" },
    { id: "rapport_hebdomadaire", label: "📅 Rapport Hebdomadaire",   description: "Semaine en cours" },
    { id: "rapport_mensuel",      label: "📆 Rapport Mensuel",        description: "Mois en cours" },
    { id: "bilan_parc",           label: "🚌 État du Parc",           description: "Bus et assurances" },
    { id: "bilan_assurance",      label: "🛡 Bilan Assurance",        description: "Polices et sinistres" },
    { id: "bilan_carburant",      label: "⛽ Bilan Carburant",        description: "Consommation" },
    { id: "bilan_boc",            label: "📬 Bilan Courrier BOC",     description: "Courriers du mois" },
];

export class TransportChatbot extends Component {
    static template = "transport_ai_agent.Chatbot";

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            messages: [],
            question: "",
            loading: false,
            showRapports: false,
            downloadingId: null,
            sessionId: `odoo_${Date.now()}`,
            open: false,
        });
        this.messagesEndRef = useRef("messagesEnd");
    }

    // ── Chat ─────────────────────────────────────────────────────────────────

    async envoyerQuestion() {
        const q = this.state.question.trim();
        if (!q || this.state.loading) return;

        this.state.messages.push({ role: "user", texte: q, ts: new Date() });
        this.state.question = "";
        this.state.loading = true;
        this.scrollBas();

        try {
            const r = await fetch(`${AGENT_URL}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: q,
                    session_id: this.state.sessionId,
                    is_admin: true,
                }),
            });
            const data = await r.json();
            const reponse = data.reponse || "Pas de réponse.";

            this.state.messages.push({
                role: "agent",
                texte: reponse,
                ts: new Date(),
                // Détecter si la réponse mentionne un rapport → proposer PDF
                proposerPDF: this._detecterRapportDansReponse(reponse),
            });
        } catch (e) {
            this.state.messages.push({
                role: "agent",
                texte: "❌ Erreur de connexion à l'agent.",
                ts: new Date(),
            });
        } finally {
            this.state.loading = false;
            this.scrollBas();
        }
    }

    onKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.envoyerQuestion();
        }
    }

    _detecterRapportDansReponse(texte) {
        const mots = ["rapport", "bilan", "synthèse", "état du parc",
                      "hebdomadaire", "journalier", "mensuel", "exploitation"];
        return mots.some(m => texte.toLowerCase().includes(m));
    }

    // ── Téléchargement PDF ───────────────────────────────────────────────────

    async telechargerPDF(typeRapport) {
        if (this.state.downloadingId) return;
        this.state.downloadingId = typeRapport;

        const rapport = RAPPORTS.find(r => r.id === typeRapport);
        const label = rapport ? rapport.label : typeRapport;

        this.state.messages.push({
            role: "agent",
            texte: `⏳ Génération du PDF "${label}" en cours...`,
            ts: new Date(),
        });
        this.scrollBas();

        try {
            const r = await fetch(`${AGENT_URL}/rapport/${typeRapport}/pdf`, {
                method: "GET",
            });

            if (!r.ok) {
                const err = await r.json();
                throw new Error(err.detail || `Erreur ${r.status}`);
            }

            // Récupérer le nom du fichier depuis le header
            const disposition = r.headers.get("Content-Disposition") || "";
            const match = disposition.match(/filename="?([^"]+)"?/);
            const nomFichier = match ? match[1] : `${typeRapport}.pdf`;

            // Déclencher le téléchargement
            const blob = await r.blob();
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement("a");
            a.href     = url;
            a.download = nomFichier;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            this.state.messages.push({
                role: "agent",
                texte: `✅ PDF "${label}" téléchargé : ${nomFichier}`,
                ts: new Date(),
            });

            this.notification.add(`Rapport ${label} téléchargé.`, { type: "success" });

        } catch (e) {
            this.state.messages.push({
                role: "agent",
                texte: `❌ Erreur téléchargement : ${e.message}`,
                ts: new Date(),
            });
            this.notification.add(`Erreur : ${e.message}`, { type: "danger" });
        } finally {
            this.state.downloadingId = null;
            this.scrollBas();
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    scrollBas() {
        setTimeout(() => {
            const el = this.messagesEndRef.el;
            if (el) el.scrollIntoView({ behavior: "smooth" });
        }, 50);
    }

    toggleRapports() {
        this.state.showRapports = !this.state.showRapports;
    }

    toggleOpen() {
        this.state.open = !this.state.open;
    }

    effacerChat() {
        this.state.messages = [];
        this.state.sessionId = `odoo_${Date.now()}`;
    }

    formatTs(ts) {
        return ts.toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
    }

    get rapports() {
        return RAPPORTS;
    }
}

// Template XML inline (à déplacer dans chatbot_widget.xml)
TransportChatbot.template = xml`
<div class="transport-chatbot">

  <!-- Bouton flottant -->
  <button class="chatbot-toggle" t-on-click="toggleOpen">
    <t t-if="!state.open">💬</t>
    <t t-else="">✕</t>
  </button>

  <!-- Fenêtre chatbot -->
  <div class="chatbot-window" t-att-class="state.open ? 'open' : ''">

    <!-- Header -->
    <div class="chatbot-header">
      <span>🚌 Agent IA Transport</span>
      <div class="chatbot-actions">
        <button t-on-click="toggleRapports" title="Rapports PDF">📄</button>
        <button t-on-click="effacerChat" title="Nouveau chat">🗑</button>
      </div>
    </div>

    <!-- Panel rapports PDF -->
    <div class="rapports-panel" t-if="state.showRapports">
      <div class="rapports-titre">📊 Télécharger un rapport PDF</div>
      <t t-foreach="rapports" t-as="rapport" t-key="rapport.id">
        <button
          class="rapport-btn"
          t-att-class="state.downloadingId === rapport.id ? 'loading' : ''"
          t-on-click="() => telechargerPDF(rapport.id)"
          t-att-disabled="state.downloadingId !== null">
          <span class="rapport-label"><t t-esc="rapport.label"/></span>
          <span class="rapport-desc"><t t-esc="rapport.description"/></span>
          <span class="rapport-icon">
            <t t-if="state.downloadingId === rapport.id">⏳</t>
            <t t-else="">⬇</t>
          </span>
        </button>
      </t>
    </div>

    <!-- Messages -->
    <div class="chatbot-messages">
      <t t-if="state.messages.length === 0">
        <div class="chatbot-welcome">
          <div class="welcome-icon">🚌</div>
          <div class="welcome-text">
            Bonjour ! Je suis votre assistant IA transport.<br/>
            Posez-moi vos questions ou téléchargez un rapport PDF.
          </div>
          <div class="suggestions">
            <span t-on-click="() => { state.question = 'État du parc bus'; envoyerQuestion(); }">État du parc bus</span>
            <span t-on-click="() => { state.question = 'Rapport journalier'; envoyerQuestion(); }">Rapport journalier</span>
            <span t-on-click="() => { state.question = 'Liste les tournées planifiées'; envoyerQuestion(); }">Tournées planifiées</span>
          </div>
        </div>
      </t>

      <t t-foreach="state.messages" t-as="msg" t-key="msg_index">
        <div class="message" t-att-class="msg.role">
          <div class="message-bubble">
            <t t-esc="msg.texte"/>
          </div>
          <!-- Bouton PDF si rapport détecté dans la réponse -->
          <div class="pdf-suggestion" t-if="msg.proposerPDF">
            <span>Télécharger ce rapport en PDF :</span>
            <t t-foreach="rapports" t-as="r" t-key="r.id">
              <button class="pdf-btn" t-on-click="() => telechargerPDF(r.id)">
                <t t-esc="r.label"/>
              </button>
            </t>
          </div>
          <div class="message-ts"><t t-esc="formatTs(msg.ts)"/></div>
        </div>
      </t>

      <div class="loading-indicator" t-if="state.loading">
        <span>⚡ Agent en cours de réflexion...</span>
      </div>

      <div t-ref="messagesEnd"/>
    </div>

    <!-- Input -->
    <div class="chatbot-input">
      <textarea
        t-model="state.question"
        t-on-keydown="onKeyDown"
        placeholder="Posez votre question..."
        rows="1"
        t-att-disabled="state.loading"/>
      <button
        class="send-btn"
        t-on-click="envoyerQuestion"
        t-att-disabled="state.loading or !state.question.trim()">
        ➤
      </button>
    </div>

  </div>
</div>
`;