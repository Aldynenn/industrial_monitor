// ---------- Event listeners & initialization ----------
document.getElementById("save-visibility-btn")?.addEventListener("click", saveVisibilityConfig);
document.getElementById("clear-graph-btn")?.addEventListener("click", () => {
    clearGraphHistory();
    scheduleGraphRedraw();
});
document.getElementById("admin-add-graph-btn")?.addEventListener("click", adminAddGraph);
document.getElementById("admin-save-graphs-btn")?.addEventListener("click", adminSaveGraphs);
window.addEventListener("resize", () => {
    scheduleGraphRedraw();
});

setAuthenticated(false, "Not authenticated");
setRole("-");
drawAllGraphs();
