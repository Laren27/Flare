-- Metric: Escalation rate (Ch. 18A)
-- Definition: incidents requiring expansion / total, split by ADR-012 trigger
-- condition A (empty candidate set) versus B (acceptance timeout).
--
-- This is the metric that distinguishes TOO FEW RESPONDERS from UNRESPONSIVE
-- RESPONDERS. They look identical from the outside -- an incident that took too
-- long -- and they have entirely different remedies: recruit, or re-engage. A
-- single "escalation rate" number cannot tell you which, which is precisely why
-- ADR-015 specifies the split.
--
-- escalation_trigger records the condition that STARTED escalation, not the one
-- at the final rung (ADR-023). Recording the last would file nearly everything
-- as empty_set, since the last rung almost always finds nobody new.

WITH window_sos AS (
    SELECT id, wave_count, status
    FROM sos
    WHERE created_at >= now() - make_interval(days => :window_days)
)
SELECT
    COALESCE(h.escalation_trigger, 'none')                       AS trigger,
    count(*)                                                     AS incidents,
    round(count(*)::numeric / nullif(
        (SELECT count(*) FROM window_sos), 0), 3)                AS share,
    count(*) FILTER (WHERE s.status = 'no_responder_found')       AS ended_unmatched,
    round(avg(COALESCE(h.escalation_count, 0)), 2)                AS mean_expansions
FROM window_sos s
LEFT JOIN incident_history h ON h.sos_id = s.id
GROUP BY COALESCE(h.escalation_trigger, 'none')
ORDER BY incidents DESC;
