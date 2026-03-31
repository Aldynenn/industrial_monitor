// ---------- Sidebar ----------
function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebar-overlay");
    const isOpen = sidebar.classList.contains("open");
    sidebar.classList.toggle("open", !isOpen);
    overlay.classList.toggle("hidden", isOpen);
}

function showLoginPanel(show) {
    const panel = document.getElementById("login-panel");
    if (panel) panel.classList.toggle("hidden", !show);
}

function clearLoginInputs() {
    const password = document.getElementById("ws-password");
    const username = document.getElementById("ws-username");
    if (password) password.value = "";
    if (username) username.value = "";
}

function showAdminPanel(show) {
    const panel = document.getElementById("admin-details");
    if (panel) panel.classList.toggle("hidden", !show);
    const graphPanel = document.getElementById("admin-graph-details");
    if (graphPanel) graphPanel.classList.toggle("hidden", !show);
}
