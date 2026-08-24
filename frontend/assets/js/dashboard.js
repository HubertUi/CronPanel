/* Dashboard page: current user + system health. */

(async function () {
    let currentUser;
    try {
        currentUser = await Auth.requireAuthentication();
    } catch (error) {
        return; /* requireAuthentication already redirected */
    }

    document.getElementById("user-name").textContent = currentUser.username;
    document.getElementById("user-role").textContent = currentUser.role;

    const statusElement = document.getElementById("system-status");
    const versionElement = document.getElementById("system-version");
    const databaseElement = document.getElementById("database-status");

    try {
        const health = await Api.get("/api/health");

        const healthy = health.status === "ok";
        statusElement.textContent = healthy ? "Operativo" : "Degradado";
        statusElement.className = "status-value " + (healthy ? "status-ok" : "status-error");

        versionElement.textContent = health.version;

        const dbOk = health.database === "ok";
        databaseElement.textContent = dbOk ? "Conectada" : "Sin conexión";
        databaseElement.className = "status-value " + (dbOk ? "status-ok" : "status-error");
    } catch (error) {
        statusElement.textContent = "Sin respuesta";
        statusElement.className = "status-value status-error";
    }

    document.getElementById("logout-button").addEventListener("click", function () {
        Auth.logout();
    });
})();
