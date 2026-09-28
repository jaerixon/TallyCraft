"""GUI tests for Import from Etsy and the Etsy section of Settings. No network:
the Etsy account is a fake (see test_etsy.py for the API layer)."""

import json
import os

import pytest

from tallycraft import etsy_ui, gui, packing_ui
from tallycraft.etsy import EtsyAccount, EtsyError, parse_receipt
from test_etsy import FakeEtsy, receipt
from test_gui_packing import TK_STARTUP_FLAKE, _tk_available, app, files, pump  # noqa: F401  (pytest fixtures)

pytestmark = [pytest.mark.skipif(not _tk_available(), reason="no display for Tk"), TK_STARTUP_FLAKE, pytest.mark.gui]


class FakeAccount:
    def __init__(self, orders=None, error=None, connected=True):
        self.connected, self.shop_name = connected, "TailsAndTimber"
        self.orders, self.error = orders or [], error

    def open_orders(self):
        if self.error:
            raise self.error
        return self.orders, len(self.orders)


def save_presets(app, files):
    pieces = [{"path": files["panel"], "units": "in", "count": 2, "mtime": os.path.getmtime(files["panel"])},
              {"path": files["pin"], "units": "in", "count": 4, "mtime": os.path.getmtime(files["pin"])}]
    app.storage.save_package("XL Standard Box", pieces)
    app.storage.save_package("Ramp", pieces[1:])


def run_import(app, monkeypatch, order, choose_unmatched=None):
    """Import `order` with the order picker answered automatically."""
    monkeypatch.setattr(gui, "OrderPicker", lambda *a, **k: type("P", (), {"run": lambda self: order})())
    if choose_unmatched is not None:
        monkeypatch.setattr(gui, "UnmatchedDialog",
                            lambda parent, unmatched, presets: type("U", (), {"run": lambda self: choose_unmatched})())
    app.import_from_etsy()
    pump(app, lambda: app.cget("cursor") == "" and (app.calls["info"] or app.calls["error"] or app.calls["ask"]))


def test_import_builds_order_and_prefills_packing_dialog(app, files, monkeypatch):
    save_presets(app, files)
    order = parse_receipt(receipt(items=(("xl standard box", 2), ("Ramp", 1))))
    app.etsy = FakeAccount([order])
    run_import(app, monkeypatch, order)
    assert [(p.name, p.quantity, p.preset_name) for p in app.order.packages] == [
        ("XL Standard Box", 2, "XL Standard Box"), ("Ramp", 1, "Ramp")]
    assert not any(p.is_dirty for p in app.order.packages)
    assert "Imported Etsy order #3141592653" in app.calls["info"][-1]

    seen = {}

    class Dialog:
        def __init__(self, *a, prefill=None, **k):
            seen["prefill"] = prefill

        def run(self):
            return None
    monkeypatch.setattr(gui, "PackingDialog", Dialog)
    app.cal_mode.set("control")
    app._on_mode_changed()
    app.ctl_length.set("4")
    app.ctl_width.set("2")
    app.ctl_weight.set("23.456")
    app.calculate()
    app.update()
    app.create_packing_list()
    assert seen["prefill"] == {"name": "Jordan Rivera", "etsy_order": "3141592653", "order_date": order.order_date,
                               "address": "1223 Elegance Court\nApt 4\nSpringfield, IL 62704\nUnited States"}
    app.new_blank_package()  # still the same order: prefill kept
    app.order = gui.Order.with_blank_package()  # a different order: no stale customer details
    assert app._etsy_prefill[0] is not app.order


def test_unmatched_items_are_chosen_and_remembered(app, files, monkeypatch):
    save_presets(app, files)
    order = parse_receipt(receipt(items=(("XL Standard Box", 1), ("Tunnel Pack", 3), ("Gift Wrap", 1))))
    app.etsy = FakeAccount([order])
    run_import(app, monkeypatch, order, choose_unmatched=[("Ramp", True), (None, False)])
    assert [(p.name, p.quantity) for p in app.order.packages] == [("XL Standard Box", 1), ("Ramp", 3)]
    assert "Skipped: 1× Model: Gift Wrap" in app.calls["info"][-1]
    saved = json.loads(app.storage.settings_path.read_text(encoding="utf-8"))
    assert saved["etsy_mappings"] == {"tunnel pack": "Ramp"}  # only the one marked Remember

    # next time the remembered item is matched without asking
    app.calls["info"].clear()
    monkeypatch.setattr(gui, "UnmatchedDialog", lambda parent, unmatched, presets: type("U", (), {
        "run": lambda self: [(None, False)] * len(unmatched)})())
    app.answers["ask"] = [True]  # replace the current order
    run_import(app, monkeypatch, order)
    assert [(p.name, p.quantity) for p in app.order.packages] == [("XL Standard Box", 1), ("Ramp", 3)]


def test_cancelling_unmatched_keeps_the_current_order(app, files, monkeypatch):
    save_presets(app, files)
    before = app.order
    order = parse_receipt(receipt(items=(("Tunnel Pack", 1),)))
    app.etsy = FakeAccount([order])
    monkeypatch.setattr(gui, "OrderPicker", lambda *a, **k: type("P", (), {"run": lambda self: order})())
    monkeypatch.setattr(gui, "UnmatchedDialog", lambda *a, **k: type("U", (), {"run": lambda self: None})())
    app.import_from_etsy()
    pump(app, lambda: app.cget("cursor") == "")
    app.update()
    assert app.order is before


@pytest.mark.parametrize("error, shown", [
    (EtsyError("TallyCraft couldn't reach Etsy. Check the internet connection.", "offline"), "error"),
    (EtsyError("Etsy isn't responding properly right now (error 503).", "down"), "error"),
    (EtsyError("Etsy is limiting how often TallyCraft can ask (rate limit).", "rate"), "error"),
    (EtsyError("Your Etsy login has expired.", "expired"), "ask"),
])
def test_etsy_errors_are_shown_and_manual_entry_still_works(app, files, error, shown):
    app.etsy = FakeAccount(error=error)
    app.import_from_etsy()
    pump(app, lambda: app.calls["error"] or app.calls["ask"])
    assert str(error) in (app.calls[shown][-1])
    assert app.order.is_single_blank() and app.cget("cursor") == ""
    app.import_files()  # manual work continues
    assert app.order.packages[0].order


def test_not_connected_offers_settings(app, monkeypatch):
    app.etsy = FakeAccount(connected=False)
    opened = []
    monkeypatch.setattr(app, "open_settings", lambda: opened.append(True))
    app.answers["ask"] = [True]
    app.import_from_etsy()
    assert "isn't connected" in app.calls["ask"][-1] and opened


def test_no_open_orders(app):
    app.etsy = FakeAccount([])
    app.import_from_etsy()
    pump(app, lambda: app.calls["info"])
    assert "no paid, unshipped orders" in app.calls["info"][-1]


# ---------------------------------------------------------------- dialogs

def test_order_picker_shows_matches_and_returns_the_choice(app):
    orders = [parse_receipt(receipt(rid=1, items=(("XL Standard Box", 2),))),
              parse_receipt(receipt(rid=2, name="Sam Lee", items=(("Tunnel Pack", 1),)))]
    d = etsy_ui.OrderPicker(app, orders, 7, ["XL Standard Box"], {})
    d.update()
    assert "→ package \"XL Standard Box\"" in d.detail.get("1.0", "end")
    d.tree.selection_set("1")
    d.update()
    assert "you'll choose one" in d.detail.get("1.0", "end")
    assert "newest 2 of 7" in str([w.cget("text") for w in d.winfo_children()[0].winfo_children()
                                   if isinstance(w, etsy_ui.ttk.Label)])
    d._ok()
    assert d.result is orders[1]


def test_unmatched_dialog_requires_a_choice(app):
    order = parse_receipt(receipt(items=(("Tunnel Pack", 1), ("Gift", 1))))
    from tallycraft.etsy import match_items
    unmatched = match_items(order, ["Ramp"], {})
    d = etsy_ui.UnmatchedDialog(app, unmatched, ["Ramp"])
    d._ok()
    assert d.result is None and "every item" in d.error.cget("text")
    d.choices[0].set("Ramp")
    d.choices[1].set(etsy_ui.SKIP)
    d.remember[1].set(False)
    d._ok()
    assert d.result == [("Ramp", True), (None, False)]


def test_settings_etsy_section_saves_keys_outside_settings(app, tmp_path):
    fake = FakeEtsy()
    account = EtsyAccount(app.storage.etsy_path, transport=fake)
    d = packing_ui.SettingsDialog(app, app.settings, app.storage, None, etsy=account)
    assert d.etsy.status.cget("text") == "Not connected"
    d.etsy.keystring.set("fakekeystring0001")
    d.etsy.secret.set("fakesecret0002")
    d.etsy.callback.set("http://localhost:3003/oauth/redirect")
    d._ok()
    assert d.result["etsy_callback_url"] == "http://localhost:3003/oauth/redirect"
    assert "fakesecret0002" not in json.dumps(d.result) and "fakekeystring0001" not in json.dumps(d.result)
    again = EtsyAccount(app.storage.etsy_path)
    assert again.keystring == "fakekeystring0001" and again.has_secret
    assert "fakesecret0002" not in app.storage.etsy_path.read_text(encoding="utf-8")


def test_settings_shows_connected_shop_and_forgets_matches(app):
    fake = FakeEtsy()
    account = EtsyAccount(app.storage.etsy_path, transport=fake)
    account.set_keys("fakekeystring0001", "fakesecret0002")
    account.data.update({"refresh_token": "r", "access_token": "a", "shop_id": 222, "shop_name": "TailsAndTimber"})
    settings = dict(app.settings, etsy_mappings={"tunnel pack": "Ramp"})
    d = packing_ui.SettingsDialog(app, settings, app.storage, None, etsy=account)
    assert d.etsy.status.cget("text") == "Connected to TailsAndTimber"
    assert d.etsy.connect_button.cget("text") == "Disconnect"
    assert "1 remembered match" in d.etsy.forget_button.cget("text")
    d.etsy.forget()
    app.answers["ask"] = [True]
    d.etsy.disconnect()
    assert d.etsy.status.cget("text") == "Not connected" and not account.connected
    d._ok()
    assert d.result["etsy_mappings"] == {}
