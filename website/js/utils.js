// ---------- Utility functions ----------
function recordPacketArrival() {
    const now = performance.now();
    if (_lastPacketTime !== null) {
        _packetIntervalSum += now - _lastPacketTime;
        _packetIntervalCount++;
        const avgMs = _packetIntervalSum / _packetIntervalCount;
        const el = document.getElementById("avg-interval");
        if (el) el.textContent = avgMs < 1000 ? `${avgMs.toFixed(0)} ms` : `${(avgMs / 1000).toFixed(2)} s`;
    }
    _lastPacketTime = now;
}

function resetPacketInterval() {
    _lastPacketTime = null;
    _packetIntervalSum = 0;
    _packetIntervalCount = 0;
    const el = document.getElementById("avg-interval");
    if (el) el.textContent = "– ms";
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

// ---------- Status display ----------
function setConnected(connected) {
    const el = document.getElementById("connection-status");
    const text = document.getElementById("status-text");
    if (connected) {
        el.classList.add("connected");
        text.textContent = "Connected";
    } else {
        el.classList.remove("connected");
        text.textContent = "Disconnected";
    }
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
