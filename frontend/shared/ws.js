/* Real-time channel client.
 *
 * Mirrors ADR-022 on the browser side: connect, then send the auth frame
 * first. The token never goes in the URL, because a URL is written to access
 * logs and browser history and a JWT valid for an hour is a credential.
 */

import { auth } from "./api.js";

export class RealtimeChannel extends EventTarget {
  constructor(userId) {
    super();
    this.userId = userId;
    this.socket = null;
    this.retryDelay = 1000;
    this.closedByUs = false;
  }

  connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    this.socket = new WebSocket(`${scheme}://${location.host}/ws/${this.userId}`);

    this.socket.addEventListener("open", () => {
      this.socket.send(JSON.stringify({ type: "auth", token: auth.token }));
    });

    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "auth_ok") {
        this.retryDelay = 1000;
        this.dispatchEvent(new CustomEvent("ready"));
        return;
      }
      this.dispatchEvent(new CustomEvent(message.type, { detail: message }));
    });

    this.socket.addEventListener("close", (event) => {
      this.dispatchEvent(new CustomEvent("offline", { detail: event }));
      if (this.closedByUs) return;

      // 1008 is the server refusing our credentials (ADR-022). Retrying with
      // the same bad token would just loop, so this is terminal.
      if (event.code === 1008) {
        this.dispatchEvent(new CustomEvent("unauthorized"));
        return;
      }

      setTimeout(() => this.connect(), this.retryDelay);
      this.retryDelay = Math.min(this.retryDelay * 2, 15000);
    });
  }

  close() {
    this.closedByUs = true;
    this.socket?.close();
  }
}
