/**
 * Map engine contract (documentation module).
 *
 * MapFrame — payload from app → engine on each year change:
 * {
 *   year: number,
 *   locale: "zh" | "ja" | "en",
 *   coastline: GeoJSON.MultiPolygon | GeoJSON.Polygon | null,
 *   polities: Array<{
 *     id: string,
 *     names: Record<string,string>,
 *     color: string,
 *     mode: string,
 *     geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
 *   }>,
 *   markers: Array<{
 *     id: string,
 *     lon: number,
 *     lat: number,
 *     names: Record<string,string>,
 *     kind: string
 *   }>,
 *   disputes: Array<{
 *     id: string,
 *     names: Record<string,string>,
 *     short_note?: string,
 *     parties?: Array<unknown>,
 *     kind?: string,
 *     sensitivity?: string,
 *     geometry?: { lon: number, lat: number }
 *   }>
 * }
 *
 * MapSelectEvent — engine → app:
 * { kind: "polity" | "marker" | "dispute", data: object }
 *
 * Engine instance methods:
 *   setFrame(frame: MapFrame): void
 *   fitHome(): void
 *   on(type: "select", handler): void
 *   destroy(): void
 */

export const MAP_ENGINE_EVENTS = Object.freeze({
  SELECT: "select",
});

export const MAP_SELECT_KIND = Object.freeze({
  POLITY: "polity",
  MARKER: "marker",
  DISPUTE: "dispute",
  EVENT: "event",
});
