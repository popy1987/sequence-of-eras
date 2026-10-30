-- sequence-of-eras SQLite schema
-- Single-file local DB for Web + iOS packaging.
-- Logical design: doc/数据库设计.md
-- Coordinates: WGS 84, GeoJSON text, lon/lat order.
-- Temporal queries use query_from / query_to day ordinals
-- (0 = astronomical year -200000-01-01, proleptic Gregorian).

PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 5. Scenarios
-- ---------------------------------------------------------------------------
CREATE TABLE scenario (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN (
                'wikipedia_consensus', 'scholarly_alternative', 'legendary'
              )),
  is_default  INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
  note        TEXT
);

-- ---------------------------------------------------------------------------
-- 6. Sources & bindings
-- ---------------------------------------------------------------------------
CREATE TABLE source (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN (
                  'wikipedia', 'wikidata', 'dataset', 'map',
                  'book', 'article', 'inscription'
                )),
  title         TEXT NOT NULL,
  language      TEXT,
  locator       TEXT,
  revision      TEXT,
  url           TEXT,
  retrieved_on  TEXT,
  license       TEXT,
  note          TEXT
);

CREATE TABLE source_binding (
  id           TEXT PRIMARY KEY,
  object_kind  TEXT NOT NULL,
  object_id    TEXT NOT NULL,
  source_id    TEXT NOT NULL REFERENCES source(id),
  role         TEXT NOT NULL CHECK (role IN (
                 'fact_spine', 'wording', 'geometry', 'dating', 'conflict'
               )),
  summary      TEXT,
  is_primary   INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1))
);
CREATE INDEX idx_source_binding_object ON source_binding(object_kind, object_id);

CREATE TABLE external_id (
  id           TEXT PRIMARY KEY,
  object_kind  TEXT NOT NULL,
  object_id    TEXT NOT NULL,
  system       TEXT NOT NULL,
  value        TEXT NOT NULL
);
CREATE INDEX idx_external_id_object ON external_id(object_kind, object_id);
CREATE UNIQUE INDEX uq_external_id ON external_id(system, value);

-- ---------------------------------------------------------------------------
-- 4. Time points (shared)
-- ---------------------------------------------------------------------------
CREATE TABLE time_point (
  id                 TEXT PRIMARY KEY,
  earliest_year      INTEGER,
  earliest_month     INTEGER CHECK (earliest_month BETWEEN 1 AND 12 OR earliest_month IS NULL),
  earliest_day       INTEGER CHECK (earliest_day BETWEEN 1 AND 31 OR earliest_day IS NULL),
  latest_year        INTEGER,
  latest_month       INTEGER CHECK (latest_month BETWEEN 1 AND 12 OR latest_month IS NULL),
  latest_day         INTEGER CHECK (latest_day BETWEEN 1 AND 31 OR latest_day IS NULL),
  preferred_year     INTEGER,
  preferred_month    INTEGER CHECK (preferred_month BETWEEN 1 AND 12 OR preferred_month IS NULL),
  preferred_day      INTEGER CHECK (preferred_day BETWEEN 1 AND 31 OR preferred_day IS NULL),
  precision          TEXT NOT NULL CHECK (precision IN (
                       'day', 'month', 'year', 'decade',
                       'century', 'millennium', 'kiloyear'
                     )),
  confidence         TEXT NOT NULL CHECK (confidence IN (
                       'exact', 'circa', 'estimated', 'disputed',
                       'after_this', 'before_this'
                     )),
  dating_method      TEXT CHECK (dating_method IN (
                       'calendar', 'cal_bp', 'bp_1950',
                       'years_ago', 'geological', 'historical_text'
                     )),
  original_expression TEXT,
  bp_epoch_year      INTEGER,
  ordinal_earliest   INTEGER NOT NULL,
  ordinal_latest     INTEGER NOT NULL,
  ordinal_preferred  INTEGER NOT NULL,
  CHECK (ordinal_earliest <= ordinal_latest)
);

CREATE TABLE calendar_expression (
  id              TEXT PRIMARY KEY,
  time_point_id   TEXT NOT NULL REFERENCES time_point(id),
  calendar        TEXT NOT NULL CHECK (calendar IN (
                    'japanese_lunisolar', 'chinese_lunisolar',
                    'julian', 'gregorian', 'proleptic_gregorian'
                  )),
  era_name_id     TEXT,
  era_year        INTEGER,
  month           INTEGER,
  day             INTEGER,
  is_leap_month   INTEGER NOT NULL DEFAULT 0 CHECK (is_leap_month IN (0, 1)),
  original_text   TEXT
);

-- ---------------------------------------------------------------------------
-- 7. Regions & periods
-- ---------------------------------------------------------------------------
CREATE TABLE region (
  id                TEXT PRIMARY KEY,
  parent_id         TEXT REFERENCES region(id),
  kind              TEXT NOT NULL CHECK (kind IN (
                      'archipelago', 'island_chain', 'cultural_region',
                      'historical_frontier', 'overseas_theater'
                    )),
  geometry_id       TEXT,
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

CREATE TABLE period (
  id                TEXT PRIMARY KEY,
  parent_id         TEXT REFERENCES period(id),
  kind              TEXT NOT NULL CHECK (kind IN (
                      'historiographic', 'cultural', 'political',
                      'regnal', 'regional'
                    )),
  region_id         TEXT REFERENCES region(id),
  scenario_id       TEXT NOT NULL REFERENCES scenario(id),
  sort_order        INTEGER NOT NULL DEFAULT 0,
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_period_query ON period(scenario_id, query_from, query_to);

-- ---------------------------------------------------------------------------
-- 8. Actors, persons, offices
-- ---------------------------------------------------------------------------
CREATE TABLE actor (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'archaeological_culture', 'ethnic_group', 'clan',
                      'polity', 'domain', 'religious_power',
                      'foreign_power', 'occupation_authority', 'modern_state'
                    )),
  historicity       TEXT NOT NULL DEFAULT 'historical' CHECK (historicity IN (
                      'historical', 'semi_legendary', 'legendary', 'disputed'
                    )),
  legend_color      TEXT,
  legend_group      TEXT,
  scenario_id       TEXT REFERENCES scenario(id),
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER,
  query_to          INTEGER
);

CREATE TABLE actor_relation (
  id                TEXT PRIMARY KEY,
  actor_a_id        TEXT NOT NULL REFERENCES actor(id),
  actor_b_id        TEXT NOT NULL REFERENCES actor(id),
  relation          TEXT NOT NULL CHECK (relation IN (
                      'successor', 'split_from', 'merged_into', 'vassal_of',
                      'allied_with', 'rival_of', 'dual_subordinate_of',
                      'renamed_to', 'occupies'
                    )),
  confidence        TEXT NOT NULL DEFAULT 'exact',
  scenario_id       TEXT REFERENCES scenario(id),
  causing_event_id  TEXT,
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

CREATE TABLE person (
  id                TEXT PRIMARY KEY,
  historicity       TEXT NOT NULL DEFAULT 'historical' CHECK (historicity IN (
                      'historical', 'semi_legendary', 'legendary', 'disputed'
                    )),
  birth_time_id     TEXT REFERENCES time_point(id),
  death_time_id     TEXT REFERENCES time_point(id)
);

CREATE TABLE office_holding (
  id                TEXT PRIMARY KEY,
  person_id         TEXT REFERENCES person(id),
  actor_id          TEXT NOT NULL REFERENCES actor(id),
  office            TEXT NOT NULL,
  sequence_no       INTEGER,
  scenario_id       TEXT REFERENCES scenario(id),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_office_holding_query ON office_holding(query_from, query_to);

-- ---------------------------------------------------------------------------
-- 4.6 Chronology
-- ---------------------------------------------------------------------------
CREATE TABLE chronology_track (
  id                TEXT PRIMARY KEY,
  culture           TEXT NOT NULL CHECK (culture IN ('japan', 'china')),
  role              TEXT NOT NULL CHECK (role IN ('primary', 'reference', 'regional')),
  actor_id          TEXT REFERENCES actor(id),
  show_in_header    INTEGER NOT NULL DEFAULT 0 CHECK (show_in_header IN (0, 1)),
  priority          INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE dynasty (
  id                TEXT PRIMARY KEY,
  chronology_track_id TEXT NOT NULL REFERENCES chronology_track(id),
  lineage           TEXT NOT NULL CHECK (lineage IN ('main', 'regional')),
  historicity       TEXT NOT NULL DEFAULT 'historical',
  map_actor_id      TEXT REFERENCES actor(id),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_dynasty_query ON dynasty(chronology_track_id, query_from, query_to);

CREATE TABLE era_name (
  id                TEXT PRIMARY KEY,
  chronology_track_id TEXT NOT NULL REFERENCES chronology_track(id),
  dynasty_id        TEXT REFERENCES dynasty(id),
  is_private        INTEGER NOT NULL DEFAULT 0 CHECK (is_private IN (0, 1)),
  year_start_calendar TEXT NOT NULL CHECK (year_start_calendar IN (
                      'japanese_lunisolar', 'chinese_lunisolar', 'gregorian'
                    )),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_era_name_query ON era_name(chronology_track_id, query_from, query_to);

CREATE TABLE year_start (
  id                TEXT PRIMARY KEY,
  calendar          TEXT NOT NULL CHECK (calendar IN (
                      'japanese_lunisolar', 'chinese_lunisolar', 'gregorian'
                    )),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT NOT NULL REFERENCES time_point(id),
  source_id         TEXT REFERENCES source(id),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

-- ---------------------------------------------------------------------------
-- 9. Space, geometry, control
-- ---------------------------------------------------------------------------
CREATE TABLE spatial_framework (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'cultural_schematic', 'province', 'district',
                      'domain_holding', 'prefecture', 'coastline', 'custom'
                    )),
  boundary_quality  TEXT CHECK (boundary_quality IN (
                      'schematic', 'approximate', 'reconstructed',
                      'modern_proxy', 'surveyed'
                    )),
  source_id         TEXT REFERENCES source(id),
  license           TEXT,
  note              TEXT,
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER,
  query_to          INTEGER
);

CREATE TABLE spatial_unit (
  id                TEXT PRIMARY KEY,
  framework_id      TEXT NOT NULL REFERENCES spatial_framework(id),
  kind              TEXT NOT NULL CHECK (kind IN (
                      'culture_area', 'circuit', 'province', 'district',
                      'domain_part', 'prefecture', 'coast_region', 'custom_region'
                    )),
  modern_counterpart_id TEXT,
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER,
  query_to          INTEGER
);

CREATE TABLE spatial_membership (
  id                TEXT PRIMARY KEY,
  child_unit_id     TEXT NOT NULL REFERENCES spatial_unit(id),
  parent_unit_id    TEXT NOT NULL REFERENCES spatial_unit(id),
  relation          TEXT NOT NULL CHECK (relation IN ('part_of', 'seat_of')),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

CREATE TABLE geometry (
  id                TEXT PRIMARY KEY,
  shape_type        TEXT NOT NULL CHECK (shape_type IN (
                      'point', 'multi_point', 'line', 'multi_line',
                      'polygon', 'multi_polygon'
                    )),
  srid              TEXT NOT NULL DEFAULT 'EPSG:4326',
  detail_level      TEXT NOT NULL DEFAULT 'overview' CHECK (detail_level IN (
                      'overview', 'regional', 'detail'
                    )),
  simplified_from_id TEXT REFERENCES geometry(id),
  bbox_west         REAL,
  bbox_south        REAL,
  bbox_east         REAL,
  bbox_north        REAL,
  label_lon         REAL,
  label_lat         REAL,
  reliability_radius_m REAL,
  boundary_quality  TEXT CHECK (boundary_quality IN (
                      'schematic', 'approximate', 'reconstructed',
                      'modern_proxy', 'surveyed'
                    )),
  geojson           TEXT NOT NULL,
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER,
  query_to          INTEGER
);

CREATE TABLE control_record (
  id                TEXT PRIMARY KEY,
  scenario_id       TEXT NOT NULL REFERENCES scenario(id),
  actor_id          TEXT NOT NULL REFERENCES actor(id),
  spatial_unit_id   TEXT REFERENCES spatial_unit(id),
  geometry_id       TEXT REFERENCES geometry(id),
  control_mode      TEXT NOT NULL CHECK (control_mode IN (
                      'direct', 'administered', 'delegated', 'domain',
                      'vassal', 'alliance', 'nominal', 'dual', 'occupation',
                      'sphere', 'claimed', 'contested', 'cultural',
                      'presence', 'uncertain'
                    )),
  claim_status      TEXT NOT NULL DEFAULT 'preferred' CHECK (claim_status IN (
                      'preferred', 'competing', 'rejected'
                    )),
  paint_priority    INTEGER NOT NULL DEFAULT 100,
  causing_event_id  TEXT,
  disputed_region_id TEXT,
  boundary_quality  TEXT,
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to),
  CHECK (
    (spatial_unit_id IS NOT NULL AND geometry_id IS NULL)
    OR (spatial_unit_id IS NULL AND geometry_id IS NOT NULL)
  )
);
CREATE INDEX idx_control_query ON control_record(scenario_id, query_from, query_to);
CREATE INDEX idx_control_actor ON control_record(actor_id);

-- ---------------------------------------------------------------------------
-- 9.5 Disputed regions
-- ---------------------------------------------------------------------------
CREATE TABLE disputed_region (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'island_group', 'island', 'sea_area',
                      'archipelago_status', 'land_border'
                    )),
  spatial_unit_id   TEXT REFERENCES spatial_unit(id),
  geometry_id       TEXT REFERENCES geometry(id),
  status            TEXT NOT NULL CHECK (status IN ('active', 'historical', 'dormant')),
  name_strategy     TEXT NOT NULL DEFAULT 'all_party_names' CHECK (name_strategy IN (
                      'neutral_id', 'all_party_names', 'wikipedia_ja_title'
                    )),
  sensitivity       TEXT NOT NULL DEFAULT 'standard' CHECK (sensitivity IN (
                      'standard', 'high'
                    )),
  scenario_id       TEXT REFERENCES scenario(id),
  short_note        TEXT,
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to),
  CHECK (
    spatial_unit_id IS NOT NULL OR geometry_id IS NOT NULL
  )
);

CREATE TABLE dispute_party (
  id                TEXT PRIMARY KEY,
  disputed_region_id TEXT NOT NULL REFERENCES disputed_region(id),
  actor_id          TEXT NOT NULL REFERENCES actor(id),
  role              TEXT NOT NULL CHECK (role IN (
                      'administers', 'claims_sovereignty', 'claims_historical',
                      'recognizes_other', 'interested_party'
                    )),
  name_record_id    TEXT,
  claim_status      TEXT NOT NULL DEFAULT 'competing' CHECK (claim_status IN (
                      'preferred', 'competing', 'rejected'
                    )),
  control_record_id TEXT REFERENCES control_record(id),
  scenario_id       TEXT REFERENCES scenario(id),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_dispute_party_region ON dispute_party(disputed_region_id);

CREATE TABLE dispute_milestone (
  id                TEXT PRIMARY KEY,
  disputed_region_id TEXT NOT NULL REFERENCES disputed_region(id),
  event_id          TEXT,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'claim_begins', 'administration_changes', 'treaty',
                      'occupation_begins', 'occupation_ends',
                      'status_change', 'incident'
                    )),
  time_point_id     TEXT NOT NULL REFERENCES time_point(id),
  note              TEXT
);

-- deferred FK: control_record.disputed_region_id -> disputed_region
-- created after both tables exist via index only; enforced in app layer
-- or by rebuild script integrity check.

-- ---------------------------------------------------------------------------
-- 10. Places & names
-- ---------------------------------------------------------------------------
CREATE TABLE place (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'archaeological_site', 'settlement', 'palace', 'capital',
                      'castle', 'kofun', 'shrine', 'temple', 'port',
                      'battlefield', 'city', 'island'
                    )),
  lon               REAL,
  lat               REAL,
  reliability_radius_m REAL,
  geometry_id       TEXT REFERENCES geometry(id)
);

CREATE TABLE place_seat (
  id                TEXT PRIMARY KEY,
  actor_id          TEXT NOT NULL REFERENCES actor(id),
  place_id          TEXT NOT NULL REFERENCES place(id),
  kind              TEXT NOT NULL CHECK (kind IN (
                      'primary', 'secondary', 'temporary', 'ritual'
                    )),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

CREATE TABLE place_function (
  id                TEXT PRIMARY KEY,
  place_id          TEXT NOT NULL REFERENCES place(id),
  function_kind     TEXT NOT NULL CHECK (function_kind IN (
                      'capital', 'kokufu', 'castle_town', 'daimyo_seat',
                      'ritual_center', 'port', 'occupation_hq', 'site_occupation'
                    )),
  actor_id          TEXT REFERENCES actor(id),
  scenario_id       TEXT REFERENCES scenario(id),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

CREATE TABLE name_record (
  id                TEXT PRIMARY KEY,
  object_kind       TEXT NOT NULL,
  object_id         TEXT NOT NULL,
  language          TEXT NOT NULL CHECK (language IN (
                      'ja', 'ja_reading', 'romaji',
                      'zh_hans', 'zh_hant', 'en'
                    )),
  text              TEXT NOT NULL,
  kind              TEXT NOT NULL DEFAULT 'common' CHECK (kind IN (
                      'common', 'official', 'historical', 'posthumous',
                      'personal', 'short', 'scholarly'
                    )),
  is_primary        INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
  scenario_id       TEXT REFERENCES scenario(id),
  party_actor_id    TEXT REFERENCES actor(id),
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 1 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER,
  query_to          INTEGER
);
CREATE INDEX idx_name_object ON name_record(object_kind, object_id);

CREATE TABLE note (
  id                TEXT PRIMARY KEY,
  object_kind       TEXT NOT NULL,
  object_id         TEXT NOT NULL,
  language          TEXT NOT NULL,
  purpose           TEXT NOT NULL CHECK (purpose IN ('card', 'caption', 'uncertainty')),
  body              TEXT NOT NULL,
  start_time_id     TEXT REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 1 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER,
  query_to          INTEGER
);

-- ---------------------------------------------------------------------------
-- 11. Events
-- ---------------------------------------------------------------------------
CREATE TABLE event (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'archaeological', 'political', 'military', 'diplomatic',
                      'institutional', 'succession', 'disaster', 'cultural',
                      'territorial', 'demographic'
                    )),
  importance        INTEGER NOT NULL CHECK (importance BETWEEN 1 AND 5),
  timeline_policy   TEXT NOT NULL DEFAULT 'zoom' CHECK (timeline_policy IN (
                      'always', 'zoom', 'chapter'
                    )),
  short_note        TEXT,
  alignment         TEXT NOT NULL DEFAULT 'follows' CHECK (alignment IN (
                      'follows', 'partial', 'disputed'
                    )),
  scenario_id       TEXT NOT NULL REFERENCES scenario(id),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_event_query ON event(scenario_id, query_from, query_to);

CREATE TABLE event_relation (
  id                TEXT PRIMARY KEY,
  parent_event_id   TEXT NOT NULL REFERENCES event(id),
  child_event_id    TEXT NOT NULL REFERENCES event(id),
  relation          TEXT NOT NULL DEFAULT 'part_of' CHECK (relation IN ('part_of'))
);

CREATE TABLE event_participant (
  id                TEXT PRIMARY KEY,
  event_id          TEXT NOT NULL REFERENCES event(id),
  actor_id          TEXT REFERENCES actor(id),
  person_id         TEXT REFERENCES person(id),
  role              TEXT NOT NULL CHECK (role IN (
                      'initiator', 'opponent', 'subject',
                      'affected', 'victor', 'defeated'
                    )),
  note              TEXT,
  CHECK (actor_id IS NOT NULL OR person_id IS NOT NULL)
);

CREATE TABLE event_place (
  id                TEXT PRIMARY KEY,
  event_id          TEXT NOT NULL REFERENCES event(id),
  place_id          TEXT REFERENCES place(id),
  spatial_unit_id   TEXT REFERENCES spatial_unit(id),
  geometry_id       TEXT REFERENCES geometry(id),
  role              TEXT NOT NULL CHECK (role IN (
                      'primary', 'theater', 'origin', 'destination'
                    )),
  scenario_id       TEXT REFERENCES scenario(id),
  CHECK (
    place_id IS NOT NULL
    OR spatial_unit_id IS NOT NULL
    OR geometry_id IS NOT NULL
  )
);

-- ---------------------------------------------------------------------------
-- 12. Map layers & features
-- ---------------------------------------------------------------------------
CREATE TABLE map_layer (
  id                TEXT PRIMARY KEY,
  sort_order        INTEGER NOT NULL,
  default_on        INTEGER NOT NULL DEFAULT 1 CHECK (default_on IN (0, 1))
);

CREATE TABLE map_feature (
  id                TEXT PRIMARY KEY,
  layer_id          TEXT NOT NULL REFERENCES map_layer(id),
  scenario_id       TEXT NOT NULL REFERENCES scenario(id),
  geometry_source   TEXT NOT NULL CHECK (geometry_source IN ('authored', 'derived')),
  object_kind       TEXT NOT NULL,
  object_id         TEXT NOT NULL,
  geometry_id       TEXT REFERENCES geometry(id),
  style_json        TEXT,
  label_name_id     TEXT REFERENCES name_record(id),
  display_rank      INTEGER NOT NULL DEFAULT 1 CHECK (display_rank BETWEEN 1 AND 3),
  importance        INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);
CREATE INDEX idx_map_feature_query ON map_feature(layer_id, scenario_id, query_from, query_to);

CREATE TABLE route_line (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN (
                      'road', 'sea_lane', 'march', 'mission',
                      'railway', 'boundary_work'
                    )),
  geometry_id       TEXT NOT NULL REFERENCES geometry(id),
  actor_id          TEXT REFERENCES actor(id),
  event_id          TEXT REFERENCES event(id),
  display_rank      INTEGER NOT NULL DEFAULT 2,
  start_time_id     TEXT NOT NULL REFERENCES time_point(id),
  end_time_id       TEXT REFERENCES time_point(id),
  end_inclusive     INTEGER NOT NULL DEFAULT 1 CHECK (end_inclusive IN (0, 1)),
  open_ended        INTEGER NOT NULL DEFAULT 0 CHECK (open_ended IN (0, 1)),
  query_from        INTEGER NOT NULL,
  query_to          INTEGER NOT NULL,
  CHECK (query_from <= query_to)
);

-- Helpful views for "valid on day D"
CREATE VIEW v_periods_open AS
SELECT * FROM period;

CREATE VIEW v_controls_open AS
SELECT * FROM control_record;

CREATE VIEW v_disputes_open AS
SELECT * FROM disputed_region;

CREATE VIEW v_events_open AS
SELECT * FROM event;

CREATE VIEW v_era_names_open AS
SELECT * FROM era_name;
