import { Component, useState, onPatched, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const AGENT_URL = "http://localhost:8000";

// ── Rapports prédéfinis — multilingue ───────────────────────────────────────
const RAPPORTS_I18N = {
    rapport_journalier: {
        fr: { label: "📋 Rapport journalier d'exploitation", description: "Tournées du jour, km, écarts, annulations",       categorie: "Exploitation" },
        en: { label: "📋 Daily operations report",           description: "Today's trips, km, deviations, cancellations",    categorie: "Operations"   },
        ar: { label: "📋 تقرير التشغيل اليومي",              description: "رحلات اليوم، الكم، الانحرافات، الإلغاءات",       categorie: "التشغيل"      },
    },
    rapport_hebdomadaire: {
        fr: { label: "📋 Rapport hebdomadaire d'exploitation", description: "Bilan 7 jours : tournées, chauffeurs, lignes",  categorie: "Exploitation" },
        en: { label: "📋 Weekly operations report",            description: "7-day summary: trips, drivers, lines",          categorie: "Operations"   },
        ar: { label: "📋 تقرير التشغيل الأسبوعي",             description: "ملخص 7 أيام: الرحلات، السائقين، الخطوط",       categorie: "التشغيل"      },
    },
    rapport_mensuel: {
        fr: { label: "📋 Rapport mensuel d'exploitation",      description: "Bilan du mois : km, recettes, top chauffeurs",  categorie: "Exploitation" },
        en: { label: "📋 Monthly operations report",           description: "Monthly summary: km, revenue, top drivers",     categorie: "Operations"   },
        ar: { label: "📋 تقرير التشغيل الشهري",               description: "ملخص الشهر: الكم، الإيرادات، أفضل السائقين",   categorie: "التشغيل"      },
    },
    bilan_parc: {
        fr: { label: "🚌 Synthèse état du parc bus",           description: "État de chaque bus, assurances, km du mois",   categorie: "Parc"         },
        en: { label: "🚌 Fleet status report",                 description: "Each bus status, insurance, monthly km",        categorie: "Fleet"        },
        ar: { label: "🚌 تقرير حالة الأسطول",                 description: "حالة كل حافلة، التأمين، الكم الشهري",          categorie: "الأسطول"      },
    },
    bilan_assurance: {
        fr: { label: "🛡️ Bilan mensuel assurance et sinistres", description: "Polices actives, sinistres, expirations à 30j", categorie: "Assurance" },
        en: { label: "🛡️ Monthly insurance report",            description: "Active policies, claims, 30-day expirations",   categorie: "Insurance"    },
        ar: { label: "🛡️ تقرير التأمين الشهري",               description: "البوليصات النشطة، الحوادث، انتهاءات 30 يوم",  categorie: "التأمين"      },
    },
    bilan_carburant: {
        fr: { label: "⛽ Rapport mensuel consommation carburant", description: "BGI/BGE, litres par bus, coût total",        categorie: "Carburant"    },
        en: { label: "⛽ Monthly fuel consumption report",      description: "BGI/BGE, liters per bus, total cost",          categorie: "Fuel"         },
        ar: { label: "⛽ تقرير استهلاك الوقود الشهري",          description: "BGI/BGE، اللترات لكل حافلة، التكلفة الإجمالية", categorie: "الوقود"     },
    },
    bilan_boc: {
        fr: { label: "📬 Synthèse courrier BOC",               description: "Courriers reçus, en attente, en retard",       categorie: "BOC"          },
        en: { label: "📬 Mail management report",              description: "Received mail, pending, overdue",               categorie: "Mail"         },
        ar: { label: "📬 تقرير البريد",                        description: "البريد الوارد، قيد الانتظار، المتأخر",         categorie: "البريد"       },
    },
};

// Langue UI (détectée depuis le navigateur ou défaut ar car ERP tunisien)
function detecterLangueUI() {
    // Priorité 1 : langue de session Odoo (fiable)
    try {
        const odooLang = (
            odoo?.session_info?.user_context?.lang ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        if (odooLang.startsWith("ar")) return "ar";
        if (odooLang.startsWith("en")) return "en";
        if (odooLang.startsWith("fr")) return "fr";
    } catch(e) {}
    // Priorité 2 : attribut lang du document HTML
    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("ar")) return "ar";
    if (htmlLang.startsWith("en")) return "en";
    // Priorité 3 : direction du texte (RTL = arabe)
    if (document.documentElement.dir === "rtl") return "ar";
    // Défaut
    return "fr";
}
const UI_LANG = detecterLangueUI();

// RAPPORTS dans la langue de l'UI
const RAPPORTS = Object.entries(RAPPORTS_I18N).map(([id, trs]) => ({
    id,
    ...(trs[UI_LANG] || trs["fr"]),
}));

// ── Raccourcis statistiques — multilingue ───────────────────────────────────
const STATS_RACCOURCIS_I18N = {
    fr: [
        { module: "🚌 Parc bus",    couleur: "#2196F3", questions: ["Combien de bus disponibles ?", "Répartition des bus par état", "Bus sans tournée ce mois"] },
        { module: "⛽ Carburant",   couleur: "#FF9800", questions: ["Consommation par bus", "Litres BGI vs BGE", "Évolution du coût carburant"] },
        { module: "📋 Tournées",    couleur: "#4CAF50", questions: ["Tournées par ligne ce mois", "Taux de réalisation", "Évolution sur 6 mois"] },
        { module: "🛡️ Assurances",  couleur: "#9C27B0", questions: ["Polices expirant dans 30 jours", "Répartition par type", "Sinistres ce trimestre"] },
        { module: "📬 BOC",         couleur: "#F44336", questions: ["Courriers en attente", "Répartition arrivée/départ", "Courriers par statut"] },
    ],
    en: [
        { module: "🚌 Fleet",       couleur: "#2196F3", questions: ["How many buses available?", "Bus distribution by status", "Buses with no trip this month"] },
        { module: "⛽ Fuel",        couleur: "#FF9800", questions: ["Consumption per bus", "BGI vs BGE liters", "Fuel cost trend"] },
        { module: "📋 Trips",       couleur: "#4CAF50", questions: ["Trips per line this month", "Completion rate", "6-month trend"] },
        { module: "🛡️ Insurance",   couleur: "#9C27B0", questions: ["Policies expiring in 30 days", "Distribution by type", "Claims this quarter"] },
        { module: "📬 Mail",        couleur: "#F44336", questions: ["Pending mail", "Incoming vs outgoing", "Mail by status"] },
    ],
    ar: [
        { module: "🚌 الأسطول",     couleur: "#2196F3", questions: ["كم عدد الحافلات المتاحة؟", "توزيع الحافلات حسب الحالة", "حافلات بدون رحلة هذا الشهر"] },
        { module: "⛽ الوقود",       couleur: "#FF9800", questions: ["الاستهلاك لكل حافلة", "لترات BGI مقابل BGE", "تطور تكلفة الوقود"] },
        { module: "📋 الرحلات",     couleur: "#4CAF50", questions: ["الرحلات حسب الخط هذا الشهر", "معدل الإنجاز", "التطور على 6 أشهر"] },
        { module: "🛡️ التأمين",     couleur: "#9C27B0", questions: ["البوليصات المنتهية خلال 30 يوم", "التوزيع حسب النوع", "الحوادث هذا الفصل"] },
        { module: "📬 البريد",      couleur: "#F44336", questions: ["البريد قيد الانتظار", "الوارد مقابل الصادر", "البريد حسب الحالة"] },
    ],
};
const STATS_RACCOURCIS = STATS_RACCOURCIS_I18N[UI_LANG] || STATS_RACCOURCIS_I18N["fr"];

class AiChatInterface extends Component {
    static template = "transport_ai_agent.ChatInterface";
    static props = { ...standardFieldProps };

    setup() {
        this.orm          = useService("orm");
        this.notification = useService("notification");
        // Recalculer la langue au moment du montage (Odoo est prêt)
        const lang = detecterLangueUI();
        this.STATS_RACCOURCIS = STATS_RACCOURCIS_I18N[lang] || STATS_RACCOURCIS_I18N["fr"];
        this._chartInstance    = null;

        this.state = useState({
            mode: "chat",  // "chat" | "rapport" | "stats"

            // ── Rapports (reactive pour re-render quand langue change) ──────
            rapports: Object.entries(RAPPORTS_I18N).map(([id, trs]) => ({id, ...(trs["fr"])})),

            // ── Chat ──────────────────────────────────────────────────────────
            messages: [],
            question: "",
            loading: false,
            history: [],
            currentId: this.props.record.resId || null,

            // ── Rapport ───────────────────────────────────────────────────────
            rapportSelectionne: null,
            rapportTexte: "",
            rapportDetectionMsg: "",
            rapportLoading: false,
            rapportResultat: null,
            rapportErreur: null,

            // ── Statistiques ──────────────────────────────────────────────────
            statsQuestion: "",
            statsLoading: false,
            statsErreur: null,
            statsTexte: "",
            statsKpis: [],
            statsViz: null,
            statsVizType: "bar",
            statsHasResult: false,
            statsHistory: [],       // historique indépendant
            statsCurrentId: null,   // conversation stats dédiée

            // ── User ──────────────────────────────────────────────────────────
            userInitials: "??",
            userName: "Chargement...",
            userId: null,

            // ── UI langue ─────────────────────────────────────────────────────
            uiLang: detecterLangueUI(),
        });

        onWillStart(async () => {
            await this.loadUserInfo();
            await this.loadHistory();
            await this.loadStatsHistory();
            if (this.state.currentId) await this.loadMessages();
        });

        onMounted(() => {
            if (this.state.mode === "stats" && this.state.statsViz && !this._chartInstance) {
                this._renderChart();
            }
        });

        onPatched(() => {
            this.scrollToBottom();
            // Créer le graphique seulement s'il n'existe pas encore
            if (this.state.mode === "stats" && this.state.statsViz && !this._chartInstance) {
                this._renderChart();
            }
        });
    }

    // ── Mode switch ──────────────────────────────────────────────────────────
    getDateFormatted() {
        const locale = this.state.uiLang === 'ar' ? 'ar-TN'
                     : this.state.uiLang === 'en' ? 'en-GB'
                     : 'fr-FR';
        return new Date().toLocaleDateString(locale, {day:'2-digit', month:'long', year:'numeric'});
    }

    setMode(mode) {
        this.state.mode = mode;
    }

    nouvelleStatsConversation() {
        this.state.statsCurrentId = null;
        this.state.statsQuestion  = "";
        this.state.statsHasResult = false;
        this.state.statsViz       = null;
        this.state.statsKpis      = [];
        this.state.statsTexte     = "";
        this.state.statsErreur    = null;
        this._destroyChart();
    }

    // ── Historique Stats indépendant ─────────────────────────────────────────

    async loadStatsHistory() {
        try {
            const domain = this.state.userId
                ? [["create_uid", "=", this.state.userId], ["name", "=like", "[STATS]%"]]
                : [["name", "=like", "[STATS]%"]];
            const convs = await this.orm.searchRead(
                "transport.ai.conversation", domain,
                ["id","name","create_date","message_ids"],
                { order: "create_date desc", limit: 20 }
            );
            this.state.statsHistory = convs
                .filter(c => c.message_ids.length > 0)
                .map(c => ({
                    id:   c.id,
                    name: c.name.replace("[STATS] ", ""),
                    date: this._formatDate(c.create_date),
                }));
        } catch (e) {}
    }

    async newStatsConversation(question) {
        const nom = `[STATS] ${question.slice(0, 45)}`;
        const id  = await this.orm.create("transport.ai.conversation", [{ name: nom }]);
        this.state.statsCurrentId = id;
        return id;
    }

    async loadStatsConversation(id) {
        this.state.statsCurrentId = id;
        this._destroyChart();
        this.state.statsHasResult = false;
        this.state.statsViz       = null;
        this.state.statsKpis      = [];
        this.state.statsTexte     = "";
        this.state.statsErreur    = null;
        this.state.statsLoading   = true;

        try {
            // Récupérer tous les messages de la conversation
            const msgs = await this.orm.searchRead(
                "transport.ai.message",
                [["conversation_id", "=", id]],
                ["content", "message_type", "create_date"],
                { order: "create_date asc" }
            );

            // Récupérer la question (message user)
            const userMsg = msgs.find(m => m.message_type === "user");
            if (userMsg) this.state.statsQuestion = userMsg.content;

            // Récupérer la réponse agent (message agent)
            const agentMsg = msgs.filter(m => m.message_type === "agent").pop();
            if (agentMsg && agentMsg.content) {
                const parsed = this._parseStatsJSON(agentMsg.content);
                if (parsed) {
                    this._appliquerStats(parsed, parsed.texte || agentMsg.content);
                } else {
                    // Réponse texte simple
                    this.state.statsTexte    = agentMsg.content;
                    this.state.statsHasResult= true;
                }
            }
        } catch (e) {
            console.error("Erreur chargement stats:", e);
            this.state.statsErreur = "Erreur lors du chargement de la statistique.";
        } finally {
            this.state.statsLoading = false;
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // STATISTIQUES
    // ══════════════════════════════════════════════════════════════════════════

    onStatsInput(ev) {
        this.state.statsQuestion = ev.target.value;
    }

    onStatsKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.envoyerStatsQuestion();
        }
    }

    clickRaccourci(question) {
        this.state.statsQuestion = question;
        this.envoyerStatsQuestion();
    }

    async envoyerStatsQuestion() {
        const q = this.state.statsQuestion.trim();
        if (!q || this.state.statsLoading) return;

        this.state.statsLoading  = true;
        this.state.statsErreur   = null;
        this.state.statsTexte    = "";
        this.state.statsKpis     = [];
        this.state.statsViz      = null;
        this.state.statsHasResult= false;
        this._destroyChart();

        try {
            // Utiliser une conversation stats dédiée (préfixe [STATS])
            if (!this.state.statsCurrentId) {
                await this.newStatsConversation(q);
            }

            const result = await this.orm.call(
                "transport.ai.conversation",
                "ask_question",
                [[this.state.statsCurrentId]],
                { question: q, mode_stats: true }
            );

            let raw = "";
            if (result && typeof result === "object") {
                raw = result.reponse || result.content || result.texte || "";
                if (result.stats) {
                    this._appliquerStats(result.stats, raw);
                    await this.loadStatsHistory();
                    return;
                }
            } else if (typeof result === "string") {
                raw = result;
            }

            // Vérifier si accès refusé
            if (raw && (raw.includes("Acces refuse") || raw.includes("Accès refusé") || raw.startsWith("🔒"))) {
                this.state.statsErreur    = raw;
                this.state.statsHasResult = false;
                return;
            }

            const parsed = this._parseStatsJSON(raw);
            if (parsed) {
                this._appliquerStats(parsed, parsed.texte || raw);
            } else {
                this.state.statsTexte    = raw;
                this.state.statsHasResult= true;
            }

            // Mettre à jour le nom de la conversation avec la question
            await this.orm.write(
                "transport.ai.conversation",
                [this.state.statsCurrentId],
                { name: `[STATS] ${q.slice(0, 45)}` }
            );

            // Prochaine question = nouvelle conversation
            this.state.statsCurrentId = null;
            await this.loadStatsHistory();

        } catch (e) {
            console.error("Erreur stats:", e);
            this.state.statsErreur = "Erreur de connexion à l'agent IA.";
        } finally {
            this.state.statsLoading = false;
        }
    }

    _parseStatsJSON(raw) {
        try {
            // Chercher un bloc JSON dans le texte
            const m = raw.match(/\{[\s\S]*"kpis"[\s\S]*\}/);
            if (m) return JSON.parse(m[0]);
            // Essayer le texte entier
            const clean = raw.replace(/```json|```/g, "").trim();
            if (clean.startsWith("{")) return JSON.parse(clean);
        } catch (e) {}
        return null;
    }

    _appliquerStats(data, texte) {
        this.state.statsTexte     = texte || data.texte || "";
        this.state.statsHasResult = true;

        // KPI cards — toujours afficher si présents
        this.state.statsKpis = data.kpis || [];

        // Si pas de KPIs mais valeur scalaire dans texte → créer un KPI auto
        if (this.state.statsKpis.length === 0 && data.visualisation) {
            const viz = data.visualisation;
            if ((viz.type === "kpi" || !viz.labels || viz.labels.length === 0)
                && viz.data && viz.data.length > 0) {
                // Extraire la valeur depuis data
                this.state.statsKpis = [{
                    label:    viz.title || this.state.statsQuestion,
                    valeur:   viz.data[0],
                    tendance: "=",
                }];
            }
        }

        const viz = data.visualisation;
        // Graphique seulement si labels multiples et pas type kpi
        if (viz && viz.labels && Array.isArray(viz.labels)
            && viz.labels.length > 1 && viz.data && viz.data.length > 1
            && viz.type !== "kpi") {
            this.state.statsViz     = viz;
            this.state.statsVizType = viz.type || "bar";
        } else {
            this.state.statsViz = null;
        }
    }

    setVizType(type) {
        this._destroyChart();
        this.state.statsVizType = type;
        // Délai pour laisser le DOM se mettre à jour avant de recréer le canvas
        setTimeout(() => this._renderChart(), 50);
    }

    _destroyChart() {
        if (this._chartInstance) {
            try { this._chartInstance.destroy(); } catch(e) {}
            this._chartInstance = null;
        }
        // Vider le canvas pour éviter l'effet "graphique fantôme"
        const canvas = document.getElementById("ai_stats_chart");
        if (canvas) {
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    async _renderChart() {
        const viz = this.state.statsViz;
        if (!viz || !viz.labels || !viz.data) return;

        // Attendre que Chart.js soit disponible (chargé depuis CDN)
        let attempts = 0;
        while (typeof window.Chart === "undefined" && attempts < 20) {
            await new Promise(r => setTimeout(r, 100));
            attempts++;
        }
        if (typeof window.Chart === "undefined") {
            console.error("Chart.js non disponible");
            return;
        }

        const canvas = document.getElementById("ai_stats_chart");
        if (!canvas) return;

        this._destroyChart();

        const type      = this.state.statsVizType || viz.type || "bar";
        const ctx       = canvas.getContext("2d");
        const chartType = type === "donut" ? "doughnut" : type;
        const isRound   = ["doughnut","pie","polarArea"].includes(chartType);
        const isRadar   = chartType === "radar";
        const hasScales = !isRound && !isRadar;

        const COULEURS = [
            "#2196F3","#4CAF50","#FF9800","#9C27B0","#F44336",
            "#00BCD4","#8BC34A","#FF5722","#607D8B","#E91E63",
        ];

        let datasets;
        if (Array.isArray(viz.data[0])) {
            datasets = viz.data.map((d, i) => ({
                label:           viz.series ? viz.series[i] : `Série ${i+1}`,
                data:            d,
                backgroundColor: isRound
                    ? COULEURS.slice(0, d.length).map(c => c + "CC")
                    : COULEURS[i % COULEURS.length] + (isRadar ? "40" : "CC"),
                borderColor:     COULEURS[i % COULEURS.length],
                borderWidth:     type === "line" ? 2.5 : 1.5,
                tension:         0.4,
                fill:            isRadar,
                pointRadius:     type === "line" ? 5 : 3,
            }));
        } else {
            datasets = [{
                label:           viz.title || "Données",
                data:            viz.data,
                backgroundColor: isRound || isRadar
                    ? COULEURS.slice(0, viz.data.length).map(c => c + "CC")
                    : "#2196F3CC",
                borderColor: isRound || isRadar
                    ? COULEURS.slice(0, viz.data.length)
                    : "#2196F3",
                borderWidth:      type === "line" ? 2.5 : 1.5,
                tension:          0.4,
                fill:             isRadar,
                pointRadius:      type === "line" ? 5 : 3,
                pointHoverRadius: type === "line" ? 7 : 4,
            }];
        }

        try {
            this._chartInstance = new window.Chart(ctx, {
                type: chartType,
                data: { labels: viz.labels, datasets },
                options: {
                    responsive:          true,
                    maintainAspectRatio: false,
                    animation:           { duration: 700, easing: "easeInOutQuart" },
                    plugins: {
                        legend: {
                            display:  isRound || isRadar || datasets.length > 1,
                            position: "bottom",
                            labels:   { font: { size: 11 }, padding: 14, usePointStyle: true },
                        },
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const v = ctx.parsed?.y ?? ctx.parsed?.r ?? ctx.raw;
                                    return ` ${ctx.dataset.label}: ${typeof v === "number" ? v.toLocaleString("fr-FR") : v}`;
                                }
                            }
                        },
                    },
                    scales: hasScales ? {
                        x: { grid: { color: "#f1f5f9" }, ticks: { font: { size: 10 } } },
                        y: {
                            grid:        { color: "#f1f5f9" },
                            ticks:       { font: { size: 10 }, callback: v => Number(v).toLocaleString("fr-FR") },
                            beginAtZero: true,
                        },
                    } : isRadar ? {
                        r: { ticks: { font: { size: 9 }, backdropColor: "transparent" } }
                    } : {},
                },
            });
        } catch(e) {
            console.error("Erreur rendu Chart.js:", e);
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // RAPPORT
    // ══════════════════════════════════════════════════════════════════════════

    selectRapport(id) {
        this.state.rapportSelectionne  = id;
        this.state.rapportTexte        = "";
        this.state.rapportDetectionMsg = "";
        this.state.rapportResultat     = null;
        this.state.rapportErreur       = null;
    }

    getRapportLabel(id) {
        const r = RAPPORTS.find(r => r.id === id);
        return r ? r.label : id;
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

            let raw = "", pdf_url = null;
            if (result && typeof result === "object") {
                raw     = result.reponse || result.content || result.texte || "";
                pdf_url = result.pdf_url || null;
            } else if (typeof result === "string") {
                raw = result;
            }

            const parsed = this._parseContent(raw);
            if (!pdf_url && parsed.pdf_url) { pdf_url = parsed.pdf_url; raw = parsed.content; }

            if (pdf_url) {
                const m1  = pdf_url.match(/\/rapport\/([^/]+)\/pdf/);
                const m2  = pdf_url.match(/\/rapports\/fichiers\/([^/]+\.pdf)/);
                const tid = m1 ? m1[1] : null;
                const nom = m2 ? m2[1] : null;
                const rpt = tid ? RAPPORTS.find(r => r.id === tid) : null;
                this.state.rapportResultat = {
                    label: rpt ? rpt.label : (UI_LANG === "ar" ? "تقرير مخصص" : UI_LANG === "en" ? "Custom report" : "Rapport personnalisé"),
                    pdf_url, texte: raw,
                    nom_fichier: nom || (tid ? `${tid}_${this._dateStr()}.pdf` : "rapport.pdf"),
                };
                if (tid) this.state.rapportSelectionne = tid;
                this.state.rapportDetectionMsg = "";
                this.notification.add(this.state.uiLang === "ar" ? "تم إنشاء التقرير!" : this.state.uiLang === "en" ? "Report generated!" : "Rapport généré !", { type: "success" });
            } else {
                this.state.rapportDetectionMsg = "";
                this.state.rapportErreur = raw || "Aucun rapport trouvé. Essayez une formulation différente.";
            }
        } catch (e) {
            this.state.rapportDetectionMsg = "";
            this.state.rapportErreur = "Erreur de connexion à l'agent IA.";
        } finally {
            this.state.rapportLoading = false;
        }
    }

    async genererRapport() {
        const id = this.state.rapportSelectionne;
        if (!id || this.state.rapportLoading) return;

        this.state.rapportLoading  = true;
        this.state.rapportResultat = null;
        this.state.rapportErreur   = null;

        try {
            // Appel direct FastAPI avec la langue correcte — bypass ask_question
            const lang     = this.state.uiLang || "fr";
            const pdf_url  = `${AGENT_URL}/rapport/${id}/pdf?langue=${lang}`;
            const label    = this.getRapportLabel(id);
            this.state.rapportResultat = {
                label, pdf_url,
                nom_fichier: `${id}_${this._dateStr()}.pdf`,
            };
            this.notification.add(
                this.state.uiLang === "ar" ? "تم إنشاء التقرير!" :
                this.state.uiLang === "en" ? "Report generated!" : "Rapport généré !",
                { type: "success" }
            );
        } catch (e) {
            console.error("Erreur rapport:", e);
            this.state.rapportErreur = "Erreur de connexion à l'agent IA.";
        } finally {
            this.state.rapportLoading = false;
        }
    }

    ouvrirRapportPDF() {
        if (this.state.rapportResultat?.pdf_url)
            window.open(this.state.rapportResultat.pdf_url, "_blank");
    }

    async telechargerRapportPDF() {
        const r = this.state.rapportResultat;
        if (!r?.pdf_url) return;
        const url = r.pdf_url.includes("?") ? r.pdf_url + "&dl=true" : r.pdf_url + "?dl=true";
        await this.telechargerPDF(url, r.nom_fichier || "rapport.pdf");
    }

    // ══════════════════════════════════════════════════════════════════════════
    // CHAT
    // ══════════════════════════════════════════════════════════════════════════

    async loadUserInfo() {
        try {
            const info = await this.orm.call(
                "transport.ai.conversation", "get_current_user_info", [], {}
            );
            this.state.userName     = info.name     || "Utilisateur";
            this.state.userInitials = info.initials || "UT";
            this.state.userId       = info.id       || null;

            // Langue Odoo de l'utilisateur — fiable car vient du serveur
            const lang = info.ui_lang || "fr";
            this.state.uiLang   = lang;
            this.state.rapports = Object.entries(RAPPORTS_I18N).map(([id, trs]) => ({
                id, ...(trs[lang] || trs["fr"]),
            }));
            this.RAPPORTS         = this.state.rapports;
            this.STATS_RACCOURCIS = STATS_RACCOURCIS_I18N[lang] || STATS_RACCOURCIS_I18N["fr"];
        } catch (e) {
            this.state.userName     = "Utilisateur";
            this.state.userInitials = "UT";
        }
    }

    async loadHistory() {
        try {
            const domain = this.state.userId
                ? [["create_uid", "=", this.state.userId]]
                : [];
            const convs  = await this.orm.searchRead(
                "transport.ai.conversation", domain,
                ["id","name","create_date","message_ids"],
                { order: "create_date desc", limit: 30 }
            );
            this.state.history = convs
                .filter(c =>
                    c.message_ids.length > 0 &&
                    c.name !== "Nouvelle conversation" &&
                    !c.name.startsWith("[STATS]")   // exclure les conversations stats
                )
                .map(c => ({ id: c.id, name: c.name, date: this._formatDate(c.create_date) }));
        } catch (e) {}
    }

    async loadMessages() {
        try {
            const msgs = await this.orm.searchRead(
                "transport.ai.message",
                [["conversation_id", "=", this.state.currentId]],
                ["content","message_type","create_date"],
                { order: "create_date asc" }
            );
            this.state.messages = msgs.map(m => {
                const p = this._parseContent(m.content || "");
                return { id: m.id, content: p.content, pdf_url: p.pdf_url, type: m.message_type, time: this._formatTime(m.create_date) };
            });
        } catch (e) {}
    }

    async newConversation() {
        const id = await this.orm.create("transport.ai.conversation", [{ name: "Nouvelle conversation" }]);
        this.state.currentId = id;
        this.state.messages  = [];
        await this.loadHistory();
    }

    async loadConversation(id) {
        this.state.currentId = id;
        this.state.messages  = [];
        await this.loadMessages();
    }

    async sendQuestion() {
        const q = this.state.question.trim();
        if (!q || this.state.loading) return;
        if (!this.state.currentId) await this.newConversation();

        this.state.messages.push({ id: Date.now(), content: q, pdf_url: null, type: "user", time: this._now() });
        this.state.question = "";
        this.state.loading  = true;
        const ta = document.querySelector(".ai_textarea");
        if (ta) ta.style.height = "auto";

        try {
            const result = await this.orm.call(
                "transport.ai.conversation", "ask_question",
                [[this.state.currentId]], { question: q }
            );

            let raw = "", pdf_url = null;
            if (result && typeof result === "object") {
                raw     = result.reponse || result.content || result.texte || "";
                pdf_url = result.pdf_url || null;
            } else if (typeof result === "string" && result.trim()) {
                raw = result;
            } else {
                raw = "Aucune réponse reçue.";
            }

            const parsed = this._parseContent(raw);
            if (!pdf_url && parsed.pdf_url) { pdf_url = parsed.pdf_url; raw = parsed.content; }

            this.state.messages.push({
                id: Date.now() + 1, content: raw || "Aucune réponse reçue.",
                pdf_url, type: "agent", time: this._now(),
            });
            await this.loadHistory();
        } catch (e) {
            this.state.messages.push({
                id: Date.now() + 1, content: "Erreur de connexion à l'agent IA.",
                pdf_url: null, type: "agent", time: this._now(),
            });
        } finally {
            this.state.loading = false;
        }
    }

    async askSuggestion(q) { this.state.question = q; await this.sendQuestion(); }

    // ── Utilitaires ──────────────────────────────────────────────────────────

    _parseContent(content) {
        const m = content.match(/PDF_URL:(https?:\/\/[^\r\n\s]+)/);
        if (m) {
            return { content: content.replace(/\nPDF_URL:https?:\/\/[^\r\n]+/, "").trim(), pdf_url: m[1].trim().replace(/\r$/, "") };
        }
        return { content, pdf_url: null };
    }

    ouvrirPDF(pdf_url) { window.open(pdf_url, "_blank"); }

    async telechargerPDF(pdf_url, nomFichier) {
        const url = pdf_url.includes("localhost:8000") && !pdf_url.includes("?dl")
            ? (pdf_url.includes("?") ? pdf_url + "&dl=true" : pdf_url + "?dl=true")
            : pdf_url;
        try {
            const r    = await fetch(url);
            if (!r.ok) throw new Error(`Erreur ${r.status}`);
            const blob = await r.blob();
            const a    = Object.assign(document.createElement("a"), {
                href: URL.createObjectURL(blob), download: nomFichier || "rapport.pdf",
            });
            document.body.appendChild(a); a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);
            this.notification.add("PDF téléchargé.", { type: "success" });
        } catch (e) {
            this.notification.add(`Erreur : ${e.message}`, { type: "danger" });
        }
    }

    _getNomFichier(pdf_url) {
        const m = pdf_url.match(/\/rapport\/([^/]+)\/pdf/);
        return m ? `${m[1]}_${this._dateStr()}.pdf` : "rapport.pdf";
    }

    onInput(ev) {
        this.state.question    = ev.target.value;
        ev.target.style.height = "auto";
        ev.target.style.height = Math.min(ev.target.scrollHeight, 140) + "px";
    }

    onKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendQuestion(); }
    }

    scrollToBottom() {
        const el = document.getElementById("ai_messages_list");
        if (el) el.scrollTop = el.scrollHeight;
    }

    _formatTime(d) { return d ? new Date(d).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : ""; }
    _formatDate(d) {
        if (!d) return "";
        const dt   = new Date(d);
        const now  = new Date();
        const diff = Math.floor((now - dt) / 86400000);
        if (diff === 0) return "Aujourd'hui";
        if (diff === 1) return "Hier";
        if (diff < 7)   return `Il y a ${diff} j`;
        return dt.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
    }
    _now()    { return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); }
    _dateStr(){ return new Date().toISOString().slice(0, 10); }
}

registry.category("fields").add("ai_chat_messages", {
    component: AiChatInterface,
    supportedTypes: ["one2many"],
});