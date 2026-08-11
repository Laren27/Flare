-- Metric: Time to acceptance (Ch. 18A)
-- Definition: matched_at - created_at, reported as p50 / p90 / max.
--
-- Percentiles, never a mean. Emergency response is a tail-latency problem: the
-- mean is the statistic that hides exactly the failures that matter, because a
-- hundred fast dispatches drown the one that took eleven minutes. p90 is the
-- number worth arguing about.
--
-- The histogram buckets are returned by time_to_acceptance_histogram.sql; this
-- query returns the summary figures only.

SELECT
    count(*)                                                         AS matched_count,
    percentile_cont(0.5) WITHIN GROUP (
        ORDER BY extract(epoch FROM (matched_at - created_at))
    )                                                                AS p50_seconds,
    percentile_cont(0.9) WITHIN GROUP (
        ORDER BY extract(epoch FROM (matched_at - created_at))
    )                                                                AS p90_seconds,
    max(extract(epoch FROM (matched_at - created_at)))                AS max_seconds
FROM sos
WHERE matched_at IS NOT NULL
  AND created_at >= now() - make_interval(days => :window_days);
