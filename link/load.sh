#!/bin/bash
# Load the CISCE lists and links into ws_trideep.cisce_scraper (Metabase: "Workspace: trideep"). Run on a team box.
# usage: python link/merge.py <dir>; cp <dir>/cisce_all.csv <dir>/cisce.csv; python link/link.py <dir> udise_all.csv;
#        (cd link && python link_2021.py <dir>); link/load.sh <dir>
# <dir> holds the CSVs that merge.py and link.py read and write (see their docstrings), plus udise_cisce.csv
set -euo pipefail
D=$1
q() { psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "$1"; }
load() { q "truncate cisce_scraper.$1"; psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "\copy cisce_scraper.$1 from '$D/$2' csv header"; }

q "create schema if not exists cisce_scraper"
q "create table if not exists cisce_scraper.udise_cisce (udise text primary key, name text, state text, district text, block text,
   locality text, pincode text, mgmt text, category text, gender text, lat float8, lon float8, board_sec text, board_high_sec text,
   address text, email text, website text, estd_year text, residential text, class_from int, class_to int, enrol_total int,
   teachers_total int, medium text, udise_year_id int)"
q "comment on table cisce_scraper.udise_cisce is 'UDISE+ schools (udise db, flat.profile year_id 12) whose secondary or higher secondary board is ICSE/ISC (3-ICSE)'"
q "create table if not exists cisce_scraper.cisce_2018 (code text primary key, name text, address text, pin text, state text, district text, country text)"
q "comment on table cisce_scraper.cisce_2018 is 'CISCE locator list of 2018, public dataset github.com/deedy/cisce_schools_data (2,341 schools)'"
q "create table if not exists cisce_scraper.cisce_2021 (code text, name_and_place text, phone text)"
q "comment on table cisce_scraper.cisce_2021 is 'CISCE list of 2021, public dataset github.com/Nitish-Kumar-kushwaha/list-of-all-CISCE-schools-in-India (5 codes twice)'"
q "create table if not exists cisce_scraper.link_cisce_udise (code text, udise text, method text, score float8, source text)"
q "comment on table cisce_scraper.link_cisce_udise is 'CISCE code to UDISE code (link/link.py); method = how it matched; source = which CISCE list'"
q "drop view if exists cisce_scraper.schools; drop view if exists cisce_scraper.schools_full; drop view if exists cisce_scraper.udise_without_code"
q "drop table if exists cisce_scraper.cisce_all; create table cisce_scraper.cisce_all (code text primary key, name text, state text, district text,
   locality text, address text, pin text, country text, gender text, residence text, status text, icse bool, isc bool, cve bool, head text,
   phones text, email text, website text, lat float8, lng float8, first_seen date, last_seen date, on_locator_2026 bool, n_sources int, sources text)"
q "comment on table cisce_scraper.cisce_all is 'Every CISCE code seen 2015-2026 (link/merge.py): Wayback copies of www.cisce.org/locate-search.aspx, locate.cisce.org pages of 2026-10-20 (raw cache of github.com/magesh-xseed/milestones), lists of github.com/deedy and github.com/Nitish-Kumar-kushwaha. Newest source wins per field'"
q "create table if not exists cisce_scraper.cisce_presence (code text, source text, date date)"
q "comment on table cisce_scraper.cisce_presence is 'Which list showed which CISCE code on which date (full lists: wayback-cisce.org; partial: locate.cisce.org 2026)'"

load udise_cisce udise_cisce.csv
load cisce_all cisce_all.csv
load cisce_presence cisce_presence.csv
load cisce_2018 cisce_2018.csv
load cisce_2021 cisce_2021.csv
q "truncate cisce_scraper.link_cisce_udise"
psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "\copy cisce_scraper.link_cisce_udise (code, udise, method, score) from '$D/cisce_udise_link.csv' csv header"
q "update cisce_scraper.link_cisce_udise set source = 'merged' where source is null"
if [ -f "$D/link_2021.csv" ]; then
  psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "\copy cisce_scraper.link_cisce_udise (code, udise, method, score) from '$D/link_2021.csv' csv header"
  q "update cisce_scraper.link_cisce_udise set source = '2021' where source is null"
fi
q "create view cisce_scraper.schools_full as select a.*, l.udise, l.method as link_method, u.name as udise_name, u.mgmt as udise_mgmt,
   u.class_from, u.class_to, u.enrol_total, u.teachers_total, u.lat as udise_lat, u.lon as udise_lon
   from cisce_scraper.cisce_all a left join cisce_scraper.link_cisce_udise l using (code) left join cisce_scraper.udise_cisce u using (udise)"
q "comment on view cisce_scraper.schools_full is 'One row per CISCE code with its UDISE+ link (if any)'"
q "create view cisce_scraper.udise_without_code as select u.* from cisce_scraper.udise_cisce u
   where not exists (select 1 from cisce_scraper.link_cisce_udise l where l.udise = u.udise)"
q "comment on view cisce_scraper.udise_without_code is 'UDISE+ schools with board ICSE/ISC that no CISCE code links to (new schools, other names, or a wrong board field)'"
psql -d ws_trideep -Atc "select 'udise_cisce', count(*) from cisce_scraper.udise_cisce union all select 'cisce_2018', count(*) from cisce_scraper.cisce_2018
  union all select 'cisce_2021', count(*) from cisce_scraper.cisce_2021 union all select 'link_cisce_udise', count(*) from cisce_scraper.link_cisce_udise
  union all select 'cisce_all', count(*) from cisce_scraper.cisce_all
  union all select 'udise_without_code', count(*) from cisce_scraper.udise_without_code"
