-- Metric: AI degradation rate (Ch. 18A)
-- Definition: ai_status != 'ok' / total.
--
-- Honest reporting of the system's weakest dependency. ADR-013 makes the AI
-- call non-blocking precisely because it is expected to fail sometimes; this
-- measures how often "sometimes" actually is, rather than leaving it as an
-- assurance.
--
-- The statuses are kept separate rather than summed into one degradation
-- figure, because they mean different things and have different fixes:
--   timeout -> the 3s budget is too tight, or the provider is slow
--   error   -> quota exhausted, network failure, or a malformed response
--   skipped -> no description given, or no API key configured (not a fault)

SELECT
    ai_status,
    count(*)                                                    AS incidents,
    round(count(*)::numeric / nullif(sum(count(*)) OVER (), 0), 3) AS share
FROM sos
WHERE created_at >= now() - make_interval(days => :window_days)
GROUP BY ai_status
ORDER BY incidents DESC;
