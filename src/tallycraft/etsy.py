"""Etsy Open API v3: connect a shop (OAuth 2.0 with PKCE), read its open orders,
and match the ordered variations to package presets. Read-only: TallyCraft asks
for the transactions_r (receipts, including shipping addresses) and shops_r
(which shop is connected) scopes and never changes anything on Etsy.

The API keystring, shared secret, and tokens are kept in etsy_connection.json
next to settings.json, encrypted for the Windows user (DPAPI) when available.
They are never logged or shown: every message that could reach the user goes
through _scrub(). See SPEC §12.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
API_BASE = "https://api.etsy.com/v3/application"
SCOPES = ("transactions_r", "shops_r")  # read-only
DEFAULT_CALLBACK = "http://localhost:3003/oauth/redirect"  # Etsy's own quick-start example
CONNECTION_FILE = "etsy_connection.json"
ORDER_LIMIT = 50  # newest open orders shown in "Import from Etsy"
TIMEOUT_S = 20
EXPIRY_MARGIN_S = 120  # refresh the access token this long before it expires

RECONNECT = "Open Settings > Etsy and press Connect again."
MANUAL = "You can still enter the order by hand."


class EtsyError(Exception):
    """A problem talking to Etsy, phrased for the user (never contains keys or tokens).

    kind: "setup" (keys/callback), "offline", "expired" (connect again), "permission",
    "rate" (too many requests), "down" (Etsy's side), "cancelled", or "other"."""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


# ============================================================================ secrets on disk

def _protect(data: bytes) -> tuple[str, str]:
    """Encrypt for the current Windows user (DPAPI); plain base64 where that's unavailable."""
    try:
        import win32crypt
        blob = win32crypt.CryptProtectData(data, "TallyCraft Etsy connection", None, None, None, 0)
        return "dpapi", base64.b64encode(blob).decode("ascii")
    except Exception:
        return "plain", base64.b64encode(data).decode("ascii")


def _unprotect(scheme: str, text: str) -> bytes:
    raw = base64.b64decode(text)
    if scheme == "dpapi":
        import win32crypt
        return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
    return raw


# ============================================================================ orders

@dataclass
class EtsyItem:
    title: str
    quantity: int
    variations: list[tuple[str, str]] = field(default_factory=list)  # (name, value), e.g. ("Model", "XL Box")
    personalization: str = ""

    @property
    def key(self) -> str:
        """What a remembered mapping is keyed on: the variation values, else the listing title."""
        return " / ".join(v for _n, v in self.variations) or self.title

    def describe(self) -> str:
        text = ", ".join(f"{n}: {v}" if n else v for n, v in self.variations) or self.title
        return f"{self.quantity}× {text}"


@dataclass
class EtsyOrder:
    receipt_id: str
    buyer_name: str
    order_date: str  # YYYY-MM-DD (local time)
    address: str  # multi-line shipping address, without the recipient's name
    items: list[EtsyItem]

    def items_text(self) -> str:
        return "; ".join(i.describe() for i in self.items)

    def prefill(self) -> dict:
        """Customer details for the Create Packing List dialog."""
        return {"name": self.buyer_name, "address": self.address, "etsy_order": self.receipt_id,
                "order_date": self.order_date}


def _s(value) -> str:
    """Etsy returns some text HTML-escaped (&#39; &amp;)."""
    return html.unescape(str(value)).strip() if value not in (None, "") else ""


def _address(r: dict, name: str) -> str:
    formatted = _s(r.get("formatted_address"))
    if formatted:
        lines = [ln.strip() for ln in formatted.replace("\r", "").split("\n") if ln.strip()]
        if lines and name and lines[0].casefold() == name.casefold():
            lines = lines[1:]  # the name is printed separately on the packing list
        return "\n".join(lines)
    city_line = " ".join(x for x in (", ".join(x for x in (_s(r.get("city")), _s(r.get("state"))) if x),
                                     _s(r.get("zip"))) if x)
    return "\n".join(x for x in (_s(r.get("first_line")), _s(r.get("second_line")), city_line,
                                 _s(r.get("country_iso"))) if x)


def parse_receipt(r: dict) -> EtsyOrder:
    name = _s(r.get("name"))
    ts = r.get("created_timestamp") or r.get("create_timestamp")
    try:
        order_date = datetime.fromtimestamp(int(ts)).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        order_date = ""
    items = []
    for t in r.get("transactions") or []:
        variations, personal = [], []
        for v in t.get("variations") or []:
            vname, value = _s(v.get("formatted_name")), _s(v.get("formatted_value"))
            if vname.casefold().startswith("personali"):
                personal.append(value)
            elif value:
                variations.append((vname, value))
        try:
            qty = max(1, int(t.get("quantity") or 1))
        except (TypeError, ValueError):
            qty = 1
        items.append(EtsyItem(_s(t.get("title")) or "(untitled listing)", qty, variations, "; ".join(personal)))
    return EtsyOrder(str(r.get("receipt_id", "")), name, order_date, _address(r, name), items)


# ============================================================================ matching

@dataclass
class ItemMatch:
    item: EtsyItem
    preset: str | None  # package preset name, or None (unmatched / skipped)
    how: str  # "variation", "title", "remembered", "skipped" (remembered skip), or "" (unmatched)


def match_items(order: EtsyOrder, preset_names: list[str], mappings: dict[str, str]) -> list[ItemMatch]:
    """Each item's variation value -> the package preset with the same name (case-insensitive).
    mappings: remembered choices, item.key casefolded -> preset name ("" = skip)."""
    presets = {n.strip().casefold(): n for n in preset_names}
    out = []
    for item in order.items:
        remembered = mappings.get(item.key.strip().casefold())
        if remembered == "":
            out.append(ItemMatch(item, None, "skipped"))
            continue
        if remembered and remembered.strip().casefold() in presets:
            out.append(ItemMatch(item, presets[remembered.strip().casefold()], "remembered"))
            continue
        hit = next((presets[v.strip().casefold()] for _n, v in item.variations if v.strip().casefold() in presets),
                   None)
        if hit:
            out.append(ItemMatch(item, hit, "variation"))
        elif item.title.strip().casefold() in presets:
            out.append(ItemMatch(item, presets[item.title.strip().casefold()], "title"))
        else:
            out.append(ItemMatch(item, None, ""))
    return out


def packages_for(matches: list[ItemMatch]) -> list[tuple[str, int]]:
    """(preset name, quantity) in first-seen order; the same preset twice adds up."""
    totals: dict[str, int] = {}
    for m in matches:
        if m.preset:
            totals[m.preset] = totals.get(m.preset, 0) + m.item.quantity
    return list(totals.items())


# ============================================================================ callback listener

def parse_callback(url: str) -> tuple[str, int, str]:
    """(host, port, path) for the local listener. Only http://localhost / 127.0.0.1 can be caught here."""
    u = urllib.parse.urlsplit((url or "").strip())
    if u.scheme != "http" or (u.hostname or "") not in ("localhost", "127.0.0.1"):
        raise EtsyError("The callback URL must start with http://localhost: (or http://127.0.0.1:) so TallyCraft "
                        "can catch Etsy's reply on this computer, for example " + DEFAULT_CALLBACK + ". Use the "
                        "exact callback URL registered for your app at etsy.com/developers.", "setup")
    try:
        port = u.port or 80
    except ValueError:
        raise EtsyError("The callback URL has an invalid port number.", "setup") from None
    return u.hostname, port, u.path or "/"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        session: ConnectSession = self.server.session  # type: ignore[attr-defined]
        u = urllib.parse.urlsplit(self.path)
        if u.path != session.path:
            self.send_error(404)
            return
        q = urllib.parse.parse_qs(u.query)
        ok, text = session._receive(q)
        body = ("<!doctype html><meta charset='utf-8'><title>TallyCraft</title>"
                "<body style='font-family:Segoe UI,sans-serif;margin:3em'>"
                f"<h2>{'TallyCraft is connected' if ok else 'TallyCraft could not connect'}</h2>"
                f"<p>{html.escape(text)}</p></body>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # the query string holds the one-time code: never print it
        pass


class ConnectSession:
    """One browser approval: PKCE values, the Etsy page to open, and the local listener."""

    def __init__(self, keystring: str, callback_url: str):
        self.host, self.port, self.path = parse_callback(callback_url)
        self.redirect_uri = callback_url.strip()
        self.verifier = secrets.token_urlsafe(64)[:96]  # 43-128 chars of [A-Za-z0-9-_]
        digest = hashlib.sha256(self.verifier.encode("ascii")).digest()
        self.challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        self.state = secrets.token_urlsafe(24)
        self.url = AUTH_URL + "?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": keystring, "redirect_uri": self.redirect_uri,
            "scope": " ".join(SCOPES), "state": self.state, "code_challenge": self.challenge,
            "code_challenge_method": "S256"}, quote_via=urllib.parse.quote)
        self.code: str | None = None
        self.error: EtsyError | None = None
        self.done = threading.Event()
        try:
            self._server = HTTPServer((self.host, self.port), _Handler)
        except OSError:
            raise EtsyError(f"TallyCraft couldn't listen on port {self.port} for Etsy's reply (another program may "
                            "be using it). Close other programs or TallyCraft windows and try again.",
                            "setup") from None
        self._server.session = self  # type: ignore[attr-defined]
        self._server.timeout = 0.25

    def _receive(self, q: dict) -> tuple[bool, str]:
        if self.done.is_set():
            return False, "This approval was already handled. You can close this tab."
        if q.get("state", [""])[0] != self.state:
            return False, "The reply didn't match this connection attempt. Press Connect in TallyCraft again."
        if "error" in q:
            reason = q.get("error_description", q["error"])[0]
            self.error = EtsyError("Etsy didn't approve the connection" + (
                " (you pressed Deny)." if q["error"][0] == "access_denied" else f": {reason}."), "cancelled")
            self.done.set()
            return False, "The connection wasn't approved. You can close this tab."
        code = q.get("code", [""])[0]
        if not code:
            return False, "Etsy's reply had no approval code. Press Connect in TallyCraft again."
        self.code = code
        self.done.set()
        return True, "You can close this tab and go back to TallyCraft."

    def wait(self, timeout_s: float = 300, cancelled: threading.Event | None = None) -> str:
        """Serve the callback until Etsy redirects back, the user cancels, or time runs out."""
        end = time.monotonic() + timeout_s
        try:
            while not self.done.is_set():
                if cancelled is not None and cancelled.is_set():
                    raise EtsyError("Connecting to Etsy was cancelled.", "cancelled")
                if time.monotonic() > end:
                    raise EtsyError("Etsy's approval page wasn't completed in time. Press Connect to try again.",
                                    "cancelled")
                self._server.handle_request()
        finally:
            self.close()
        if self.error:
            raise self.error
        return self.code  # type: ignore[return-value]

    def close(self) -> None:
        try:
            self._server.server_close()
        except OSError:
            pass


# ============================================================================ account / API

def _http(method: str, url: str, headers: dict, data: bytes | None = None, timeout: float = TIMEOUT_S):
    """(status, headers, body). Raises EtsyError("offline") when Etsy can't be reached at all."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return exc.code, dict(exc.headers or {}), body
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError):
        raise EtsyError("TallyCraft couldn't reach Etsy. Check the internet connection and try again. "
                        + MANUAL, "offline") from None


class EtsyAccount:
    """The connected shop: keys, tokens, and read-only API calls."""

    def __init__(self, path: Path, transport=_http, clock=time.time):
        self.path = Path(path)
        self._transport = transport
        self._clock = clock
        self._lock = threading.Lock()
        self.data = self._load()

    # ---- storage
    def _load(self) -> dict:
        try:
            wrapper = json.loads(self.path.read_text(encoding="utf-8"))
            data = json.loads(_unprotect(wrapper["scheme"], wrapper["data"]).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}  # unreadable (e.g. copied from another Windows user): start over

    def _save(self) -> None:
        scheme, text = _protect(json.dumps(self.data).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"type": "tallycraft.etsy_connection", "scheme": scheme, "data": text}),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def keystring(self) -> str:
        return self.data.get("keystring", "")

    @property
    def has_secret(self) -> bool:
        return bool(self.data.get("shared_secret"))

    @property
    def connected(self) -> bool:
        return bool(self.data.get("refresh_token") and self.data.get("shop_id"))

    @property
    def shop_name(self) -> str:
        return self.data.get("shop_name", "")

    def set_keys(self, keystring: str, shared_secret: str | None) -> None:
        """shared_secret None = keep the saved one. New keys drop the old connection."""
        keystring = keystring.strip()
        changed = keystring != self.keystring or (shared_secret is not None
                                                  and shared_secret.strip() != self.data.get("shared_secret", ""))
        if not changed:
            return
        new = {"keystring": keystring,
               "shared_secret": self.data.get("shared_secret", "") if shared_secret is None else shared_secret.strip()}
        if keystring == self.keystring:
            new.update({k: v for k, v in self.data.items() if k not in new})
        self.data = new
        self._save()

    def disconnect(self) -> None:
        """Forget the tokens (the keys stay so Connect is one click)."""
        self.data = {k: self.data[k] for k in ("keystring", "shared_secret") if k in self.data}
        self._save()

    # ---- messages
    def _scrub(self, text: str) -> str:
        for key in ("keystring", "shared_secret", "access_token", "refresh_token"):
            value = self.data.get(key)
            if value and len(value) >= 4:
                text = text.replace(value, "[hidden]")
        return text

    def _require_keys(self) -> None:
        if not self.keystring or not self.has_secret:
            raise EtsyError("Enter your Etsy API keystring and shared secret in Settings > Etsy first. They're on "
                            "the Your Apps page at etsy.com/developers.", "setup")

    def _api_key(self) -> str:
        return f"{self.keystring}:{self.data.get('shared_secret', '')}"

    def _fail(self, status: int, headers: dict, body: bytes, during: str) -> EtsyError:
        if status == 429:
            wait = {k.lower(): v for k, v in headers.items()}.get("retry-after")
            when = f" Try again in {wait} seconds." if wait and str(wait).isdigit() else " Wait a minute and try again."
            return EtsyError("Etsy is limiting how often TallyCraft can ask (rate limit)." + when, "rate")
        if status >= 500:
            return EtsyError(f"Etsy isn't responding properly right now (error {status}). Try again in a few "
                             f"minutes. {MANUAL}", "down")
        if status == 401:
            return EtsyError(f"Your Etsy login has expired or was removed. {RECONNECT}", "expired")
        if status == 403:
            return EtsyError(f"Etsy didn't allow TallyCraft to {during}. Check that you connected the right shop, "
                             f"then {RECONNECT[0].lower() + RECONNECT[1:]}", "permission")
        try:
            detail = json.loads(body.decode("utf-8", "replace")).get("error") or ""
        except (ValueError, AttributeError):
            detail = ""
        detail = self._scrub(str(detail))[:200]
        return EtsyError(f"Etsy couldn't {during} (error {status}{': ' + detail if detail else ''}).", "other")

    # ---- OAuth
    def begin_connect(self, callback_url: str) -> ConnectSession:
        self._require_keys()
        return ConnectSession(self.keystring, callback_url)

    def finish_connect(self, session: ConnectSession, code: str) -> str:
        """Trade the approval code for tokens, find the shop, save. Returns the shop name."""
        tokens = self._token_request({"grant_type": "authorization_code", "client_id": self.keystring,
                                      "redirect_uri": session.redirect_uri, "code": code,
                                      "code_verifier": session.verifier}, "finish connecting")
        with self._lock:
            self._store_tokens(tokens)
        me = self.get("/users/me", during="find your shop")
        shop_id = me.get("shop_id")
        if not shop_id:
            self.disconnect()
            raise EtsyError("This Etsy account doesn't have a shop, so there are no orders to import.", "other")
        shop = self.get(f"/shops/{int(shop_id)}", during="read your shop's name")
        self.data.update({"shop_id": int(shop_id), "user_id": me.get("user_id"),
                          "shop_name": _s(shop.get("shop_name")) or f"shop {shop_id}",
                          "connected_at": datetime.now().isoformat(timespec="seconds")})
        self._save()
        return self.shop_name

    def _token_request(self, form: dict, during: str) -> dict:
        status, headers, body = self._transport(
            "POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                                "x-api-key": self._api_key()},
            urllib.parse.urlencode(form).encode("ascii"))
        if status in (400, 401) and form.get("grant_type") == "refresh_token":
            self.disconnect()
            raise EtsyError(f"Your Etsy login has expired. {RECONNECT}", "expired")
        if status != 200:
            raise self._fail(status, headers, body, during)
        try:
            tokens = json.loads(body.decode("utf-8"))
            tokens["access_token"], tokens["refresh_token"]
        except (ValueError, KeyError, TypeError):
            raise EtsyError(f"Etsy sent an unexpected reply while trying to {during}. Try again.", "other") from None
        return tokens

    def _store_tokens(self, tokens: dict) -> None:
        self.data["access_token"] = tokens["access_token"]
        self.data["refresh_token"] = tokens["refresh_token"]
        self.data["expires_at"] = self._clock() + float(tokens.get("expires_in") or 3600)
        self._save()

    def _access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            if not self.data.get("refresh_token"):
                raise EtsyError(f"TallyCraft isn't connected to Etsy. {RECONNECT}", "expired")
            if force_refresh or self._clock() > float(self.data.get("expires_at") or 0) - EXPIRY_MARGIN_S:
                tokens = self._token_request({"grant_type": "refresh_token", "client_id": self.keystring,
                                              "refresh_token": self.data["refresh_token"]}, "renew the login")
                self._store_tokens(tokens)
            return self.data["access_token"]

    # ---- API
    def get(self, path: str, params: dict | None = None, during: str = "read from your shop") -> dict:
        self._require_keys()
        url = API_BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        for attempt in range(2):
            headers = {"Accept": "application/json", "x-api-key": self._api_key(),
                       "Authorization": f"Bearer {self._access_token(force_refresh=attempt > 0)}"}
            status, rh, body = self._transport("GET", url, headers)
            if status == 401 and attempt == 0:
                continue  # the access token may have been revoked early: renew once
            if status != 200:
                raise self._fail(status, rh, body, during)
            try:
                return json.loads(body.decode("utf-8"))
            except ValueError:
                raise EtsyError(f"Etsy sent an unexpected reply while trying to {during}. Try again.",
                                "other") from None
        raise EtsyError(f"Your Etsy login has expired. {RECONNECT}", "expired")  # pragma: no cover

    def open_orders(self, limit: int = ORDER_LIMIT) -> tuple[list[EtsyOrder], int]:
        """Paid, not shipped, not canceled orders, newest first. Returns (orders, total count on Etsy)."""
        if not self.connected:
            raise EtsyError(f"TallyCraft isn't connected to Etsy. {RECONNECT}", "expired")
        data = self.get(f"/shops/{int(self.data['shop_id'])}/receipts",
                        {"was_paid": "true", "was_shipped": "false", "was_canceled": "false", "limit": limit,
                         "sort_on": "created", "sort_order": "desc"}, during="read your open orders")
        receipts = data.get("results") or []
        return [parse_receipt(r) for r in receipts], int(data.get("count") or len(receipts))
