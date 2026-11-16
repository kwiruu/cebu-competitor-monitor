-- Cebu Competitor Monitor schema. Safe to run more than once.

create table if not exists competitors (
    id            bigint generated always as identity primary key,
    name          text not null,
    website       text not null unique,
    niche         text not null default 'cebu-tours',
    is_us         boolean not null default false,   -- the business we compare against
    crawl_delay_s integer not null default 1,
    active        boolean not null default true
);

create table if not exists pages (
    id            bigint generated always as identity primary key,
    competitor_id bigint not null references competitors(id),
    url           text not null unique,
    page_type     text not null default 'package',  -- package | home
    active        boolean not null default true
);

create table if not exists scrape_runs (
    id          bigint generated always as identity primary key,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text not null default 'running'     -- running | ok | partial | failed
);

-- One row per page per run. Lets us tell "offer removed" apart from "page failed to load".
create table if not exists page_fetches (
    run_id       bigint not null references scrape_runs(id),
    page_id      bigint not null references pages(id),
    http_status  integer,
    ok           boolean not null,
    offers_found integer not null default 0,
    error        text,
    primary key (run_id, page_id)
);

-- A stable identity for a package, after fuzzy matching of its name.
create table if not exists offers (
    id             bigint generated always as identity primary key,
    competitor_id  bigint not null references competitors(id),
    canonical_name text not null,
    category       text not null default 'other',   -- e.g. canyoneering+whale_shark
    unique (competitor_id, canonical_name)
);

-- What we saw for an offer in one run. Never updated, only inserted.
create table if not exists offer_snapshots (
    id          bigint generated always as identity primary key,
    run_id      bigint not null references scrape_runs(id),
    offer_id    bigint not null references offers(id),
    page_id     bigint not null references pages(id),
    raw_name    text not null,
    price       numeric(12,2) not null,             -- lowest listed price
    price_high  numeric(12,2),                      -- highest listed price, if tiered
    currency    text not null default 'PHP',
    captured_at timestamptz not null default now(),
    unique (run_id, offer_id)
);

-- Each change is a ticket: status moves new -> reviewed -> actioned.
create table if not exists changes (
    id            bigint generated always as identity primary key,
    run_id        bigint not null references scrape_runs(id),
    competitor_id bigint not null references competitors(id),
    offer_id      bigint not null references offers(id),
    change_type   text not null,                    -- price_change | new_offer | removed_offer
    old_value     numeric(12,2),
    new_value     numeric(12,2),
    pct_change    numeric(7,2),
    status        text not null default 'new',
    decision      text,                             -- match_price | watch | ignore
    detected_at   timestamptz not null default now(),
    unique (run_id, offer_id, change_type)
);

-- Used by later steps (GEO score, mention sample, weekly brief).
create table if not exists geo_scores (
    id            bigint generated always as identity primary key,
    run_id        bigint not null references scrape_runs(id),
    competitor_id bigint not null references competitors(id),
    total         integer not null,
    breakdown     jsonb not null
);

create table if not exists mention_results (
    id            bigint generated always as identity primary key,
    run_id        bigint not null references scrape_runs(id),
    question      text not null,
    competitor_id bigint not null references competitors(id),
    mentioned     boolean not null,
    position      integer
);

create table if not exists briefs (
    id              bigint generated always as identity primary key,
    run_id          bigint not null references scrape_runs(id),
    summary         text not null,
    recommendations jsonb not null
);

create index if not exists offer_snapshots_offer_run_idx on offer_snapshots (offer_id, run_id);

-- Price history with the previous price beside each row (window function: LAG).
create or replace view v_price_history as
select
    c.name           as competitor,
    o.canonical_name as offer,
    o.category,
    s.run_id,
    s.captured_at,
    s.price,
    s.currency,
    lag(s.price) over (partition by s.offer_id order by s.run_id) as prev_price
from offer_snapshots s
join offers o      on o.id = s.offer_id
join competitors c on c.id = o.competitor_id;

-- Latest price per offer, ranked cheapest first inside each category (window function: RANK).
create or replace view v_latest_prices as
with latest as (
    select s.*,
           row_number() over (partition by s.offer_id order by s.run_id desc) as rn
    from offer_snapshots s
)
select
    c.name           as competitor,
    c.is_us,
    o.category,
    o.canonical_name as offer,
    l.price,
    l.price_high,
    l.currency,
    l.captured_at,
    rank() over (partition by o.category, l.currency order by l.price) as price_rank_in_category
from latest l
join offers o      on o.id = l.offer_id
join competitors c on c.id = o.competitor_id
where l.rn = 1;
