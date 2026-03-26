// ---------- Graphs ----------
function scheduleGraphRedraw() {
    if (graphRedrawScheduled) return;
    graphRedrawScheduled = true;
    requestAnimationFrame(() => {
        drawAllGraphs();
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
