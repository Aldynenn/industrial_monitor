// ---------- Configuration ----------
// Known value→max pairings for sliders
const SLIDER_PAIRS = {
    "ET": "PT",   // Timer:   elapsed time / preset time
    "CV": "PV",   // Counter: current value / preset value
};

let ws = null;
let uiBuilt = false;
let isAuthenticated = false;
let role = "user";
let latestData = {};
let visibilityConfig = {};
let visibilityEditorInitialized = false;
let vizSettingsInitialized = false;

const LOCAL_PREFS_KEY = "industrial_monitor_visualization";
const DEFAULT_BOOL_ACTIVE_COLOR = "#22c55e";

let visualizationPrefs = {
    boolActiveColors: {},
    graphs: [],
};

const graphState = {
    history: {},
    maxPoints: 240,
};

let graphRedrawScheduled = false;

function scheduleGraphRedraw() {
    if (graphRedrawScheduled) return;
    graphRedrawScheduled = true;
    requestAnimationFrame(() => {
        drawAllGraphs();
        graphRedrawScheduled = false;
    });
}

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
        setAuthenticated(false, "Not authenticated");
        log("Connection established", "info");
        authenticateClient();
    });

    ws.addEventListener("message", (event) => {
        try {
            const payload = JSON.parse(event.data);
            handleMessage(payload);
        } catch (e) {
            log(`Bad message: ${e.message}`, "error");
        }
    });

    ws.addEventListener("close", () => {
        setConnected(false);
        setAuthenticated(false, "Not authenticated");
        setRole("-");
        showAdminPanel(false);
        clearRenderedData(true);
        log("Connection closed", "info");
    });

    ws.addEventListener("error", () => {
        log("WebSocket error", "error");
    });
}

function authenticateClient() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        log("Connect first before authenticating", "error");
        return;
    }

    const username = document.getElementById("ws-username").value.trim();
    const password = document.getElementById("ws-password").value;
    if (!username || !password) {
        setAuthenticated(false, "Username/password required");
        return;
    }

    ws.send(JSON.stringify({
        type: "auth",
        username,
        password,
    }));
    log(`Auth request sent for '${username}'`, "info");
}

function handleMessage(payload) {
    if (!payload || typeof payload !== "object") {
        log("Ignored invalid message payload", "error");
        return;
    }

    if (payload.type === "auth_required") {
        log(payload.message || "Server requires authentication", "info");
        return;
    }

    if (payload.type === "auth") {
        if (payload.ok) {
            setAuthenticated(true, "Authenticated");
            setRole(payload.role || "user");
            showAdminPanel((payload.role || "user") === "admin");
            requestVisibilityConfig();
            log(payload.message || "Authentication successful", "info");
        } else {
            setAuthenticated(false, payload.message || "Authentication failed");
            setRole("-");
            showAdminPanel(false);
            log(payload.message || "Authentication failed", "error");
        }
        return;
    }

    if (payload.type === "visibility_config") {
        visibilityConfig = payload.config && typeof payload.config === "object" ? payload.config : {};
        maybeInitVisibilityEditor(latestData, visibilityConfig);
        log("Visibility configuration updated", "info");
        return;
    }

    if (payload.type === "visibility_set") {
        if (payload.ok) {
            clearRenderedData(false);
        }
        log(payload.message || "Visibility updated", payload.ok ? "info" : "error");
        return;
    }

    if (payload.type === "error") {
        log(payload.message || "Server error", "error");
        return;
    }

    if (payload.type === "plc_data") {
        if (!isAuthenticated) {
            log("Received data before authentication; ignoring", "error");
            return;
        }
        latestData = payload.data || {};
        maybeInitVisualizationSettings(latestData);
        updateUI(latestData);
        maybeInitVisibilityEditor(latestData, visibilityConfig);
        if (updateGraphHistory(latestData)) {
            scheduleGraphRedraw();
        }
        return;
    }

    // Backward compatibility for legacy server that sends raw data objects.
    if (isAuthenticated) {
        latestData = payload;
        maybeInitVisualizationSettings(latestData);
        updateUI(payload);
        maybeInitVisibilityEditor(latestData, visibilityConfig);
        if (updateGraphHistory(latestData)) {
            scheduleGraphRedraw();
        }
    }
}

function requestVisibilityConfig() {
    if (!ws || ws.readyState !== WebSocket.OPEN || !isAuthenticated) return;
    ws.send(JSON.stringify({ type: "visibility_get" }));
}

function clearRenderedData(clearEditor = false) {
    uiBuilt = false;
    latestData = {};

    const container = document.getElementById("data-container");
    if (container) container.innerHTML = "";

    if (clearEditor) {
        visibilityEditorInitialized = false;
        const editor = document.getElementById("visibility-editor");
        if (editor) editor.innerHTML = "";
    }

    vizSettingsInitialized = false;
    const viz = document.getElementById("viz-settings");
    if (viz) viz.innerHTML = "";

    const graphList = document.getElementById("graph-list");
    if (graphList) graphList.innerHTML = "";

    clearGraphHistory();
    drawAllGraphs();
}

function makeFieldKey(dbName, fieldName) {
    return `${dbName}.${fieldName}`;
}

function splitFieldKey(fieldKey) {
    const idx = fieldKey.indexOf(".");
    if (idx < 0) return ["", fieldKey];
    return [fieldKey.slice(0, idx), fieldKey.slice(idx + 1)];
}

function flattenData(data) {
    const out = [];
    for (const [dbName, fields] of Object.entries(data || {})) {
        if (!fields || typeof fields !== "object") continue;
        for (const [fieldName, value] of Object.entries(fields)) {
            out.push({ dbName, fieldName, fieldKey: makeFieldKey(dbName, fieldName), value });
        }
    }
    return out;
}

function saveVisualizationPrefs() {
    try {
        localStorage.setItem(LOCAL_PREFS_KEY, JSON.stringify(visualizationPrefs));
    } catch {
        // Ignore storage failures silently.
    }
}

function loadVisualizationPrefs() {
    try {
        const raw = localStorage.getItem(LOCAL_PREFS_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return;
        visualizationPrefs.boolActiveColors = parsed.boolActiveColors && typeof parsed.boolActiveColors === "object"
            ? parsed.boolActiveColors
            : {};

        if (Array.isArray(parsed.graphs)) {
            visualizationPrefs.graphs = parsed.graphs
                .filter((g) => g && typeof g === "object")
                .map((g, idx) => ({
                    id: typeof g.id === "string" && g.id ? g.id : `graph_${idx + 1}`,
                    name: typeof g.name === "string" && g.name.trim() ? g.name.trim() : `Graph ${idx + 1}`,
                    fieldKeys: Array.isArray(g.fieldKeys) ? g.fieldKeys.filter((k) => typeof k === "string") : [],
                }));
        } else if (Array.isArray(parsed.graphFields)) {
            // Migration path from legacy single-graph format.
            visualizationPrefs.graphs = [
                {
                    id: "graph_1",
                    name: "Graph 1",
                    fieldKeys: parsed.graphFields.filter((x) => typeof x === "string"),
                },
            ];
        }
    } catch {
        // Ignore storage failures silently.
    }

    ensureGraphDefinitions();
}

function ensureGraphDefinitions() {
    if (!Array.isArray(visualizationPrefs.graphs)) {
        visualizationPrefs.graphs = [];
    }
    if (!visualizationPrefs.graphs.length) {
        visualizationPrefs.graphs.push(createGraphDefinition("Graph 1"));
    }
}

function createGraphDefinition(name) {
    return {
        id: `graph_${Date.now()}_${Math.floor(Math.random() * 100000)}`,
        name: name || `Graph ${visualizationPrefs.graphs.length + 1}`,
        fieldKeys: [],
    };
}

function getAllSelectedGraphFieldKeys() {
    const out = new Set();
    visualizationPrefs.graphs.forEach((g) => {
        (g.fieldKeys || []).forEach((k) => out.add(k));
    });
    return out;
}

function clearGraphHistory() {
    graphState.history = {};
}

function pruneGraphHistory() {
    const used = getAllSelectedGraphFieldKeys();
    Object.keys(graphState.history).forEach((fieldKey) => {
        if (!used.has(fieldKey)) {
            delete graphState.history[fieldKey];
        }
    });
}

function updateGraphHistory(data) {
    const now = Date.now();
    const selected = getAllSelectedGraphFieldKeys();
    if (!selected.size) return false;

    let appended = false;

    const flattened = flattenData(data);
    for (const item of flattened) {
        if (!selected.has(item.fieldKey)) continue;
        let numericValue = null;
        if (typeof item.value === "number") numericValue = item.value;
        if (typeof item.value === "boolean") numericValue = item.value ? 1 : 0;
        if (numericValue === null) continue;
        if (!graphState.history[item.fieldKey]) graphState.history[item.fieldKey] = [];
        graphState.history[item.fieldKey].push({ t: now, v: numericValue });
        appended = true;
        if (graphState.history[item.fieldKey].length > graphState.maxPoints) {
            graphState.history[item.fieldKey].shift();
        }
    }

    return appended;
}

function getSeriesColor(fieldKey, idx) {
    const [dbName, fieldName] = splitFieldKey(fieldKey);
    const configured = visualizationPrefs.boolActiveColors[fieldKey];
    if (configured) return configured;
    const palette = ["#3b82f6", "#22c55e", "#ef4444", "#f59e0b", "#14b8a6", "#eab308", "#a855f7"];
    const seed = `${dbName}.${fieldName}`.length + idx;
    return palette[seed % palette.length];
}

function renderGraphs(data) {
    ensureGraphDefinitions();

    const list = document.getElementById("graph-list");
    if (!list) return;
    list.innerHTML = "";

    const graphFields = flattenData(data).filter((f) => typeof f.value === "boolean" || typeof f.value === "number");

    visualizationPrefs.graphs.forEach((graph, graphIdx) => {
        const card = document.createElement("article");
        card.className = "graph-card";
        card.dataset.graphId = graph.id;

        const header = document.createElement("div");
        header.className = "graph-card-header";

        const titleInput = document.createElement("input");
        titleInput.className = "graph-title-input";
        titleInput.type = "text";
        titleInput.value = graph.name;
        titleInput.placeholder = `Graph ${graphIdx + 1}`;
        titleInput.addEventListener("change", () => {
            graph.name = titleInput.value.trim() || `Graph ${graphIdx + 1}`;
            saveVisualizationPrefs();
        });

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "remove-graph-btn";
        removeBtn.textContent = "Remove";
        removeBtn.disabled = visualizationPrefs.graphs.length === 1;
        removeBtn.addEventListener("click", () => {
            visualizationPrefs.graphs = visualizationPrefs.graphs.filter((g) => g.id !== graph.id);
            ensureGraphDefinitions();
            pruneGraphHistory();
            saveVisualizationPrefs();
            renderGraphs(latestData);
            scheduleGraphRedraw();
        });

        header.appendChild(titleInput);
        header.appendChild(removeBtn);

        const controls = document.createElement("div");
        controls.className = "graph-controls";

        if (!graphFields.length) {
            const row = document.createElement("div");
            row.className = "graph-control-row";
            row.textContent = "No numeric/boolean fields available";
            controls.appendChild(row);
        } else {
            graphFields.forEach((f) => {
                const row = document.createElement("label");
                row.className = "graph-control-row";

                const label = document.createElement("span");
                label.textContent = `${f.dbName}.${f.fieldName}`;

                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.checked = graph.fieldKeys.includes(f.fieldKey);
                cb.addEventListener("change", () => {
                    if (cb.checked) {
                        if (!graph.fieldKeys.includes(f.fieldKey)) {
                            graph.fieldKeys.push(f.fieldKey);
                        }
                    } else {
                        graph.fieldKeys = graph.fieldKeys.filter((k) => k !== f.fieldKey);
                    }
                    pruneGraphHistory();
                    saveVisualizationPrefs();
                    scheduleGraphRedraw();
                });

                row.appendChild(label);
                row.appendChild(cb);
                controls.appendChild(row);
            });
        }

        const summary = document.createElement("div");
        summary.className = "graph-summary";
        summary.id = `graph-summary-${graph.id}`;

        const canvas = document.createElement("canvas");
        canvas.className = "graph-canvas";
        canvas.id = `graph-canvas-${graph.id}`;
        canvas.width = 1200;
        canvas.height = 320;

        card.appendChild(header);
        card.appendChild(controls);
        card.appendChild(summary);
        card.appendChild(canvas);
        list.appendChild(card);
    });
}

function drawGraphCanvas(graph, graphIndex) {
    const canvas = document.getElementById(`graph-canvas-${graph.id}`);
    const summary = document.getElementById(`graph-summary-${graph.id}`);
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssWidth = canvas.clientWidth || 1200;
    const cssHeight = canvas.clientHeight || 320;
    canvas.width = Math.floor(cssWidth * dpr);
    canvas.height = Math.floor(cssHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, cssWidth, cssHeight);

    const selected = (graph.fieldKeys || []).filter((k) => Array.isArray(graphState.history[k]) && graphState.history[k].length);
    if (!selected.length) {
        if (summary) summary.textContent = "No fields selected or no samples yet";
        ctx.fillStyle = "#888";
        ctx.font = "13px Segoe UI";
        ctx.fillText("Select fields for this graph and wait for samples", 18, 26);
        return;
    }

    if (summary) summary.textContent = `${selected.length} field(s) plotted`;

    const left = 44;
    const top = 14;
    const right = cssWidth - 14;
    const bottom = cssHeight - 28;
    const width = right - left;
    const height = bottom - top;

    let minT = Number.POSITIVE_INFINITY;
    let maxT = Number.NEGATIVE_INFINITY;
    let minV = Number.POSITIVE_INFINITY;
    let maxV = Number.NEGATIVE_INFINITY;

    selected.forEach((fieldKey) => {
        graphState.history[fieldKey].forEach((p) => {
            if (p.t < minT) minT = p.t;
            if (p.t > maxT) maxT = p.t;
            if (p.v < minV) minV = p.v;
            if (p.v > maxV) maxV = p.v;
        });
    });

    if (!Number.isFinite(minT) || !Number.isFinite(maxT)) return;
    if (maxT === minT) maxT += 1000;
    if (maxV === minV) {
        minV -= 1;
        maxV += 1;
    }

    ctx.strokeStyle = "#2a2d3a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, top);
    ctx.lineTo(left, bottom);
    ctx.lineTo(right, bottom);
    ctx.stroke();

    ctx.fillStyle = "#888";
    ctx.font = "11px Segoe UI";
    ctx.fillText(maxV.toFixed(2), 4, top + 10);
    ctx.fillText(minV.toFixed(2), 4, bottom - 2);

    selected.forEach((fieldKey, idx) => {
        const color = getSeriesColor(fieldKey, graphIndex + idx);
        const points = graphState.history[fieldKey];
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        points.forEach((p, i) => {
            const x = left + ((p.t - minT) / (maxT - minT)) * width;
            const y = bottom - ((p.v - minV) / (maxV - minV)) * height;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        const legendY = top + 14 + idx * 14;
        if (legendY < bottom - 2) {
            ctx.fillStyle = color;
            ctx.fillRect(right - 190, legendY - 8, 10, 2);
            ctx.fillStyle = "#cfd3dd";
            ctx.font = "11px Segoe UI";
            ctx.fillText(fieldKey, right - 176, legendY - 2);
        }
    });
}

function drawAllGraphs() {
    ensureGraphDefinitions();
    visualizationPrefs.graphs.forEach((graph, idx) => drawGraphCanvas(graph, idx));
}

function addGraph() {
    ensureGraphDefinitions();
    visualizationPrefs.graphs.push(createGraphDefinition(`Graph ${visualizationPrefs.graphs.length + 1}`));
    saveVisualizationPrefs();
    renderGraphs(latestData);
    scheduleGraphRedraw();
}

function applyBoolVisualStyles(dbName, fieldName, value) {
    const fieldKey = makeFieldKey(dbName, fieldName);
    const card = document.getElementById(`bool-${dbName}-${fieldName}`);
    const el = document.getElementById(`bval-${dbName}-${fieldName}`);
    if (!card || !el) return;

    if (value) {
        const activeColor = visualizationPrefs.boolActiveColors[fieldKey] || DEFAULT_BOOL_ACTIVE_COLOR;
        card.style.borderColor = activeColor;
        el.style.color = activeColor;
    } else {
        card.style.borderColor = "";
        el.style.color = "";
    }
}

function renderVisualizationSettings(data) {
    const root = document.getElementById("viz-settings");
    if (!root) return;
    root.innerHTML = "";

    const fields = flattenData(data);
    const boolFields = fields.filter((f) => typeof f.value === "boolean");

    const boolGroup = document.createElement("div");
    boolGroup.className = "viz-group";
    boolGroup.innerHTML = "<h3>Boolean Active Colors</h3>";

    if (!boolFields.length) {
        const row = document.createElement("div");
        row.className = "viz-row";
        row.textContent = "No boolean fields available";
        boolGroup.appendChild(row);
    } else {
        boolFields.forEach((f) => {
            const row = document.createElement("label");
            row.className = "viz-row";
            const text = document.createElement("span");
            text.textContent = `${f.dbName}.${f.fieldName}`;

            const color = document.createElement("input");
            color.type = "color";
            color.value = visualizationPrefs.boolActiveColors[f.fieldKey] || DEFAULT_BOOL_ACTIVE_COLOR;
            color.addEventListener("input", () => {
                visualizationPrefs.boolActiveColors[f.fieldKey] = color.value;
                saveVisualizationPrefs();
                applyBoolVisualStyles(f.dbName, f.fieldName, Boolean(latestData?.[f.dbName]?.[f.fieldName]));
            });

            row.appendChild(text);
            row.appendChild(color);
            boolGroup.appendChild(row);
        });
    }

    root.appendChild(boolGroup);
}

function showAdminPanel(show) {
    const panel = document.getElementById("admin-panel");
    if (!panel) return;
    panel.classList.toggle("hidden", !show);
}

function maybeInitVisualizationSettings(data) {
    if (vizSettingsInitialized) return;
    if (!data || !Object.keys(data).length) return;
    renderVisualizationSettings(data);
    renderGraphs(data);
    vizSettingsInitialized = true;
}

function maybeInitVisibilityEditor(data, config) {
    if (role !== "admin" || visibilityEditorInitialized) return;
    if (!data || !Object.keys(data).length) return;
    renderVisibilityEditor(data, config);
    visibilityEditorInitialized = true;
}

function renderVisibilityEditor(data, config) {
    const root = document.getElementById("visibility-editor");
    if (!root) return;
    root.innerHTML = "";

    const dataObj = data && typeof data === "object" ? data : {};
    const configObj = config && typeof config === "object" ? config : {};
    const dbNames = new Set([...Object.keys(dataObj), ...Object.keys(configObj)]);

    for (const dbName of dbNames) {
        const fields = dataObj[dbName];
        const dbConfig = configObj[dbName] && typeof configObj[dbName] === "object" ? configObj[dbName] : {};
        const dataFieldNames = fields && typeof fields === "object" ? Object.keys(fields) : [];
        const fieldNames = Array.from(new Set([...dataFieldNames, ...Object.keys(dbConfig)]));
        if (!fieldNames.length) continue;

        const card = document.createElement("div");
        card.className = "visibility-db";

        const title = document.createElement("h3");
        title.className = "visibility-db-title";
        title.textContent = formatName(dbName);
        card.appendChild(title);

        for (const fieldName of fieldNames) {
            const row = document.createElement("label");
            row.className = "visibility-field";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.dataset.db = dbName;
            checkbox.dataset.field = fieldName;
            checkbox.checked = dbConfig[fieldName] !== false;

            const text = document.createElement("span");
            text.textContent = fieldName;

            row.appendChild(checkbox);
            row.appendChild(text);
            card.appendChild(row);
        }

        root.appendChild(card);
    }
}

function saveVisibilityConfig() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        log("Connect first before saving visibility", "error");
        return;
    }
    if (!isAuthenticated || role !== "admin") {
        log("Only admins can save visibility settings", "error");
        return;
    }

    const nextConfig = {};
    document.querySelectorAll("#visibility-editor input[type='checkbox']").forEach((input) => {
        const db = input.dataset.db;
        const field = input.dataset.field;
        if (!db || !field) return;
        if (!nextConfig[db]) nextConfig[db] = {};
        nextConfig[db][field] = Boolean(input.checked);
    });

    ws.send(JSON.stringify({ type: "visibility_set", config: nextConfig }));
}

// ---------- Build DOM dynamically from first message ----------
function formatName(name) {
    return name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function formatNumericValue(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return String(value);
    if (Number.isInteger(num)) return num.toLocaleString();
    return num.toFixed(6);
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
                applyBoolVisualStyles(dbName, key, val);
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
                        <span class="slider-value" id="sval-${dbName}-${valKey}">${formatNumericValue(curVal)}</span>
                        <span class="slider-sep">/</span>
                        <span class="slider-max" id="smax-${dbName}-${valKey}">${formatNumericValue(maxVal)}</span>
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
                    <div class="numeric-value" id="nval-${dbName}-${key}">${formatNumericValue(fields[key])}</div>
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
            applyBoolVisualStyles(dbName, key, value);
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
            if (valEl) valEl.textContent = formatNumericValue(fields[valKey]);
            if (maxEl) maxEl.textContent = formatNumericValue(fields[maxKey]);
        }

        // Standalone numerics
        for (const [key, value] of Object.entries(fields)) {
            if (typeof value !== "number" || isPaired(key, fields)) continue;
            const el = document.getElementById(`nval-${dbName}-${key}`);
            if (el) el.textContent = formatNumericValue(value);
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

function setAuthenticated(ok, message) {
    isAuthenticated = ok;
    const el = document.getElementById("auth-status");
    el.textContent = message || (ok ? "Authenticated" : "Not authenticated");
    el.classList.remove("ok", "fail");
    el.classList.add(ok ? "ok" : "fail");
    if (!ok) {
        visibilityEditorInitialized = false;
        const editor = document.getElementById("visibility-editor");
        if (editor) editor.innerHTML = "";
    }
    setConnected(ok);
}

function setRole(value) {
    role = String(value || "-").toLowerCase();
    const roleEl = document.getElementById("role-status");
    if (roleEl) {
        roleEl.textContent = `Role: ${value || "-"}`;
    }
}

document.getElementById("save-visibility-btn")?.addEventListener("click", saveVisibilityConfig);
document.getElementById("clear-graph-btn")?.addEventListener("click", () => {
    clearGraphHistory();
    scheduleGraphRedraw();
});
document.getElementById("add-graph-btn")?.addEventListener("click", addGraph);
window.addEventListener("resize", () => {
    scheduleGraphRedraw();
});

loadVisualizationPrefs();
setAuthenticated(false, "Not authenticated");
setRole("-");
drawAllGraphs();