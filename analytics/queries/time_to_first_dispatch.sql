-- Metric: Time to first dispatch (Ch. 18A)
-- Definition: first_dispatch_at - created_at.
--
-- This is the metric that separates an engineering problem from a network
-- problem. Time to acceptance mixes system latency with human latency; this
-- isolates the part the code is responsible for. If this number is bad, fix the
-- code. If this is fine and acceptance is slow, the responders are the issue --
-- entirely different remedies, which is why both are reported.

SELECT
    count(*)                                                              AS dispatched_count,
    avg(extract(epoch FROM (first_dispatch_at - created_at)))              AS mean_seconds,
    percentile_cont(0.5) WITHIN GROUP (
        ORDER BY extract(epoch FROM (first_dispatch_at - created_at))
    )                                                                     AS p50_seconds,
    percentile_cont(0.9) WITHIN GROUP (
        ORDER BY extract(epoch FROM (first_dispatch_at - created_at))
    )                                                                     AS p90_seconds,
    max(extract(epoch FROM (first_dispatch_at - created_at)))              AS max_seconds
FROM sos
WHERE first_dispatch_at IS NOT NULL
  AND created_at >= now() - make_interval(days => :window_days);
