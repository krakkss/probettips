alter table probettips.daily_tips
add column if not exists strategy text not null default 'official';

update probettips.daily_tips
set strategy = 'official'
where strategy is distinct from 'official';

alter table probettips.daily_tips
drop constraint if exists daily_tips_pkey;

alter table probettips.daily_tips
add constraint daily_tips_pkey primary key (tip_date, strategy);

alter table probettips.candidate_picks
add column if not exists strategy text not null default 'official';

update probettips.candidate_picks
set strategy = 'official'
where strategy is distinct from 'official';

alter table probettips.candidate_picks
drop constraint if exists candidate_unique_per_day;

alter table probettips.candidate_picks
drop constraint if exists candidate_picks_tip_date_fkey;

alter table probettips.candidate_picks
add constraint candidate_tip_fk foreign key (tip_date, strategy)
references probettips.daily_tips(tip_date, strategy)
on delete cascade;

alter table probettips.candidate_picks
add constraint candidate_unique_per_day
unique (tip_date, strategy, candidate_rank, match_id, market, bet_type);

drop index if exists probettips.idx_probettips_daily_tips_status;
create index if not exists idx_probettips_daily_tips_status
on probettips.daily_tips(status, tip_date desc, strategy);

drop index if exists probettips.idx_probettips_candidate_tip_date;
create index if not exists idx_probettips_candidate_tip_date
on probettips.candidate_picks(tip_date, strategy, candidate_rank);
