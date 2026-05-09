create schema if not exists probettips;

create table if not exists probettips.daily_tips (
  tip_date date not null,
  strategy text not null default 'official',
  source text not null,
  status text not null default 'pending',
  result text,
  combined_odds numeric(10, 2) not null,
  combined_probability numeric(10, 4) not null,
  recommendation_tier text,
  selected_picks_json jsonb not null default '[]'::jsonb,
  settlement_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tip_date, strategy)
);

create table if not exists probettips.candidate_picks (
  id bigint generated always as identity primary key,
  tip_date date not null,
  strategy text not null default 'official',
  candidate_rank integer not null,
  selected boolean not null default false,
  match_id text not null,
  competition_code text,
  league text not null,
  match_label text not null,
  kickoff text,
  bet_type text not null,
  market text not null,
  probability numeric(10, 6) not null,
  odds numeric(10, 2) not null,
  confidence numeric(10, 6) not null,
  risk_score numeric(10, 6) not null,
  market_stability numeric(10, 6) not null,
  dynamic_threshold numeric(10, 6) not null,
  rationale text,
  created_at timestamptz not null default now(),
  constraint candidate_tip_fk foreign key (tip_date, strategy) references probettips.daily_tips(tip_date, strategy) on delete cascade,
  constraint candidate_unique_per_day unique (tip_date, strategy, candidate_rank, match_id, market, bet_type)
);

create index if not exists idx_probettips_daily_tips_status on probettips.daily_tips(status, tip_date desc, strategy);
create index if not exists idx_probettips_candidate_tip_date on probettips.candidate_picks(tip_date, strategy, candidate_rank);

create or replace function probettips.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists daily_tips_set_updated_at on probettips.daily_tips;
create trigger daily_tips_set_updated_at
before update on probettips.daily_tips
for each row
execute function probettips.set_updated_at();
