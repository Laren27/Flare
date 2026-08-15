/* Thin API client. Same-origin, because the frontend is served by FastAPI
 * itself -- no CORS layer to configure and no second host to keep in sync. */

const TOKEN_KEY = "flare.token";
const USER_KEY = "flare.user";

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get user() {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  get isAuthenticated() {
    return Boolean(this.token);
  },
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;

  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401) {
    // The token expired or was never valid. JWT expiry is enforced server-side
    // (Ch. 22), so the client's only correct response is to send them to log in.
    auth.clear();
    if (!location.pathname.endsWith("/login.html")) {
      location.href = "/app/login.html";
    }
    throw new ApiError(401, "Session expired");
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, payload?.detail ?? null);
  }
  return payload;
}

export const api = {
  signup: (body) => request("POST", "/auth/signup", body),
  login: (phone, password) => request("POST", "/auth/login", { phone, password }),
  me: () => request("GET", "/auth/me"),

  createSos: (lat, lng, description) =>
    request("POST", "/sos", { lat, lng, description }),
  getSos: (id) => request("GET", `/sos/${id}`),
  acceptSos: (id) => request("POST", `/sos/${id}/accept`),
  declineSos: (id) => request("POST", `/sos/${id}/decline`),
  // Cancel and resolve are different outcomes, not two names for one (ADR-025):
  // resolve asserts that help arrived, cancel that the citizen withdrew.
  cancelSos: (id) => request("POST", `/sos/${id}/cancel`),
  resolveSos: (id) => request("POST", `/sos/${id}/resolve`),

  volunteerMe: () => request("GET", "/volunteers/me"),
  // Going online carries a position (ADR-026); the server refuses without one.
  setAvailability: (available, position = null) =>
    request("PATCH", "/volunteers/availability", {
      available,
      lat: position?.lat ?? null,
      lng: position?.lng ?? null,
    }),

  analytics: (windowDays = 30) => request("GET", `/admin/analytics?window_days=${windowDays}`),
  adminIncidents: () => request("GET", "/admin/incidents"),
};

/** Browser geolocation as a promise, with an honest failure. */
export function currentPosition(options = {}) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("This browser cannot report a location."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      (error) => reject(new Error(error.message || "Location permission denied.")),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000, ...options }
    );
  });
}

export function requireAuth(role) {
  if (!auth.isAuthenticated) {
    location.href = "/app/login.html";
    return null;
  }
  const user = auth.user;
  if (role && user?.role !== role) {
    location.href = "/app/login.html";
    return null;
  }
  return user;
}

/* `initials` moved to shared/format.js. Turning a display name into two
 * letters is not an API-client concern, and having it here meant every page
 * that wanted an avatar imported the network layer to get it. */
