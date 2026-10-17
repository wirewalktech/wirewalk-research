/* Wirewalk source fields: how a visitor arrived, sent with an inquiry.

   First-party and self-contained. No cookies, no third-party requests, and this
   script makes no network request of its own: the only place the data goes is
   the inquiry form the visitor chooses to send.

   1. Capture. On each arrival at this site, the campaign tags in the link
      (utm_source, utm_medium, utm_campaign, utm_term, utm_content), ad click ids
      (gclid, gbraid, wbraid, msclkid, rdt_cid, li_fat_id, fbclid), the landing page PATH (never its query
      string) and the referring site's HOST NAME (never the full referring URL)
      are kept in this browser's localStorage under "ww_src" as a first touch and
      a last touch. Each touch expires 30 days after it was recorded; an expired
      or unreadable record is deleted when read.
        - A tagged link or a visit from another site is a new touch: it replaces
          the last touch, and becomes the first touch too if there is none.
        - A visit with no referrer and no tags (typed or bookmarked) only fills an
          empty first touch, so it never overwrites the campaign that brought
          someone here.
        - Moving between pages of this site is not a new touch.
   2. Send. When a form that posts to the Wirewalk inquiry endpoint
      (/api/enquiry) is submitted, hidden _src_* inputs are added to it: the last
      touch (or the first, or this visit) as _src_utm_*, _src_gclid, _src_rdt_cid,
      _src_li_fat_id, _src_fbclid, _src_msclkid, _src_gbraid, _src_wbraid, _src_landing and _src_referrer, and the first
      touch, when it differs, as _src_first_*. The portal computes the channel
      server-side from these; nothing here decides it. A page can restrict this
      to particular forms with <meta name="ww-src-forms" content="<selector>">.
   Storage may be blocked (private windows, strict settings): every access is
   wrapped, and the current visit is still sent from memory. Without JavaScript
   the form posts exactly as it always did. Values are only ever written into
   input values (never markup), clipped, and stripped of control characters. */
(function () {
  "use strict";
  if (window.__wwSrcFields) return;
  window.__wwSrcFields = true;

  var KEY = "ww_src", TTL = 30 * 24 * 3600 * 1000;
  var TAGS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];
  var CLICKS = ["gclid", "rdt_cid", "li_fat_id", "fbclid", "msclkid", "gbraid", "wbraid"];
  var FIELDS = TAGS.concat(CLICKS, ["landing", "referrer"]);
  var LIMIT = { landing: 300, referrer: 200 };
  var ENDPOINT = /\/api\/enquiry\/?$/;

  function clip(v, n) {
    return String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, n);
  }
  function limit(k) { return LIMIT[k] || (k.indexOf("utm_") === 0 ? 200 : 100); }

  /* A stored touch is trusted only as far as its shape: known keys, strings, a time. */
  function clean(t, now) {
    if (!t || typeof t !== "object" || typeof t.at !== "number" || !(now - t.at < TTL) || t.at > now + 60000) return null;
    var out = { at: t.at };
    FIELDS.forEach(function (k) { if (typeof t[k] === "string" && clip(t[k], limit(k))) out[k] = clip(t[k], limit(k)); });
    return out;
  }
  function read(now) {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return {};
      var r = JSON.parse(raw) || {}, first = clean(r.first, now), last = clean(r.last, now);
      if (!first && !last) { localStorage.removeItem(KEY); return {}; }
      return { first: first, last: last };
    } catch (e) {
      try { localStorage.removeItem(KEY); } catch (e2) { /* storage blocked */ }
      return {};
    }
  }
  function write(r) {
    try { localStorage.setItem(KEY, JSON.stringify({ first: r.first || null, last: r.last || null })); }
    catch (e) { /* storage blocked: the in-memory copy still serves this page */ }
  }

  /* ---------------- this visit ---------------- */
  var now = Date.now(), here = location.hostname.toLowerCase();
  var q; try { q = new URLSearchParams(location.search); } catch (e) { q = null; }
  var touch = { at: now, landing: clip(location.pathname, LIMIT.landing) }, tagged = false;
  TAGS.concat(CLICKS).forEach(function (k) {
    var v = q && clip(q.get(k), limit(k));
    if (v) { touch[k] = v; tagged = true; }
  });
  var refHost = "", internal = false;
  try {
    if (document.referrer) {
      refHost = new URL(document.referrer).hostname.toLowerCase();
      if (refHost === here) { internal = true; refHost = ""; }
    }
  } catch (e) { refHost = ""; }
  if (refHost) touch.referrer = clip(refHost, LIMIT.referrer);

  var rec = read(now);
  if (tagged || refHost) {
    rec.last = touch;
    if (!rec.first) rec.first = touch;
    write(rec);
  } else if (!internal && !rec.first) {
    rec.first = touch;
    write(rec);
  }

  /* ---------------- on submit ---------------- */
  function values() {
    var r = read(Date.now());
    var first = r.first || rec.first, last = r.last || rec.last;
    var main = last || first || touch, out = [];
    FIELDS.forEach(function (k) { if (main[k]) out.push(["_src_" + k, main[k]]); });
    if (first && first !== main && first.at !== main.at)
      FIELDS.forEach(function (k) { if (first[k]) out.push(["_src_first_" + k, first[k]]); });
    return out;
  }
  /* Optional opt-in: <meta name="ww-src-forms" content="#some-form"> limits the
     fields to forms matching that selector (a site that wants other inquiry forms
     left exactly as they are). Without the meta, every inquiry form qualifies. */
  var only = document.querySelector('meta[name="ww-src-forms"]');
  only = only ? only.getAttribute("content") || "" : "";
  function isEnquiry(form) {
    if (!form || form.nodeName !== "FORM" || !ENDPOINT.test(form.getAttribute("action") || "")) return false;
    if (!only) return true;
    try { return form.matches(only); } catch (e) { return false; }
  }
  function owned(form, name) {
    for (var i = 0; i < form.elements.length; i++) {
      var el = form.elements[i];
      if (el.name === name && !el.hasAttribute("data-ww-src")) return true;
    }
    return false;
  }

  /* Hidden inputs, added once the page's own handlers have let the submit stand. */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || !isEnquiry(form)) return;
    try {
      Array.prototype.slice.call(form.querySelectorAll("input[data-ww-src]")).forEach(function (el) { el.parentNode.removeChild(el); });
      values().forEach(function (kv) {
        if (owned(form, kv[0])) return;
        var i = document.createElement("input");
        i.type = "hidden"; i.name = kv[0]; i.value = kv[1];
        i.setAttribute("data-ww-src", "");
        form.appendChild(i);
      });
    } catch (err) { /* attribution must never stop an inquiry */ }
  });

  /* form.submit() skips the submit event but still builds the form data. */
  document.addEventListener("formdata", function (e) {
    if (!isEnquiry(e.target) || !e.formData) return;
    try { values().forEach(function (kv) { if (!e.formData.has(kv[0])) e.formData.append(kv[0], kv[1]); }); }
    catch (err) { /* never block the send */ }
  });
})();
