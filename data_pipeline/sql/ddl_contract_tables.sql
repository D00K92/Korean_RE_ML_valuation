-- DDL for the korea_real_estate.* contract dataset (Data <-> ML boundary).
--
-- The raw source tables (molit_resale, molit_apt_trade, ecos_macro, applyhome,
-- commercial) are LOAD-created by data_pipeline/warehouse/bigquery_io.py from the
-- GCS Parquet lake (schema autodetect + Hive partitioning on `region`), so they
-- need no explicit CREATE TABLE here. This file (a) creates the dataset and
-- (b) documents the contract each downstream query relies on. Parameterise
-- ${PROJECT} / ${DATASET} at apply time (defaults: current project / korea_real_estate).

CREATE SCHEMA IF NOT EXISTS `${PROJECT}.${DATASET}`
OPTIONS (location = 'asia-northeast3');

-- Contract columns the ML pillar depends on (documentation; loads autodetect):
--   molit_resale     : region, deal_date DATE, exclusive_area_m2, dealAmount,
--                      price_per_m2, right_type, cancel_type, aptNm, umdNm, sggCd ...
--   molit_apt_trade  : region, deal_date DATE, exclusive_area_m2, price_per_m2 ...  (comps)
--   ecos_macro       : month DATE, base_rate, mortgage_rate, m2, sentiment_csi ...
--   applyhome        : announce_no, notice_date DATE, supply_price, move_in_ym,
--                      total_units, builder, house_name, supply_region ...
--   commercial       : region, lat, lon, category ...  (spatial amenity POIs)
--   features         : the assembled ML matrix (written by the preprocess step)
