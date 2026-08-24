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
};
