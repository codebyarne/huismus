// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

// Progressive enhancement for the app shell. Nothing here is required:
// every link and form works as plain HTML when this file doesn't load.

if (window.htmx) {
  // Boosted page swaps animate like cross-document navigations do
  // (see @view-transition in huismus.css).
  window.htmx.config.globalViewTransitions = true;
}

// Fallback for invoker commands (<button command="show-modal" commandfor="id">)
// in browsers that don't support them yet.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[commandfor]");
  if (!button || "command" in HTMLButtonElement.prototype) return;
  const target = document.getElementById(button.getAttribute("commandfor"));
  const command = button.getAttribute("command");
  if (command === "show-modal") target?.showModal();
  if (command === "close") target?.close();
});

// "Sorteren" on a stacked list opens under its button with CSS anchor
// positioning (huismus.css). Where that is missing (the Mac app on macOS 15,
// older Safari and Firefox) the menu would sit in a corner of the window,
// so its place is set here from the button's: right edges in line, or the
// left ones when the menu would leave the screen. Without JS it sits bottom
// right, above the tab bar.
if (!CSS.supports("position-area: bottom")) {
  const place = () => {
    const menu = document.querySelector("#sorteer-menu:popover-open");
    const button = document.getElementById("sorteer-knop");
    if (!menu) return;
    menu.style.visibility = "";
    if (!button) return;
    const box = button.getBoundingClientRect();
    const left = box.right - menu.offsetWidth;
    // At once: with "reduce motion" on, huismus.css gives every change a
    // transition of 1 ms, and WebKit then showed the menu for a moment where
    // it was the time before.
    menu.style.transition = "none";
    menu.style.inset = `${box.bottom + 6}px auto auto ${left < 0 ? box.left : left}px`;
  };
  // Neither event bubbles: capture. The menu's width is only known once it
  // is open, so it stays out of sight for the moment in between instead of
  // showing where it was last time.
  document.addEventListener(
    "beforetoggle",
    (event) => {
      if (event.target.id === "sorteer-menu" && event.newState === "open") {
        event.target.style.visibility = "hidden";
      }
    },
    true,
  );
  document.addEventListener("toggle", (event) => event.target.id === "sorteer-menu" && place(), true);
  window.addEventListener("scroll", place, { passive: true });
  window.addEventListener("resize", place);
}

// An out-of-band swap keeps any button and only updates it. Leaving a field
// sends the editor's live totals, whose answer brings a new "Uitgeven…"
// button (documents/_editor_live.html). If that answer landed between
// mousedown and mouseup, a new element got the mouseup and the click was
// lost: the dialog stayed shut. Contents are only replaced when they differ,
// for the same reason (the press may be on the icon). htmx then swaps
// nothing, so process() picks up any hx-* attribute that changed.
document.addEventListener("htmx:oobBeforeSwap", (event) => {
  const { target, fragment } = event.detail;
  const fresh = fragment.firstElementChild;
  if (!(target instanceof HTMLButtonElement) || !(fresh instanceof HTMLButtonElement)) return;
  if (fragment.childElementCount !== 1) return;
  event.detail.shouldSwap = false;
  for (const { name } of [...target.attributes]) {
    if (!fresh.hasAttribute(name)) target.removeAttribute(name);
  }
  for (const { name, value } of fresh.attributes) target.setAttribute(name, value);
  if (target.innerHTML !== fresh.innerHTML) target.replaceChildren(...fresh.childNodes);
  window.htmx.process(target);
});

// Toasts: the close button removes one; success and info disappear on their
// own after 5 seconds, warnings and errors stay until closed.
document.addEventListener("click", (event) => {
  const close = event.target.closest(".toast [data-dismiss]");
  if (close) close.closest(".toast").remove();
});

function scheduleToasts(root) {
  for (const toast of root.querySelectorAll(".toast.flash-success, .toast.flash-info")) {
    if (toast.dataset.scheduled) continue;
    toast.dataset.scheduled = "1";
    setTimeout(() => toast.remove(), 5000);
  }
}

if (window.htmx) {
  // Called for the initial page and for every piece of swapped-in content.
  window.htmx.onLoad(scheduleToasts);
} else {
  scheduleToasts(document);
}

// "+ Contactpersoon" and the like: add an empty form to a Django formset.
// The markup names the pieces with the formset's prefix:
//   <button data-formset-add="persons">          the button
//   <div data-formset-forms="persons">           where the forms go
//   <template data-formset-empty="persons">      {{ formset.empty_form }}
// plus id_persons-TOTAL_FORMS, which Django's management form always has.
// Without JS the formset still has its one empty extra form to fill in, or
// the button is a submit button that saves and comes back with one.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-formset-add]");
  if (!button) return;
  // A submit button (an expense's "Regel toevoegen") saves without JS;
  // with JS the line is added here instead. The other ones are type=button.
  if (button.type === "submit") event.preventDefault();
  const prefix = button.dataset.formsetAdd;
  const total = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
  const template = document.querySelector(`template[data-formset-empty="${prefix}"]`);
  const forms = document.querySelector(`[data-formset-forms="${prefix}"]`);
  forms.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", total.value));
  total.value = Number(total.value) + 1;
  // A new line of an expense starts with the category of the line above
  // it (owner, 2026-11-20); without JS the server does (expenses/views.py).
  const [above, added] = [...forms.children].slice(-2);
  const category = added?.querySelector("select[name$='-category']");
  if (category && above) {
    category.value = above.querySelector("select[name$='-category']")?.value ?? "";
    const fresh = added.querySelector("input[data-combobox-new]");
    if (fresh) fresh.value = above.querySelector("input[data-combobox-new]")?.value ?? "";
  }
  // The pickers of the new form (enhanceCombobox, below).
  if (added) enhanceComboboxes(added);
});

// Busy buttons: the button that sends a form shows its spinner until the
// answer is there (huismus.css: .btn.is-loading). htmx marks the form, not
// the button, so this does it. Only buttons that have a .spinner: the
// class hides the label. Not for <dialog> forms, which just close, nor for
// a button with formtarget="_blank" (the editor's "Voorbeeld-pdf"), whose
// answer opens in a new tab. A new page replaces the button; an answer that
// doesn't (an error, a download) clears it when that form's own request
// ends — not another one's, like the editor's live totals — and pageshow
// does after "back".
// Whether a button's answer opens somewhere else than this page: a new tab,
// or the frame of the editor's preview dialog (formTarget set by its click
// handler below, before the submit).
const opensElsewhere = (button) => !["", "_self"].includes(button?.formTarget ?? "");

function markBusy(event) {
  const button = event.submitter;
  if (button?.querySelector(".spinner") && !opensElsewhere(button)) {
    button.classList.add("is-loading");
  }
}
const clearBusyButtons = (form) => {
  for (const button of document.querySelectorAll(".btn.is-loading")) {
    if (!form || button.form === form) button.classList.remove("is-loading");
  }
};
document.addEventListener("htmx:afterRequest", (event) => clearBusyButtons(event.detail.elt));
window.addEventListener("pageshow", () => clearBusyButtons());

const formMethod = (event) =>
  (event.submitter?.getAttribute("formmethod") || event.target.getAttribute("method") || "get").toLowerCase();

// The htmx requests on their way (by their XMLHttpRequest), whether a form
// waits for them, and whether this page is being left.
const sending = new Set();
let waiting = false;
let leaving = false;
const ended = (xhr) => {
  if (!sending.delete(xhr)) return;
  if (sending.size === 0) document.dispatchEvent(new Event("huismus:idle"));
};
// htmx:afterRequest comes first, before htmx sends a request queued behind
// this one. But htmx tells only the element that sent it, and once that
// element is gone (a part that fetches itself, replaced by a page change) the
// document never hears it. So the request's own end (loadend: an answer, an
// error or an abort) counts too; without it the request stayed here, and
// every form waited for it until the window closed (BUGS-BY-HAND.md).
document.addEventListener("htmx:beforeSend", (event) => {
  const xhr = event.detail.xhr;
  sending.add(xhr);
  xhr.addEventListener("loadend", () => ended(xhr));
});
document.addEventListener("htmx:afterRequest", (event) => ended(event.detail.xhr));
document.addEventListener("htmx:beforeRequest", (event) => {
  if (leaving) event.preventDefault();
});
// A page that is slow to come (a boosted link or GET form): after half a
// second the sparrow hops at the top (#pagina-laden, base.html). Looked up
// each time: a boosted page swaps <body>, and the element with it. Buttons
// that post have their own spinner, and parts that fetch themselves aren't
// boosted, so neither shows it.
let pageWaitTimer;
const pageWait = (show) => {
  clearTimeout(pageWaitTimer);
  const sparrow = document.getElementById("pagina-laden");
  if (sparrow) sparrow.hidden = !show;
};
document.addEventListener("htmx:beforeRequest", (event) => {
  if (!event.detail.boosted || event.defaultPrevented) return;
  clearTimeout(pageWaitTimer);
  pageWaitTimer = setTimeout(() => pageWait(true), 500);
});
document.addEventListener("htmx:afterRequest", (event) => {
  if (event.detail.boosted) pageWait(false);
});
window.addEventListener("pageshow", () => pageWait(false));
// Back to this page from the browser's cache: it may send again.
window.addEventListener("pageshow", () => {
  leaving = false;
});

// A form that sends data (POST) is submitted by the browser itself, not by
// htmx's boost: stopping the event here, before htmx sees it, lets the
// browser do the plain submit, as without JS. In WebKit (Safari, and the
// desktop app on a Mac) a boosted POST sometimes got its answer but never
// showed it: after "Proefdraai" the upload page simply stayed. Searching and
// filtering (GET) and links stay boosted. Forms with their own hx-post (the
// editor's live totals) aren't boosted and are left alone. This also opens
// a formtarget="_blank" answer in its new tab, which htmx would ignore.
//
// The editor's live totals may still be on their way, or about to go (they
// wait 400 ms after typing). Leaving the page would cut them off, which htmx
// reports as an error, and so does ending them (htmx:abort). So no new ones
// are sent, and the form waits for those underway, then sends itself.
document.addEventListener(
  "submit",
  (event) => {
    if (formMethod(event) !== "post" || event.target.hasAttribute("hx-post")) return;
    event.stopPropagation();
    if (opensElsewhere(event.submitter)) return;
    // A second click while the first one waits, or once the page is being
    // left: the first one goes. Otherwise the browser would cut off the
    // first request and send the form again; after "Leegmaken" or
    // "Terugzetten" that second one finds the database already replaced
    // (huismus-intern/besluiten.md, 2026-10-31). "Back" (pageshow) makes it clickable again.
    if (waiting || leaving) {
      event.preventDefault();
      return;
    }
    markBusy(event);
    if (sending.size > 0) {
      event.preventDefault();
      waiting = true;
      const { target: form, submitter } = event;
      document.addEventListener(
        "huismus:idle",
        () => {
          waiting = false;
          form.requestSubmit(submitter);
        },
        { once: true },
      );
      return;
    }
    // Every POST here leaves the page (downloads are GET links).
    leaving = true;
  },
  true,
);

// Every other form (htmx's): the same busy button.
document.addEventListener("submit", (event) => {
  if (formMethod(event) !== "dialog") markBusy(event);
});

// Dropzones: a file input marked data-autosubmit sends its form as soon as a
// file is chosen or dropped; .is-over highlights the zone while dragging.
// Without JS the form has its own submit button (in <noscript>).
document.addEventListener("change", (event) => {
  if (event.target.matches("input[type=file][data-autosubmit]")) {
    event.target.form.requestSubmit();
  }
});
for (const type of ["dragenter", "dragover", "dragleave", "drop"]) {
  document.addEventListener(type, (event) => {
    const zone = event.target.closest?.("[data-dropzone]");
    if (zone) zone.classList.toggle("is-over", type === "dragenter" || type === "dragover");
  });
}

// Multi-file inputs with data-file-summary="<id>": show which files were
// chosen before the form is sent (the server says what it recognized).
document.addEventListener("change", (event) => {
  const input = event.target;
  if (!input.matches?.("input[type=file][data-file-summary]")) return;
  const summary = document.getElementById(input.dataset.fileSummary);
  if (summary) summary.textContent = [...input.files].map((file) => file.name).join(", ");
});

// A select with data-shows-group="<name>": the elements with
// data-group="<name>" show only while something is chosen (e.g. the mail
// fields while "Mailen via" is not "Niet ingesteld"). Without JS they are
// always shown.
// Likewise radios: a group named in data-shows-group shows while one of its
// radios is chosen (the cards of Instellingen → Btw), a group named in
// data-hides-group hides while one of its radios is chosen (the question
// about btw verlegd without VAT, /welkom/werk/). A group is named by one
// kind of attribute, never both.
function showGroups(root) {
  for (const select of root.querySelectorAll("select[data-shows-group]")) {
    for (const element of document.querySelectorAll(`[data-group="${select.dataset.showsGroup}"]`)) {
      element.hidden = !select.value;
    }
  }
  const visible = new Map();
  for (const radio of root.querySelectorAll("input[type=radio][data-shows-group]")) {
    const group = radio.dataset.showsGroup;
    visible.set(group, Boolean(visible.get(group)) || radio.checked);
  }
  for (const radio of root.querySelectorAll("input[type=radio][data-hides-group]")) {
    const group = radio.dataset.hidesGroup;
    visible.set(group, visible.get(group) !== false && !radio.checked);
  }
  for (const [group, shown] of visible) {
    for (const element of document.querySelectorAll(`[data-group="${group}"]`)) element.hidden = !shown;
  }
}
showGroups(document);
// A page reached through hx-boost doesn't run this module again: hide the
// groups of the new page too (BUGS-BY-HAND.md, 2026-11-22;
// tests/e2e/test_vat_exempt.py comes to Instellingen → Btw through a link).
document.addEventListener("htmx:load", () => showGroups(document));
// Every radio, not only the one with data-hides-group: choosing another
// answer ("Ja") has to show the group again.
document.addEventListener("change", (event) => {
  if (event.target.matches("select[data-shows-group], input[type=radio]")) showGroups(event.target.form);
});

// Table rows with a .row-link: a click anywhere in the row follows that
// link. Without JS the link in the row's main cell still works. Not for
// clicks on other links, buttons or fields in the row, nor while text in
// the row is being selected.
document.addEventListener("click", (event) => {
  const row = event.target.closest("tr.is-link");
  if (!row || event.target.closest("a, button, input, select, textarea, label")) return;
  if (window.getSelection().toString()) return;
  row.querySelector(".row-link")?.click();
});

// Keyboard shortcuts, only while not typing in a field:
//   n  a new item for the current page (data-shortcut-new on <main>),
//      or the "+ Nieuw" menu elsewhere
//   /  jump to the page's search field
function isTyping(target) {
  return target.closest?.("input, textarea, select, [contenteditable=true]");
}
document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
  if (event.key === "/") {
    const search = document.querySelector("main input[type=search]");
    if (search) {
      event.preventDefault();
      search.focus();
    }
  } else if (event.key === "n") {
    const url = document.querySelector("main[data-shortcut-new]")?.dataset.shortcutNew;
    if (url) {
      window.location.assign(url);
    } else {
      // The four choices of the phone's +: the menu panel itself has only "Nieuwe factuur".
      document.getElementById("plus-menu")?.showPopover?.();
    }
  }
});

// Invoice editor: Tab from the last field of the last line adds a line and
// moves on to its description. Assumes [data-formset-forms] holds only the
// .line elements (the "Regel toevoegen" button sits outside it), so its
// last child is the last line.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Tab" || event.shiftKey) return;
  const forms = event.target.closest("[data-formset-forms]");
  const line = event.target.closest(".line");
  if (!forms || !line || line !== forms.lastElementChild) return;
  const fields = [...line.querySelectorAll("input:not([type=hidden]):not([type=checkbox]), select")];
  if (event.target !== fields.at(-1)) return;
  event.preventDefault();
  document.querySelector(`[data-formset-add="${forms.dataset.formsetForms}"]`)?.click();
  forms.lastElementChild.querySelector("textarea")?.focus();
});

// Searchable picker for a long <select data-combobox> (the invoice editor's
// customer): a text field that filters the options, arrow keys and Enter to
// choose. The <select> stays in the form, hidden, and gets the value, so
// the form and its live preview work exactly as without JS.
//
// With an <input data-combobox-new> beside the select (an expense line's
// category, expenses/_category_field.html) a text that is no option is a
// new one: it goes into that input, hidden here, and the server makes it.
function enhanceCombobox(select) {
  if (select.dataset.comboboxReady || select.disabled) return;
  select.dataset.comboboxReady = "1";
  const options = [...select.options].filter((option) => option.value);
  const fresh = select.parentElement.querySelector("input[data-combobox-new]");
  const hint = select.parentElement.querySelector("[data-combobox-new-hint]");
  const wrapper = document.createElement("div");
  wrapper.className = "combo";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "input";
  input.autocomplete = "off";
  input.placeholder = select.dataset.combobox;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-label", select.labels[0]?.textContent ?? "");
  input.value = select.selectedOptions[0]?.value ? select.selectedOptions[0].text : "";
  if (fresh) {
    fresh.hidden = true;
    if (fresh.value) input.value = fresh.value;
    if (hint) hint.hidden = !fresh.value;
  }
  const list = document.createElement("ul");
  list.className = "combo-list";
  list.id = `${select.id}-opties`;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  input.setAttribute("aria-controls", list.id);
  select.hidden = true;
  select.after(wrapper);
  wrapper.append(input, list);
  if (select.labels[0]) select.labels[0].htmlFor = "";

  let active = 0;
  let shown = [];
  const render = () => {
    const query = input.value.trim().toLowerCase();
    shown = options.filter((option) => option.text.toLowerCase().includes(query)).slice(0, 8);
    // The text itself as a new one, unless it is an option's name.
    const typed = input.value.trim();
    if (fresh && typed && !options.some((option) => option.text.toLowerCase() === query)) {
      shown.push({ text: `${fresh.getAttribute("aria-label")}: ${typed}`, add: typed });
    }
    active = Math.min(active, Math.max(shown.length - 1, 0));
    list.replaceChildren(
      ...shown.map((option, index) => {
        const item = document.createElement("li");
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", index === active ? "true" : "false");
        item.textContent = option.text;
        if (option.add) item.className = "combo-action";
        item.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(option);
        });
        return item;
      }),
    );
    list.hidden = shown.length === 0;
    input.setAttribute("aria-expanded", String(!list.hidden));
  };
  const choose = (option) => {
    select.value = option.add ? "" : option.value;
    input.value = option.add ?? option.text;
    if (fresh) fresh.value = option.add ?? "";
    if (hint) hint.hidden = !option.add;
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };
  input.addEventListener("focus", render);
  input.addEventListener("input", () => {
    active = 0;
    render();
  });
  input.addEventListener("blur", () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    if (fresh) {
      // What was typed counts: an option by its name, else a new one;
      // nothing typed is none.
      const typed = input.value.trim();
      const same = options.find((option) => option.text.toLowerCase() === typed.toLowerCase());
      choose(same ?? (typed ? { add: typed } : { value: "", text: "" }));
      return;
    }
    // Typed something that isn't a customer: show the chosen one again.
    input.value = select.selectedOptions[0]?.value ? select.selectedOptions[0].text : "";
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + shown.length) % Math.max(shown.length, 1);
      render();
    } else if (event.key === "Enter" && !list.hidden && shown[active]) {
      event.preventDefault();
      choose(shown[active]);
    } else if (event.key === "Escape") {
      list.hidden = true;
    }
  });
}

function enhanceComboboxes(root) {
  root.querySelectorAll?.("select[data-combobox]").forEach(enhanceCombobox);
}
if (window.htmx) {
  window.htmx.onLoad(enhanceComboboxes);
} else {
  enhanceComboboxes(document);
}

// hx-boost swaps only <body>, so <html lang> would keep the language of the
// first page load — after switching NL/EN too. Take it from each boosted
// response, so screen readers and the browser know the page's language.
document.addEventListener("htmx:afterRequest", (event) => {
  if (!event.detail.boosted || !event.detail.successful) return;
  const match = event.detail.xhr.responseText.match(/<html[^>]*\blang="([^"]+)"/);
  if (match) document.documentElement.lang = match[1];
});

// Textareas that grow with their text (the description of an invoice line).
// field-sizing: content does this in newer browsers (huismus.css); this is
// the fallback for the others.
function growTextarea(textarea) {
  if (CSS.supports("field-sizing", "content")) return;
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}
document.addEventListener("input", (event) => {
  if (event.target.matches?.("textarea.line-desc")) growTextarea(event.target);
});
function growAll(root) {
  for (const textarea of root.querySelectorAll("textarea.line-desc")) growTextarea(textarea);
}
// htmx.onLoad runs for the first page and for every swapped-in page; without
// htmx there are no swaps, so one pass over the page is enough.
if (window.htmx) {
  window.htmx.onLoad(growAll);
} else {
  growAll(document);
}
// A line added with "Regel toevoegen" comes from a <template>, not a swap.
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-formset-add]")) queueMicrotask(() => growAll(document));
});

// The service worker that shows the offline page in the installed app
// (huismus/core/pwa.py). Browsers without one, or on plain http:// other than
// localhost, just show their own error page; nothing else depends on it.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// "Kiezen…" next to the backup folder's path (Instellingen → Back-ups):
// only in the desktop app's own window, where pywebview offers the
// system's folder dialog (desktop/app.py, Api.choose_folder). Elsewhere
// the button stays hidden and the path is typed in.
const desktopApi = () => window.pywebview?.api?.choose_folder;
function showFolderButtons(root) {
  if (!desktopApi()) return;
  for (const button of root.querySelectorAll("[data-choose-folder]")) button.hidden = false;
}
// pywebview's bridge can arrive after this module runs: then pywebviewready.
// htmx.onLoad also covers the Back-ups page reached by a boosted link,
// which swaps the page in without loading this module again.
window.addEventListener("pywebviewready", () => showFolderButtons(document));
if (window.htmx) window.htmx.onLoad(showFolderButtons);
else showFolderButtons(document);
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-choose-folder]");
  if (!button || !desktopApi()) return;
  const folder = await window.pywebview.api.choose_folder();
  if (!folder) return;
  const form = button.form;
  form.elements.other_path.value = folder;
  const other = form.querySelector('input[name="folder"][value="other"]');
  if (other) other.checked = true;
});

// A file to download (<a data-file>: the year overview's CSV) in the
// installed app. That has no address bar and no back button; in a window of
// its own the file should open in a sheet with "Gereed". For PDFs this was
// not enough on an iPhone (huismus-intern/besluiten.md, 2026-11-01): they now open on
// a page of their own, below. In a browser tab, and in the desktop app, the
// link stays as it is.
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-file]");
  if (link && window.matchMedia("(display-mode: standalone)").matches) {
    link.target = "_blank";
    link.rel = "noopener";
  }
});

// A form whose answer is a file that takes a while (<form data-download>:
// the export's ZIP, 17 s on a Pi). The page stays, so its busy button
// (markBusy) would spin forever: the form sends a token in its field
// "klaar", the server sends it back as the cookie huismus_download with the
// file, and once that is there the button is clickable again.
const DOWNLOAD_COOKIE = "huismus_download";
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.matches?.("form[data-download]") || event.defaultPrevented) return;
  const token = String(Date.now()) + String(Math.random()).slice(2, 8);
  form.elements.klaar.value = token;
  const started = Date.now();
  const timer = setInterval(() => {
    const arrived = document.cookie.split("; ").includes(`${DOWNLOAD_COOKIE}=${token}`);
    // Five minutes: as long as the server waits (gunicorn's 300 s).
    if (arrived || Date.now() - started > 300000) {
      clearInterval(timer);
      document.cookie = `${DOWNLOAD_COOKIE}=; path=/; max-age=0`;
      clearBusyButtons(form);
    }
  }, 500);
});

// "Delen" on the PDF page (documents/pdf_page.html): the system's share
// sheet (Mail, Bewaar in Bestanden), only where the browser can share a
// file. The PDF is fetched as the page loads: iOS refuses to share once the
// tap has had to wait for the network. In the installed app Share takes
// Download's place, since a download there can take over the screen.
// Without JS, or without sharing, Download stays. The button and the
// Download link sit side by side in the page head's .actions.
const sharedFiles = new WeakMap();
async function prepareShareButtons(root) {
  for (const button of root.querySelectorAll("[data-share-pdf]")) {
    if (!navigator.canShare) continue;
    try {
      const response = await fetch(button.dataset.sharePdf);
      if (!response.ok) continue;
      const blob = await response.blob();
      const file = new File([blob], button.dataset.filename, { type: "application/pdf" });
      if (!navigator.canShare({ files: [file] })) continue;
      sharedFiles.set(button, file);
      button.hidden = false;
      if (window.matchMedia("(display-mode: standalone)").matches) {
        const download = button.parentElement.querySelector("[data-download-pdf]");
        if (download) download.hidden = true;
      }
    } catch {
      // Offline, or the browser refused the file: Download stays, as it
      // would without JS. Nothing for the user to do about it.
    }
  }
}
if (window.htmx) window.htmx.onLoad(prepareShareButtons);
else prepareShareButtons(document);
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-share-pdf]");
  const file = button && sharedFiles.get(button);
  if (!file) return;
  try {
    await navigator.share({ files: [file] });
  } catch {
    // Closed without sharing (AbortError): nothing to do.
  }
});

// "Voorbeeld-pdf" in the editor, in the installed app: a new tab there
// takes over the screen with no way back, and what was typed would be lost
// (huismus-intern/besluiten.md, 2026-11-01). So the same POST goes to the frame in a
// dialog over the editor (documents/_editor_dialogs.html); "Sluiten", Esc
// or a tap beside it returns to the editor ("Sluiten" uses the invoker
// command, with the fallback at the top of this file). In a browser tab, in
// the desktop app and without JS it still opens in a new tab. The click
// comes before the submit, so the form already goes to the frame.
let pdfOpener = null;
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-preview-pdf]");
  const dialog = button && document.getElementById(button.dataset.previewPdf);
  if (!dialog || !window.matchMedia("(display-mode: standalone)").matches) return;
  const template = dialog.querySelector("template");
  const frame = template.content.firstElementChild.cloneNode();
  template.after(frame);
  button.formTarget = frame.name;
  pdfOpener = button;
  dialog.showModal();
});

// A receipt (<a data-view-receipt>: "Bonnetje openen" in Verwerken, a
// thumbnail on an expense or among the receipts without one), in the
// installed app: as with "Voorbeeld-pdf", a new tab there takes over the
// screen with no way back, and in Verwerken what was typed would be gone.
// So it opens in the dialog (expenses/_receipt_dialog.html): a PDF in a
// frame, a photo as itself. In a browser tab, in the desktop app and
// without JS the link still opens the file in a new tab.
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-view-receipt]");
  const dialog = link && document.getElementById(link.dataset.viewReceipt);
  if (!dialog || !window.matchMedia("(display-mode: standalone)").matches) return;
  event.preventDefault();
  const template = dialog.querySelector(link.hasAttribute("data-pdf") ? "template[data-pdf]" : "template[data-photo]");
  const shown = template.content.firstElementChild.cloneNode();
  shown.src = link.getAttribute("href");
  if (shown.tagName === "IMG") shown.alt = link.dataset.label;
  else shown.title = link.dataset.label;
  shown.dataset.shown = "";
  dialog.querySelector("h2").textContent = link.dataset.name;
  template.after(shown);
  pdfOpener = link;
  dialog.showModal();
});

document.addEventListener("click", (event) => {
  // A tap on the backdrop lands on the dialog itself, not on its content.
  if (event.target.matches?.("dialog.is-pdf")) event.target.close();
});
// "close" doesn't bubble, hence capture.
document.addEventListener(
  "close",
  (event) => {
    if (!event.target.matches?.("dialog.is-pdf")) return;
    // Gone, so the next preview doesn't first show the previous one.
    event.target.querySelector("iframe, [data-shown]")?.remove();
    // Focus back on the button that opened it; on a phone that one is in
    // the closed "Meer" menu, so on that menu's button.
    const menu = pdfOpener?.closest("[popover]");
    const target = menu && !menu.matches(":popover-open")
      ? document.querySelector(`[popovertarget="${menu.id}"]`)
      : pdfOpener;
    target?.focus();
  },
  true,
);

// "Kopiëren" next to a read-only field (Instellingen → AI-assistenten).
// Only where the browser offers the clipboard (HTTPS or this computer):
// elsewhere the button stays hidden and the field's text is selected by hand.
function showCopyButtons(root) {
  for (const button of root.querySelectorAll("[data-reveal]")) button.hidden = false;
  if (!navigator.clipboard?.writeText) return;
  for (const button of root.querySelectorAll("[data-copy]")) button.hidden = false;
}

// "Toon" next to a hidden field (the key on AI-assistenten): shows it as
// text until "Verberg".
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-reveal]");
  if (!button) return;
  const field = document.getElementById(button.dataset.reveal);
  const shown = field.type === "password";
  field.type = shown ? "text" : "password";
  button.dataset.label ??= button.textContent;
  button.textContent = shown ? button.dataset.hide : button.dataset.label;
});
if (window.htmx) window.htmx.onLoad(showCopyButtons);
else showCopyButtons(document);
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const field = document.getElementById(button.dataset.copy);
  try {
    await navigator.clipboard.writeText(field.value);
  } catch {
    // Refused (no permission): selected, so it can be copied by hand.
    field.select();
    return;
  }
  // The label from before the first click: a second click within the two
  // seconds would otherwise keep "Gekopieerd".
  button.dataset.label ??= button.textContent;
  button.textContent = button.dataset.copied;
  setTimeout(() => (button.textContent = button.dataset.label), 2000);
});

// Bonnetjes lezen: choosing a known service puts its address and model
// (data-url, data-model on its option) in the fields, unless the user typed
// something of their own there: a field is filled only while it is empty
// or still holds another service's suggestion. Without JS, saving fills in
// what was left empty (expenses.reading_views).
document.addEventListener("change", (event) => {
  const select = event.target;
  if (!select.matches?.("[data-service-fields] select[name=provider]")) return;
  const option = select.selectedOptions[0];
  if (!option?.dataset.url) return;
  const suggested = (name) => [...select.options].map((o) => o.dataset[name]).filter(Boolean);
  for (const name of ["url", "model"]) {
    const field = select.form.elements[name];
    if (!field.value || suggested(name).includes(field.value)) field.value = option.dataset[name];
  }
});

// Verwerken: a PDF receipt in the browser's own viewer, only on a wide
// screen (huismus-intern/besluiten.md, 2026-11-06). The frame gets its src
// here, so a phone never loads it: an iPhone shows only the first page in a
// frame, Android often nothing. Without JS: the file's name and "Bonnetje
// openen", as on a phone.
const wideScreen = window.matchMedia("(min-width: 981px)");

// The browser's PDF viewer takes the cursor once it has started, a moment
// after the frame loaded: whoever was typing the amount by then, typed the
// rest into the PDF (#137). Until VIEWER_STARTS_MS after the frame's load,
// focus that lands on the frame goes back to where it was. A frame that
// never loads stops being watched after LOAD_WAIT_MS. Call this before the
// frame gets its src.
const VIEWER_STARTS_MS = 2000;
const LOAD_WAIT_MS = 15000;
function keepFocusHere(frame) {
  // A field can have the cursor already, from before this script ran.
  let last = document.activeElement === document.body ? null : document.activeElement;
  const remember = (event) => {
    if (event.target !== frame) last = event.target;
  };
  const giveBack = () =>
    setTimeout(() => {
      if (document.activeElement !== frame) return;
      if (last?.isConnected) last.focus();
      else frame.blur();
    }, 0);
  document.addEventListener("focusin", remember);
  // Focus that moves into a frame is a blur of this window.
  window.addEventListener("blur", giveBack);
  const stop = () => {
    document.removeEventListener("focusin", remember);
    window.removeEventListener("blur", giveBack);
  };
  const giveUp = setTimeout(stop, LOAD_WAIT_MS);
  frame.addEventListener(
    "load",
    () => {
      clearTimeout(giveUp);
      setTimeout(stop, VIEWER_STARTS_MS);
    },
    { once: true },
  );
}

function showReceiptPdfs(root) {
  for (const frame of root.querySelectorAll("iframe[data-wide-src]")) {
    const wide = wideScreen.matches;
    if (wide && !frame.src) {
      keepFocusHere(frame);
      frame.src = frame.dataset.wideSrc;
    }
    frame.hidden = !wide;
    const file = frame.parentElement.querySelector("[data-pdf-file]");
    if (file) file.hidden = wide;
  }
}
wideScreen.addEventListener("change", () => showReceiptPdfs(document));
if (window.htmx) window.htmx.onLoad(showReceiptPdfs);
else showReceiptPdfs(document);

// The photo first (#188, expenses/photo_views.py): on a phone, a link to the
// new-expense form opens a choice instead (base.html, #camera): the camera,
// a photo or PDF the phone has, or the ordinary form. A chosen file is sent
// at once; Huismus puts it with the receipts and opens the page with the
// amount. Closing the camera leaves the choice open. On a wide screen, in
// the desktop app and without JS, the link is the ordinary form.
const phone = window.matchMedia("(max-width: 760px) and (pointer: coarse)");

// Capture, and no further: htmx's boost listens on the link itself.
document.addEventListener(
  "click",
  (event) => {
    const camera = document.getElementById("camera");
    const link = event.target.closest?.("a[href]");
    if (!camera || !link || !phone.matches || event.defaultPrevented) return;
    if (link.pathname !== camera.dataset.newExpense || link.search) return;
    // "Zonder bonnetje" in the choice itself: the ordinary form.
    if (camera.contains(link)) return;
    event.preventDefault();
    event.stopPropagation();
    link.closest("[popover]")?.hidePopover();
    for (const input of camera.querySelectorAll("input[type=file]")) input.value = "";
    camera.showModal();
  },
  true,
);

// A photo taken or chosen, from that choice or from "Opnieuw" on the photo page:
// sent with fetch, so a failed connection leaves the photo here to send
// again. A photo from the camera isn't always in the library too: a
// browser error page would lose it.
let unsent = null;

function cameraToast(id) {
  for (const toast of document.querySelectorAll("[data-camera-toast]")) toast.remove();
  const template = document.getElementById(id);
  if (template) document.getElementById("toasts")?.append(template.content.cloneNode(true));
}

// A photo made smaller before it is sent: a phone's photo is 3 to 10 MB,
// minutes of uploading on a weak connection, and a receipt reads as well at
// LONG_SIDE pixels. Upright, the way the camera held it. Anything the
// browser can't draw (a PDF, a HEIC outside Safari) and a photo that
// wouldn't get smaller go as they are.
const LONG_SIDE = 2000;
const JPEG_QUALITY = 0.8;

async function smaller(file) {
  if (!file.type.startsWith("image/")) return file;
  try {
    // Not through an <img>: the page's policy allows no blob: addresses.
    const image = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, LONG_SIDE / Math.max(image.width, image.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(image.width * scale);
    canvas.height = Math.round(image.height * scale);
    const context = canvas.getContext("2d");
    // White under a see-through PNG, like paper.
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    image.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.[^.]*$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;
  }
}

// No answer after this long counts as no connection: the photo stays here
// to send again, instead of "Bonnetje uploaden…" for ever.
const UPLOAD_TIMEOUT_MS = 60000;

async function sendPhoto(form, file) {
  unsent = { form, file };
  cameraToast("camera-busy");
  const data = new FormData(form);
  data.set("file", await smaller(file));
  let response;
  try {
    // The header asks Huismus to say where to go (X-Huismus-Go) rather than
    // to redirect: following a redirect here would use up the next page's
    // message, such as why it refused the file (expenses/photo_views.py).
    response = await fetch(form.action, {
      method: "POST",
      body: data,
      headers: { "X-Huismus-Camera": "1" },
      signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
    });
  } catch (error) {
    // No answer in time, or none at all: no connection with Huismus.
    cameraToast(error.name === "TimeoutError" ? "camera-failed" : "camera-offline");
    return;
  }
  if (!response.ok) {
    // Huismus answered, with an error.
    cameraToast("camera-failed");
    return;
  }
  unsent = null;
  // Sent: a browser that brings this page back with its fields filled in
  // (Back, a reload) mustn't find the photo to send a second time.
  for (const input of form.querySelectorAll("input[type=file][data-camera]")) input.value = "";
  // Where Huismus sends it: the photo page, or the ordinary form with the
  // reason it refused the file. Signed out meanwhile: the login page.
  window.location.assign(response.headers.get("X-Huismus-Go") || response.url);
}

document.addEventListener("change", (event) => {
  const input = event.target;
  if (!input.matches?.("input[type=file][data-camera]") || !input.files.length) return;
  // The choice closes: the messages lie under an open dialog.
  input.closest("dialog")?.close();
  sendPhoto(input.form, input.files[0]);
});

document.addEventListener("click", (event) => {
  if (event.target.closest?.("[data-camera-retry]") && unsent) sendPhoto(unsent.form, unsent.file);
});

// A photo taken before this script ran (a slow phone or connection, #227):
// its change event had nobody listening, so it is sent now. So is one
// that failed to send and is still in its field after a reload.
for (const input of document.querySelectorAll("input[type=file][data-camera]")) {
  if (input.files.length) {
    sendPhoto(input.form, input.files[0]);
    break;
  }
}
