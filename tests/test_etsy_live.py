"""Opt-in live test: lists the real open orders of your connected Etsy shop.

Skipped unless you ask for it. Connect first in TallyCraft (Settings > Etsy), then:

    set TALLYCRAFT_ETSY_LIVE=1
    set TALLYCRAFT_ETSY_DIR=D:\\path\\to\\the TallyCraft folder you connected from
    .venv\\Scripts\\python -m pytest tests\\test_etsy_live.py -s

It only reads from Etsy. It uses (and may renew) the login saved in that folder's
etsy_connection.json, exactly as TallyCraft itself does. Nothing is written
anywhere else, and keys/tokens are never printed.
"""

import os
from pathlib import Path

import pytest

from tallycraft.etsy import EtsyAccount

pytestmark = pytest.mark.skipif(os.environ.get("TALLYCRAFT_ETSY_LIVE") != "1",
                                reason="live Etsy test: set TALLYCRAFT_ETSY_LIVE=1 and TALLYCRAFT_ETSY_DIR to run it")


def test_list_real_open_orders():
    folder = os.environ.get("TALLYCRAFT_ETSY_DIR")
    assert folder, "Set TALLYCRAFT_ETSY_DIR to the TallyCraft folder where you connected to Etsy."
    account = EtsyAccount(Path(folder) / "etsy_connection.json")
    assert account.connected, f"Not connected in {folder}. Use Settings > Etsy > Connect in TallyCraft first."
    orders, total = account.open_orders()
    print(f"\nShop {account.shop_name}: {total} paid, unshipped order(s); showing {len(orders)}.")
    for o in orders:
        print(f"  #{o.receipt_id}  {o.order_date}  {o.buyer_name}")
        for item in o.items:
            print(f"      {item.describe()}")
    assert all(o.receipt_id for o in orders)
