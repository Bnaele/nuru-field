-- Nuru Field — database schema
--
-- Apply this in the Supabase SQL editor (or `psql "$SUPABASE_DB_URL" -f schema.sql`).
-- It is idempotent: running it twice is safe.
--
-- Access model
-- ------------
-- The FastAPI backend connects with SUPABASE_SERVICE_KEY, which bypasses Row Level
-- Security. Every table below therefore has RLS *enabled*, so the public anon key
-- used by the React app cannot read anything it is not explicitly granted.
--
-- The browser currently talks only to the API, never to Postgres directly. The
-- policies below exist so that granting the browser read access later does not
-- require rethinking the model: anon sees nothing, an authenticated user sees
-- their own rows, service role sees everything.
--
-- Column names are derived from actual usage in backend/main.py — not invented.
-- If an endpoint adds a column, add it here in the same commit.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Crop reference
-- ---------------------------------------------------------------------------
-- Global, not per-region. Each row is a crop's ecological envelope from FAO
-- ECOCROP (min/max optimal temperature, annual rainfall, soil pH). Recommendations
-- are produced by scoring a field's *measured* climate and soil against these
-- envelopes, so there is no hand-written "crop suits province X" table anywhere.
--
-- The table covers every taxon the archive has a usable envelope for (~2,070), not
-- a shortlist. ECOCROP only carries scientific names, so `name` is the common name
-- where one is known (508 species) and the scientific name otherwise (1,558) --
-- compare the two columns to tell which. `name` is therefore deliberately NOT
-- unique: "Tomato" can come from two synonymous taxa.
--
-- `family` is the botanical family from the archive. It is the only identity an
-- unnamed species has, and the API searches on it, so it is indexed.
--
-- Rainfall and pH are nullable because the archive genuinely lacks them for a
-- handful of species. They are empty rather than defaulted to a plausible
-- midpoint; the scorer renormalises its weights over what is present.
--
-- Regenerate backend/data/crop_reference.csv with:
--     python backend/data/build_crop_data.py
-- Source: FAO ECOCROP, DOI 10.5281/zenodo.13319716
create table if not exists crop_reference (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    scientific_name text not null unique,
    family          text,                    -- botanical family, from the archive
    category        text,
    min_temp        numeric(5, 1) not null,  -- degrees C, optimal range
    max_temp        numeric(5, 1) not null,
    min_rainfall_mm numeric(7, 1),           -- mm per year, optimal range
    max_rainfall_mm numeric(7, 1),
    min_ph          numeric(4, 1),           -- optimal soil pH range
    max_ph          numeric(4, 1),
    source          text,
    created_at      timestamptz not null default now()
);

create index if not exists crop_reference_name_idx
    on crop_reference (name);

create index if not exists crop_reference_category_idx
    on crop_reference (category);

create index if not exists crop_reference_family_idx
    on crop_reference (family);

-- ---------------------------------------------------------------------------
-- Market prices
-- ---------------------------------------------------------------------------
-- Real daily figures from the Joburg Market price sheet, not seeded estimates.
-- `price_per_kg` is derived from total value divided by total kilograms sold for
-- the day, which is the realised average price rather than a quoted asking price.
--
-- `source_url` and `as_of` are mandatory: the UI must be able to tell a grower
-- which day a price belongs to and where it came from.
create table if not exists market_prices (
    id             uuid primary key default gen_random_uuid(),
    market         text not null,           -- 'Joburg Market'
    as_of          date not null,           -- date the sheet reports for
    commodity      text not null,           -- 'APPLES'
    price_per_kg   numeric(10, 2),          -- derived: value / kg sold
    total_value_zar numeric(16, 2),
    total_kg_sold  numeric(14, 2),
    qty_available_kg numeric(14, 2),
    source_url     text not null,
    fetched_at     timestamptz not null default now(),
    unique (market, as_of, commodity)
);

create index if not exists market_prices_lookup_idx
    on market_prices (market, as_of desc, commodity);

-- ---------------------------------------------------------------------------
-- Field profiles
-- ---------------------------------------------------------------------------
-- main.py previously tried three different column layouts at insert time because
-- the real table was never committed. This is the one it should use.
create table if not exists field_profiles (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references auth.users (id) on delete cascade,
    label      text not null,
    latitude   double precision not null,
    longitude  double precision not null,
    summary    text default '',
    notes      text default '',
    created_at timestamptz not null default now()
);

create index if not exists field_profiles_user_idx
    on field_profiles (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Photo analyses
-- ---------------------------------------------------------------------------
create table if not exists soil_scans (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    location        text,
    analysis_result text not null,
    image_url       text,
    created_at      timestamptz not null default now()
);

create index if not exists soil_scans_user_idx
    on soil_scans (user_id, created_at desc);

create table if not exists plant_photos (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    plant_id        uuid,
    photo_url       text,
    analysis_result text not null,
    location        text,
    created_at      timestamptz not null default now()
);

create index if not exists plant_photos_user_idx
    on plant_photos (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Plants and watering
-- ---------------------------------------------------------------------------
-- The frontend kept these in localStorage. Server-side is the source of truth:
-- records must survive a browser clear and follow the user across devices.
create table if not exists plants (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null references auth.users (id) on delete cascade,
    name           text not null,
    crop_type      text,
    planting_date  date,
    last_watered_at timestamptz,
    created_at     timestamptz not null default now()
);

create index if not exists plants_user_idx
    on plants (user_id, created_at desc);

create table if not exists plant_waterings (
    id         uuid primary key default gen_random_uuid(),
    plant_id   uuid not null references plants (id) on delete cascade,
    user_id    uuid not null references auth.users (id) on delete cascade,
    watered_at timestamptz not null default now()
);

create index if not exists plant_waterings_plant_idx
    on plant_waterings (plant_id, watered_at desc);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table crop_reference  enable row level security;
alter table market_prices   enable row level security;
alter table field_profiles  enable row level security;
alter table soil_scans      enable row level security;
alter table plant_photos    enable row level security;
alter table plants          enable row level security;
alter table plant_waterings enable row level security;

-- Reference data is public-readable by design: there is nothing personal in it,
-- and the API serves it without authentication anyway.
drop policy if exists crop_reference_read on crop_reference;
create policy crop_reference_read on crop_reference
    for select to anon, authenticated using (true);

drop policy if exists market_prices_read on market_prices;
create policy market_prices_read on market_prices
    for select to anon, authenticated using (true);

-- Everything user-owned is owner-only. `auth.uid()` is the JWT subject.
drop policy if exists field_profiles_owner on field_profiles;
create policy field_profiles_owner on field_profiles
    for all to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists soil_scans_owner on soil_scans;
create policy soil_scans_owner on soil_scans
    for all to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists plant_photos_owner on plant_photos;
create policy plant_photos_owner on plant_photos
    for all to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists plants_owner on plants;
create policy plants_owner on plants
    for all to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists plant_waterings_owner on plant_waterings;
create policy plant_waterings_owner on plant_waterings
    for all to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);
