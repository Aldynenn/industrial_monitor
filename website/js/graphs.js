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
                    type: "time",
                    time: {
                        tooltipFormat: "HH:mm:ss",
                        displayFormats: {
                            second: "HH:mm:ss",
                            minute: "HH:mm",
                            hour: "HH:mm",
                        },
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

    const list = document.getElementById("graph-list");
    if (!list) return;

    destroyAllCharts();
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

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "remove-graph-btn";
        removeBtn.textContent = "Remove";
        removeBtn.disabled = visualizationPrefs.graphs.length === 1;
        removeBtn.addEventListener("click", () => {
            if (chartInstances[graph.id]) {
                chartInstances[graph.id].destroy();
                delete chartInstances[graph.id];
            }
            visualizationPrefs.graphs = visualizationPrefs.graphs.filter((g) => g.id !== graph.id);
            ensureGraphDefinitions();
            pruneGraphHistory();
            saveVisualizationPrefs();
            renderGraphs(latestData);
            scheduleGraphRedraw();
        });

        headerBtns.appendChild(resetZoomBtn);
        headerBtns.appendChild(removeBtn);
        header.appendChild(titleInput);
        header.appendChild(headerBtns);

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

        const canvasWrap = document.createElement("div");
        canvasWrap.className = "graph-canvas-wrap";

        const canvas = document.createElement("canvas");
        canvas.id = `graph-canvas-${graph.id}`;

        canvasWrap.appendChild(canvas);

        card.appendChild(header);
        card.appendChild(controls);
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

function addGraph() {
    ensureGraphDefinitions();
    visualizationPrefs.graphs.push(createGraphDefinition(`Graph ${visualizationPrefs.graphs.length + 1}`));
    saveVisualizationPrefs();
    renderGraphs(latestData);
    scheduleGraphRedraw();
}
