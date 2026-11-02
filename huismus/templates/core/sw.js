// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

// Service worker for the installed app (huismus/core/pwa.py). It keeps one page,
// the offline page, and shows it when a page can't be fetched. Everything
// else goes to the server as if this file didn't exist.

const CACHE = "huismus-offline-v1";
const OFFLINE_URL = "{{ offline_url }}";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.add(new Request(OFFLINE_URL, { cache: "reload" }))),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Older versions of this cache, from an earlier sw.js.
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  // Only opening a page. Forms (POST), htmx requests, files and downloads
  // are left alone; offline they fail as they would without this worker.
  if (event.request.mode !== "navigate" || event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
});
