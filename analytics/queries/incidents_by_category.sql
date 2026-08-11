-- Supporting view: incident mix by AI category.
--
-- Not one of the seven ADR-015 metrics, but the dashboard renders it and every
-- figure on screen must be traceable to a named query file (Ch. 18A). This is
-- that file.
--
-- Incidents the AI never classified appear as 'unspecified' rather than being
-- dropped, so the chart's total always matches the funnel's first stage.

SELECT
    COALESCE(nullif(ai_category, ''), 'unspecified')            AS category,
    count(*)                                                    AS incidents,
    round(count(*)::numeric / nullif(sum(count(*)) OVER (), 0), 3) AS share
FROM sos
WHERE created_at >= now() - make_interval(days => :window_days)
GROUP BY COALESCE(nullif(ai_category, ''), 'unspecified')
ORDER BY incidents DESC;
