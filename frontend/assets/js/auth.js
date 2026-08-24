/* Session handling: login, logout and route guards. */

const Auth = {
    TOKEN_KEY: "cronpanel_token",

    saveSession(token) {
        localStorage.setItem(this.TOKEN_KEY, token);
    },

    clearSession() {
        localStorage.removeItem(this.TOKEN_KEY);
    },

    isAuthenticated() {
        return Boolean(localStorage.getItem(this.TOKEN_KEY));
    },

    redirectToLogin() {
        window.location.replace("login.html");
    },

    async requireAuthentication() {
        if (!this.isAuthenticated()) {
            this.redirectToLogin();
            throw new Error("Not authenticated");
        }
        try {
            const me = await Api.get("/api/auth/me");
            return me;
        } catch (error) {
            this.redirectToLogin();
            throw error;
        }
    },

    async login(username, password) {
        const form = new FormData();
        form.append("username", username);
        form.append("password", password);

        const tokenResponse = await Api.request("/api/auth/login", {
            method: "POST",
            body: form,
        });
        this.saveSession(tokenResponse.access_token);
        return tokenResponse;
    },

    async logout() {
        try {
            await Api.post("/api/auth/logout", {});
        } catch (error) {
            /* Session is discarded locally regardless. */
        }
        this.clearSession();
        this.redirectToLogin();
    },
};

/* Login page wiring */
(function () {
    const loginForm = document.getElementById("login-form");
    if (!loginForm) {
        return;
    }

    if (Auth.isAuthenticated()) {
        window.location.replace("dashboard.html");
        return;
    }

    const errorBox = document.getElementById("login-error");
    const submitButton = document.getElementById("login-button");

    loginForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        errorBox.classList.add("hidden");

        const username = document.getElementById("username").value.trim();
        const password = document.getElementById("password").value;

        submitButton.disabled = true;
        try {
            await Auth.login(username, password);
            window.location.replace("dashboard.html");
        } catch (error) {
            errorBox.textContent = error.message || "No se pudo iniciar sesión.";
            errorBox.classList.remove("hidden");
        } finally {
            submitButton.disabled = false;
            document.getElementById("password").value = "";
        }
    });
})();
