-- Metric: Acceptance rate (Ch. 18A)
-- Definition: accepted / alerted, sliced by skill class and by radius band.
--
-- This is the metric that tests whether ADR-007's skill ranking actually
-- improves outcomes or merely reorders a list. If CPR-trained responders accept
-- at the same rate as general volunteers, the ranking is cosmetic and the
-- project should say so rather than claim a benefit it cannot evidence.
--
-- Denominator is Notifications, not DispatchEvents: an alert that was never
-- delivered (no_socket) cannot be accepted, and counting it would depress the
-- rate for a reason that has nothing to do with the responder's willingness.

SELECT
    v.skills                                                     AS skill_class,
    CASE
        WHEN e.radius_m_at_eval <= 1000 THEN '0-1km'
        WHEN e.radius_m_at_eval <= 2000 THEN '1-2km'
        ELSE                                 '2-3km'
    END                                                          AS radius_band,
    count(*)                                                     AS alerted,
    count(*) FILTER (WHERE n.status = 'accepted')                AS accepted,
    count(*) FILTER (WHERE n.status = 'declined')                AS declined,
    count(*) FILTER (WHERE n.status = 'sent')                    AS ignored,
    round(
        count(*) FILTER (WHERE n.status = 'accepted')::numeric
        / nullif(count(*), 0),
        3
    )                                                            AS acceptance_rate
FROM notifications n
JOIN volunteers v ON v.user_id = n.volunteer_id
JOIN sos s        ON s.id = n.sos_id
-- The evaluation that produced this alert, for the radius it was sent at.
LEFT JOIN dispatch_events e
       ON e.sos_id = n.sos_id
      AND e.volunteer_id = n.volunteer_id
      AND e.wave_number = n.wave_number
WHERE s.created_at >= now() - make_interval(days => :window_days)
GROUP BY v.skills, radius_band
ORDER BY v.skills, radius_band;
