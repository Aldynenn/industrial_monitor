// ---------- Visualization preferences (server-backed) ----------
function saveVisualizationPrefs() {
    // Admin saves via the graph management panel; this is a no-op for normal users.
    // Bool colors for the current user's own view are saved immediately.
    if (!ws || ws.readyState !== WebSocket.OPEN || !isAuthenticated) return;
    ws.send(JSON.stringify({
        type: "graphs_set",
        username: currentUsername,
        graphs: visualizationPrefs.graphs,
        boolActiveColors: visualizationPrefs.boolActiveColors,
    }));
}

function requestGraphConfig(username) {
    if (!ws || ws.readyState !== WebSocket.OPEN || !isAuthenticated) return;
    ws.send(JSON.stringify({ type: "graphs_get", username: username || "" }));
}

function requestUserList() {
    if (!ws || ws.readyState !== WebSocket.OPEN || !isAuthenticated || role !== "admin") return;
    ws.send(JSON.stringify({ type: "users_list" }));
}

function applyGraphConfig(payload) {
    const username = payload.username || "";
    const graphs = Array.isArray(payload.graphs) ? payload.graphs : [];
    const colors = payload.boolActiveColors && typeof payload.boolActiveColors === "object"
        ? payload.boolActiveColors : {};

    // Normalize graphs
    const normalized = graphs
        .filter((g) => g && typeof g === "object")
        .map((g, idx) => ({
            id: typeof g.id === "string" && g.id ? g.id : `graph_${Date.now()}_${idx}`,
            name: typeof g.name === "string" && g.name.trim() ? g.name.trim() : `Graph ${idx + 1}`,
            fieldKeys: Array.isArray(g.fieldKeys) ? g.fieldKeys.filter((k) => typeof k === "string") : [],
        }));

    if (username === currentUsername || !username) {
        // This is the logged-in user's own config
        visualizationPrefs.graphs = normalized;
        visualizationPrefs.boolActiveColors = colors;
        clearGraphHistory();
        if (latestData && Object.keys(latestData).length) {
            renderGraphs(latestData);
            scheduleGraphRedraw();
        }
    }

    // If admin is editing this user, update the admin editing pane
    if (role === "admin" && username === adminSelectedUser) {
        adminEditingPrefs = { graphs: normalized, boolActiveColors: { ...colors } };
        renderAdminGraphEditor(latestData);
    }
}

function applyUserList(usernames) {
    adminUserList = Array.isArray(usernames) ? usernames : [];
    renderAdminUserSelector();
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

            if (role !== "admin") {
                color.disabled = true;
            } else {
                color.addEventListener("input", () => {
                    visualizationPrefs.boolActiveColors[f.fieldKey] = color.value;
                    saveVisualizationPrefs();
                    applyBoolVisualStyles(f.dbName, f.fieldName, Boolean(latestData?.[f.dbName]?.[f.fieldName]));
                });
            }

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
    if (graphConfigInitialized) {
        renderGraphs(data);
    }
    vizSettingsInitialized = true;
}

// ---------- Admin graph management ----------
function renderAdminUserSelector() {
    const container = document.getElementById("admin-graph-user-select");
    if (!container) return;
    container.innerHTML = "";

    const label = document.createElement("label");
    label.textContent = "User: ";
    label.className = "admin-graph-label";

    const select = document.createElement("select");
    select.id = "admin-graph-user-dropdown";
    select.className = "admin-graph-dropdown";

    adminUserList.forEach((u) => {
        const opt = document.createElement("option");
        opt.value = u;
        opt.textContent = u;
        if (u === adminSelectedUser) opt.selected = true;
        select.appendChild(opt);
    });

    select.addEventListener("change", () => {
        adminSelectedUser = select.value;
        if (adminSelectedUser) {
            requestGraphConfig(adminSelectedUser);
        }
    });

    container.appendChild(label);
    container.appendChild(select);

    // Auto-select first user if none selected
    if (!adminSelectedUser && adminUserList.length) {
        adminSelectedUser = adminUserList[0];
        requestGraphConfig(adminSelectedUser);
    }
}

function renderAdminGraphEditor(data) {
    const root = document.getElementById("admin-graph-editor");
    if (!root) return;
    root.innerHTML = "";

    if (!adminSelectedUser) {
        root.textContent = "Select a user above.";
        return;
    }

    const graphFields = flattenData(data || {}).filter(
        (f) => typeof f.value === "boolean" || typeof f.value === "number"
    );

    if (!adminEditingPrefs.graphs.length) {
        const hint = document.createElement("p");
        hint.className = "admin-help";
        hint.textContent = "No graphs configured for this user. Click 'Add Graph' to create one.";
        root.appendChild(hint);
    }

    adminEditingPrefs.graphs.forEach((graph, graphIdx) => {
        const card = document.createElement("div");
        card.className = "admin-graph-card";

        const header = document.createElement("div");
        header.className = "admin-graph-card-header";

        const titleInput = document.createElement("input");
        titleInput.className = "graph-title-input";
        titleInput.type = "text";
        titleInput.value = graph.name;
        titleInput.placeholder = `Graph ${graphIdx + 1}`;
        titleInput.addEventListener("change", () => {
            graph.name = titleInput.value.trim() || `Graph ${graphIdx + 1}`;
        });

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "remove-graph-btn";
        removeBtn.textContent = "Remove";
        removeBtn.addEventListener("click", () => {
            adminEditingPrefs.graphs = adminEditingPrefs.graphs.filter((g) => g.id !== graph.id);
            renderAdminGraphEditor(data);
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
                });

                row.appendChild(label);
                row.appendChild(cb);
                controls.appendChild(row);
            });
        }

        card.appendChild(header);
        card.appendChild(controls);
        root.appendChild(card);
    });
}

function adminAddGraph() {
    const id = `graph_${Date.now()}_${Math.floor(Math.random() * 100000)}`;
    adminEditingPrefs.graphs.push({
        id: id,
        name: `Graph ${adminEditingPrefs.graphs.length + 1}`,
        fieldKeys: [],
    });
    renderAdminGraphEditor(latestData);
}

function adminSaveGraphs() {
    if (!ws || ws.readyState !== WebSocket.OPEN || !isAuthenticated || role !== "admin") {
        log("Admin privileges required to save graphs", "error");
        return;
    }
    if (!adminSelectedUser) {
        log("Select a user first", "error");
        return;
    }
    ws.send(JSON.stringify({
        type: "graphs_set",
        username: adminSelectedUser,
        graphs: adminEditingPrefs.graphs,
        boolActiveColors: adminEditingPrefs.boolActiveColors || {},
    }));
}

// ---------- Visibility editor ----------
function maybeInitVisibilityEditor(data, config) {
    if (role !== "admin" || visibilityEditorInitialized) return;
    if (!data || !Object.keys(data).length) return;
    renderVisibilityUserSelector();
    visibilityEditorInitialized = true;
}

function renderVisibilityUserSelector() {
    const container = document.getElementById("visibility-user-select");
    if (!container) return;
    container.innerHTML = "";

    const label = document.createElement("label");
    label.textContent = "User: ";
    label.className = "admin-graph-label";

    const select = document.createElement("select");
    select.id = "visibility-user-dropdown";
    select.className = "admin-graph-dropdown";

    adminUserList.forEach((u) => {
        const opt = document.createElement("option");
        opt.value = u;
        opt.textContent = u;
        if (u === adminVisSelectedUser) opt.selected = true;
        select.appendChild(opt);
    });

    select.addEventListener("change", () => {
        adminVisSelectedUser = select.value;
        if (adminVisSelectedUser) {
            requestVisibilityConfig(adminVisSelectedUser);
        }
    });

    container.appendChild(label);
    container.appendChild(select);

    // Auto-select first user if none selected
    if (!adminVisSelectedUser && adminUserList.length) {
        adminVisSelectedUser = adminUserList[0];
        requestVisibilityConfig(adminVisSelectedUser);
    }
}

function applyVisibilityConfig(payload) {
    const username = payload.username || "";
    const config = payload.config && typeof payload.config === "object" ? payload.config : {};

    // If this is for the logged-in user's own view, store it
    if (username === currentUsername || !username) {
        visibilityConfig = config;
    }

    // If admin is editing this user, update the admin editing pane
    if (role === "admin" && username === adminVisSelectedUser) {
        adminVisEditingConfig = { ...config };
        renderVisibilityEditor(latestData, adminVisEditingConfig);
    }
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
    if (!adminVisSelectedUser) {
        log("Select a user first", "error");
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

    ws.send(JSON.stringify({ type: "visibility_set", username: adminVisSelectedUser, config: nextConfig }));
}
