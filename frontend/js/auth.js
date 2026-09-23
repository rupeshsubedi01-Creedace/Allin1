/**
 * API-key support for the PWA.
 *
 * When the server is started with ALLIN1_API_KEY, every /api/* call needs that
 * key. This module:
 *   1. stores the key in localStorage (it never leaves the browser otherwise),
 *   2. transparently attaches it to every same-origin /api/* fetch(),
 *   3. exposes query() so EventSource and <a download> links — neither of
 *      which can send custom headers — can pass ?key= as well,
 *   4. shows the key dialog when the server says a key is required.
 *
 * It must be loaded BEFORE app.js so the fetch wrapper is in place.
 */
(() => {
  "use strict";

  const STORAGE_KEY = "allin1_api_key";
  const HEADER = "X-API-Key";

  const nativeFetch = window.fetch.bind(window);

  const getKey = () => {
    try {
      return localStorage.getItem(STORAGE_KEY) || "";
    } catch {
      return "";
    }
  };

  const setKey = (value) => {
    try {
      if (value) localStorage.setItem(STORAGE_KEY, value);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* private-mode browsers: the key just won't persist */
    }
  };

  /** `?key=…` for URLs that cannot carry headers, or "" when no key is set. */
  const query = () => {
    const key = getKey();
    return key ? `?key=${encodeURIComponent(key)}` : "";
  };

  const isApiRequest = (input) => {
    const raw = typeof input === "string" ? input : input && input.url;
    if (!raw) return false;
    try {
      const url = new URL(raw, window.location.href);
      return url.origin === window.location.origin && url.pathname.startsWith("/api/");
    } catch {
      return false;
    }
  };

  window.fetch = (input, init) => {
    const options = init ? { ...init } : {};
    if (isApiRequest(input) && getKey()) {
      const headers = new Headers(options.headers || (input && input.headers) || {});
      if (!headers.has(HEADER)) headers.set(HEADER, getKey());
      options.headers = headers;
    }
    return nativeFetch(input, options).then((response) => {
      if (response.status === 401) {
        setKey("");
        showDialog("This server needs an API key. Enter the ALLIN1_API_KEY value you set when starting it.");
      }
      return response;
    });
  };

  // ------------------------------------------------------------- dialog
  let dialog = null;

  function elements() {
    return {
      dialog: document.getElementById("auth-dialog"),
      input: document.getElementById("auth-key-input"),
      error: document.getElementById("auth-key-error"),
      form: document.getElementById("auth-key-form"),
      button: document.getElementById("auth-key-btn"),
    };
  }

  function showDialog(message) {
    const ui = elements();
    if (!ui.dialog) return;
    if (message) {
      ui.error.textContent = message;
      ui.error.hidden = false;
    }
    ui.input.value = "";
    if (typeof ui.dialog.showModal === "function") {
      if (!ui.dialog.open) ui.dialog.showModal();
    } else {
      ui.dialog.setAttribute("open", "");
    }
  }

  function hideDialog() {
    const ui = elements();
    if (!ui.dialog) return;
    if (typeof ui.dialog.close === "function" && ui.dialog.open) ui.dialog.close();
    else ui.dialog.removeAttribute("open");
    ui.error.hidden = true;
  }

  function wireDialog() {
    const ui = elements();
    if (!ui.dialog) return;

    ui.form.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = ui.input.value.trim();
      if (!value) {
        ui.error.textContent = "Paste the API key to continue.";
        ui.error.hidden = false;
        return;
      }
      setKey(value);
      // Reload so EventSource/download links pick the key up everywhere.
      window.location.reload();
    });

    ui.dialog.querySelectorAll("[data-auth-close]").forEach((btn) => {
      btn.addEventListener("click", () => hideDialog());
    });

    if (ui.button) {
      ui.button.addEventListener("click", (event) => {
        event.preventDefault();
        showDialog("Paste the ALLIN1_API_KEY configured on your server. Clearing it and saving an empty value is not allowed — use “Forget key” to sign out.");
      });
    }

    const forget = document.getElementById("auth-forget-btn");
    if (forget) {
      forget.addEventListener("click", (event) => {
        event.preventDefault();
        setKey("");
        window.location.reload();
      });
    }
  }

  async function reflectAuthState() {
    try {
      const response = await nativeFetch("/api/health", { cache: "no-store" });
      const data = await response.json();
      const button = document.getElementById("auth-key-btn");
      if (button) {
        button.hidden = false;
        button.classList.toggle("key-active", Boolean(data.auth_required && getKey()));
        button.title = data.auth_required ? "API key required" : "API key settings";
      }
      if (data.auth_required && !getKey()) {
        showDialog("This Allin1 server requires an API key. Paste your ALLIN1_API_KEY to continue.");
      }
    } catch {
      /* offline / server unreachable: app.js surfaces its own error */
    }
  }

  window.Allin1Auth = { getKey, setKey, query, showDialog, hideDialog };

  window.addEventListener("DOMContentLoaded", () => {
    wireDialog();
    reflectAuthState();
  });
})();
