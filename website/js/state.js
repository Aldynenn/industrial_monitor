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
let currentUsername = "";
let latestData = {};
let visibilityConfig = {};
let visibilityEditorInitialized = false;
let vizSettingsInitialized = false;
let graphConfigInitialized = false;

const DEFAULT_BOOL_ACTIVE_COLOR = "#22c55e";

let visualizationPrefs = {
    boolActiveColors: {},
    graphs: [],
};

// Admin graph management state
let adminUserList = [];
let adminSelectedUser = "";
let adminEditingPrefs = { graphs: [], boolActiveColors: {} };

// Admin visibility management state
let adminVisSelectedUser = "";
let adminVisEditingConfig = {};

const graphState = {
    history: {},
    maxPoints: 500,
    sweepStart: null,
    sweepDuration: 10000, // 10 seconds in ms
};

const chartInstances = {};

let graphRedrawScheduled = false;

// ---------- Reconnect state ----------
let _reconnectTimer = null;
let _reconnectDelay = 0;
const _RECONNECT_BASE_MS = 1000;
const _RECONNECT_MAX_MS = 30000;
let _wasAuthenticated = false;   // true if we had a successful session before disconnect
let _manualDisconnect = false;   // true when user clicks Disconnect

// ---------- Packet interval tracking ----------
let _lastPacketTime = null;
let _packetIntervalSum = 0;
let _packetIntervalCount = 0;
