-- Leakage-safe comparable-sale features for each MOLIT resale label row.
--
-- Encodes CORE INVARIANT #1 (no look-ahead): a comp is usable for a label row
-- only if it was publicly reported on or before that row's prediction date, i.e.
--     comp.deal_date + reporting_lag_days <= label.deal_date
-- The reporting lag (~30d) models MOLIT's reporting delay. Never join a comp that
-- was not yet reported as of the row's date. Explicit column lists only (no SELECT *).
--
-- Params: ${PROJECT}, ${DATASET}, ${REPORTING_LAG_DAYS} (default 30),
--         ${COMP_WINDOW_DAYS} (trailing comp window, e.g. 90).

WITH labels AS (
  SELECT
    l.sggCd            AS region_code,
    l.umdNm            AS dong,
    l.deal_date        AS prediction_date,
    l.exclusive_area_m2,
    l.price_per_m2     AS label_price_per_m2
  FROM `${PROJECT}.${DATASET}.molit_resale` AS l
  WHERE l.cancel_type IS NULL          -- exclude 해제(cancelled) rows from the label
),
comps AS (
  SELECT
    c.region           AS region_code,
    c.deal_date        AS comp_deal_date,
    c.exclusive_area_m2 AS comp_area_m2,
    c.price_per_m2     AS comp_price_per_m2
  FROM `${PROJECT}.${DATASET}.molit_apt_trade` AS c
)
SELECT
  lb.region_code,
  lb.dong,
  lb.prediction_date,
  lb.exclusive_area_m2,
  lb.label_price_per_m2,
  COUNT(cp.comp_price_per_m2)                       AS n_comps,
  AVG(cp.comp_price_per_m2)                         AS comp_avg_price_per_m2,
  APPROX_QUANTILES(cp.comp_price_per_m2, 2)[OFFSET(1)] AS comp_median_price_per_m2
FROM labels AS lb
LEFT JOIN comps AS cp
  ON cp.region_code = lb.region_code
  -- reporting-lag guard: comp must have been reported by the prediction date
  AND DATE_ADD(cp.comp_deal_date, INTERVAL ${REPORTING_LAG_DAYS} DAY) <= lb.prediction_date
  -- trailing comp window
  AND cp.comp_deal_date >= DATE_SUB(lb.prediction_date, INTERVAL ${COMP_WINDOW_DAYS} DAY)
GROUP BY
  lb.region_code, lb.dong, lb.prediction_date,
  lb.exclusive_area_m2, lb.label_price_per_m2;
