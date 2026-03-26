// ---------- Event listeners & initialization ----------
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
