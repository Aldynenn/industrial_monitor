// ---------- Visualization preferences ----------
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

function maybeInitVisualizationSettings(data) {
    if (vizSettingsInitialized) return;
    if (!data || !Object.keys(data).length) return;
    renderVisualizationSettings(data);
    renderGraphs(data);
    vizSettingsInitialized = true;
}

// ---------- Visibility editor ----------
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
