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

const chartInstances = {};

let graphRedrawScheduled = false;

// ---------- Packet interval tracking ----------
let _lastPacketTime = null;
let _packetIntervalSum = 0;
let _packetIntervalCount = 0;
