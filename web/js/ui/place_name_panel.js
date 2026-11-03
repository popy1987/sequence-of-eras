/**
 * Overlay: proportional place-name timeline for a modern prefecture.
 */
import { pickName } from "../core/names.js";
import {
  axisRange,
  spanStyle,
  formatYearRange,
  kindLabel,
  kindColor,
} from "../core/place_name_index.js";
import { getLocale, t } from "../i18n/index.js";

/**
 * @param {object} opts
 * @param {HTMLElement} opts.root
 * @param {(year: number) => void} opts.onJumpYear
 * @param {() => void} [opts.onClose]
 * @param {(y: number) => string} opts.formatYear
 */
export function createPlaceNamePanel({ root, onJumpYear, onClose, formatYear }) {
  const titleEl = root.querySelector("#place-name-title");
  const metaEl = root.querySelector("#place-name-meta");
  const trackEl = root.querySelector("#place-name-track");
  const listEl = root.querySelector("#place-name-list");
  const legendEl = root.querySelector("#place-name-legend");
  const axisMin = root.querySelector("#place-name-axis-min");
  const axisMax = root.querySelector("#place-name-axis-max");
  const closeBtn = root.querySelector("#place-name-close");

  closeBtn?.addEventListener("click", () => {
    hide();
    onClose?.();
  });

  function hide() {
    root.hidden = true;
  }

  function show(index, entry) {
    if (!entry) {
      hide();
      return;
    }
    const locale = getLocale();
    const range = axisRange(index, entry);
    titleEl.textContent = pickName(entry.names, locale) || entry.code;
    metaEl.textContent = t("placeName.meta", {
      code: entry.code,
      n: String((entry.spans || []).length),
    });

    if (axisMin) axisMin.textContent = formatYear(range.yearMin);
    if (axisMax) axisMax.textContent = formatYear(range.yearMax);

    // Legend
    legendEl.innerHTML = "";
    const kinds = index.kinds || {};
    Object.keys(kinds).forEach((k) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="pn-swatch" style="background:${kindColor(k)}"></span>${kindLabel(index, k, locale)}`;
      legendEl.appendChild(li);
    });

    // Absolute proportional track: each span is one lane; width ∝ duration.
    trackEl.innerHTML = "";
    const spans = [...(entry.spans || [])].sort(
      (a, b) => a.from_year - b.from_year || a.to_year - b.to_year
    );
    const laneH = 16;
    const laneGap = 3;
    trackEl.style.height = `${Math.max(56, spans.length * (laneH + laneGap) + 12)}px`;
    spans.forEach((s, i) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "pn-bar";
      const st = spanStyle(s, range);
      el.style.left = st.left;
      el.style.width = st.width;
      el.style.background = st.background;
      el.style.top = `${6 + i * (laneH + laneGap)}px`;
      el.style.height = `${laneH}px`;
      el.style.bottom = "auto";
      el.title = `${pickName(s.names, locale)} · ${formatYearRange(s.from_year, s.to_year, formatYear)}`;
      el.textContent = pickName(s.names, locale);
      el.addEventListener("click", () => onJumpYear(s.from_year));
      trackEl.appendChild(el);
    });

    // Detail list (same order)
    listEl.innerHTML = "";
    spans.forEach((s) => {
      const li = document.createElement("li");
      li.className = "pn-row";
      const dur = s.to_year - s.from_year;
      li.innerHTML = `
        <span class="pn-row-swatch" style="background:${kindColor(s.kind)}"></span>
        <div class="pn-row-body">
          <strong>${pickName(s.names, locale)}</strong>
          <span class="pn-row-meta">${kindLabel(index, s.kind, locale)} · ${formatYearRange(s.from_year, s.to_year, formatYear)} · ${t("placeName.duration", { n: String(dur) })}</span>
          ${s.note ? `<span class="pn-row-note">${s.note}</span>` : ""}
        </div>
        <button type="button" class="ghost-btn pn-jump" data-year="${s.from_year}">${t("placeName.jump")}</button>
      `;
      li.querySelector(".pn-jump")?.addEventListener("click", () =>
        onJumpYear(s.from_year)
      );
      listEl.appendChild(li);
    });

    root.hidden = false;
  }

  return { show, hide, isOpen: () => !root.hidden };
}
