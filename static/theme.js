(() => {
    "use strict";

    const root = document.documentElement;
    const storageKey = "findback-theme";
    const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
    let storedTheme = null;

    try {
        storedTheme = window.localStorage.getItem(storageKey);
    } catch (_error) {
        // Storage can be disabled; theme switching still works for this page.
    }

    const validTheme = (value) => value === "light" || value === "dark";
    let hasStoredChoice = validTheme(storedTheme);

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        const toggle = document.getElementById("theme-toggle");
        if (toggle) {
            const dark = theme === "dark";
            toggle.setAttribute("aria-pressed", String(dark));
            toggle.setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} theme`);
            toggle.textContent = `${dark ? "Light" : "Dark"} theme`;
        }
    }

    applyTheme(hasStoredChoice ? storedTheme : (systemTheme.matches ? "dark" : "light"));

    document.addEventListener("DOMContentLoaded", () => {
        applyTheme(root.getAttribute("data-theme"));
        const toggle = document.getElementById("theme-toggle");
        if (toggle) {
            toggle.addEventListener("click", () => {
                const nextTheme = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
                hasStoredChoice = true;
                applyTheme(nextTheme);
                try {
                    window.localStorage.setItem(storageKey, nextTheme);
                } catch (_error) {
                    // Keep the selected theme for this page when storage is unavailable.
                }
            });
        }

        if (typeof systemTheme.addEventListener === "function") {
            systemTheme.addEventListener("change", (event) => {
                if (!hasStoredChoice) {
                    applyTheme(event.matches ? "dark" : "light");
                }
            });
        }

        const searchForm = document.querySelector('form[action="/search"]');
        if (searchForm) {
            searchForm.addEventListener("submit", () => {
                const submitButton = searchForm.querySelector('button[type="submit"]');
                if (!submitButton || submitButton.disabled) return;
                submitButton.disabled = true;
                submitButton.setAttribute("aria-busy", "true");
                const label = submitButton.querySelector("[data-submit-label]");
                if (label) label.textContent = "Comparing reports…";
                const status = document.getElementById("search-status");
                if (status) status.textContent = "Comparing your search with active found reports.";
            });
        }
    });
})();
