// HockeyGameBot Dashboard JS - build 2025-12-05 v1.1

const TEAM_NAME_MAP = {
    "ANA": "Anaheim Ducks",
    "ARI": "Arizona Coyotes",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CAR": "Carolina Hurricanes",
    "CBJ": "Columbus Blue Jackets",
    "CGY": "Calgary Flames",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens",
    "NJD": "New Jersey Devils",
    "NSH": "Nashville Predators",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SEA": "Seattle Kraken",
    "SJS": "San Jose Sharks",
    "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Hockey Club",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WPG": "Winnipeg Jets",
    "WSH": "Washington Capitals"
};


let lastFetchTime = null;
let bots = [];
let currentTeamSlug = null;
let fetchIntervalId = null;

function setMainViewVisible(visible) {
    const content = document.getElementById("content");
    if (!content) return;
    content.style.display = visible ? "block" : "none";
}

function setBotsTableVisible(visible) {
    const container = document.getElementById("botsGridContainer");
    if (!container) return;
    container.style.display = visible ? "block" : "none";
}

function setStatusBadgeVisible(visible) {
    const badge = document.getElementById("statusBadge");
    const lastUpdate = document.getElementById("lastUpdate");
    if (badge) badge.style.display = visible ? "flex" : "none";
    if (lastUpdate) lastUpdate.style.display = visible ? "block" : "none";
}

function formatSecondsAgo(ts) {
    if (!ts) return "—";

    const now = Math.floor(Date.now() / 1000);
    const diff = Math.max(0, now - ts);

    if (diff < 5) return "just now";
    if (diff < 60) return `${diff}s ago`;

    const m = Math.floor(diff / 60);
    if (m < 60) return `${m}m ago`;

    const h = Math.floor(m / 60);
    const remM = m % 60;
    if (h < 24) {
        return remM > 0 ? `${h}h ${remM}m ago` : `${h}h ago`;
    }

    const d = Math.floor(h / 24);
    const remH = h % 24;
    return remH > 0 ? `${d}d ${remH}h ago` : `${d}d ago`;
}

function formatUptime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

function formatTimestamp(isoString) {
    if (!isoString) return "Never";
    const date = new Date(isoString);
    return date.toLocaleString();
}

function timeSince(isoString) {
    if (!isoString) return "Never";
    const date = new Date(isoString);
    const seconds = Math.floor((new Date() - date) / 1000);

    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

function updateStatusBadge(status) {
    const badge = document.getElementById("statusBadge");
    const text = document.getElementById("statusText");

    if (!badge || !text) return;

    badge.className = "status-badge status-" + status.toLowerCase();
    text.textContent = status;
}

function renderDashboard(data) {
    const bot = data.bot;
    const game = data.game;
    const events = data.events;
    const performance = data.performance;
    const errors = data.errors;
    const socials = data.socials;
    const health = data.health;

    const cache = data.cache || {};
    const cacheSummary = cache.summary || {};
    const cacheRaw = cache.raw || null;

    const pregame = (cacheRaw && cacheRaw.pregame_posts) || {};
    const pregameSent = pregame.sent || {};
    const pregameRoots = pregame.root_refs || {};

    const rootPlatformsText = Object.keys(pregameRoots).length
        ? Object.keys(pregameRoots).sort().join(", ")
        : "None";

    // Update header
    updateStatusBadge(bot.status);
    const lastUpdate = document.getElementById("lastUpdate");
    if (lastUpdate) {
        lastUpdate.textContent = `Last Update: ${timeSince(bot.last_update)}`;
    }

    let html = "";

    // Game Information
    html += '<div class="card game-card-full">';
    html += '<div class="card-title">Game Information</div>';

    if (game.game_id && game.game_state !== null) {
        if (game.home_team && game.away_team) {
            html += '<div class="game-score">';
            html += `<div class="team-score">
                        <div class="team-name">${game.away_team}</div>
                        <div class="score">${game.away_score || 0}</div>
                     </div>`;
            html += '<div class="vs">@</div>';
            html += `<div class="team-score">
                        <div class="team-name">${game.home_team}</div>
                        <div class="score">${game.home_score || 0}</div>
                     </div>`;
            html += "</div>";
        }

        if (game.period || game.time_remaining) {
            html += '<div class="period-info">';
            html += `<div>
                        <div class="period-label">Period</div>
                        <div class="period-value">${game.period || "N/A"}</div>
                     </div>`;
            html += `<div>
                        <div class="period-label">Time Remaining</div>
                        <div class="period-value">${game.time_remaining || "N/A"}</div>
                     </div>`;
            html += `<div>
                        <div class="period-label">Intermission</div>
                        <div class="period-value">${game.in_intermission ? "Yes" : "No"}</div>
                     </div>`;
            html += "</div>";
        }

        html += `<div class="stat-row">
                    <span class="stat-label">Game ID</span>
                    <span class="stat-value">${game.game_id}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Game State</span>
                    <span class="stat-value">${game.game_state}</span>
                 </div>`;
        if (game.venue) {
            html += `<div class="stat-row">
                        <span class="stat-label">Venue</span>
                        <span class="stat-value">${game.venue}</span>
                     </div>`;
        }
    } else {
        html += '<div class="no-game">No active game</div>';
    }

    html += "</div>";

    // Row 2: Bot stats + health
    html += '<div class="grid">';

    html += '<div class="card">';
    html += '<div class="card-title">Bot Statistics</div>';
    html += `<div class="stat-row">
                <span class="stat-label">Uptime</span>
                <span class="stat-value">${formatUptime(bot.uptime_seconds)}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Live Loops</span>
                <span class="stat-value">${performance.live_loop_count}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Started</span>
                <span class="stat-value">${timeSince(bot.start_time)}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Last Loop</span>
                <span class="stat-value">${timeSince(performance.last_loop_time)}</span>
             </div>`;
    html += "</div>";

    html += '<div class="card">';
    html += '<div class="card-title">System Health</div>';
    html += `<div class="stat-row">
                <span class="stat-label">Status</span>
                <span class="stat-value ${health.healthy ? "health-good" : "health-bad"}">
                    ${health.healthy ? "✓ Healthy" : "✗ Issues Detected"}
                </span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Total Errors</span>
                <span class="stat-value">${errors.count}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Last Error</span>
                <span class="stat-value">${timeSince(errors.last_error_time)}</span>
             </div>`;

    const issues = (health && Array.isArray(health.issues)) ? health.issues : [];

    if (!health.healthy && issues.length > 0) {
        html += '<ul class="issues-list">';
        issues.forEach((issue) => {
            html += `<li>⚠️ ${issue}</li>`;
        });
        html += "</ul>";
    }

    if (errors.last_error) {
        html += `<div style="margin-top: 12px; padding: 8px; background: #fef2f2; border-radius: 4px; font-size: 12px; color: #991b1b;">
                    ${errors.last_error}
                 </div>`;
    }
    html += "</div>";
    html += "</div>";

    // Row 3: events / API / social
    html += '<div class="grid">';

    html += '<div class="card">';
    html += '<div class="card-title">Game Events Processed</div>';
    html += '<div class="event-grid">';

    const eventTypes = [
        { key: "total", label: "Total Events" },
        { key: "goals", label: "Goals" },
        { key: "penalties", label: "Penalties" },
        { key: "shots", label: "Shots" },
        { key: "saves", label: "Saves" },
        { key: "hits", label: "Hits" },
        { key: "blocks", label: "Blocks" },
        { key: "takeaways", label: "Takeaways" },
        { key: "giveaways", label: "Giveaways" },
        { key: "faceoffs", label: "Faceoffs" },
    ];

    eventTypes.forEach((event) => {
        html += `<div class="event-stat">
                    <div class="event-stat-value">${events[event.key]}</div>
                    <div class="event-stat-label">${event.label}</div>
                 </div>`;
    });

    html += "</div>";
    html += "</div>";

    html += '<div class="card">';
    html += '<div class="card-title">API Performance</div>';
    html += `<div class="stat-row">
                <span class="stat-label">Total Calls</span>
                <span class="stat-value">${performance.api_calls.total}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Successful</span>
                <span class="stat-value" style="color: #10b981;">${performance.api_calls.successful}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Failed</span>
                <span class="stat-value" style="color: #ef4444;">${performance.api_calls.failed}</span>
             </div>`;
    const successRate =
        performance.api_calls.total > 0
            ? (
                (performance.api_calls.successful / performance.api_calls.total) *
                100
            ).toFixed(1)
            : 100;
    html += `<div class="stat-row">
                <span class="stat-label">Success Rate</span>
                <span class="stat-value">${successRate}%</span>
             </div>`;
    html += "</div>";

    const previewSent = Object.values(socials.preview_posts || {}).filter(
        (v) => v
    ).length;
    html += '<div class="card">';
    html += '<div class="card-title">Social Media</div>';
    html += `<div class="stat-row">
                <span class="stat-label">Posts Sent</span>
                <span class="stat-value">${socials.posts_sent}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Last Post</span>
                <span class="stat-value">${timeSince(socials.last_post_time)}</span>
             </div>`;
    html += `<div class="stat-row">
                <span class="stat-label">Preview Posts</span>
                <span class="stat-value">${previewSent}/4</span>
             </div>`;
    html += "</div>";

    html += "</div>";

    // Row 4: cache
    html += '<div class="grid">';
    html += '<div class="card">';
    html += '<div class="card-title">Cache / Restart-Safe State</div>';

    if (!cache.enabled || !cacheSummary) {
        html += '<p class="json-empty">Cache has not been initialized yet.</p>';
    } else {
        html += `<div class="stat-row">
                    <span class="stat-label">Enabled</span>
                    <span class="stat-value">${cache.enabled ? "Yes" : "No"}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Season ID</span>
                    <span class="stat-value">${cacheSummary.season_id || "—"}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Game ID</span>
                    <span class="stat-value">${cacheSummary.game_id || "—"}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Team</span>
                    <span class="stat-value">${cacheSummary.team_abbrev || "—"}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Processed Events</span>
                    <span class="stat-value">${cacheSummary.processed_events ?? 0}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Goal Snapshots</span>
                    <span class="stat-value">${cacheSummary.goal_snapshots ?? 0}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Last Sort Order</span>
                    <span class="stat-value">${cacheSummary.last_sort_order ?? "—"}</span>
                 </div>`;
        html += `<div class="stat-row">
                    <span class="stat-label">Thread Roots</span>
                    <span class="stat-value">${rootPlatformsText}</span>
                 </div>`;

        const pregameKinds = [
            { key: "core", label: "Core Preview" },
            { key: "season_series", label: "Season Series" },
            { key: "team_stats", label: "Team Stats Chart" },
            { key: "officials", label: "Officials" },
        ];

        html += '<div class="cache-goals" style="margin-top: 12px;">';
        html += '<div class="cache-goals-header">Pregame Socials</div>';
        html +=
            '<div class="cache-goals-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr));">';
        html +=
            '<div class="cache-goals-cell cache-goals-cell-head">Type</div>';
        html +=
            '<div class="cache-goals-cell cache-goals-cell-head">Status</div>';

        pregameKinds.forEach((item) => {
            const status = pregameSent[item.key] ? "Sent" : "Pending";
            html += `<div class="cache-goals-cell">${item.label}</div>`;
            html += `<div class="cache-goals-cell">${status}</div>`;
        });

        html += "</div>";
        html += "</div>";

        const goalSnapshots = (cacheRaw && cacheRaw.goal_snapshots) || {};
        const goalIds = Object.keys(goalSnapshots);
        if (goalIds.length > 0) {
            goalIds.sort((a, b) => {
                const sa = goalSnapshots[a].sort_order || 0;
                const sb = goalSnapshots[b].sort_order || 0;
                return sa - sb;
            });

            html += '<div class="cache-goals" style="margin-top: 16px;">';
            html += '<div class="cache-goals-header">Goals in Cache</div>';
            html += '<div class="cache-goals-grid">';
            html +=
                '<div class="cache-goals-cell cache-goals-cell-head">Event ID</div>';
            html +=
                '<div class="cache-goals-cell cache-goals-cell-head">Team</div>';
            html +=
                '<div class="cache-goals-cell cache-goals-cell-head">Sort Order</div>';
            html +=
                '<div class="cache-goals-cell cache-goals-cell-head">Posted</div>';

            goalIds.forEach((id) => {
                const g = goalSnapshots[id] || {};
                html += `<div class="cache-goals-cell">${id}</div>`;
                html += `<div class="cache-goals-cell">${g.team_abbrev || "—"}</div>`;
                html += `<div class="cache-goals-cell">${g.sort_order ?? "—"}</div>`;
                html += `<div class="cache-goals-cell">${g.posted ? "Yes" : "No"}</div>`;
            });

            html += "</div>";
            html += "</div>";
        }
    }

    html += "</div>";
    html += "</div>";

    document.getElementById("content").innerHTML = html;
}

function getStatusFileName() {
    if (currentTeamSlug) {
        return `status_${currentTeamSlug}.json`;
    }
    return "status.json";
}

async function fetchStatus() {
    const statusFile = getStatusFileName();

    try {
        const response = await fetch(statusFile + "?t=" + Date.now());
        if (!response.ok) {
            throw new Error("Failed to fetch " + statusFile);
        }
        const data = await response.json();
        lastFetchTime = Date.now();
        renderDashboard(data);
    } catch (error) {
        console.error("Error fetching status:", error);
        document.getElementById("content").innerHTML =
            `<div class="error-message">
                ⚠️ Error loading ${statusFile} – Make sure the bot is running and ${statusFile} exists
             </div>`;
    }
}

function getUtcResetLocalLabel() {
    const now = new Date();
    // Today at midnight UTC
    const utcMidnight = new Date(Date.UTC(
        now.getUTCFullYear(),
        now.getUTCMonth(),
        now.getUTCDate(),
        0, 0, 0, 0
    ));

    const localTime = utcMidnight.toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit"
    });

    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "local time";

    return `${localTime} ${tz}`;
}

function formatPeriodLabel(period) {
    if (period == null) return null;
    const n = Number(period);
    if (n === 1) return "1st";
    if (n === 2) return "2nd";
    if (n === 3) return "3rd";
    if (n === 4) return "OT";
    if (n === 5) return "SO";
    return `P${n}`;
}

function formatGameStateForGrid(g) {
    if (!g) return null;
    const state = g.game_state;
    const periodLabel = formatPeriodLabel(g.period);
    const time = g.time_remaining;

    if (!state) return null;

    // Pre / future
    if (state === "FUT" || state === "PRE") {
        return "Pre-Game";
    }

    // Live game
    if (state === "LIVE") {
        if (g.in_intermission) {
            // "1st INT", "2nd INT", "OT INT"
            if (periodLabel) return `${periodLabel} INT`;
            return "Intermission";
        }
        if (periodLabel && time) return `${periodLabel} • ${time}`;
        if (periodLabel) return periodLabel;
        if (time) return time;
        return "Live";
    }

    // Final states
    if (state === "OFF") {
        if (periodLabel === "OT" || periodLabel === "SO") {
            return `Final ${periodLabel}`;
        }
        return "Final";
    }

    // Fallback (shows raw state string)
    return state;
}


function renderBotsGrid() {
    const container = document.getElementById("botsGridContainer");
    const tbody = document.getElementById("botsGridBody");

    if (!container || !tbody) return;

    if (!bots || bots.length === 0) {
        container.style.display = "none";
        return;
    }

    // Hide table while in detail mode, show in overview
    container.style.display = currentTeamSlug ? "none" : "block";

    tbody.innerHTML = "";

    bots.forEach((bot) => {
        const tr = document.createElement("tr");
        tr.classList.add("bots-grid-row");

        const gameId = bot.gameId
        const statusKey = (bot.status || "").toUpperCase();
        const statusClass = {
            RUNNING: "bots-grid-status-running",
            STARTING: "bots-grid-status-starting",
            SLEEPING: "bots-grid-status-starting",
            STOPPED: "bots-grid-status-idle",
            IDLE: "bots-grid-status-idle",
            ERROR: "bots-grid-status-error",
        }[statusKey] || "bots-grid-status-idle";

        const lastUpdated = bot.last_updated
            ? formatSecondsAgo(bot.last_updated)
            : "—";

        const teamDisplay =
            bot.team_display ||
            bot.full_name ||
            bot.team_name ||
            bot.slug.toUpperCase();

        const xLimitHtml = bot.x_limit_display
            ? `<span class="x-limit-cell-pill" title="Resets at midnight UTC (${getUtcResetLocalLabel()})">${bot.x_limit_display}</span>`
            : "—";

        tr.innerHTML = `
            <td>${teamDisplay}</td>
            <td class="col-center">${gameId}</td>
            <td class="col-center"><span class="bots-grid-status ${statusClass}">${bot.status || "IDLE"}</span></td>
            <td class="cell-muted col-center">${lastUpdated}</td>
            <td class="cell-muted col-center">${bot.matchup || "—"}</td>
            <td class="cell-muted col-center">${bot.game_state_display || "—"}</td>
            <td class="cell-muted col-center">${bot.score || "—"}</td>
            <td class="x-limit-cell col-center">${xLimitHtml}</td>

        `;


        tr.addEventListener("click", () => {
            currentTeamSlug = bot.slug;

            setBotsTableVisible(false);
            setMainViewVisible(true);
            setStatusBadgeVisible(true);

            const back = document.getElementById("backToBots");
            if (back) back.style.display = "inline-flex";

            const base = window.location.pathname;
            window.history.pushState({}, "", `${base}?team=${bot.slug}`);

            fetchStatus();
        });

        tbody.appendChild(tr);
    });
}

async function loadBots() {
    let discoveredBots = [];

    try {
        const response = await fetch("/api/bots?t=" + Date.now());
        if (!response.ok) throw new Error("Failed to fetch /api/bots");
        discoveredBots = await response.json();
    } catch (err) {
        console.error("Error loading bots:", err);
        discoveredBots = [];
    }

    bots = discoveredBots;

    if (bots.length === 0) {
        currentTeamSlug = null;
        return;
    }

    const params = new URLSearchParams(window.location.search);
    const urlTeam = (params.get("team") || "").trim().toLowerCase();

    if (urlTeam && bots.some((b) => b.slug === urlTeam)) {
        currentTeamSlug = urlTeam;
    } else if (currentTeamSlug && bots.some((b) => b.slug === currentTeamSlug)) {
        // keep existing selection
    } else {
        currentTeamSlug = null;
    }

    for (let bot of bots) {
        try {
            const statusResp = await fetch(bot.status_file + "?t=" + Date.now());
            if (!statusResp.ok) throw new Error("Failed to fetch " + bot.status_file);
            const statusData = await statusResp.json();

            const botMeta = statusData.bot || {};
            const g = statusData.game || {};

            // Basic status
            bot.status = botMeta.status || "IDLE";

            // Game ID
            bot.gameId = g.game_id

            if (botMeta.last_update) {
                const ms = Date.parse(botMeta.last_update);
                bot.last_updated = isNaN(ms) ? null : Math.floor(ms / 1000);
            } else {
                bot.last_updated = null;
            }

            // Matchup for the grid
            bot.matchup =
                g.away_team && g.home_team
                    ? `${g.away_team} @ ${g.home_team}`
                    : null;

            // 👉 Full team display name for the "Team" column
            bot.team_display =
                TEAM_NAME_MAP[bot.slug.toUpperCase()] ||
                TEAM_NAME_MAP[g.home_team] ||
                TEAM_NAME_MAP[g.away_team] ||
                bot.slug.toUpperCase();


            // 👉 Score: only show once the game is not FUT
            if (
                g.away_score != null &&
                g.home_score != null &&
                g.game_state &&
                g.game_state !== "FUT"
            ) {
                bot.score = `${g.away_score} - ${g.home_score}`;
            } else {
                // Pre-game / no scores yet
                bot.score = null;
            }

            // 👉 Short game state label for the grid (period / time / final)
            bot.game_state_display = formatGameStateForGrid(g);

            const social = statusData.social || {};
            const xInfo = social.x || null;

            if (xInfo && typeof xInfo.count === "number" && typeof xInfo.content_limit === "number") {
                bot.x_limit_display = `${xInfo.count} / ${xInfo.content_limit}`;
            } else {
                bot.x_limit_display = null;
            }
        } catch (err) {
            console.error("Error loading status for", bot.slug, err);
            bot.status = "ERROR";
            bot.last_updated = null;
            bot.matchup = null;
            bot.score = null;
            bot.team_display = bot.label || bot.slug.toUpperCase();
        }
    }

}

async function initDashboard() {
    const backBtn = document.getElementById("backToBots");
    if (backBtn) {
        backBtn.addEventListener("click", () => {
            currentTeamSlug = null;

            setMainViewVisible(false);
            setBotsTableVisible(true);
            setStatusBadgeVisible(false);

            if (backBtn) backBtn.style.display = "none";

            const base = window.location.pathname;
            window.history.pushState({}, "", base);

            renderBotsGrid();
        });
    }

    await loadBots();
    renderBotsGrid();

    const xResetSpan = document.getElementById("xLimitLocalReset");
    if (xResetSpan) {
        xResetSpan.textContent = getUtcResetLocalLabel();
    }

    if (!bots || bots.length === 0) {
        setMainViewVisible(false);
        setBotsTableVisible(false);
        setStatusBadgeVisible(false);
        if (backBtn) backBtn.style.display = "none";
        return;
    }

    if (currentTeamSlug) {
        setBotsTableVisible(false);
        setMainViewVisible(true);
        setStatusBadgeVisible(true);
        if (backBtn) backBtn.style.display = "inline-flex";
        await fetchStatus();
    } else {
        setMainViewVisible(false);
        setBotsTableVisible(true);
        setStatusBadgeVisible(false);
        if (backBtn) backBtn.style.display = "none";
    }

    fetchIntervalId = setInterval(() => {
        if (currentTeamSlug) {
            fetchStatus();
        }
        renderBotsGrid();
    }, 2000);
}

document.addEventListener("DOMContentLoaded", initDashboard);
