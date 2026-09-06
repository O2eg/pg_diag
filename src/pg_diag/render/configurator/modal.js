/* Lazy, offline configurator dialog; all computation stays in the vendored page. */
(function () {
  "use strict";
  window.PgDiagConfigurator.mount = function ({artifact, showModal, hideModal}) {
    const button = document.getElementById("showConfigurator");
    const modal = document.getElementById("configuratorModal");
    const frame = document.getElementById("configuratorFrame");
    const status = document.getElementById("configuratorStatus");
    const prepared = window.PgDiagConfigurator.prepare(artifact);
    button.hidden = !prepared.ready;
    button.title = prepared.ready ? "Calculate and compare PostgreSQL settings using report data"
      : prepared.missing.join("; ");
    let loaded = false;
    const theme = () => document.documentElement.dataset.theme || "dark";
    const close = () => { hideModal(modal); button.focus(); };
    button.addEventListener("click", () => {
      showModal(modal, "closeConfigurator");
      if (loaded) {
        frame.contentWindow.postMessage({type: "pg-diag-configurator-theme", theme: theme()}, "*");
        return;
      }
      status.hidden = false;
      const page = JSON.parse(document.getElementById("pg-diag-configurator-page").textContent);
      const seed = JSON.stringify({...prepared, theme: theme()})
        .replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
      frame.srcdoc = page.replace("__PG_DIAG_CONFIGURATOR_CONTEXT__", () => seed);
      loaded = true;
    });
    document.getElementById("closeConfigurator").addEventListener("click", close);
    modal.addEventListener("click", event => { if (event.target === modal) close(); });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !modal.hidden) close();
    });
    window.addEventListener("message", event => {
      if (event.source !== frame.contentWindow) return;
      if (event.data?.type === "pg-diag-configurator-close" && !modal.hidden) close();
      if (event.data?.type === "pg-diag-configurator-ready") {
        status.hidden = !event.data.error;
        if (event.data.error) status.textContent = "Adjust inputs in Main: " + event.data.error;
      }
    });
  };
})();
