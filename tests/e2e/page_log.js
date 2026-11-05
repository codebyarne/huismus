// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

// What the page did, for a browser test that fails (tests/e2e/conftest.py).
// A click that didn't open a dialog, a page that went somewhere else: the
// error alone doesn't say which. This keeps the last events in
// sessionStorage, so a new page in the same tab keeps the old one's too.
(() => {
  const KEY = "huismus-test-log";
  const KEEP = 200;
  const started = performance.now();
  const describe = (node) => {
    if (!(node instanceof Element)) return String(node?.nodeName ?? node);
    const id = node.id ? `#${node.id}` : "";
    const text = node.closest("button, a")?.textContent.trim().slice(0, 30);
    return `${node.localName}${id}${text ? ` "${text}"` : ""}${node.isConnected ? "" : " (los)"}`;
  };
  // Read and written whole on every line: only clicks, answers and dialogs
  // log, never something as busy as mousemove.
  const log = (line) => {
    try {
      const lines = JSON.parse(sessionStorage.getItem(KEY) ?? "[]");
      lines.push(`${Math.round(performance.now() - started)} ms ${line}`);
      sessionStorage.setItem(KEY, JSON.stringify(lines.slice(-KEEP)));
    } catch {
      // No sessionStorage (about:blank): then there is no log either.
    }
  };
  log(`pagina ${location.pathname}${location.search}`);
  // All four, not just click: a click that is lost (pressed on one element,
  // released on another) shows as a press without a click.
  for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {
    document.addEventListener(type, (event) => log(`${type} op ${describe(event.target)}`), true);
  }
  document.addEventListener("submit", (event) => log(`submit ${describe(event.submitter)}`), true);
  // "toggle" doesn't bubble, hence capture.
  document.addEventListener(
    "toggle",
    (event) => event.target.localName === "dialog" && log(`${describe(event.target)} ${event.newState}`),
    true,
  );
  // One line per htmx answer, with what it swapped out of band. Without a
  // view transition or swap delay (the editor's live totals) an answer's
  // swaps run in one go between its beforeSwap and afterRequest, so no other
  // answer lands in between. With one, a swap may show at the next answer.
  let swapped = [];
  document.addEventListener("htmx:beforeRequest", (event) => log(`htmx stuurt ${event.detail.requestConfig.path}`));
  document.addEventListener("htmx:beforeSwap", () => {
    swapped = [];
  });
  document.addEventListener("htmx:oobBeforeSwap", (event) => swapped.push(`#${event.detail.target.id}`));
  document.addEventListener("htmx:afterRequest", (event) => {
    log(`htmx antwoord ${event.detail.xhr.status}${swapped.length ? `, oob: ${swapped.join(" ")}` : ""}`);
    swapped = [];
  });
  window.addEventListener("pagehide", () => log("pagina weg"));
})();
