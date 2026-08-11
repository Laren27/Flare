/* Extracted from the page so the Content-Security-Policy can stay strict.
 * script-src 'self' blocks inline execution -- which silently broke this
 * page the moment security headers were added, because all of its logic
 * lived in an inline <script>. Weakening the policy with 'unsafe-inline'
 * would have fixed the symptom and removed the protection.
 */

import { api, auth } from "/app/shared/api.js";

const HOME = { citizen: "/app/citizen/", volunteer: "/app/volunteer/", admin: "/app/admin/" };

const form = document.getElementById("form");
const message = document.getElementById("message");
const submit = document.getElementById("submit");
const tabLogin = document.getElementById("tab-login");
const tabSignup = document.getElementById("tab-signup");
const nameField = document.getElementById("name-field");
const roleField = document.getElementById("role-field");

let mode = new URLSearchParams(location.search).has("signup") ? "signup" : "login";

function render() {
  const signingUp = mode === "signup";
  tabLogin.setAttribute("aria-selected", String(!signingUp));
  tabSignup.setAttribute("aria-selected", String(signingUp));
  nameField.hidden = !signingUp;
  roleField.hidden = !signingUp;
  document.getElementById("name").required = signingUp;
  document.getElementById("password").autocomplete = signingUp ? "new-password" : "current-password";
  submit.textContent = signingUp ? "Create account" : "Sign in";
  message.hidden = true;
}

const preset = new URLSearchParams(location.search).get("signup");
if (preset === "volunteer" || preset === "citizen") {
  document.getElementById("role").value = preset;
}

tabLogin.addEventListener("click", () => { mode = "login"; render(); });
tabSignup.addEventListener("click", () => { mode = "signup"; render(); });
render();

function show(text, kind = "error") {
  message.textContent = text;
  message.className = `toast toast--${kind}`;
  message.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submit.disabled = true;
  const data = Object.fromEntries(new FormData(form));

  try {
    if (mode === "signup") {
      await api.signup({
        name: data.name.trim(),
        phone: data.phone.trim(),
        password: data.password,
        role: data.role,
      });
    }
    const token = await api.login(data.phone.trim(), data.password);
    auth.save(token.access_token, null);
    const user = await api.me();
    auth.save(token.access_token, user);
    location.href = HOME[user.role] ?? "/app/";
  } catch (error) {
    show(error.detail || error.message || "Something went wrong.");
    submit.disabled = false;
  }
});
