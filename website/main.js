// ---------- Configuration ----------
// Known value→max pairings for sliders
const SLIDER_PAIRS = {
    "ET": "PT",   // Timer:   elapsed time / preset time
    "CV": "PV",   // Counter: current value / preset value
};

let ws = null;
let messageCount = 0;
let uiBuilt = false;

// ---------- WebSocket ----------
function toggleConnection() {
    if (ws && ws.readyState <= WebSocket.OPEN) {
        ws.close();
    } else {
        connect();
    }
}

function connect() {
    const url = document.getElementById("ws-url").value.trim();
    if (!url) return;

    log(`Connecting to ${url}…`, "info");
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
        setConnected(true);
        log("Connection established", "info");
        messageCount = 0;
    });

    ws.addEventListener("message", (event) => {
        messageCount++;
        try {
            const data = JSON.parse(event.data);
            updateUI(data);
        } catch (e) {
            log(`Bad message: ${e.message}`, "error");
        }
    });

    ws.addEventListener("close", () => {
        setConnected(false);
        log("Connection closed", "info");
    });

    ws.addEventListener("error", () => {
        log("WebSocket error", "error");
    });
}

// ---------- Build DOM dynamically from first message ----------
function formatName(name) {
    return name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function isPaired(key, fields) {
    if (SLIDER_PAIRS[key] && fields[SLIDER_PAIRS[key]] !== undefined) return true;
    for (const [valKey, maxKey] of Object.entries(SLIDER_PAIRS)) {
        if (key === maxKey && fields[valKey] !== undefined) return true;
    }
    return false;
}

function buildUI(data) {
    const container = document.getElementById("data-container");
    container.innerHTML = "";

    for (const [dbName, fields] of Object.entries(data)) {
        const section = document.createElement("section");
        section.className = "db-section";

        const title = document.createElement("h2");
        title.className = "db-title";
        title.textContent = formatName(dbName);
        section.appendChild(title);

        const boolKeys = [];
        const numericKeys = [];
        for (const [key, value] of Object.entries(fields)) {
            if (typeof value === "boolean") boolKeys.push(key);
            else if (typeof value === "number") numericKeys.push(key);
        }

        // Bool cards
        if (boolKeys.length) {
            const grid = document.createElement("div");
            grid.className = "bool-grid";
            boolKeys.forEach(key => {
                const val = fields[key];
                const card = document.createElement("div");
                card.className = `bool-card ${val ? "active" : ""}`;
                card.id = `bool-${dbName}-${key}`;
                card.innerHTML = `
                    <div class="label">${key}</div>
                    <div class="bool-value ${val ? "is-true" : "is-false"}"
                         id="bval-${dbName}-${key}">${val ? "true" : "false"}</div>
                `;
                grid.appendChild(card);
            });
            section.appendChild(grid);
        }

        // Paired sliders
        const pairedKeys = new Set();
        const sliderWrap = document.createElement("div");
        sliderWrap.className = "slider-grid";
        let hasSliders = false;

        for (const [valKey, maxKey] of Object.entries(SLIDER_PAIRS)) {
            if (fields[valKey] !== undefined && fields[maxKey] !== undefined) {
                pairedKeys.add(valKey);
                pairedKeys.add(maxKey);
                hasSliders = true;
                const curVal = Number(fields[valKey]);
                const maxVal = Number(fields[maxKey]);
                const card = document.createElement("div");
                card.className = "slider-card";
                card.innerHTML = `
                    <div class="label">${valKey} / ${maxKey}</div>
                    <input type="range" class="data-slider" id="slider-${dbName}-${valKey}"
                           min="0" max="${maxVal}" value="${curVal}" disabled />
                    <div class="slider-info">
                        <span class="slider-value" id="sval-${dbName}-${valKey}">${curVal.toLocaleString()}</span>
                        <span class="slider-sep">/</span>
                        <span class="slider-max" id="smax-${dbName}-${valKey}">${maxVal.toLocaleString()}</span>
                    </div>
                `;
                sliderWrap.appendChild(card);
            }
        }
        if (hasSliders) section.appendChild(sliderWrap);

        // Standalone numerics
        const standaloneKeys = numericKeys.filter(k => !pairedKeys.has(k));
        if (standaloneKeys.length) {
            const numWrap = document.createElement("div");
            numWrap.className = "numeric-grid";
            standaloneKeys.forEach(key => {
                const card = document.createElement("div");
                card.className = "numeric-card";
                card.innerHTML = `
                    <div class="label">${key}</div>
                    <div class="numeric-value" id="nval-${dbName}-${key}">${Number(fields[key]).toLocaleString()}</div>
                `;
                numWrap.appendChild(card);
            });
            section.appendChild(numWrap);
        }

        container.appendChild(section);
    }

    uiBuilt = true;
}

// ---------- UI Updates ----------
function updateUI(data) {
    if (!uiBuilt) buildUI(data);

    for (const [dbName, fields] of Object.entries(data)) {
        // Booleans
        for (const [key, value] of Object.entries(fields)) {
            if (typeof value !== "boolean") continue;
            const el = document.getElementById(`bval-${dbName}-${key}`);
            const card = document.getElementById(`bool-${dbName}-${key}`);
            if (el) {
                el.textContent = value ? "true" : "false";
                el.className = `bool-value ${value ? "is-true" : "is-false"}`;
            }
            if (card) card.className = `bool-card ${value ? "active" : ""}`;
        }

        // Paired sliders
        for (const [valKey, maxKey] of Object.entries(SLIDER_PAIRS)) {
            if (fields[valKey] === undefined || fields[maxKey] === undefined) continue;
            const slider = document.getElementById(`slider-${dbName}-${valKey}`);
            if (!slider) continue;
            slider.max = Number(fields[maxKey]);
            slider.value = Number(fields[valKey]);
            const valEl = document.getElementById(`sval-${dbName}-${valKey}`);
            const maxEl = document.getElementById(`smax-${dbName}-${valKey}`);
            if (valEl) valEl.textContent = Number(fields[valKey]).toLocaleString();
            if (maxEl) maxEl.textContent = Number(fields[maxKey]).toLocaleString();
        }

        // Standalone numerics
        for (const [key, value] of Object.entries(fields)) {
            if (typeof value !== "number" || isPaired(key, fields)) continue;
            const el = document.getElementById(`nval-${dbName}-${key}`);
            if (el) el.textContent = Number(value).toLocaleString();
        }
    }
}

function setConnected(connected) {
    const el = document.getElementById("connection-status");
    const text = document.getElementById("status-text");
    const btn = document.getElementById("connect-btn");
    if (connected) {
        el.classList.add("connected");
        text.textContent = "Connected";
        btn.textContent = "Disconnect";
        btn.classList.add("disconnect");
    } else {
        el.classList.remove("connected");
        text.textContent = "Disconnected";
        btn.textContent = "Connect";
        btn.classList.remove("disconnect");
    }
}

// ---------- Log ----------
const logEl = document.getElementById("log");
function log(msg, cls = "") {
    const ts = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = `entry ${cls}`;
    entry.textContent = `[${ts}] ${msg}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
    // Keep last 200 entries
    while (logEl.children.length > 200) logEl.removeChild(logEl.firstChild);
}