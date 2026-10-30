/**
 * Application shell: timeline, chrono labels, inspector, atlasAPI, i18n.
 * Talks to map engines only through MapFrame + select events.
 */
import { resolveMapEngineId } from "./config.js";
import {
  formatGregorianYear,
  japanEraLabel,
  chinaRefLabel,
} from "./core/chrono.js";
import {
  pickName,
  periodLabel,
  buildMapFrame,
  loadAtlas,
  activeDisputes,
  phaseForYear,
} from "./core/atlas_model.js";
import { createMapEngine } from "./map/registry.js";
import { MAP_ENGINE_EVENTS, MAP_SELECT_KIND } from "./map/contract.js";
import {
  resolveInitialLocale,
  setLocale,
  getLocale,
  t,
  modeLabel,
  onLocaleChange,
  applyDocumentLocale,
  bindLanguageSwitcher,
} from "./i18n/index.js";

const $ = (sel) => document.querySelector(sel);

function openInspector(title, meta, body, parties) {
  $("#inspector").hidden = false;
  $("#inspector-title").textContent = title;
  $("#inspector-meta").textContent = meta || "";
  $("#inspector-body").textContent = body || "";
  const ul = $("#inspector-parties");
  ul.innerHTML = "";
  (parties || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    ul.appendChild(li);
  });
}

function renderLegend(phase) {
  const list = $("#legend-list");
  list.innerHTML = "";
  (phase.polities || []).forEach((p) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="swatch" style="background:${p.color}"></span><span></span>`;
    li.querySelector("span:last-child").textContent =
      `${pickName(p.names)} · ${modeLabel(p.mode)}`;
    list.appendChild(li);
  });
  if (!(phase.polities || []).length) {
    const li = document.createElement("li");
    li.innerHTML =
      `<span class="swatch" style="background:#5b7c6a"></span><span>${t("legend.empty")}</span>`;
    list.appendChild(li);
  }
}

function stripPeriodSuffix(name) {
  return String(name || "")
    .replace(/时代|時代| period$/i, "")
    .trim();
}

function setBootMessage(text, { error = false } = {}) {
  const overlay = $("#boot-overlay");
  const msg = $("#boot-message");
  if (msg) msg.textContent = text;
  if (overlay) overlay.classList.toggle("is-error", Boolean(error));
}

function finishBoot() {
  const overlay = $("#boot-overlay");
  if (overlay) overlay.hidden = true;
}

async function boot() {
  setLocale(resolveInitialLocale(), { persist: true, syncUrl: true });
  applyDocumentLocale();
  bindLanguageSwitcher();
  setBootMessage(t("boot.loading"));

  const atlas = await loadAtlas();
  setBootMessage(t("boot.rendering"));

  const engineId = resolveMapEngineId();
  const host = $("#map-host");
  const map = createMapEngine(engineId, host, {
    ariaLabel: t("map.aria"),
  });

  const yearMin = atlas.meta.year_min;
  const yearMax = atlas.meta.year_max;
  let year = atlas.meta.default_year;
  let playing = false;
  let playTimer = null;
  let lastSelect = null;

  const slider = $("#year-slider");
  const yearInput = $("#year-input");
  slider.min = String(yearMin);
  slider.max = String(yearMax);
  slider.step = "1";
  yearInput.min = String(yearMin);
  yearInput.max = String(yearMax);

  function refreshChrome() {
    $("#year-min-label").textContent = formatGregorianYear(yearMin);
    $("#year-max-label").textContent = formatGregorianYear(yearMax);
    const engineTag = $("#engine-tag");
    if (engineTag) engineTag.textContent = t("nav.engine", { id: engineId });
    $("#btn-play").textContent = playing ? t("nav.pause") : t("nav.play");
  }

  function rebuildTicks() {
    const ticks = $("#period-ticks");
    ticks.innerHTML = "";
    atlas.periods
      .filter((p) => !p.region_id && p.from_year != null)
      .forEach((p) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "tick";
        el.dataset.periodId = p.id;
        el.textContent = stripPeriodSuffix(pickName(p.names));
        el.title = `${pickName(p.names)} (${p.from_year}–${p.to_year ?? "…"})`;
        el.addEventListener("click", () => setYear(p.from_year));
        ticks.appendChild(el);
      });
  }

  function setYear(next, { pushUrl = true } = {}) {
    year = Math.max(yearMin, Math.min(yearMax, Math.round(Number(next)) || year));
    if (year === 0) year = -1;
    slider.value = String(year);
    yearInput.value = String(year);

    const locale = getLocale();
    const frame = buildMapFrame(atlas, year, locale);
    const phase = frame.phase;

    $("#phase-label").textContent =
      `${pickName(phase.label)} · ${formatGregorianYear(year)}`;
    $("#chrono-gregorian").textContent = formatGregorianYear(year);
    $("#chrono-japan").textContent =
      `${t("chrono.japanPrefix")} ${japanEraLabel(atlas, year)}`;
    $("#chrono-china").textContent =
      `${t("chrono.chinaPrefix")} ${chinaRefLabel(atlas, year)}`;
    $("#chrono-period").textContent =
      `${t("chrono.periodPrefix")} ${periodLabel(atlas, year)}`;

    map.setFrame(frame);
    renderLegend(phase);

    [...$("#period-ticks").children].forEach((el) => {
      el.classList.toggle("is-current", el.dataset.periodId === phase.id);
    });

    if (pushUrl) {
      const url = new URL(location.href);
      url.searchParams.set("year", String(year));
      url.searchParams.set("lang", locale);
      history.replaceState(null, "", url);
    }
  }

  function showSelect(kind, data) {
    lastSelect = { kind, data };
    if (kind === MAP_SELECT_KIND.POLITY) {
      openInspector(
        pickName(data.names),
        t("inspect.controlMode", { mode: modeLabel(data.mode) }),
        t("inspect.polityBody"),
        []
      );
    } else if (kind === MAP_SELECT_KIND.MARKER) {
      const lines = [t("inspect.coords", { lon: data.lon, lat: data.lat })];
      let body = t("inspect.markerBody");
      if (data.kind === "kofun" && data.burial_from != null && data.burial_to != null) {
        body = data.note || t("inspect.kofunBody");
        lines.unshift(
          t("inspect.kofunBurial", {
            from: data.burial_from,
            to: data.burial_to,
          })
        );
        if (data.confidence) {
          lines.push(t("inspect.kofunConfidence", { confidence: data.confidence }));
        }
      } else if (data.kind === "event") {
        body = data.short_note || t("inspect.eventBody");
        const from = data.from_year;
        const to = data.to_year;
        lines.unshift(
          from === to
            ? t("inspect.eventYear", { year: from })
            : t("inspect.eventRange", { from, to })
        );
        if (data.conflict_class) {
          lines.push(t(`conflict.${data.conflict_class}`));
        }
        if (data.event_kind) {
          lines.push(t("inspect.eventKind", { kind: data.event_kind }));
        }
      }
      openInspector(pickName(data.names), data.kind, body, lines);
    } else if (kind === MAP_SELECT_KIND.DISPUTE) {
      openInspector(
        pickName(data.names) || data.id,
        t("inspect.disputeMeta", {
          kind: data.kind || "",
          sensitivity: data.sensitivity || "",
        }),
        data.short_note || t("inspect.disputeBody"),
        (data.parties || []).map(
          (p) =>
            `${pickName(p.actor_names) || p.actor_id} · ${p.role} · ${p.claim_status}`
        )
      );
    }
  }

  map.on(MAP_ENGINE_EVENTS.SELECT, ({ kind, data }) => showSelect(kind, data));

  $("#inspector-close").addEventListener("click", () => {
    $("#inspector").hidden = true;
    lastSelect = null;
  });

  slider.addEventListener("input", () => setYear(slider.value));
  yearInput.addEventListener("change", () => setYear(yearInput.value));
  $("#btn-today").addEventListener("click", () =>
    setYear(new Date().getFullYear())
  );
  $("#btn-play").addEventListener("click", () => {
    playing = !playing;
    $("#btn-play").setAttribute("aria-pressed", String(playing));
    $("#btn-play").textContent = playing ? t("nav.pause") : t("nav.play");
    if (playing) {
      playTimer = setInterval(() => {
        const step = year < 500 ? 20 : year < 1500 ? 5 : 1;
        let n = year + step;
        if (n > yearMax) n = yearMin;
        setYear(n);
      }, 700);
    } else if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
  });

  onLocaleChange(() => {
    applyDocumentLocale();
    refreshChrome();
    rebuildTicks();
    setYear(year, { pushUrl: true });
    if (lastSelect) showSelect(lastSelect.kind, lastSelect.data);
  });

  refreshChrome();
  rebuildTicks();

  const params = new URLSearchParams(location.search);
  if (params.has("year")) year = Number(params.get("year"));
  setYear(year, { pushUrl: false });
  map.fitHome();

  window.atlasAPI = {
    gotoYear(y) {
      setYear(y);
      return { year };
    },
    setLang(lang) {
      return setLocale(lang);
    },
    getLang() {
      return getLocale();
    },
    inspectYear(y = year) {
      const phase = phaseForYear(atlas, y);
      return {
        year: y,
        lang: getLocale(),
        engine: engineId,
        gregorian: formatGregorianYear(y),
        japan: japanEraLabel(atlas, y),
        china: chinaRefLabel(atlas, y),
        period: periodLabel(atlas, y),
        phase: phase.id,
        polities: (phase.polities || []).map((p) => ({
          id: p.id,
          name: pickName(p.names),
          mode: p.mode,
        })),
        disputes: activeDisputes(atlas, y).map((d) => d.id),
      };
    },
    listPhases() {
      return atlas.phases.map((p) => ({
        id: p.id,
        from: p.from_year,
        to: p.to_year,
        label: pickName(p.label),
      }));
    },
    listEngines() {
      return { current: engineId };
    },
  };

  finishBoot();

  console.info(
    `atlasAPI ready (engine=${engineId}, lang=${getLocale()}): atlasAPI.setLang('ja'), atlasAPI.gotoYear(-2000)`
  );
}

boot().catch((err) => {
  setBootMessage(err.message || t("error.atlasMissing"), { error: true });
  console.error(err);
});
