-- Metric: Dispatch funnel (Ch. 18A)
-- Definition: counts at created -> candidates found -> alerted -> accepted -> resolved.
--
-- This is the metric that locates precisely where the system leaks. Each stage
-- counts INCIDENTS, not people: "alerted" means the incident reached at least
-- one responder, not how many responders it reached. Mixing the two units is
-- the easiest way to produce a funnel that cannot be reasoned about.
--
-- Every stage is derived from DispatchEvents or SOS, per ADR-014 -- no stage is
-- reconstructed from something the system never observed.

WITH window_sos AS (
    SELECT id, status
    FROM sos
    WHERE created_at >= now() - make_interval(days => :window_days)
),
with_candidates AS (
    -- An incident "found candidates" if anything was evaluated as reachable,
    -- whether or not delivery then succeeded.
    SELECT DISTINCT sos_id
    FROM dispatch_events
    WHERE sos_id IN (SELECT id FROM window_sos)
      AND (outcome = 'alerted' OR rejection_reason = 'no_socket')
),
with_alerts AS (
    SELECT DISTINCT sos_id
    FROM dispatch_events
    WHERE sos_id IN (SELECT id FROM window_sos)
      AND outcome = 'alerted'
)
SELECT 1 AS stage_order, 'SOS created'      AS stage, count(*) AS count FROM window_sos
UNION ALL
SELECT 2, 'Candidates found', count(*) FROM with_candidates
UNION ALL
SELECT 3, 'Alerted',          count(*) FROM with_alerts
UNION ALL
SELECT 4, 'Accepted',         count(*) FROM window_sos WHERE status IN ('matched', 'resolved')
UNION ALL
SELECT 5, 'Resolved',         count(*) FROM window_sos WHERE status = 'resolved'
ORDER BY stage_order;
