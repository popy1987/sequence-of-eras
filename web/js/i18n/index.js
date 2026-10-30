/**
 * Locale runtime: zh / ja / en.
 * Priority: ?lang= → localStorage → navigator → default zh.
 */
import { LOCALES, LOCALE_META, MESSAGES } from "./messages.js";

const STORAGE_KEY = "soe.lang";
const listeners = new Set();

let current = "zh";

function normalize(raw) {
  if (!raw) return null;
  const s = String(raw).trim().toLowerCase();
  if (s === "zh" || s === "zh-cn" || s === "zh_hans" || s === "zh-hans") return "zh";
  if (s === "ja" || s === "jp" || s.startsWith("ja-")) return "ja";
  if (s === "en" || s.startsWith("en-")) return "en";
  return null;
}

export function resolveInitialLocale() {
  const q = normalize(new URLSearchParams(location.search).get("lang"));
  if (q) return q;
  try {
    const stored = normalize(localStorage.getItem(STORAGE_KEY));
    if (stored) return stored;
  } catch (_) {
    /* ignore */
  }
  if (typeof navigator !== "undefined") {
    const nav = normalize(navigator.language) ||
      (navigator.languages || []).map(normalize).find(Boolean);
    if (nav) return nav;
  }
  return "zh";
}

export function getLocale() {
  return current;
}

export function nameKey(locale = current) {
  return LOCALE_META[locale]?.nameKey || "zh_hans";
}

export function t(key, vars = {}, locale = current) {
  const table = MESSAGES[locale] || MESSAGES.zh;
  let text = table[key] ?? MESSAGES.zh[key] ?? key;
  for (const [k, v] of Object.entries(vars)) {
    text = text.replaceAll(`{${k}}`, String(v));
  }
  return text;
}

export function modeLabel(mode, locale = current) {
  if (!mode) return "";
  const key = `mode.${mode}`;
  const translated = t(key, {}, locale);
  return translated === key ? mode : translated;
}

export function setLocale(next, { persist = true, syncUrl = true } = {}) {
  const loc = normalize(next) || "zh";
  if (loc === current) {
    applyDocumentLocale(loc);
    return current;
  }
  current = loc;
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, loc);
    } catch (_) {
      /* ignore */
    }
  }
  if (syncUrl) {
    const url = new URL(location.href);
    url.searchParams.set("lang", loc);
    history.replaceState(null, "", url);
  }
  applyDocumentLocale(loc);
  listeners.forEach((fn) => fn(loc));
  return current;
}

export function onLocaleChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function applyDocumentLocale(locale = current) {
  const meta = LOCALE_META[locale] || LOCALE_META.zh;
  document.documentElement.lang = meta.htmlLang;
  document.title = t("meta.title", {}, locale);
  const desc = document.querySelector('meta[name="description"]');
  if (desc) desc.setAttribute("content", t("meta.description", {}, locale));

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (!key) return;
    const attr = node.getAttribute("data-i18n-attr");
    const value = t(key, {}, locale);
    if (attr) node.setAttribute(attr, value);
    else node.textContent = value;
  });

  document.querySelectorAll("[data-lang]").forEach((btn) => {
    const active = btn.getAttribute("data-lang") === locale;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
}

export function bindLanguageSwitcher(root = document) {
  root.querySelectorAll("[data-lang]").forEach((btn) => {
    btn.addEventListener("click", () => {
      setLocale(btn.getAttribute("data-lang"));
    });
  });
}

export { LOCALES, LOCALE_META };
