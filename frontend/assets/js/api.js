/* Thin REST client for CronPanel's API.
   Attaches the JWT and normalizes error handling. */

class ApiError extends Error {
    constructor(errorCode, message, statusCode) {
        super(message);
        this.name = "ApiError";
        this.errorCode = errorCode;
        this.statusCode = statusCode;
    }
}

const Api = {
    baseUrl: "",

    getToken() {
        return localStorage.getItem("cronpanel_token");
    },

    async request(path, options = {}) {
        const headers = Object.assign({}, options.headers || {});
        const token = this.getToken();
        if (token) {
            headers["Authorization"] = "Bearer " + token;
        }

        let body = options.body;
        if (body && !(body instanceof FormData)) {
            headers["Content-Type"] = "application/json";
            body = JSON.stringify(body);
        }

        let response;
        try {
            response = await fetch(this.baseUrl + path, {
                method: options.method || "GET",
                headers,
                body,
            });
        } catch (networkError) {
            throw new ApiError("NETWORK_ERROR", "No se pudo contactar al servidor.", 0);
        }

        if (response.status === 401 && !path.startsWith("/api/auth/login")) {
            Auth.clearSession();
            window.location.replace("login.html");
            throw new ApiError("NOT_AUTHENTICATED", "Sesión expirada.", 401);
        }

        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new ApiError(
                payload.error || "HTTP_ERROR",
                payload.message || "Error inesperado.",
                response.status
            );
        }

        return payload;
    },

    get(path) {
        return this.request(path);
    },

    post(path, body) {
        return this.request(path, { method: "POST", body });
    },

    put(path, body) {
        return this.request(path, { method: "PUT", body });
    },

    patch(path, body) {
        return this.request(path, { method: "PATCH", body });
    },

    delete(path) {
        return this.request(path, { method: "DELETE" });
    },

    /* ---- CronJobs ---- */
    getCronJobs(filter) {
        const params = new URLSearchParams();
        if (filter) {
            if ("active" in filter) params.set("active", filter.active);
            if (filter.name) params.set("name", filter.name);
            if (filter.schedule) params.set("schedule", filter.schedule);
            if (filter.limit) params.set("limit", filter.limit);
            if (filter.offset) params.set("offset", filter.offset);
        }
        const qs = params.toString();
        return this.get("/api/cron-jobs" + (qs ? "?" + qs : ""));
    },

    getCronJob(id) {
        return this.get("/api/cron-jobs/" + id);
    },

    createCronJob(body) {
        return this.post("/api/cron-jobs", body);
    },

    updateCronJob(id, body) {
        return this.put("/api/cron-jobs/" + id, body);
    },

    updateCronJobStatus(id, isActive) {
        return this.patch("/api/cron-jobs/" + id + "/status", { is_active: isActive });
    },

    deleteCronJob(id) {
        return this.delete("/api/cron-jobs/" + id);
    },

    getCronJobHistory(id) {
        return this.get("/api/cron-jobs/" + id + "/history");
    },

    validateCronExpression(scheduleExpression) {
        return this.post("/api/cron-jobs/validate", { schedule_expression: scheduleExpression });
    },
};
