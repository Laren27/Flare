-- Metric: Time to acceptance, as a distribution (Ch. 18A)
--
-- ADR-015 asks for distributions wherever one exists, and says so out loud as
-- part of the deliverable. A histogram shows the shape -- a long right tail
-- versus a fat middle are different problems -- where p50/p90 alone cannot.
--
-- Buckets are fixed rather than computed so the axis is stable between runs.
-- A chart whose buckets move when the data moves cannot be compared to itself.

WITH accepted AS (
    SELECT extract(epoch FROM (matched_at - created_at)) AS seconds
    FROM sos
    WHERE matched_at IS NOT NULL
      -- Same exclusion as time_to_acceptance.sql (ADR-025). The two must agree:
      -- a histogram drawn from a different population than the p50/p90 printed
      -- beneath it is a chart that contradicts its own caption.
      AND status <> 'cancelled'
      AND created_at >= now() - make_interval(days => :window_days)
),
bucketed AS (
    SELECT
        CASE
            WHEN seconds <  60  THEN '0-1m'
            WHEN seconds < 120  THEN '1-2m'
            WHEN seconds < 180  THEN '2-3m'
            WHEN seconds < 300  THEN '3-5m'
            WHEN seconds < 480  THEN '5-8m'
            ELSE                     '8m+'
        END AS bucket
    FROM accepted
)
SELECT
    labels.bucket,
    labels.sort_order,
    count(bucketed.bucket) AS count
FROM (VALUES
    ('0-1m', 1), ('1-2m', 2), ('2-3m', 3), ('3-5m', 4), ('5-8m', 5), ('8m+', 6)
) AS labels(bucket, sort_order)
LEFT JOIN bucketed ON bucketed.bucket = labels.bucket
GROUP BY labels.bucket, labels.sort_order
ORDER BY labels.sort_order;
