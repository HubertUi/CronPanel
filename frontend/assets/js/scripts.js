/* Scripts (allow-list) page: admin CRUD; operators and viewers read-only. */

(function () {
    "use strict";

    let currentUser = null;
    let editingScriptId = null;

    function perms() {
        if (!currentUser) {
            return { read: false, manage: false };
        }
        const role = currentUser.role;
        return {
            read: role === "admin" || role === "operator" || role === "viewer",
            manage: role === "admin",
        };
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

    function renderScripts(scripts) {
        const tbody = document.getElementById("scripts-body");
        tbody.innerHTML = "";

        if (!scripts || scripts.length === 0) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 5;
            td.className = "muted";
            td.textContent = "No hay scripts registrados.";
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        const p = perms();

        scripts.forEach(function (script) {
            const tr = document.createElement("tr");

            const nameTd = document.createElement("td");
            nameTd.textContent = script.name;
            tr.appendChild(nameTd);

            const pathTd = document.createElement("td");
            const code = document.createElement("code");
            code.className = "cron-command";
            code.textContent = script.path;
            code.title = script.path;
            pathTd.appendChild(code);
            tr.appendChild(pathTd);

            const statusTd = document.createElement("td");
            const badge = document.createElement("span");
            badge.className =
                "status-badge " + (script.is_enabled ? "status-active" : "status-inactive");
            badge.textContent = script.is_enabled ? "Habilitado" : "Deshabilitado";
            statusTd.appendChild(badge);
            tr.appendChild(statusTd);

            const byTd = document.createElement("td");
            byTd.textContent = script.created_by_username || "—";
            tr.appendChild(byTd);

            const actionsTd = document.createElement("td");
            actionsTd.className = "actions-col";

            if (p.manage) {
                const edit = document.createElement("button");
                edit.className = "btn btn-secondary btn-small";
                edit.type = "button";
                edit.textContent = "Editar";
                edit.addEventListener("click", function () {
                    clearAlert();
                    openScriptModal(script);
                });
                actionsTd.appendChild(edit);

                const remove = document.createElement("button");
                remove.className = "btn btn-secondary btn-small btn-danger";
                remove.type = "button";
                remove.textContent = "Eliminar";
                remove.addEventListener("click", function () {
                    if (!window.confirm("¿Eliminar el script «" + script.name + "»?")) {
                        return;
                    }
                    clearAlert();
                    Api.deleteScript(script.id)
                        .then(function () {
                            return loadScripts();
                        })
                        .catch(function (error) {
                            showAlert(error.message || "No se pudo eliminar el script.");
                        });
                });
                actionsTd.appendChild(remove);
            }

            tr.appendChild(actionsTd);
            tbody.appendChild(tr);
        });
    }

    function loadScripts() {
        clearAlert();
        return Api.getScripts()
            .then(function (scripts) {
                renderScripts(scripts);
            })
            .catch(function (error) {
                showAlert(error.message || "No se pudieron cargar los scripts.");
            });
    }

    /* ---- Modal crear/editar ---- */
    function openScriptModal(script) {
        editingScriptId = script ? script.id : null;
        document.getElementById("modal-title").textContent = script ? "Editar script" : "Nuevo script";
        document.getElementById("script-id").value = script ? script.id : "";
        document.getElementById("script-name").value = script ? script.name : "";
        document.getElementById("script-path").value = script ? script.path : "";
        document.getElementById("script-description").value = script ? (script.description || "") : "";
        document.getElementById("script-enabled").checked = script ? script.is_enabled : true;
        document.getElementById("script-path-hint")
            .textContent = "Debe ser un archivo dentro del directorio permitido (allow-list).";
        document.getElementById("script-modal").classList.remove("hidden");
        document.getElementById("script-name").focus();
    }

    function closeScriptModal() {
        document.getElementById("script-modal").classList.add("hidden");
    }

    function collectForm() {
        const payload = {
            name: document.getElementById("script-name").value.trim(),
            path: document.getElementById("script-path").value.trim(),
        };
        const description = document.getElementById("script-description").value.trim();
        if (description) {
            payload.description = description;
        }
        if (editingScriptId) {
            payload.is_enabled = document.getElementById("script-enabled").checked;
        }
        return payload;
    }

    function wireForm() {
        const form = document.getElementById("script-form");
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            clearAlert();
            const payload = collectForm();

            const request = editingScriptId
                ? Api.updateScript(editingScriptId, payload)
                : Api.createScript(payload);

            const saveButton = document.getElementById("modal-save");
            saveButton.disabled = true;
            request
                .then(function () {
                    closeScriptModal();
                    return loadScripts();
                })
                .catch(function (error) {
                    showAlert(error.message || "No se pudo guardar el script.");
                })
                .finally(function () {
                    saveButton.disabled = false;
                });
        });

        document.getElementById("modal-cancel").addEventListener("click", closeScriptModal);
        document.getElementById("modal-close").addEventListener("click", closeScriptModal);
    }

    (async function init() {
        try {
            currentUser = await Auth.requireAuthentication();
        } catch (error) {
            return;
        }

        document.getElementById("user-name").textContent = currentUser.username;
        document.getElementById("user-role").textContent = currentUser.role;

        const p = perms();
        if (!p.read) {
            showAlert("No tiene permisos para ver esta sección.");
            return;
        }

        if (!p.manage) {
            document.getElementById("new-script-button").classList.add("hidden");
        }

        document.getElementById("logout-button").addEventListener("click", function () {
            Auth.logout();
        });
        document.getElementById("new-script-button").addEventListener("click", function () {
            clearAlert();
            openScriptModal(null);
        });

        wireForm();
        await loadScripts();
    })();
})();