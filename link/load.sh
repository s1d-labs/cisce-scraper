#!/bin/bash
# Load the CISCE lists and links into ws_trideep.cisce_scraper (Metabase: "Workspace: trideep"). Run on a team box.
# usage: link/load.sh <dir>   (<dir> holds the CSVs that link.py reads and writes, plus cisce_2018.csv, cisce_2021.csv)
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
q "create table if not exists cisce_scraper.link_cisce_cbse (udise text, cbse_aff_no text, cbse_name text, score float8, evidence text)"
q "comment on table cisce_scraper.link_cisce_cbse is 'UDISE CISCE schools with the same name in the same district on the CBSE list (cbse-schools); name+district alone may be another campus'"

load udise_cisce udise_cisce.csv
load cisce_2018 cisce_2018.csv
load cisce_2021 cisce_2021.csv
q "truncate cisce_scraper.link_cisce_udise"
psql -d ws_trideep -v ON_ERROR_STOP=1 -qc "\copy cisce_scraper.link_cisce_udise (code, udise, method, score) from '$D/cisce_udise_link.csv' csv header"
q "update cisce_scraper.link_cisce_udise set source = '2018' where source is null"
load link_cisce_cbse cisce_cbse_link.csv
psql -d ws_trideep -Atc "select 'udise_cisce', count(*) from cisce_scraper.udise_cisce union all select 'cisce_2018', count(*) from cisce_scraper.cisce_2018
  union all select 'cisce_2021', count(*) from cisce_scraper.cisce_2021 union all select 'link_cisce_udise', count(*) from cisce_scraper.link_cisce_udise
  union all select 'link_cisce_cbse', count(*) from cisce_scraper.link_cisce_cbse"
