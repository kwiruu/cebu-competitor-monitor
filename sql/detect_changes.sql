-- Compare one run against earlier runs and write tickets into `changes`.
-- Parameter: %(run_id)s

-- 1. Price changes: LAG puts the previous price beside the current one.
with history as (
    select
        s.offer_id,
        s.run_id,
        s.price,
        lag(s.price) over (partition by s.offer_id order by s.run_id) as prev_price
    from offer_snapshots s
    where s.run_id <= %(run_id)s
)
insert into changes (run_id, competitor_id, offer_id, change_type, old_value, new_value, pct_change)
select
    h.run_id,
    o.competitor_id,
    h.offer_id,
    'price_change',
    h.prev_price,
    h.price,
    round((h.price - h.prev_price) / nullif(h.prev_price, 0) * 100, 2)
from history h
join offers o on o.id = h.offer_id
where h.run_id = %(run_id)s
  and h.prev_price is not null
  and h.price <> h.prev_price
on conflict do nothing;

-- 2. New offers: first time we see the offer, on a page we had already read before.
with first_seen as (
    select
        s.offer_id,
        s.run_id,
        s.page_id,
        s.price,
        row_number() over (partition by s.offer_id order by s.run_id) as seen_no
    from offer_snapshots s
    where s.run_id <= %(run_id)s
)
insert into changes (run_id, competitor_id, offer_id, change_type, new_value)
select f.run_id, o.competitor_id, f.offer_id, 'new_offer', f.price
from first_seen f
join offers o on o.id = f.offer_id
where f.run_id = %(run_id)s
  and f.seen_no = 1
  and exists (
      select 1 from page_fetches pf
      where pf.page_id = f.page_id and pf.ok and pf.run_id < %(run_id)s
  )
on conflict do nothing;

-- 3. Removed offers: on the page last time it loaded, missing now, and the page did load now.
with page_runs as (
    select
        pf.page_id,
        pf.run_id,
        lag(pf.run_id) over (partition by pf.page_id order by pf.run_id) as prev_run_id
    from page_fetches pf
    where pf.ok and pf.run_id <= %(run_id)s
)
insert into changes (run_id, competitor_id, offer_id, change_type, old_value)
select pr.run_id, o.competitor_id, prev.offer_id, 'removed_offer', prev.price
from page_runs pr
join offer_snapshots prev on prev.run_id = pr.prev_run_id and prev.page_id = pr.page_id
join offers o on o.id = prev.offer_id
where pr.run_id = %(run_id)s
  and not exists (
      select 1 from offer_snapshots cur
      where cur.run_id = pr.run_id and cur.offer_id = prev.offer_id
  )
on conflict do nothing;
