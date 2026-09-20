/* Ejecuciones page: history of every run, read-only. */

(function () {
    "use strict";

    let currentUser = null;

    const statusLabels = {
        running: "En ejecución",
        success: "Éxito",
        failed: "Fallida",
        timed_out: "Agotó el tiempo",
    };

    const statusClass = {
        running: "status-running",
        success: "status-success",
        failed: "status-failed",
        timed_out: "status-timed_out",
    };

    function perms() {
        if (!currentUser) {
            return { read: false };
        }
        const role = currentUser.role;
        return { read: role === "admin" || role === "operator" || role === "viewer" };
    }

    function showAlert(message) {
        const box = document.getElementById("page-alert");
        box.textContent = message;
        box.classList.remove("hidden");
    }

    function clearAlert() {
        document.getElementById("page-alert").classList.add("hidden");
    }

    function esc(value) {
        const div = document.createElement("div");
        div.textContent = String(value === null || value === undefined ? "" : value);
        return div.innerHTML;
    }

    function fmtDuration(ms) {
        if (ms == null) {
            return "—";
        }
        return (ms / 1000).toFixed(2) + " s";
    }

    function openExecution(execution) {
        document.getElementById("run-title").textContent =
            "Ejecución #" + execution.id + " · " + (execution.cron_job_name || "tarea eliminada");
        const when = execution.finished_at
            ? new Date(execution.finished_at).toLocaleString()
            : "";
        const errorLine = execution.error ? "\n[error: " + execution.error + "]" : "";
        document.getElementById("run-status").textContent =
            (statusLabels[execution.status] || execution.status) +
            " · código de salida: " +
            (execution.exit_code === null ? "—" : execution.exit_code) +
            " · duración: " + fmtDuration(execution.duration_ms) +
            (when ? " · fin: " + when : "") +
            " · usuario: " + (execution.username || "—");
        document.getElementById("run-stdout").textContent =
            execution.stdout || "(sin salida estándar)";
        document.getElementById("run-stderr").textContent =
            (execution.stderr || "(sin errores)") + errorLine;
        document.getElementById("run-modal").classList.remove("hidden");
    }

    function renderExecutions(executions) {
        const tbody = document.getElementById("executions-body");
        tbody.innerHTML = "";

        if (!executions || executions.length === 0) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 9;
            td.className = "muted";
            td.textContent = "No hay ejecuciones registradas.";
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        executions.forEach(function (execution) {
            const tr = document.createElement("tr");

            const jobTd = document.createElement("td");
            jobTd.textContent = execution.cron_job_name || "—";
            tr.appendChild(jobTd);

            const scriptTd = document.createElement("td");
            scriptTd.textContent = execution.script_name || "—";
            tr.appendChild(scriptTd);

            const statusTd = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = "status-badge " + (statusClass[execution.status] || "status-inactive");
            badge.textContent = statusLabels[execution.status] || execution.status;
            statusTd.appendChild(badge);
            tr.appendChild(statusTd);

            const triggerTd = document.createElement("td");
            triggerTd.textContent = execution.trigger || "manual";
            tr.appendChild(triggerTd);

            const codeTd = document.createElement("td");
            const code = document.createElement("code");
            code.textContent = execution.exit_code === null ? "—" : String(execution.exit_code);
            codeTd.appendChild(code);
            tr.appendChild(codeTd);

            const durTd = document.createElement("td");
            durTd.textContent = fmtDuration(execution.duration_ms);
            tr.appendChild(durTd);

            const startTd = document.createElement("td");
            startTd.textContent = execution.started_at
                ? new Date(execution.started_at).toLocaleString()
                : "";
            tr.appendChild(startTd);

            const userTd = document.createElement("td");
            userTd.textContent = execution.username || "—";
            tr.appendChild(userTd);

            const outTd = document.createElement("td");
            outTd.className = "actions-col";
            const view = document.createElement("button");
            view.className = "btn btn-secondary btn-small";
            view.type = "button";
            view.textContent = "Ver";
            view.addEventListener("click", function () {
                clearAlert();
                openExecution(execution);
            });
            outTd.appendChild(view);
            tr.appendChild(outTd);

            tbody.appendChild(tr);
        });
    }

    function loadExecutions() {
        clearAlert();
        const filter = {};
        const status = document.getElementById("filter-status").value;
        if (status) {
            filter.status = status;
        }
        return Api.getExecutions(filter)
            .then(function (executions) {
                renderExecutions(executions);
            })
            .catch(function (error) {
                showAlert(error.message || "No se pudieron cargar las ejecuciones.");
            });
    }

    function wireModalClosers() {
        document.getElementById("run-close").addEventListener("click", function () {
            document.getElementById("run-modal").classList.add("hidden");
        });
        document.getElementById("run-done").addEventListener("click", function () {
            document.getElementById("run-modal").classList.add("hidden");
        });
    }

    (async function init() {
        try {
            currentUser = await Auth.requireAuthentication();
        } catch (error) {
            return;
        }

        document.getElementById("user-name").textContent = currentUser.username;
        document.getElementById("user-role").textContent = currentUser.role;

        if (!perms().read) {
            showAlert("No tiene permisos para ver esta sección.");
            return;
        }

        document.getElementById("logout-button").addEventListener("click", function () {
            Auth.logout();
        });
        document.getElementById("refresh-button").addEventListener("click", loadExecutions);
        document.getElementById("filter-status").addEventListener("change", loadExecutions);
        wireModalClosers();

        await loadExecutions();
    })();
})();