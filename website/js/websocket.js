// ---------- WebSocket ----------
function cancelReconnect() {
    if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
    }
    _reconnectDelay = 0;
    hideToast();
}

function scheduleReconnect() {
    if (_manualDisconnect) return;
    _reconnectDelay = _reconnectDelay ? Math.min(_reconnectDelay * 2, _RECONNECT_MAX_MS) : _RECONNECT_BASE_MS;
    const secs = (_reconnectDelay / 1000).toFixed(0);
    showToast(`Connection lost — reconnecting in ${secs}s…`);
    log(`Reconnecting in ${secs}s…`, "info");
    _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null;
        connect();
    }, _reconnectDelay);
}

function toggleConnection() {
    if (ws && ws.readyState <= WebSocket.OPEN) {
        _manualDisconnect = true;
        cancelReconnect();
        ws.close();
    } else {
        _manualDisconnect = false;
        cancelReconnect();
        connect();
    }
}

function connect() {
    const url = document.getElementById("ws-url").value.trim();
    if (!url) return;

    log(`Connecting to ${url}…`, "info");
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
        cancelReconnect();
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
        const hadSession = isAuthenticated || _wasAuthenticated;
        setConnected(false);
        setAuthenticated(false, "Not authenticated");
        setRole("-");
        currentUsername = "";
        showAdminPanel(false);
        showLoginPanel(true);
        document.getElementById("disconnect-btn")?.classList.add("hidden");
        document.getElementById("sidebar-toggle-btn")?.classList.add("hidden");
        document.getElementById("avg-interval-label")?.classList.add("hidden");
        resetPacketInterval();
        // Close sidebar on disconnect
        document.getElementById("sidebar")?.classList.remove("open");
        document.getElementById("sidebar-overlay")?.classList.add("hidden");
        clearRenderedData(true);
        log("Connection closed", "info");
        // Auto-reconnect if the connection was not manually closed
        if (!_manualDisconnect && hadSession) {
            scheduleReconnect();
        }
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
            _wasAuthenticated = true;
            _reconnectDelay = 0;
            currentUsername = document.getElementById("ws-username").value.trim();
            setAuthenticated(true, "Authenticated");
            setRole(payload.role || "user");
            showAdminPanel((payload.role || "user") === "admin");
            showLoginPanel(false);
            clearLoginInputs();
            document.getElementById("disconnect-btn")?.classList.remove("hidden");
            document.getElementById("avg-interval-label")?.classList.remove("hidden");
            if ((payload.role || "user") === "admin") {
                document.getElementById("sidebar-toggle-btn")?.classList.remove("hidden");
                requestUserList();
            }
            requestVisibilityConfig();
            log(payload.message || "Authentication successful", "info");
        } else {
            currentUsername = "";
            setAuthenticated(false, payload.message || "Authentication failed");
            setRole("-");
            showAdminPanel(false);
            log(payload.message || "Authentication failed", "error");
        }
        return;
    }

    if (payload.type === "visibility_config") {
        applyVisibilityConfig(payload);
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

    if (payload.type === "graphs_config") {
        graphConfigInitialized = true;
        applyGraphConfig(payload);
        log(`Graph config received for '${payload.username || "self"}'`, "info");
        return;
    }

    if (payload.type === "graphs_set") {
        log(payload.message || "Graphs saved", payload.ok ? "info" : "error");
        return;
    }

    if (payload.type === "users_list") {
        applyUserList(payload.usernames);
        renderVisibilityUserSelector();
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
        recordPacketArrival();
        const incoming = payload.data || {};
        if (payload.full) {
            // Full snapshot — replace state entirely
            latestData = incoming;
        } else {
            // Delta — merge changed fields into existing state
            for (const [dbName, fields] of Object.entries(incoming)) {
                if (!fields || typeof fields !== "object") continue;
                if (!latestData[dbName] || typeof latestData[dbName] !== "object") {
                    latestData[dbName] = {};
                }
                Object.assign(latestData[dbName], fields);
            }
        }
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
        recordPacketArrival();
        latestData = payload;
        maybeInitVisualizationSettings(latestData);
        updateUI(payload);
        maybeInitVisibilityEditor(latestData, visibilityConfig);
        if (updateGraphHistory(latestData)) {
            scheduleGraphRedraw();
        }
    }
}

function requestVisibilityConfig(username) {
    if (!ws || ws.readyState !== WebSocket.OPEN || !isAuthenticated) return;
    const msg = { type: "visibility_get" };
    if (username) msg.username = username;
    ws.send(JSON.stringify(msg));
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

        adminVisSelectedUser = "";
        adminVisEditingConfig = {};
        const visUserSelect = document.getElementById("visibility-user-select");
        if (visUserSelect) visUserSelect.innerHTML = "";

        graphConfigInitialized = false;
        adminUserList = [];
        adminSelectedUser = "";
        adminEditingPrefs = { graphs: [], boolActiveColors: {} };
        const adminGraphEditor = document.getElementById("admin-graph-editor");
        if (adminGraphEditor) adminGraphEditor.innerHTML = "";
        const adminUserSelect = document.getElementById("admin-graph-user-select");
        if (adminUserSelect) adminUserSelect.innerHTML = "";
    }

    vizSettingsInitialized = false;
    const viz = document.getElementById("viz-settings");
    if (viz) viz.innerHTML = "";

    const graphList = document.getElementById("graph-list");
    if (graphList) {
        destroyAllCharts();
        graphList.innerHTML = "";
    }

    clearGraphHistory();
    drawAllGraphs();
}
