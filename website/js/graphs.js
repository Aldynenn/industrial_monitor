// ---------- Graphs (Chart.js) ----------
function scheduleGraphRedraw() {
    if (graphRedrawScheduled) return;
    graphRedrawScheduled = true;
    requestAnimationFrame(() => {
        updateAllCharts();
        graphRedrawScheduled = false;
    });
}

function ensureGraphDefinitions() {
    if (!Array.isArray(visualizationPrefs.graphs)) {
        visualizationPrefs.graphs = [];
    }
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
    graphState.sweepStart = null;
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

    // Initialize or reset sweep when 10s window is exceeded
    if (graphState.sweepStart === null) {
        graphState.sweepStart = now;
    } else if (now - graphState.sweepStart >= graphState.sweepDuration) {
        graphState.sweepStart = now;
        // Clear all history to restart from the left
        for (const key of Object.keys(graphState.history)) {
            graphState.history[key] = [];
        }
    }

    let appended = false;
    const elapsed = (now - graphState.sweepStart) / 1000; // seconds into sweep

    const flattened = flattenData(data);
    for (const item of flattened) {
        if (!selected.has(item.fieldKey)) continue;
        let numericValue = null;
        if (typeof item.value === "number") numericValue = item.value;
        if (typeof item.value === "boolean") numericValue = item.value ? 1 : 0;
        if (numericValue === null) continue;
        if (!graphState.history[item.fieldKey]) graphState.history[item.fieldKey] = [];
        graphState.history[item.fieldKey].push({ t: elapsed, v: numericValue });
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

function destroyAllCharts() {
    for (const id of Object.keys(chartInstances)) {
        if (chartInstances[id]) {
            chartInstances[id].destroy();
            delete chartInstances[id];
        }
    }
}

function createChartInstance(canvas, graph, graphIndex) {
    const ctx = canvas.getContext("2d");
    const chart = new Chart(ctx, {
        type: "line",
        data: { datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: "index",
                intersect: false,
            },
            scales: {
                x: {
                    type: "linear",
                    min: 0,
                    max: graphState.sweepDuration / 1000,
                    title: {
                        display: true,
                        text: "Time (s)",
                        color: "#888",
                    },
                    grid: { color: "#2a2d3a" },
                    ticks: { color: "#888", maxRotation: 0, autoSkipPadding: 20 },
                    border: { color: "#2a2d3a" },
                },
                y: {
                    grid: { color: "#2a2d3a" },
                    ticks: { color: "#888" },
                    border: { color: "#2a2d3a" },
                },
            },
            plugins: {
                legend: {
                    display: true,
                    position: "top",
                    labels: {
                        color: "#cfd3dd",
                        usePointStyle: true,
                        pointStyle: "line",
                        padding: 14,
                        font: { size: 11 },
                    },
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: "#1e2130",
                    titleColor: "#cfd3dd",
                    bodyColor: "#cfd3dd",
                    borderColor: "#3a3f55",
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        title: function (items) {
                            if (items.length) return `${items[0].parsed.x.toFixed(2)}s`;
                            return "";
                        },
                        label: function (context) {
                            const v = context.parsed.y;
                            return `${context.dataset.label}: ${v % 1 === 0 ? v : v.toFixed(3)}`;
                        },
                    },
                },
                zoom: {
                    pan: {
                        enabled: true,
                        mode: "x",
                    },
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: "x",
                    },
                },
            },
        },
    });

    chartInstances[graph.id] = chart;
    return chart;
}

function renderGraphs(data) {
    ensureGraphDefinitions();

    const panel = document.getElementById("graph-panel");
    const list = document.getElementById("graph-list");
    if (!list) return;

    destroyAllCharts();
    list.innerHTML = "";

    if (!visualizationPrefs.graphs.length) {
        if (panel) {
            const hint = document.createElement("p");
            hint.className = "graph-empty-hint";
            hint.textContent = role === "admin"
                ? "No graphs configured. Use the Graph Configuration panel in Settings to add graphs."
                : "No graphs have been configured for your account. Contact an administrator.";
            list.appendChild(hint);
        }
        return;
    }

    visualizationPrefs.graphs.forEach((graph, graphIdx) => {
        const card = document.createElement("article");
        card.className = "graph-card";
        card.dataset.graphId = graph.id;

        const header = document.createElement("div");
        header.className = "graph-card-header";

        const titleEl = document.createElement("span");
        titleEl.className = "graph-title-label";
        titleEl.textContent = graph.name || `Graph ${graphIdx + 1}`;

        const headerBtns = document.createElement("div");
        headerBtns.className = "graph-card-header-btns";

        const resetZoomBtn = document.createElement("button");
        resetZoomBtn.type = "button";
        resetZoomBtn.className = "reset-zoom-btn";
        resetZoomBtn.textContent = "Reset Zoom";
        resetZoomBtn.addEventListener("click", () => {
            const chart = chartInstances[graph.id];
            if (chart) chart.resetZoom();
        });

        headerBtns.appendChild(resetZoomBtn);
        header.appendChild(titleEl);
        header.appendChild(headerBtns);

        const fieldList = document.createElement("div");
        fieldList.className = "graph-field-list";
        if (graph.fieldKeys && graph.fieldKeys.length) {
            fieldList.textContent = graph.fieldKeys.join(", ");
        } else {
            fieldList.textContent = "No fields assigned";
        }

        const summary = document.createElement("div");
        summary.className = "graph-summary";
        summary.id = `graph-summary-${graph.id}`;

        const canvasWrap = document.createElement("div");
        canvasWrap.className = "graph-canvas-wrap";

        const canvas = document.createElement("canvas");
        canvas.id = `graph-canvas-${graph.id}`;

        canvasWrap.appendChild(canvas);

        card.appendChild(header);
        card.appendChild(fieldList);
        card.appendChild(summary);
        card.appendChild(canvasWrap);
        list.appendChild(card);

        createChartInstance(canvas, graph, graphIdx);
    });

    updateAllCharts();
}

function updateChartData(graph, graphIndex) {
    const chart = chartInstances[graph.id];
    if (!chart) return;

    const summary = document.getElementById(`graph-summary-${graph.id}`);

    const selected = (graph.fieldKeys || []).filter(
        (k) => Array.isArray(graphState.history[k]) && graphState.history[k].length
    );

    if (!selected.length) {
        if (summary) summary.textContent = "No fields selected or no samples yet";
        chart.data.datasets = [];
        chart.update("none");
        return;
    }

    if (summary) summary.textContent = `${selected.length} field(s) plotted`;

    chart.data.datasets = selected.map((fieldKey, idx) => {
        const color = getSeriesColor(fieldKey, graphIndex + idx);
        return {
            label: fieldKey,
            data: graphState.history[fieldKey].map((p) => ({ x: p.t, y: p.v })),
            borderColor: color,
            backgroundColor: color + "20",
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.3,
            fill: false,
        };
    });

    chart.update("none");
}

function updateAllCharts() {
    ensureGraphDefinitions();
    visualizationPrefs.graphs.forEach((graph, idx) => updateChartData(graph, idx));
}

function drawAllGraphs() {
    updateAllCharts();
}
