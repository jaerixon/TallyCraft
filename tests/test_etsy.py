"""Etsy import: every Etsy call is mocked (no network). The keys below are made up."""

import json
import threading
import urllib.parse
import urllib.request

import pytest

from tallycraft import etsy
from tallycraft.etsy import EtsyAccount, EtsyError, match_items, packages_for, parse_receipt

KEY, SECRET = "fakekeystring0001", "fakesecret0002"
ACCESS, REFRESH = "111.fake-access-token", "111.fake-refresh-token"


def receipt(rid=3141592653, name="Jordan Rivera", items=(("XL Standard Box", 1),), **over):
    r = {"receipt_id": rid, "name": name, "created_timestamp": 1790500000, "is_paid": True, "is_shipped": False,
         "formatted_address": f"{name}\n1223 Elegance Court\nApt 4\nSpringfield, IL 62704\nUnited States",
         "transactions": [{"title": "Rabbit castle kit", "quantity": q,
                           "variations": [{"property_id": 1, "value_id": 2, "formatted_name": "Model",
                                           "formatted_value": v}]} for v, q in items]}
    r.update(over)
    return r


class FakeEtsy:
    """Stands in for urllib: records requests, answers from a script."""

    def __init__(self):
        self.calls = []
        self.receipts = [receipt()]
        self.fail = {}  # url fragment -> (status, headers, body) returned once
        self.token_status = 200
        self.clock = 1_000_000.0

    def __call__(self, method, url, headers, data=None):
        self.calls.append((method, url, dict(headers), data))
        for frag, reply in list(self.fail.items()):
            if frag in url:
                del self.fail[frag]
                return reply
        if url == etsy.TOKEN_URL:
            if self.token_status != 200:
                return self.token_status, {}, b'{"error": "invalid_grant"}'
            n = len([c for c in self.calls if c[1] == etsy.TOKEN_URL])
            return 200, {}, json.dumps({"access_token": f"{ACCESS}{n}", "refresh_token": f"{REFRESH}{n}",
                                        "expires_in": 3600, "token_type": "Bearer"}).encode()
        if url.endswith("/users/me"):
            return 200, {}, b'{"user_id": 111, "shop_id": 222}'
        if url.endswith("/shops/222"):
            return 200, {}, b'{"shop_id": 222, "shop_name": "TailsAndTimber"}'
        if "/shops/222/receipts" in url:
            return 200, {}, json.dumps({"count": len(self.receipts), "results": self.receipts}).encode()
        return 404, {}, b'{"error": "not found"}'


@pytest.fixture
def fake():
    return FakeEtsy()


def account(tmp_path, fake, connected=True):
    a = EtsyAccount(tmp_path / "etsy_connection.json", transport=fake, clock=lambda: fake.clock)
    a.set_keys(KEY, SECRET)
    if connected:
        a.data.update({"access_token": ACCESS, "refresh_token": REFRESH, "expires_at": fake.clock + 3600,
                       "shop_id": 222, "user_id": 111, "shop_name": "TailsAndTimber"})
        a._save()
    return a


# ---------------------------------------------------------------- connect (OAuth 2.0 + PKCE)

def test_connect_flow_with_pkce_and_local_listener(tmp_path, fake):
    import base64
    import hashlib
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    a = account(tmp_path, fake, connected=False)
    session = a.begin_connect(f"http://127.0.0.1:{port}/oauth/redirect")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(session.url).query)
    assert session.url.startswith(etsy.AUTH_URL)
    assert q["scope"] == ["transactions_r shops_r"]  # read-only scopes only
    assert q["client_id"] == [KEY] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == [f"http://127.0.0.1:{port}/oauth/redirect"]
    assert 43 <= len(session.verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(session.verifier.encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == [expected]
    assert SECRET not in session.url

    # The "browser" follows Etsy's redirect back to the listener.
    replies = []
    def browser():
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/oauth/redirect?code=abc123&state={session.state}",
                                    timeout=5) as r:
            replies.append(r.read().decode())
    t = threading.Thread(target=browser)
    t.start()
    code = session.wait(timeout_s=10)
    t.join()
    assert code == "abc123" and "TallyCraft is connected" in replies[0]

    assert a.finish_connect(session, code) == "TailsAndTimber"
    method, url, headers, data = fake.calls[0]
    form = urllib.parse.parse_qs(data.decode())
    assert url == etsy.TOKEN_URL and form["grant_type"] == ["authorization_code"]
    assert form["code_verifier"] == [session.verifier] and form["code"] == ["abc123"]
    assert headers["x-api-key"] == f"{KEY}:{SECRET}"
    me = next(c for c in fake.calls if c[1].endswith("/users/me"))
    assert me[2]["Authorization"].startswith("Bearer ") and me[2]["x-api-key"] == f"{KEY}:{SECRET}"
    again = EtsyAccount(a.path)  # saved
    assert again.connected and again.shop_name == "TailsAndTimber"


def test_listener_rejects_wrong_state_and_reports_denial(tmp_path, fake):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    session = account(tmp_path, fake, connected=False).begin_connect(f"http://localhost:{port}/cb")
    ok, _text = session._receive({"state": ["wrong"], "code": ["x"]})
    assert not ok and not session.done.is_set()
    session._receive({"state": [session.state], "error": ["access_denied"]})
    with pytest.raises(EtsyError, match="Deny") as e:
        session.wait(timeout_s=1)
    assert e.value.kind == "cancelled"


def test_connect_can_be_cancelled(tmp_path, fake):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    session = account(tmp_path, fake, connected=False).begin_connect(f"http://localhost:{port}/cb")
    stop = threading.Event()
    stop.set()
    with pytest.raises(EtsyError, match="cancelled"):
        session.wait(timeout_s=5, cancelled=stop)


@pytest.mark.parametrize("url", ["https://localhost:3003/cb", "http://example.com/cb", "localhost:3003", ""])
def test_callback_must_be_local_http(url):
    with pytest.raises(EtsyError) as e:
        etsy.parse_callback(url)
    assert e.value.kind == "setup"


def test_keys_are_required(tmp_path, fake):
    a = EtsyAccount(tmp_path / "e.json", transport=fake)
    with pytest.raises(EtsyError, match="keystring and shared secret") as e:
        a.begin_connect(etsy.DEFAULT_CALLBACK)
    assert e.value.kind == "setup"


# ---------------------------------------------------------------- tokens on disk

def test_keys_and_tokens_are_not_stored_in_plain_text(tmp_path, fake):
    a = account(tmp_path, fake)
    raw = a.path.read_text(encoding="utf-8")
    for secret in (KEY, SECRET, ACCESS, REFRESH):
        assert secret not in raw
    assert json.loads(raw)["scheme"] in ("dpapi", "plain")
    assert EtsyAccount(a.path).data["shared_secret"] == SECRET


def test_unreadable_connection_file_starts_over(tmp_path):
    p = tmp_path / "etsy_connection.json"
    p.write_text("{not json", encoding="utf-8")
    assert not EtsyAccount(p).connected


def test_disconnect_keeps_keys(tmp_path, fake):
    a = account(tmp_path, fake)
    a.disconnect()
    b = EtsyAccount(a.path)
    assert not b.connected and b.keystring == KEY and b.has_secret and "access_token" not in b.data


def test_new_keystring_drops_the_connection(tmp_path, fake):
    a = account(tmp_path, fake)
    a.set_keys(KEY, None)  # unchanged
    assert a.connected
    a.set_keys("otherkeystring9", "othersecret9")
    assert not a.connected and a.keystring == "otherkeystring9"


def test_expired_access_token_is_refreshed_automatically(tmp_path, fake):
    a = account(tmp_path, fake)
    fake.clock += 3600  # the hour is up
    orders, _count = a.open_orders()
    assert orders
    refresh = next(c for c in fake.calls if c[1] == etsy.TOKEN_URL)
    assert urllib.parse.parse_qs(refresh[3].decode())["grant_type"] == ["refresh_token"]
    assert EtsyAccount(a.path).data["refresh_token"] == f"{REFRESH}1"  # the new tokens are saved


def test_revoked_access_token_gets_one_refresh(tmp_path, fake):
    a = account(tmp_path, fake)
    fake.fail["/receipts"] = (401, {}, b'{"error": "invalid_token"}')
    orders, _ = a.open_orders()
    assert orders and sum(1 for c in fake.calls if c[1] == etsy.TOKEN_URL) == 1


def test_expired_login_says_connect_again(tmp_path, fake):
    a = account(tmp_path, fake)
    fake.clock += 3600
    fake.token_status = 400
    with pytest.raises(EtsyError, match="expired") as e:
        a.open_orders()
    assert e.value.kind == "expired" and "Connect again" in str(e.value)
    assert not EtsyAccount(a.path).connected  # the dead tokens are forgotten, the keys kept


# ---------------------------------------------------------------- errors in plain language

@pytest.mark.parametrize("reply, kind, words", [
    ((429, {"Retry-After": "30"}, b""), "rate", "Try again in 30 seconds"),
    ((503, {}, b"<html>down</html>"), "down", "isn't responding"),
    ((500, {}, b""), "down", "enter the order by hand"),
    ((403, {}, b'{"error": "insufficient scope"}'), "permission", "didn't allow"),
])
def test_http_errors_are_plain(tmp_path, fake, reply, kind, words):
    a = account(tmp_path, fake)
    fake.fail["/receipts"] = reply
    with pytest.raises(EtsyError) as e:
        a.open_orders()
    assert e.value.kind == kind and words in str(e.value)


def test_no_internet(tmp_path, fake, monkeypatch):
    def offline(*a, **k):
        raise urllib.error.URLError("getaddrinfo failed")
    monkeypatch.setattr(urllib.request, "urlopen", offline)
    a = account(tmp_path, fake)
    a._transport = etsy._http
    with pytest.raises(EtsyError, match="couldn't reach Etsy") as e:
        a.open_orders()
    assert e.value.kind == "offline"


def test_error_messages_never_contain_keys_or_tokens(tmp_path, fake):
    a = account(tmp_path, fake)
    body = json.dumps({"error": f"bad key {KEY}:{SECRET} token {ACCESS}"}).encode()
    fake.fail["/receipts"] = (400, {}, body)
    with pytest.raises(EtsyError) as e:
        a.open_orders()
    for secret in (KEY, SECRET, ACCESS, REFRESH):
        assert secret not in str(e.value)
    assert "[hidden]" in str(e.value)


# ---------------------------------------------------------------- orders

def test_open_orders_query(tmp_path, fake):
    orders, count = account(tmp_path, fake).open_orders()
    url = next(c[1] for c in fake.calls if "/receipts" in c[1])
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert q["was_paid"] == ["true"] and q["was_shipped"] == ["false"] and q["was_canceled"] == ["false"]
    assert url.startswith(etsy.API_BASE + "/shops/222/receipts") and count == 1
    o = orders[0]
    assert o.receipt_id == "3141592653" and o.buyer_name == "Jordan Rivera"
    assert o.address == "1223 Elegance Court\nApt 4\nSpringfield, IL 62704\nUnited States"  # name not repeated
    assert o.items[0].describe() == "1× Model: XL Standard Box"
    assert o.prefill() == {"name": "Jordan Rivera", "address": o.address, "etsy_order": "3141592653",
                           "order_date": o.order_date}
    assert len(o.order_date) == 10


def test_receipt_without_formatted_address_and_escaped_text():
    r = receipt(name="Pat O&#39;Neil", formatted_address=None, first_line="1 Main St", second_line="",
                city="Town", state="ST", zip="12345", country_iso="US")
    r["transactions"][0]["variations"].append({"formatted_name": "Personalization", "formatted_value": "Bun"})
    o = parse_receipt(r)
    assert o.buyer_name == "Pat O'Neil"
    assert o.address == "1 Main St\nTown, ST 12345\nUS"
    assert o.items[0].variations == [("Model", "XL Standard Box")] and o.items[0].personalization == "Bun"


def test_matching_variations_to_presets():
    o = parse_receipt(receipt(items=(("xl standard box", 2), ("Tunnel Pack", 1), ("XL STANDARD BOX", 1))))
    m = match_items(o, ["XL Standard Box", "Ramp"], {})
    assert [(x.preset, x.how) for x in m] == [("XL Standard Box", "variation"), (None, ""),
                                              ("XL Standard Box", "variation")]
    assert packages_for(m) == [("XL Standard Box", 3)]
    remembered = match_items(o, ["XL Standard Box", "Ramp"], {"tunnel pack": "Ramp"})
    assert remembered[1].preset == "Ramp" and remembered[1].how == "remembered"
    assert packages_for(remembered) == [("XL Standard Box", 3), ("Ramp", 1)]
    skipped = match_items(o, ["XL Standard Box"], {"tunnel pack": ""})
    assert skipped[1].preset is None and skipped[1].how == "skipped"
    gone = match_items(o, ["XL Standard Box"], {"tunnel pack": "Deleted Preset"})
    assert gone[1].how == ""  # a remembered preset that no longer exists is asked again


def test_item_without_variations_matches_on_title():
    r = receipt()
    r["transactions"][0]["variations"] = []
    r["transactions"][0]["title"] = "Ramp"
    m = match_items(parse_receipt(r), ["ramp"], {})
    assert m[0].preset == "ramp" and m[0].how == "title" and m[0].item.key == "Ramp"


def test_exe_selftest_for_etsy(tmp_path):
    from tallycraft.__main__ import selftest_etsy
    out = tmp_path / "etsy.json"
    assert selftest_etsy(str(out), []) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["round_trip"] is True
