/* Automatizaciones (CronJobs) page: list, create, edit, enable/disable,
   delete and history. Mirrors the backend RBAC: admin full access to every
   job; operator can create/edit/enable but not delete; viewer read-only. */

(function () {
    "use strict";

    let currentUser = null;

    function perms() {
        if (!currentUser) {
            return { read: false, create: false, update: false, enable: false, del: false };
        }
        const role = currentUser.role;
        return {
            read: role === "admin" || role === "operator" || role === "viewer",
            create: role === "admin" || role === "operator",
            update: role === "admin" || role === "operator",
            enable: role === "admin" || role === "operator",
            del: role === "admin",
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

    function toggleRow(job) {
        if (job.saving === "1") {
            return;
        }
        job.saving = "1";
        Api.updateCronJobStatus(job.id, !job.isActive)
            .then(() => loadJobs())
            .catch((error) => {
                showAlert(error.message || "No se pudo cambiar el estado.");
            })
            .finally(() => {
                job.saving = "0";
            });
    }

    function renderHistory(entries, jobName) {
        const list = document.getElementById("history-list");
        document.getElementById("history-title").textContent = "Historial · " + jobName;
        list.innerHTML = "";

        if (!entries || entries.length === 0) {
            const empty = document.createElement("li");
            empty.className = "history-empty muted";
            empty.textContent = "Sin cambios registrados.";
            list.appendChild(empty);
            return;
        }

        const actionLabels = {
            CREATED: "Creada",
            UPDATED: "Actualizada",
            ENABLED: "Activada",
            DISABLED: "Desactivada",
            DELETED: "Eliminada",
        };

        entries.forEach((entry) => {
            const item = document.createElement("li");
            item.className = "history-item";

            const head = document.createElement("div");
            head.className = "history-head";

            const action = document.createElement("span");
            action.className = "history-action";
            action.textContent = actionLabels[entry.action] || entry.action;

            const meta = document.createElement("span");
            meta.className = "history-meta muted";
            const when = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "";
            meta.textContent = (entry.username || "—") + " · " + when;

            head.appendChild(action);
            head.appendChild(meta);
            item.appendChild(head);

            if (entry.changes && Object.keys(entry.changes).length > 0) {
                const body = document.createElement("pre");
                body.className = "history-changes";
                const lines = Object.entries(entry.changes).map(([field, change]) => {
                    const oldValue = change && "old" in change ? change.old : null;
                    const newValue = change && "new" in change ? change.new : null;
                    return field + ": " + JSON.stringify(oldValue) + " → " + JSON.stringify(newValue);
                });
                body.textContent = lines.join("\n");
                item.appendChild(body);
            }

            list.appendChild(item);
        });
    }

    function openHistory(id, name) {
        Api.getCronJobHistory(id)
            .then((entries) => {
                renderHistory(entries, name);
                document.getElementById("history-modal").classList.remove("hidden");
            })
            .catch((error) => {
                showAlert(error.message || "No se pudo cargar el historial.");
            });
    }

    function renderJobs(jobs) {
        const tbody = document.getElementById("jobs-body");
        tbody.innerHTML = "";

        if (!jobs || jobs.length === 0) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 6;
            td.className = "muted";
            td.textContent = "No hay tareas programadas.";
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        const p = perms();

        jobs.forEach((job) => {
            const tr = document.createElement("tr");

            const nameTd = document.createElement("td");
            nameTd.textContent = job.name;
            tr.appendChild(nameTd);

            const schedTd = document.createElement("td");
            const code = document.createElement("code");
            code.className = "cron-expr";
            code.textContent = job.schedule_expression;
            schedTd.appendChild(code);
            tr.appendChild(schedTd);

            const humanTd = document.createElement("td");
            humanTd.textContent = job.human_description || "";
            tr.appendChild(humanTd);

            const cmdTd = document.createElement("td");
            const cmdCode = document.createElement("code");
            cmdCode.className = "cron-command";
            cmdCode.textContent = job.command;
            cmdTd.appendChild(cmdCode);
            tr.appendChild(cmdTd);

            const statusTd = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = "status-badge " + (job.is_active ? "status-active" : "status-inactive");
            badge.textContent = job.is_active ? "Activa" : "Inactiva";
            statusTd.appendChild(badge);
            tr.appendChild(statusTd);

            const actionsTd = document.createElement("td");
            actionsTd.className = "actions-col";

            if (p.enable) {
                const toggle = document.createElement("button");
                toggle.className = "btn btn-secondary btn-small";
                toggle.type = "button";
                toggle.textContent = job.is_active ? "Pausar" : "Activar";
                toggle.addEventListener("click", function () {
                    clearAlert();
                    toggleRow({ id: job.id, isActive: job.is_active });
                });
                actionsTd.appendChild(toggle);
            }

            if (p.update) {
                const edit = document.createElement("button");
                edit.className = "btn btn-secondary btn-small";
                edit.type = "button";
                edit.textContent = "Editar";
                edit.addEventListener("click", function () {
                    clearAlert();
                    openJobModal(job);
                });
                actionsTd.appendChild(edit);
            }

            const more = document.createElement("button");
            more.className = "btn btn-secondary btn-small";
            more.type = "button";
            more.textContent = "Historial";
            more.addEventListener("click", function () {
                clearAlert();
                openHistory(job.id, job.name);
            });
            actionsTd.appendChild(more);

            if (p.del) {
                const remove = document.createElement("button");
                remove.className = "btn btn-secondary btn-small btn-danger";
                remove.type = "button";
                remove.textContent = "Eliminar";
                remove.addEventListener("click", function () {
                    if (!window.confirm("¿Eliminar la tarea «" + job.name + "»? El historial se conserva.")) {
                        return;
                    }
                    clearAlert();
                    Api.deleteCronJob(job.id)
                        .then(() => loadJobs())
                        .catch((error) => {
                            showAlert(error.message || "No se pudo eliminar la tarea.");
                        });
                });
                actionsTd.appendChild(remove);
            }

            tr.appendChild(actionsTd);
            tbody.appendChild(tr);
        });
    }

    function loadJobs() {
        clearAlert();
        const name = document.getElementById("filter-name").value.trim();
        const activeValue = document.getElementById("filter-active").value;
        const filter = {};
        if (name) {
            filter.name = name;
        }
        if (activeValue !== "") {
            filter.active = activeValue === "true";
        }
        return Api.getCronJobs(filter)
            .then((jobs) => {
                renderJobs(jobs);
            })
            .catch((error) => {
                showAlert(error.message || "No se pudieron cargar las tareas.");
            });
    }

    /* ---- Modal crear/editar ---- */
    let editingJobId = null;
    let scheduleTimer = null;

    function setScheduleHint(text, isError) {
        const hint = document.getElementById("schedule-hint");
        hint.textContent = text || "";
        hint.className = "field-hint" + (isError ? " hint-error" : " hint-ok");
    }

    function openJobModal(job) {
        editingJobId = job ? job.id : null;
        document.getElementById("modal-title").textContent = job ? "Editar tarea" : "Nueva tarea";
        document.getElementById("job-id").value = job ? job.id : "";
        document.getElementById("job-name").value = job ? job.name : "";
        document.getElementById("job-command").value = job ? job.command : "";
        document.getElementById("job-schedule").value = job ? job.schedule_expression : "";
        document.getElementById("job-description").value = job ? (job.description || "") : "";
        setScheduleHint("", false);
        document.getElementById("job-modal").classList.remove("hidden");
        document.getElementById("job-name").focus();
    }

    function closeJobModal() {
        document.getElementById("job-modal").classList.add("hidden");
    }

    function collectJobForm() {
        const payload = {
            name: document.getElementById("job-name").value.trim(),
            command: document.getElementById("job-command").value.trim(),
            schedule_expression: document.getElementById("job-schedule").value.trim(),
        };
        const description = document.getElementById("job-description").value.trim();
        if (description) {
            payload.description = description;
        }
        return payload;
    }

    function onScheduleInput(event) {
        const expression = event.target.value.trim();
        if (scheduleTimer) {
            window.clearTimeout(scheduleTimer);
        }
        if (!expression) {
            setScheduleHint("", false);
            return;
        }
        scheduleTimer = window.setTimeout(function () {
            Api.validateCronExpression(expression)
                .then((result) => {
                    if (result.valid) {
                        setScheduleHint(
                            (result.description || "Programación válida.") +
                                (result.normalized_expression && result.normalized_expression !== expression
                                    ? " · Normalizada: " + result.normalized_expression
                                    : ""),
                            false
                        );
                    } else {
                        setScheduleHint(result.error_message || "Expresión inválida.", true);
                    }
                })
                .catch(function () {
                    setScheduleHint("", false);
                });
        }, 350);
    }

    function wireJobForm() {
        const form = document.getElementById("job-form");
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            clearAlert();
            const payload = collectJobForm();

            const request = editingJobId
                ? Api.updateCronJob(editingJobId, payload)
                : Api.createCronJob(payload);

            const saveButton = document.getElementById("modal-save");
            saveButton.disabled = true;
            request
                .then(() => {
                    closeJobModal();
                    return loadJobs();
                })
                .catch((error) => {
                    setScheduleHint("", false);
                    showAlert(error.message || "No se pudo guardar la tarea.");
                })
                .finally(() => {
                    saveButton.disabled = false;
                });
        });

        form.querySelector("#modal-cancel").addEventListener("click", closeJobModal);
        form.querySelector("#modal-close").addEventListener("click", closeJobModal);
        document.getElementById("job-schedule").addEventListener("input", onScheduleInput);
    }

    function wireModalClosers() {
        document.getElementById("history-close").addEventListener("click", function () {
            document.getElementById("history-modal").classList.add("hidden");
        });
        document.getElementById("history-done").addEventListener("click", function () {
            document.getElementById("history-modal").classList.add("hidden");
        });
    }

    function wireFilters() {
        const nameInput = document.getElementById("filter-name");
        const activeSelect = document.getElementById("filter-active");
        let timer = null;
        [nameInput, activeSelect].forEach(function (el) {
            el.addEventListener("input", function () {
                if (timer) {
                    window.clearTimeout(timer);
                }
                timer = window.setTimeout(loadJobs, 250);
            });
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

        const p = perms();
        if (!p.read) {
            showAlert("No tiene permisos para ver esta sección.");
            return;
        }

        if (!p.create) {
            document.getElementById("new-job-button").classList.add("hidden");
        }

        document.getElementById("logout-button").addEventListener("click", function () {
            Auth.logout();
        });
        document.getElementById("new-job-button").addEventListener("click", function () {
            clearAlert();
            openJobModal(null);
        });

        wireJobForm();
        wireModalClosers();
        wireFilters();

        await loadJobs();
    })();
})();