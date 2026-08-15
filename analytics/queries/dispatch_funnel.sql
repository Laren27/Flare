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

-- Cancelled incidents (ADR-025) stay in this funnel and are reported as their
-- own labelled count at the end. They were created, candidates were evaluated
-- and alerts really went out, so every stage above the exit is a true statement
-- about what the engine did. Removing them would make 'SOS created' disagree
-- with the incidents table, and would flatter the system by hiding alert
-- fatigue it genuinely caused.

WITH window_sos AS (
    SELECT id, status, matched_at
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
-- matched_at rather than a status test: an incident cancelled after a responder
-- accepted it was still accepted, and a status test would silently drop it out
-- of this stage and misattribute the loss to the responder.
SELECT 4, 'Accepted',         count(*) FROM window_sos WHERE matched_at IS NOT NULL
UNION ALL
SELECT 5, 'Resolved',         count(*) FROM window_sos WHERE status = 'resolved'
UNION ALL
-- Not a funnel stage: an exit from it, at whichever stage the citizen withdrew.
-- Named so the gap between Accepted and Resolved reads as a withdrawal rather
-- than as responders abandoning people.
SELECT 6, 'Cancelled',        count(*) FROM window_sos WHERE status = 'cancelled'
ORDER BY stage_order;
