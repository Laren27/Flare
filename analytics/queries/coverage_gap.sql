-- Metric: Coverage gap (Ch. 18A)
-- Definition: a fixed grid over the operating area. A bucket is a gap if it
-- contains at least one incident and had zero eligible responders within the
-- base radius at incident time.
--
-- This is the only metric that answers "where should we recruit responders?",
-- and it is computable only because ADR-014 records rejections rather than
-- silently filtering them. "Zero eligible responders" is read from the event
-- log as "no row with outcome='alerted'", which is a fact the system observed
-- at the time -- not a re-derivation from today's responder table, which would
-- answer a different question about a different moment.
--
-- Buckets are ~500m: 0.0045 degrees of latitude, and longitude divided by
-- cos(latitude) so cells stay roughly square away from the equator.

WITH incidents AS (
    SELECT
        s.id,
        s.lat,
        s.lng,
        floor(s.lat / :bucket_deg)                                   AS grid_y,
        floor(s.lng / (:bucket_deg / cos(radians(s.lat))))           AS grid_x,
        EXISTS (
            SELECT 1 FROM dispatch_events e
            WHERE e.sos_id = s.id
              AND e.wave_number = 1
              AND e.outcome = 'alerted'
        ) AS had_responder
    FROM sos s
    WHERE s.created_at >= now() - make_interval(days => :window_days)
)
SELECT
    grid_x,
    grid_y,
    count(*)                                              AS incident_count,
    count(*) FILTER (WHERE NOT had_responder)             AS uncovered_count,
    round(
        count(*) FILTER (WHERE NOT had_responder)::numeric / count(*),
        3
    )                                                     AS gap_severity,
    round(avg(lat)::numeric, 5)                           AS centre_lat,
    round(avg(lng)::numeric, 5)                           AS centre_lng
FROM incidents
GROUP BY grid_x, grid_y
ORDER BY gap_severity DESC, incident_count DESC;
