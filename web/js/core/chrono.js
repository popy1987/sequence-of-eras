/** Calendar / era label helpers (engine-agnostic). */

import { t, nameKey, getLocale } from "../i18n/index.js";
import { pickName } from "./names.js";

export function toJdn(year, month, day) {
  const a = Math.floor((14 - month) / 12);
  const y = year + 4800 - a;
  const m = month + 12 * a - 3;
  return (
    day +
    Math.floor((153 * m + 2) / 5) +
    365 * y +
    Math.floor(y / 4) -
    Math.floor(y / 100) +
    Math.floor(y / 400) -
    32045
  );
}

const EPOCH_JDN = toJdn(-200000, 1, 1);

export function ordinal(year, month = 7, day = 1) {
  return toJdn(year, month, day) - EPOCH_JDN;
}

export function formatGregorianYear(y, locale = getLocale()) {
  if (y > 0) return t("gregorian.ce", { y }, locale);
  return t("gregorian.bce", { y: 1 - y }, locale);
}

function covering(list, ord, fromKey = "query_from", toKey = "query_to") {
  return (list || []).filter((item) => {
    const a = item[fromKey];
    const b = item[toKey] == null ? Number.POSITIVE_INFINITY : item[toKey];
    return a <= ord && ord <= b;
  });
}

function eraYearText(n, locale) {
  if (locale === "en") {
    return n === 1 ? "1" : String(n);
  }
  if (n === 1) return t("era.gannen", {}, locale);
  if ((locale === "zh" || locale === "ja") && n >= 2 && n <= 10) {
    const digits = ["", "", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
    return `${digits[n]}${t("era.yearSuffix", {}, locale)}`;
  }
  return `${n}${t("era.yearSuffix", {}, locale)}`;
}

export function japanEraLabel(atlas, year, month = 7, day = 1, locale = getLocale()) {
  const ord = ordinal(year, month, day);
  const hit = covering(atlas.eras_japan, ord)[0];
  if (!hit) {
    const prefix = t("chrono.japanPrefix", {}, locale);
    if (year < 645) return `${prefix}${t("era.jp.beforeNengo", {}, locale)}`;
    return `${prefix}${t("era.jp.gap", {}, locale)}`;
  }
  const name = pickName(hit.names, locale);
  const startY = hit.from.year;
  let n;
  if (hit.open_ended || hit.from.year >= 1873) {
    n = year - startY + 1;
    if (year === startY) {
      const before =
        month < hit.from.month ||
        (month === hit.from.month && day < hit.from.day);
      if (before) n = 0;
    }
  } else {
    n = year - startY + 1;
  }
  if (n <= 0) return `${name}${t("era.jp.beforeChange", {}, locale)}`;
  if (locale === "en") return `${name} ${eraYearText(n, locale)}`;
  return `${name}${eraYearText(n, locale)}`;
}

export function chinaRefLabel(atlas, year, locale = getLocale()) {
  const ord = ordinal(year, 7, 1);
  const dyn = covering(atlas.dynasties_china, ord)[0];
  const prefix = t("chrono.chinaPrefix", {}, locale);
  if (!dyn) {
    return year < -841
      ? `${prefix}${t("era.cn.beforeGonghe", {}, locale)}`
      : `${prefix}${t("era.cn.gap", {}, locale)}`;
  }
  const dName = pickName(dyn.names, locale);
  if (dyn.id === "dynasty.prc") {
    return `${prefix}${t("era.cn.sameAsGregorian", {}, locale)}`;
  }
  const era = covering(atlas.eras_china, ord)[0];
  if (era) {
    const eName = pickName(era.names, locale);
    const n = year - era.from_year + 1;
    if (locale === "en") return `${dName} ${eName} ${eraYearText(n, locale)}`;
    return `${dName}${eName}${eraYearText(n, locale)}`;
  }
  if (dyn.from_year != null) {
    const n = year - dyn.from_year + 1;
    if (locale === "en") {
      return `${dName} ${eraYearText(n, locale)}${t("era.cn.dynastyYear", {}, locale)}`;
    }
    return `${dName}${eraYearText(n, locale)}${t("era.cn.dynastyYear", {}, locale)}`;
  }
  return dName;
}

// re-export for callers that only need the mapping
export { nameKey };
