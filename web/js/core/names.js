import { nameKey, getLocale } from "../i18n/index.js";

/** Resolve a multilingual `names` object using UI locale (zh→zh_hans). */
export function pickName(names, locale = getLocale()) {
  if (!names) return "";
  const primary = nameKey(locale);
  const order =
    locale === "ja"
      ? ["ja", "zh_hans", "en"]
      : locale === "en"
        ? ["en", "ja", "zh_hans"]
        : ["zh_hans", "ja", "en"];
  if (names[primary]) return names[primary];
  for (const k of order) {
    if (names[k]) return names[k];
  }
  return "";
}
