/* Fixture data for states the live backend cannot conveniently produce.
 *
 * The views render real data wherever the backend supports it. What remains
 * here is mocked for two different reasons:
 *
 *   1. States that are real but awkward to summon -- expanding-search and
 *      no-responder-found take a live escalation and 30s a rung to reach, and
 *      the already-accepted dismissal needs a second responder to win the race
 *      first. `?state=` and `?view=` render them on demand.
 *   2. Features that do not exist -- the verification queue and the volunteer's
 *      own history have no backing query. These are labelled Not built on
 *      screen, not merely left unlabelled.
 *
 * Anything here is labelled as sample data on screen. Rule 007 cuts both ways:
 * the demo must not imply these numbers were measured.
 */

export const CENTRE = { lat: 12.9716, lng: 77.5946 };

export const mockResponder = {
  name: "Arjun Singh",
  rating: 4.8,
  skill: "cpr",
  distance_m: 1200,
  lat: 12.9805,
  lng: 77.5992,
};

export const mockIncident = {
  id: 128,
  status: "matched",
  lat: CENTRE.lat,
  lng: CENTRE.lng,
  description: "Collapsed, not breathing",
  current_radius_m: 1000,
  wave_count: 1,
};

export const mockAlert = {
  sos_id: 128,
  lat: 12.9748,
  lng: 77.6031,
  description: "Collapsed, not breathing",
  distance_m: 1200,
  wave_number: 1,
  radius_m: 1000,
  ai_category: "Cardiac Arrest",
  ai_priority: "high",
  created_at: new Date().toISOString(),
};

export const mockVolunteerStats = {
  totalResponses: 56,
  livesImpacted: 23,
  rating: 4.8,
};

export const mockRecentAlerts = [
  { title: "Cardiac Arrest", area: "MG Road, Bangalore", when: "10:24 AM", status: "accepted" },
  { title: "Choking Case", area: "Indiranagar, Bangalore", when: "Yesterday", status: "accepted" },
  { title: "Trauma Injury", area: "Koramangala, Bangalore", when: "2 days ago", status: "accepted" },
];

export const mockBadges = [
  { icon: "❤️", label: "CPR", note: "Certified" },
  { icon: "➕", label: "First Aid", note: "Certified" },
  { icon: "🩸", label: "Blood Donor", note: "Verified" },
  { icon: "🏅", label: "Quick Responder", note: "Top 10%" },
];

/* ---- Admin fixtures ------------------------------------------------------
 * The analytics shapes below predate the live /admin/analytics endpoint and
 * are no longer rendered anywhere; `pendingVolunteers` is the one entry still
 * in use, by the Future Scope verification queue. */

export const mockAdmin = {
  stats: [
    { label: "Total Incidents", value: "128", delta: "+12%", direction: "up" },
    { label: "Time to Acceptance (p90)", value: "4m 32s", delta: "-8%", direction: "up" },
    { label: "Acceptance Rate", value: "78%", delta: "+5%", direction: "up" },
    { label: "Active Volunteers", value: "342", delta: "+10%", direction: "up" },
  ],

  /* ADR-015 insists on distributions over averages, so the headline latency
     chart is a histogram with p50/p90 marked, not a trend line of means. */
  acceptanceHistogram: [
    { bucket: "0–1m", count: 18 },
    { bucket: "1–2m", count: 34 },
    { bucket: "2–3m", count: 27 },
    { bucket: "3–5m", count: 21 },
    { bucket: "5–8m", count: 12 },
    { bucket: "8m+", count: 7 },
  ],
  percentiles: { p50: "2m 10s", p90: "4m 32s", max: "11m 48s" },

  /* The funnel of ADR-015: where the system leaks. */
  funnel: [
    { stage: "SOS created", count: 128 },
    { stage: "Candidates found", count: 121 },
    { stage: "Alerted", count: 114 },
    { stage: "Accepted", count: 89 },
    { stage: "Resolved", count: 84 },
  ],

  incidentsByType: [
    { label: "Cardiac Arrest", value: 40, color: "var(--flare-red)" },
    { label: "Choking", value: 20, color: "var(--blue)" },
    { label: "Trauma", value: 20, color: "var(--amber)" },
    { label: "Bleeding", value: 10, color: "var(--green)" },
    { label: "Other", value: 10, color: "var(--muted)" },
  ],

  /* Escalation split by trigger -- the metric that says whether the network is
     too sparse or merely unresponsive (ADR-012, ADR-015). */
  escalation: [
    { label: "No escalation", count: 96, color: "var(--green)" },
    { label: "Empty set (condition A)", count: 19, color: "var(--flare-red)" },
    { label: "Timeout (condition B)", count: 13, color: "var(--amber)" },
  ],

  topAreas: [
    { area: "MG Road", count: 23 },
    { area: "Koramangala", count: 18 },
    { area: "Indiranagar", count: 14 },
    { area: "Whitefield", count: 11 },
  ],

  /* Coverage grid: incidents with zero eligible responders in range. Values
     are gap severity 0-1 over a fixed grid (ADR-015). */
  coverageGrid: Array.from({ length: 8 * 12 }, (_, i) => {
    const x = i % 12;
    const y = Math.floor(i / 12);
    const hot = Math.exp(-(((x - 4) ** 2 + (y - 3) ** 2) / 9));
    const second = Math.exp(-(((x - 9) ** 2 + (y - 5) ** 2) / 6)) * 0.8;
    return Math.min(1, hot + second);
  }),

  pendingVolunteers: [
    { name: "Priya Nair", skill: "first_aid", certificate: "Red Cross First Aid", when: "2h ago" },
    { name: "Imran Sheikh", skill: "cpr", certificate: "AHA BLS Provider", when: "5h ago" },
    { name: "Divya Rao", skill: "blood_donor", certificate: "Donor Card #44192", when: "1d ago" },
  ],

  activeIncidents: [
    { id: 131, area: "MG Road", status: "matched", radius: 1000, waves: 1, age: "2m" },
    { id: 130, area: "Whitefield", status: "pending", radius: 2000, waves: 2, age: "6m" },
    { id: 129, area: "Hebbal", status: "no_responder_found", radius: 3000, waves: 3, age: "14m" },
  ],
};
