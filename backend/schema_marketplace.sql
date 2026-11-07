-- ---------------------------------------------------------------------------
-- Marketplace: input sellers and produce buyers.
--
-- Prototype only. There is no order, no payment, no escrow and no KYC anywhere
-- in this schema, on purpose: a listing is an advert and an "interest" is a
-- message. Money changes hands off the app, if it changes hands at all.
--
-- Run this in the Supabase SQL editor after schema.sql. It is idempotent, so
-- re-running it is safe.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Profiles
-- ---------------------------------------------------------------------------
-- A listing has a person behind it, and the market needs a name to show. Stored
-- separately from auth.users because a display name is public and the auth row
-- is not.
create table if not exists profiles (
    user_id      uuid primary key references auth.users (id) on delete cascade,
    display_name text not null,
    region       text,
    -- 'seller', 'buyer' or 'both'. Most smallholders are both: they sell produce
    -- and buy seed, so this is a label, not a permission.
    role         text not null default 'both' check (role in ('seller', 'buyer', 'both')),
    contact_note text default '',
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Listings
-- ---------------------------------------------------------------------------
create table if not exists listings (
    id           uuid primary key default gen_random_uuid(),
    seller_id    uuid not null references auth.users (id) on delete cascade,
    -- 'input' covers seed, seedlings, compost, fertiliser, feed, tools.
    -- 'produce' covers what comes off the field.
    kind         text not null check (kind in ('input', 'produce')),
    category     text not null default '',
    title        text not null,
    description  text not null default '',
    -- Money is integer cents. ZAR only for now; the column exists so a second
    -- currency would not need a migration.
    price_cents  integer check (price_cents is null or price_cents >= 0),
    currency     text not null default 'ZAR',
    -- Free text ("per 50 kg bag", "per bunch") because units in this trade do
    -- not reduce to a fixed enum.
    unit         text default '',
    quantity     text default '',
    region       text,
    latitude     double precision,
    longitude    double precision,
    status       text not null default 'active'
                 check (status in ('active', 'paused', 'sold', 'removed')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index if not exists listings_browse_idx
    on listings (status, kind, created_at desc);
create index if not exists listings_seller_idx
    on listings (seller_id, created_at desc);

create table if not exists listing_images (
    id           uuid primary key default gen_random_uuid(),
    listing_id   uuid not null references listings (id) on delete cascade,
    -- Path inside the `listing-photos` storage bucket, not a URL: the bucket is
    -- private and the API signs a short-lived link when it serves the listing.
    storage_path text not null,
    position     integer not null default 0,
    created_at   timestamptz not null default now()
);

create index if not exists listing_images_listing_idx
    on listing_images (listing_id, position);

-- ---------------------------------------------------------------------------
-- Interest, conversations, messages
-- ---------------------------------------------------------------------------
-- An interest is "I want to talk about this listing". Accepting it opens a
-- conversation. Both rows are kept so the seller can see who asked even after
-- the conversation exists.
create table if not exists interests (
    id         uuid primary key default gen_random_uuid(),
    listing_id uuid not null references listings (id) on delete cascade,
    buyer_id   uuid not null references auth.users (id) on delete cascade,
    message    text not null default '',
    status     text not null default 'open'
               check (status in ('open', 'accepted', 'declined')),
    created_at timestamptz not null default now(),
    -- One enquiry per person per listing: a second click should not create a
    -- second thread.
    unique (listing_id, buyer_id)
);

create index if not exists interests_listing_idx on interests (listing_id, created_at desc);
create index if not exists interests_buyer_idx   on interests (buyer_id, created_at desc);

create table if not exists conversations (
    id         uuid primary key default gen_random_uuid(),
    listing_id uuid not null references listings (id) on delete cascade,
    seller_id  uuid not null references auth.users (id) on delete cascade,
    buyer_id   uuid not null references auth.users (id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (listing_id, buyer_id)
);

create index if not exists conversations_seller_idx on conversations (seller_id, created_at desc);
create index if not exists conversations_buyer_idx  on conversations (buyer_id, created_at desc);

create table if not exists messages (
    id              uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations (id) on delete cascade,
    sender_id       uuid not null references auth.users (id) on delete cascade,
    body            text not null,
    created_at      timestamptz not null default now()
);

create index if not exists messages_conversation_idx
    on messages (conversation_id, created_at);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- The API talks to Postgres with the service key, which bypasses these, so every
-- query is already scoped by user in code. These policies are the second line of
-- defence: an anon key in a browser cannot write someone else's listing or read
-- someone else's inbox even if a route is miswritten.
alter table profiles        enable row level security;
alter table listings        enable row level security;
alter table listing_images  enable row level security;
alter table interests       enable row level security;
alter table conversations   enable row level security;
alter table messages        enable row level security;

-- Display names are public: they appear on every listing.
drop policy if exists profiles_read on profiles;
create policy profiles_read on profiles
    for select to anon, authenticated using (true);

drop policy if exists profiles_owner_write on profiles;
create policy profiles_owner_write on profiles
    for all to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Active listings are the shop window. Everything else is visible to its owner.
drop policy if exists listings_read on listings;
create policy listings_read on listings
    for select to anon, authenticated
    using (status = 'active' or auth.uid() = seller_id);

drop policy if exists listings_owner_write on listings;
create policy listings_owner_write on listings
    for all to authenticated
    using (auth.uid() = seller_id) with check (auth.uid() = seller_id);

-- Images follow their listing.
drop policy if exists listing_images_read on listing_images;
create policy listing_images_read on listing_images
    for select to anon, authenticated using (true);

drop policy if exists listing_images_owner_write on listing_images;
create policy listing_images_owner_write on listing_images
    for all to authenticated
    using (exists (
        select 1 from listings l where l.id = listing_images.listing_id and l.seller_id = auth.uid()
    ))
    with check (exists (
        select 1 from listings l where l.id = listing_images.listing_id and l.seller_id = auth.uid()
    ));

-- An interest is visible to the buyer who made it and the seller who received it.
drop policy if exists interests_read on interests;
create policy interests_read on interests
    for select to authenticated
    using (
        auth.uid() = buyer_id
        or exists (select 1 from listings l where l.id = interests.listing_id and l.seller_id = auth.uid())
    );

drop policy if exists interests_insert on interests;
create policy interests_insert on interests
    for insert to authenticated with check (auth.uid() = buyer_id);

drop policy if exists interests_update on interests;
create policy interests_update on interests
    for update to authenticated
    using (exists (select 1 from listings l where l.id = interests.listing_id and l.seller_id = auth.uid()))
    with check (exists (select 1 from listings l where l.id = interests.listing_id and l.seller_id = auth.uid()));

drop policy if exists conversations_participants on conversations;
create policy conversations_participants on conversations
    for all to authenticated
    using (auth.uid() = seller_id or auth.uid() = buyer_id)
    with check (auth.uid() = seller_id or auth.uid() = buyer_id);

drop policy if exists messages_participants on messages;
create policy messages_participants on messages
    for all to authenticated
    using (exists (
        select 1 from conversations c
        where c.id = messages.conversation_id
          and (c.seller_id = auth.uid() or c.buyer_id = auth.uid())
    ))
    with check (exists (
        select 1 from conversations c
        where c.id = messages.conversation_id
          and (c.seller_id = auth.uid() or c.buyer_id = auth.uid())
    ));

-- ---------------------------------------------------------------------------
-- Photo storage
-- ---------------------------------------------------------------------------
-- Private bucket: a listing photo may show a person's yard, and a guessable
-- public URL is not a good default. The API signs links for the listing owner
-- and for anyone viewing an active listing.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'listing-photos',
    'listing-photos',
    false,
    5242880, -- 5 MB
    array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
    set file_size_limit = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists listing_photos_read on storage.objects;
create policy listing_photos_read on storage.objects
    for select to anon, authenticated
    using (bucket_id = 'listing-photos');

-- Path convention: <user_id>/<uuid>.<ext>, so ownership is readable from the key.
drop policy if exists listing_photos_write on storage.objects;
create policy listing_photos_write on storage.objects
    for insert to authenticated
    with check (
        bucket_id = 'listing-photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

drop policy if exists listing_photos_delete on storage.objects;
create policy listing_photos_delete on storage.objects
    for delete to authenticated
    using (
        bucket_id = 'listing-photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    );
