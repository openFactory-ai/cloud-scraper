"""OAuth flow helpers — local redirect server for authorization codes."""

import http.server
import threading
import urllib.parse
from dataclasses import dataclass


@dataclass
class AuthResult:
    code: str | None = None
    error: str | None = None


class OAuthRedirectHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth authorization code."""

    auth_result: AuthResult | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthRedirectHandler.auth_result = AuthResult(code=params["code"][0])
            self._respond("Authorization successful! You can close this tab.")
        elif "error" in params:
            error = params.get("error_description", params["error"])[0]
            OAuthRedirectHandler.auth_result = AuthResult(error=error)
            self._respond(f"Authorization failed: {error}")
        else:
            self._respond("Waiting for authorization...")

    def _respond(self, message: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = f"""<!DOCTYPE html>
<html><head><title>Data Scraper</title>
<style>body{{font-family:sans-serif;display:flex;justify-content:center;
align-items:center;height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0}}
.card{{background:#16213e;padding:2rem 3rem;border-radius:12px;
text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.3)}}</style></head>
<body><div class="card"><h2>{message}</h2></div></body></html>"""
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # Suppress request logging


def run_oauth_redirect_server(port: int = 8085, timeout: float = 120.0) -> AuthResult:
    """Start a local HTTP server to capture the OAuth redirect.

    Returns the AuthResult with the authorization code or error.
    Blocks until the code is received or timeout expires.
    """
    OAuthRedirectHandler.auth_result = None
    server = http.server.HTTPServer(("127.0.0.1", port), OAuthRedirectHandler)
    server.timeout = timeout

    def serve():
        while OAuthRedirectHandler.auth_result is None:
            server.handle_request()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    server.server_close()
    return OAuthRedirectHandler.auth_result or AuthResult(error="Timed out waiting for authorization")
