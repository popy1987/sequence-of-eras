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
  spinePeriodForYear,
  spinePeriods,
  buildMapFrame,
  loadAtlas,
  activeDisputes,
  phaseForYear,
} from "./core/atlas_model.js";
import { createTimelineScale } from "./core/timeline_scale.js";
import {
  loadPlaceNameIndex,
  getPrefectureEntry,
} from "./core/place_name_index.js";
import { createPlaceNamePanel } from "./ui/place_name_panel.js";
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

  let placeNameIndex = null;
  try {
    placeNameIndex = await loadPlaceNameIndex();
  } catch (err) {
    console.warn("[place-name-index]", err);
  }

  const engineId = resolveMapEngineId();
  const host = $("#map-host");
  const map = createMapEngine(engineId, host, {
    ariaLabel: t("map.aria"),
  });
  // MapLibre (and future CDN engines) expose ready; SVG resolves immediately.
  if (map.ready) {
    try {
      await map.ready;
    } catch (err) {
      console.error(err);
      setBootMessage(err.message || t("error.atlasMissing"), { error: true });
      throw err;
    }
  }

  const yearMin = atlas.meta.year_min;
  const yearMax = atlas.meta.year_max;
  const scale = createTimelineScale(yearMin, yearMax);
  let year = atlas.meta.default_year;
  let playing = false;
  let playTimer = null;
  /** Play mode: +1 year per tick; interval depends on speed multiplier. */
  const PLAY_STEP_YEARS = 1;
  const PLAY_INTERVAL_BY_SPEED = {
    1: 10_000,
    2: 5_000,
    4: 2_500,
    10: 1_000,
  };
  let playSpeed = 1;
  let lastSelect = null;

  const slider = $("#year-slider");
  const yearInput = $("#year-input");
  // Slider is warped position space; year input stays calendar years.
  slider.min = "0";
  slider.max = String(scale.SLIDER_MAX);
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
    const spine = spinePeriods(atlas);
    let lastPos = -1;
    const minGap = 0.035;
    spine.forEach((p) => {
      const pos = scale.yearToPos(p.from_year);
      // Drop labels that would collide; keep data alignment with slider.
      if (lastPos >= 0 && pos - lastPos < minGap) return;
      lastPos = pos;
      const el = document.createElement("button");
      el.type = "button";
      el.className = "tick";
      el.dataset.periodId = p.id;
      el.dataset.fromYear = String(p.from_year);
      el.style.left = `${(pos * 100).toFixed(3)}%`;
      el.textContent = stripPeriodSuffix(pickName(p.names));
      el.title = `${pickName(p.names)} (${p.from_year}–${p.to_year ?? "…"})`;
      el.addEventListener("click", () => setYear(p.from_year));
      ticks.appendChild(el);
    });
  }

  function setYear(next, { pushUrl = true } = {}) {
    year = Math.max(yearMin, Math.min(yearMax, Math.round(Number(next)) || year));
    if (year === 0) year = -1;
    slider.value = String(scale.yearToSlider(year));
    yearInput.value = String(year);

    const locale = getLocale();
    const frame = buildMapFrame(atlas, year, locale);
    const phase = frame.phase;
    const spinePeriod = spinePeriodForYear(atlas, year);

    $("#phase-label").textContent =
      `${periodLabel(atlas, year)} · ${formatGregorianYear(year)}`;
    $("#chrono-gregorian").textContent = formatGregorianYear(year);
    $("#chrono-japan").textContent =
      `${t("chrono.japanPrefix")} ${japanEraLabel(atlas, year)}`;
    $("#chrono-china").textContent =
      `${t("chrono.chinaPrefix")} ${chinaRefLabel(atlas, year)}`;
    $("#chrono-period").textContent =
      `${t("chrono.periodPrefix")} ${periodLabel(atlas, year)}`;

    map.setFrame(frame);
    renderLegend(phase);

    const periodId = spinePeriod && spinePeriod.id;
    [...$("#period-ticks").children].forEach((el) => {
      el.classList.toggle("is-current", el.dataset.periodId === periodId);
    });

    if (pushUrl) {
      const url = new URL(location.href);
      url.searchParams.set("year", String(year));
      url.searchParams.set("lang", locale);
      history.replaceState(null, "", url);
    }
  }

  const placeNamePanel = createPlaceNamePanel({
    root: $("#place-name-panel"),
    formatYear: formatGregorianYear,
    onJumpYear: (y) => setYear(y),
    onClose: () => {
      if (lastSelect?.kind === MAP_SELECT_KIND.PREFECTURE) lastSelect = null;
    },
  });

  function showSelect(kind, data) {
    lastSelect = { kind, data };
    if (kind === MAP_SELECT_KIND.PREFECTURE) {
      $("#inspector").hidden = true;
      const entry = getPrefectureEntry(placeNameIndex, data.code);
      if (entry) {
        placeNamePanel.show(placeNameIndex, entry);
      } else {
        placeNamePanel.hide();
        openInspector(
          pickName(data.names) || data.code,
          data.code || "",
          t("placeName.missing"),
          []
        );
      }
      return;
    }
    placeNamePanel.hide();
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

  slider.addEventListener("input", () => setYear(scale.sliderToYear(slider.value)));
  yearInput.addEventListener("change", () => setYear(yearInput.value));
  $("#btn-today").addEventListener("click", () =>
    setYear(new Date().getFullYear())
  );
  function playIntervalMs() {
    return PLAY_INTERVAL_BY_SPEED[playSpeed] ?? PLAY_INTERVAL_BY_SPEED[1];
  }

  function syncSpeedButtons() {
    document.querySelectorAll(".speed-btn").forEach((btn) => {
      const on = Number(btn.dataset.speed) === playSpeed;
      btn.setAttribute("aria-pressed", String(on));
    });
  }

  function clearPlayTimer() {
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
  }

  function stopPlayback() {
    playing = false;
    clearPlayTimer();
    const btn = $("#btn-play");
    btn.setAttribute("aria-pressed", "false");
    btn.textContent = t("nav.play");
  }

  function tickPlayback() {
    let n = year + PLAY_STEP_YEARS;
    if (n === 0) n = 1; // no year 0
    if (n > yearMax) {
      stopPlayback();
      return;
    }
    setYear(n); // rebuilds MapFrame + map.setFrame once per tick
  }

  function startPlayTimer() {
    clearPlayTimer();
    playTimer = setInterval(tickPlayback, playIntervalMs());
  }

  function setPlaySpeed(speed) {
    const next = Number(speed);
    if (!PLAY_INTERVAL_BY_SPEED[next]) return;
    playSpeed = next;
    syncSpeedButtons();
    if (playing) startPlayTimer();
  }

  $("#btn-play").addEventListener("click", () => {
    if (playing) {
      stopPlayback();
      return;
    }
    playing = true;
    const btn = $("#btn-play");
    btn.setAttribute("aria-pressed", "true");
    btn.textContent = t("nav.pause");
    startPlayTimer();
  });

  document.querySelectorAll(".speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => setPlaySpeed(btn.dataset.speed));
  });
  syncSpeedButtons();

  onLocaleChange(() => {
    applyDocumentLocale();
    refreshChrome();
    rebuildTicks();
    setYear(year, { pushUrl: true });
    if (lastSelect) showSelect(lastSelect.kind, lastSelect.data);
    else placeNamePanel.hide();
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
    getTerrainCalib() {
      return map.getTerrainCalib?.() ?? null;
    },
    dumpTerrainCalib() {
      const dump = map.dumpTerrainCalib?.() ?? null;
      if (dump) console.log(dump);
      return dump;
    },
    getTerrainAffine() {
      return map.getTerrainAffine?.() ?? null;
    },
  };

  finishBoot();

  console.info(
    `atlasAPI ready (engine=${engineId}, lang=${getLocale()}): atlasAPI.setLang('ja'), atlasAPI.gotoYear(239)` +
      (map.terrainEnabled
        ? "; terrain on — atlasAPI.dumpTerrainCalib() / ?terrain=0 / ?terrain_calib=1"
        : "")
  );
}

boot().catch((err) => {
  setBootMessage(err.message || t("error.atlasMissing"), { error: true });
  console.error(err);
});
