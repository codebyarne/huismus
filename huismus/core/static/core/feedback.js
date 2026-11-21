// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

// "Wijs aan op het scherm" in the feedback panel (huismus/core/feedback_views.py,
// huismus-intern/besluiten.md 2026-11-21). Progressive enhancement: without
// this file the panel still sends, only without a picture.
//
// The picture is not a screenshot. Huismus draws the page itself on a canvas
// from what the browser laid out: every box with its background and border,
// and text only where it belongs to the app itself (buttons, menus, field
// names, column heads), never with a digit or an @ in it. All other text,
// and what is typed in a field, becomes a grey bar of the same size. So a
// name, an amount or an IBAN cannot be in it, on any page, and nothing asks
// the browser or the desktop app for permission to record the screen.

// Where text stays readable: the app's own words. Menus, action buttons
// (.btn), field names (.label), column heads, tabs, status labels. Not every
// <button> or <label>: those can hold a customer's name (a choice in a list).
// Text with a digit or an @ is never readable, also here. Known limit: a name
// without digits that someone typed into one of these places (a tab named
// after a customer, say) would stay readable; Huismus has none today.
const READABLE = "th, legend, nav, .nav, .tabbar, .btn, .label, .tab, .seg, .menu, .brand, [class*='pill']";
// Never drawn: the feedback button, its panel and the picking layer.
const OURS = "#feedback-knop, #feedback-paneel, .fb-aanwijzen, .fb-kader, .fb-balk";
// What a click picks: the nearest of these around the element under it.
const PICKABLE = "button, a, tr, li, .field, .card, .btn, table, form, section";
const MAX_WIDTH = 1440;
// The server takes a picture of at most 1.5 MB (feedback.MAX_IMAGE_BYTES);
// as base64 that is 2 MB. A bigger one is drawn again, smaller.
const MAX_DATA_URL = 1_900_000;

const panel = () => document.getElementById("feedback-paneel");
const knop = () => document.getElementById("feedback-knop");

function showButtons(root) {
  root.querySelectorAll?.("[data-fb-aanwijzen]").forEach((button) => (button.hidden = false));
}
showButtons(document);
document.addEventListener("htmx:load", (event) => showButtons(event.target));

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-fb-aanwijzen]")) startPicking();
  if (event.target.closest("[data-fb-weg]")) setImage("");
});

function setImage(dataUrl) {
  const form = document.querySelector("#feedback-inhoud .fb-form");
  if (!form) return;
  form.querySelector("input[name='fb-image']").value = dataUrl;
  const preview = form.querySelector("[data-fb-voorbeeld]");
  preview.hidden = !dataUrl;
  if (dataUrl) preview.src = dataUrl;
  else preview.removeAttribute("src");
  form.querySelector("[data-fb-weg]").hidden = !dataUrl;
  const label = form.querySelector("[data-fb-aanwijzen-tekst]");
  const button = form.querySelector("[data-fb-aanwijzen]");
  label.textContent = dataUrl ? button.dataset.opnieuw : button.dataset.nieuw;
}

// ---------- Picking ----------

function startPicking() {
  const template = document.getElementById("fb-aanwijzen-balk");
  if (!template) return;
  panel()?.hidePopover();
  knop().style.display = "none";

  const layer = document.createElement("div");
  layer.className = "fb-aanwijzen";
  const frame = document.createElement("div");
  frame.className = "fb-kader";
  frame.hidden = true;
  const bar = template.content.firstElementChild.cloneNode(true);
  document.body.append(layer, frame, bar);

  let start = null;
  let dragging = false;

  const stop = () => {
    layer.remove();
    frame.remove();
    bar.remove();
    document.removeEventListener("keydown", onKey, true);
    knop().style.display = "";
  };
  const done = (rect) => {
    stop();
    // One frame later, so the layer is gone from the layout we draw.
    requestAnimationFrame(() => {
      setImage(draw(rect));
      panel()?.showPopover();
    });
  };
  const onKey = (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    stop();
    panel()?.showPopover();
  };
  const show = (rect) => {
    frame.hidden = !rect;
    if (!rect) return;
    Object.assign(frame.style, {
      left: `${rect.left - 3}px`,
      top: `${rect.top - 3}px`,
      width: `${rect.width + 6}px`,
      height: `${rect.height + 6}px`,
    });
  };
  const dragRect = (event) => ({
    left: Math.min(start.x, event.clientX),
    top: Math.min(start.y, event.clientY),
    width: Math.abs(event.clientX - start.x),
    height: Math.abs(event.clientY - start.y),
  });

  layer.addEventListener("pointerdown", (event) => {
    start = { x: event.clientX, y: event.clientY };
    dragging = false;
    layer.setPointerCapture(event.pointerId);
  });
  layer.addEventListener("pointermove", (event) => {
    if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 6) dragging = true;
    show(dragging ? dragRect(event) : pickAt(event.clientX, event.clientY));
  });
  layer.addEventListener("pointerup", (event) => {
    const rect = dragging ? dragRect(event) : pickAt(event.clientX, event.clientY);
    start = null;
    if (rect && rect.width > 4 && rect.height > 4) done(rect);
  });
  bar.querySelector("[data-fb-hele-scherm]").addEventListener("click", () => done(null));
  bar.querySelector("[data-fb-stoppen]").addEventListener("click", () => {
    stop();
    panel()?.showPopover();
  });
  document.addEventListener("keydown", onKey, true);
}

function pickAt(x, y) {
  const under = document.elementsFromPoint(x, y).find((element) => !element.closest(OURS));
  if (!under || under === document.body || under === document.documentElement) return null;
  return (under.closest(PICKABLE) || under).getBoundingClientRect();
}

// ---------- Drawing ----------

// Fully transparent: "transparent", or a computed colour whose alpha is 0
// ("rgba(0, 0, 0, 0)", "oklab(… / 0)").
function clear(color) {
  return !color || color === "transparent" || /[,/]\s*0\)$/.test(color);
}

function box(ctx, left, top, width, height, radius) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(left, top, width, height, Math.min(radius, width / 2, height / 2));
  else ctx.rect(left, top, width, height);
}

function bar(ctx, rect, color) {
  ctx.save();
  ctx.globalAlpha = 0.32;
  ctx.fillStyle = color;
  box(ctx, rect.left, rect.top + rect.height * 0.25, Math.max(rect.width, 4), Math.max(rect.height * 0.5, 3), 3);
  ctx.fill();
  ctx.restore();
}

// What a box shows of its children: its own box when it cuts off what
// overflows (overflow other than visible), and what its parents show.
// clips is a cache for one drawing (draw() makes a new one).
function clipOf(element, clips) {
  const screen = { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
  if (!element || element === document.body || element === document.documentElement) return screen;
  if (clips.has(element)) return clips.get(element);
  const style = getComputedStyle(element);
  let clip = style.position === "fixed" ? screen : clipOf(element.parentElement, clips);
  if (style.overflowX !== "visible" || style.overflowY !== "visible") {
    const own = element.getBoundingClientRect();
    clip = {
      left: Math.max(clip.left, own.left),
      top: Math.max(clip.top, own.top),
      right: Math.min(clip.right, own.right),
      bottom: Math.min(clip.bottom, own.bottom),
    };
  }
  clips.set(element, clip);
  return clip;
}

function clipped(ctx, clip, paint) {
  if (clip.right <= clip.left || clip.bottom <= clip.top) return;
  ctx.save();
  ctx.beginPath();
  ctx.rect(clip.left, clip.top, clip.right - clip.left, clip.bottom - clip.top);
  ctx.clip();
  paint();
  ctx.restore();
}

function skipped(element) {
  return element.matches(`${OURS}, script, style, template, [hidden]`) ||
    (element.matches("[popover]") && !element.matches(":popover-open")) ||
    (element.tagName === "DIALOG" && !element.open);
}

function paintBox(ctx, element, style, rect) {
  const radius = parseFloat(style.borderTopLeftRadius) || 0;
  if (!clear(style.backgroundColor)) {
    ctx.fillStyle = style.backgroundColor;
    box(ctx, rect.left, rect.top, rect.width, rect.height, radius);
    ctx.fill();
  }
  const sides = [
    ["Top", rect.left, rect.top, rect.right, rect.top],
    ["Right", rect.right, rect.top, rect.right, rect.bottom],
    ["Bottom", rect.left, rect.bottom, rect.right, rect.bottom],
    ["Left", rect.left, rect.top, rect.left, rect.bottom],
  ];
  const widths = sides.map(([side]) => parseFloat(style[`border${side}Width`]) || 0);
  if (radius && widths.every((width) => width > 0) && !clear(style.borderTopColor)) {
    ctx.strokeStyle = style.borderTopColor;
    ctx.lineWidth = widths[0];
    box(ctx, rect.left + widths[0] / 2, rect.top + widths[0] / 2, rect.width - widths[0], rect.height - widths[0], radius);
    ctx.stroke();
  } else {
    sides.forEach(([side, x1, y1, x2, y2], index) => {
      const color = style[`border${side}Color`];
      if (!widths[index] || clear(color)) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = widths[index];
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    });
  }
  if (element.matches("img, svg, canvas, video, picture")) {
    ctx.save();
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = style.color;
    box(ctx, rect.left, rect.top, rect.width, rect.height, Math.min(4, rect.width / 4));
    ctx.fill();
    ctx.restore();
  }
  // What is typed in a field is never drawn, only that something is there.
  const typed = element.matches("input:not([type=checkbox], [type=radio], [type=hidden], [type=submit], [type=button]), textarea, select")
    && (element.value || element.tagName === "SELECT");
  if (typed) {
    const padding = parseFloat(style.paddingLeft) || 8;
    const size = parseFloat(style.fontSize) || 15;
    ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const text = element.tagName === "SELECT" ? element.selectedOptions[0]?.text || "" : element.value;
    const width = Math.min(ctx.measureText(text.split("\n")[0]).width, rect.width - 2 * padding);
    const top = element.tagName === "TEXTAREA" ? rect.top + (parseFloat(style.paddingTop) || 8) : rect.top + (rect.height - size) / 2;
    bar(ctx, { left: rect.left + padding, top, width, height: size * 1.4 }, style.color);
  }
}

function paintText(ctx, node) {
  const text = node.textContent.trim();
  const parent = node.parentElement;
  if (!text || !parent || parent.closest(OURS)) return;
  // Text only for screen readers (.sr-only: clipped to 1 px) is not on the screen.
  const own = parent.getBoundingClientRect();
  if (own.width <= 1 && own.height <= 1) return;
  if (parent.checkVisibility && !parent.checkVisibility({ visibilityProperty: true, opacityProperty: true })) return;
  const style = getComputedStyle(parent);
  const range = document.createRange();
  range.selectNodeContents(node);
  const rects = [...range.getClientRects()].filter((rect) => rect.width && rect.height);
  if (!rects.length) return;
  const readable = parent.closest(READABLE) && !/[0-9@]/.test(text) && rects.length === 1;
  if (!readable) {
    rects.forEach((rect) => bar(ctx, rect, style.color));
    return;
  }
  const [rect] = rects;
  ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  ctx.fillStyle = style.color;
  ctx.textBaseline = "middle";
  ctx.fillText(text, rect.left, rect.top + rect.height / 2, rect.width + 2);
}

function primaryColor() {
  const probe = document.createElement("span");
  probe.style.color = "var(--primary)";
  document.body.append(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();
  return color;
}

// The page as Huismus draws it, as a PNG data: URL; rect is what was pointed
// at (null: the whole screen). Small enough for the server, or "".
function draw(rect) {
  let scale = Math.min(1, MAX_WIDTH / innerWidth);
  for (let attempt = 0; attempt < 4; attempt++) {
    const picture = drawAt(rect, scale);
    if (picture.length <= MAX_DATA_URL) return picture;
    scale *= 0.7;
  }
  return "";
}

function drawAt(rect, scale) {
  const width = innerWidth;
  const height = innerHeight;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  const page = getComputedStyle(document.body).backgroundColor;
  ctx.fillStyle = clear(page) ? getComputedStyle(document.documentElement).backgroundColor : page;
  ctx.fillRect(0, 0, width, height);

  const clips = new WeakMap();
  // What is fixed to the screen (the tab bar, the top bar) lies over the
  // page, so it is drawn after it, as the browser does. paintLayer draws one
  // layer: the elements walk first finds the fixed ones inside it and leaves
  // them out (adding them to fixed, drawn later as layers of their own); the
  // text walk then leaves out text that belongs to such an inner layer.
  const fixed = [];
  const innerLayer = (node, root) => fixed.some((layer) => layer !== root && layer.contains(node) && !layer.contains(root));
  const paintLayer = (root) => {
    const elements = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, {
      acceptNode: (element) => {
        if (skipped(element)) return NodeFilter.FILTER_REJECT;
        if (getComputedStyle(element).position === "fixed") {
          fixed.push(element);
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const own = root === document.body ? [] : [root];
    for (let element = elements.nextNode(); element; element = elements.nextNode()) own.push(element);
    for (const element of own) {
      const style = getComputedStyle(element);
      if (style.display === "none") continue;
      if (element.checkVisibility && !element.checkVisibility({ visibilityProperty: true, opacityProperty: true })) continue;
      const area = element.getBoundingClientRect();
      const visible = area.width && area.height && area.bottom > 0 && area.right > 0 && area.top < height && area.left < width;
      if (visible) clipped(ctx, clipOf(element.parentElement, clips), () => paintBox(ctx, element, style, area));
    }
    const texts = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) =>
        node.parentElement?.closest(`${OURS}, script, style, template, [hidden], svg, textarea, select, option`) ||
        innerLayer(node, root)
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT,
    });
    for (let node = texts.nextNode(); node; node = texts.nextNode()) {
      clipped(ctx, clipOf(node.parentElement, clips), () => paintText(ctx, node));
    }
  };
  paintLayer(document.body);
  for (let index = 0; index < fixed.length; index++) paintLayer(fixed[index]);

  if (rect) {
    ctx.strokeStyle = primaryColor();
    ctx.lineWidth = 3;
    box(ctx, rect.left - 3, rect.top - 3, rect.width + 6, rect.height + 6, 8);
    ctx.stroke();
  }
  return canvas.toDataURL("image/png");
}
