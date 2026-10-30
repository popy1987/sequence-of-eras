/**
 * Piecewise-linear year ↔ slider position.
 * Compresses deep prehistory so historical eras occupy usable track width.
 * Slider and period ticks MUST share the same mapping.
 */

/**
 * @param {number} yearMin
 * @param {number} yearMax
 */
export function createTimelineScale(yearMin, yearMax) {
  const SLIDER_MAX = 10000;

  const raw = [
    { pos: 0, year: yearMin },
    { pos: 0.26, year: -14000 },
    { pos: 0.46, year: -400 },
    { pos: 0.54, year: 250 },
    { pos: 0.6, year: 592 },
    { pos: 0.66, year: 794 },
    { pos: 0.72, year: 1185 },
    { pos: 0.78, year: 1467 },
    { pos: 0.84, year: 1603 },
    { pos: 0.9, year: 1868 },
    { pos: 1, year: yearMax },
  ];

  const knots = [{ pos: 0, year: yearMin }];
  for (const k of raw.slice(1)) {
    const year = Math.max(yearMin, Math.min(yearMax, k.year));
    const prev = knots[knots.length - 1];
    if (year <= prev.year || k.pos <= prev.pos) continue;
    knots.push({ pos: k.pos, year });
  }
  const last = knots[knots.length - 1];
  if (last.year < yearMax) {
    knots.push({ pos: 1, year: yearMax });
  } else {
    last.pos = 1;
    last.year = yearMax;
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  /** @param {number} year @returns {number} 0..1 */
  function yearToPos(year) {
    const y = Math.max(yearMin, Math.min(yearMax, year));
    for (let i = 0; i < knots.length - 1; i++) {
      const a = knots[i];
      const b = knots[i + 1];
      if (y >= a.year && y <= b.year) {
        const t = (y - a.year) / (b.year - a.year || 1);
        return lerp(a.pos, b.pos, t);
      }
    }
    return y <= yearMin ? 0 : 1;
  }

  /** @param {number} pos 0..1 @returns {number} calendar year */
  function posToYear(pos) {
    const p = Math.max(0, Math.min(1, pos));
    for (let i = 0; i < knots.length - 1; i++) {
      const a = knots[i];
      const b = knots[i + 1];
      if (p >= a.pos && p <= b.pos) {
        const t = (p - a.pos) / (b.pos - a.pos || 1);
        return Math.round(lerp(a.year, b.year, t));
      }
    }
    return p <= 0 ? yearMin : yearMax;
  }

  function yearToSlider(year) {
    return Math.round(yearToPos(year) * SLIDER_MAX);
  }

  function sliderToYear(value) {
    return posToYear(Number(value) / SLIDER_MAX);
  }

  return {
    SLIDER_MAX,
    knots,
    yearToPos,
    posToYear,
    yearToSlider,
    sliderToYear,
  };
}
