#!/bin/bash
# Copy the Gujarat FRC school list from the hub (project cisce-scraper-frc-gujarat) into ws_trideep.cisce_scraper.frc_gujarat,
# and make the view frc_board_check: each FRC school with an ICSE board, or with a CISCE code by its UDISE code.
# Run on a team box after the pool run: link/load_frc.sh  (--view: only the view)   (ws_trideep has no link to scrape_hub, so the rows go through COPY)
set -euo pipefail
q() { psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "$1"; }
q "drop view if exists cisce_scraper.frc_board_check"
if [ "${1:-}" != "--view" ]; then                     # --view: only rebuild the view (load.sh calls it)
q "drop table if exists cisce_scraper.frc_gujarat; create table cisce_scraper.frc_gujarat (record_id text primary key, frc_id int,
   school text, udise text, district text, block text, medium text, board text, application_types text, fee_status int, seen text)"
q "comment on table cisce_scraper.frc_gujarat is 'Gujarat Fee Regulation Committee school list (frcgujarat.org, hub project cisce-scraper-frc-gujarat): one row per school, medium and board'"
psql -d scrape_hub -v ON_ERROR_STOP=1 -qc "copy (select record_id, (data->>'Id')::int, data->>'SchoolName', data->>'SchoolCode', data->>'DistrictName',
   data->>'BlockName', data->>'Medium', data->>'Board', data->>'ApplicationTypes', (data->>'FeeStatus')::int, data->>'seen'
   from records where project = 'cisce-scraper-frc-gujarat') to stdout with csv" \
 | psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "copy cisce_scraper.frc_gujarat from stdin with csv"
fi
q "create view cisce_scraper.frc_board_check as
   select f.udise, f.school, f.district, f.medium, f.board as frc_board, l.code as cisce_code, a.name as cisce_name, a.last_seen,
          case when f.board ilike '%icse%' and l.code is not null then 'ICSE in FRC, CISCE code'
               when f.board ilike '%icse%' then 'ICSE in FRC, no CISCE code'
               else 'other board in FRC, CISCE code' end as check_result
   from cisce_scraper.frc_gujarat f
   left join cisce_scraper.link_cisce_udise l on l.udise = f.udise
   left join cisce_scraper.cisce_all a on a.code = l.code
   where f.board ilike '%icse%' or l.code is not null"
q "comment on view cisce_scraper.frc_board_check is 'Gujarat: FRC board field against CISCE codes (by UDISE code). An indicator for a check, not a finding'"
psql -d ws_trideep -Atc "select check_result, count(*) from cisce_scraper.frc_board_check group by 1 order by 1"
