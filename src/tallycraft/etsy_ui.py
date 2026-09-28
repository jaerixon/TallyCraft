"""Etsy windows: the Etsy section of Settings (keys, Connect/Disconnect) and the
Import from Etsy dialogs (choose an order, choose presets for unmatched items).

Network calls run on a background thread so the window never freezes; Tk is only
touched from the main thread. See SPEC §12.
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .etsy import EtsyAccount, EtsyError, EtsyOrder, ItemMatch, match_items

SKIP = "Skip this item"


def run_background(widget: tk.Misc, work, done, failed) -> None:
    """Run work() on a thread, then done(result) or failed(EtsyError) on the Tk thread."""
    box: dict = {}

    def target():
        try:
            box["ok"] = work()
        except EtsyError as exc:
            box["err"] = exc
        except Exception as exc:  # never show str(exc): it could echo a request
            box["err"] = EtsyError(f"Something went wrong while talking to Etsy ({type(exc).__name__}). Try again. "
                                   "You can still enter the order by hand.")

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    def poll():
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        if thread.is_alive():
            widget.after(100, poll)
        elif "err" in box:
            failed(box["err"])
        else:
            done(box["ok"])

    widget.after(100, poll)


# ============================================================================ Settings section

class EtsySettings:
    """Keystring, shared secret, callback URL, connection status, Connect/Disconnect.
    Keys are saved to the (encrypted) connection file, never to settings.json."""

    def __init__(self, dialog: tk.Toplevel, parent: ttk.Frame, first_row: int, account: EtsyAccount,
                 settings: dict):
        self.dialog, self.account = dialog, account
        self.mappings = dict(settings.get("etsy_mappings") or {})
        self.keystring = tk.StringVar(value=account.keystring)
        self.secret = tk.StringVar(value="")
        self.callback = tk.StringVar(value=settings.get("etsy_callback_url") or "")
        r = first_row
        ttk.Label(parent, text="ETSY", style="Hint.TLabel").grid(row=r, column=0, columnspan=3, sticky="w",
                                                                pady=(6, 0))
        ttk.Label(parent, text="API keystring").grid(row=r + 1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(parent, textvariable=self.keystring, width=44).grid(row=r + 1, column=1, columnspan=2,
                                                                      sticky="ew", pady=3)
        ttk.Label(parent, text="Shared secret").grid(row=r + 2, column=0, sticky="w", padx=(0, 8))
        secret_box = ttk.Frame(parent)
        secret_box.grid(row=r + 2, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Entry(secret_box, textvariable=self.secret, width=28, show="•").pack(side="left")
        self.secret_hint = ttk.Label(secret_box, text="", style="Hint.TLabel")
        self.secret_hint.pack(side="left", padx=(6, 0))
        ttk.Label(parent, text="Callback URL").grid(row=r + 3, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(parent, textvariable=self.callback, width=44).grid(row=r + 3, column=1, columnspan=2, sticky="ew",
                                                                     pady=3)
        ttk.Label(parent, text="From the Your Apps page at etsy.com/developers. The callback URL must match the one "
                               "registered there exactly. TallyCraft only reads orders; it never changes anything on "
                               "Etsy.", style="Hint.TLabel", wraplength=440).grid(row=r + 4, column=1, columnspan=2,
                                                                                 sticky="w")
        status_box = ttk.Frame(parent)
        status_box.grid(row=r + 5, column=1, columnspan=2, sticky="w", pady=(4, 0))
        self.connect_button = ttk.Button(status_box, text="Connect", command=self.connect)
        self.connect_button.pack(side="left")
        self.forget_button = ttk.Button(status_box, text="Forget remembered matches", command=self.forget)
        self.forget_button.pack(side="left", padx=(6, 0))
        self.status = ttk.Label(status_box, text="", wraplength=260)
        self.status.pack(side="left", padx=(8, 0))
        self.refresh()

    def refresh(self) -> None:
        a = self.account
        self.secret_hint.configure(text="(saved; leave blank to keep it)" if a.has_secret else "")
        if a.connected:
            self.status.configure(text=f"Connected to {a.shop_name}", style="TLabel")
            self.connect_button.configure(text="Disconnect", command=self.disconnect)
        else:
            self.status.configure(text="Not connected", style="Hint.TLabel")
            self.connect_button.configure(text="Connect", command=self.connect)
        n = len(self.mappings)
        self.forget_button.configure(text=f"Forget {n} remembered match{'es' if n != 1 else ''}",
                                     state="normal" if n else "disabled")

    def save_keys(self) -> None:
        """Store what's typed (a blank secret keeps the saved one)."""
        self.account.set_keys(self.keystring.get(), self.secret.get() or None)
        self.secret.set("")
        self.refresh()

    def connect(self) -> None:
        try:
            self.save_keys()
            session = self.account.begin_connect(self.callback.get())
        except EtsyError as exc:
            messagebox.showerror("Connect to Etsy", str(exc), parent=self.dialog)
            return
        except OSError as exc:
            messagebox.showerror("Connect to Etsy", f"The Etsy connection couldn't be saved ({exc.strerror}).",
                                 parent=self.dialog)
            return
        webbrowser.open(session.url)
        waiter = ConnectWaiter(self.dialog)
        cancelled = waiter.cancelled

        def work():
            code = session.wait(cancelled=cancelled)
            return self.account.finish_connect(session, code)

        def done(shop):
            waiter.destroy()
            self.refresh()
            messagebox.showinfo("Connect to Etsy", f"Connected to your Etsy shop {shop}.", parent=self.dialog)

        def failed(exc):
            waiter.destroy()
            self.refresh()
            if not (exc.kind == "cancelled" and cancelled.is_set()):
                messagebox.showerror("Connect to Etsy", str(exc), parent=self.dialog)

        run_background(self.dialog, work, done, failed)
        waiter.run()

    def disconnect(self) -> None:
        if not messagebox.askyesno("Disconnect from Etsy", f"Disconnect from {self.account.shop_name}? Your keys "
                                   "are kept, so you can Connect again later.", parent=self.dialog):
            return
        try:
            self.account.disconnect()
        except OSError as exc:
            messagebox.showerror("Disconnect from Etsy", f"The Etsy connection file couldn't be changed "
                                                         f"({exc.strerror}).", parent=self.dialog)
        self.refresh()

    def forget(self) -> None:
        self.mappings = {}
        self.refresh()

    def values(self) -> dict:
        return {"etsy_callback_url": self.callback.get().strip(), "etsy_mappings": self.mappings}


class ConnectWaiter(tk.Toplevel):
    """"Approve TallyCraft in your browser…" with Cancel."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Connect to Etsy")
        self.transient(parent)
        self.resizable(False, False)
        self.cancelled = threading.Event()
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Your browser opened Etsy's approval page.\n\nSign in to Etsy if asked, then press "
                             "Allow Access. This window closes by itself when Etsy sends you back.",
                  wraplength=360, justify="left").pack(anchor="w")
        ttk.Button(body, text="Cancel", command=self.cancel).pack(anchor="e", pady=(12, 0))
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def cancel(self):
        self.cancelled.set()

    def run(self):
        self.grab_set()
        self.master.wait_window(self)


# ============================================================================ Import from Etsy

def _match_text(m: ItemMatch) -> str:
    if m.preset:
        return f"→ package \"{m.preset}\"" + (" (remembered)" if m.how == "remembered" else "")
    if m.how == "skipped":
        return "→ skipped (remembered)"
    return "→ no package preset with this name: you'll choose one"


class OrderPicker(tk.Toplevel):
    """Recent paid, unshipped orders. result: the chosen EtsyOrder, or None."""

    COLUMNS = (("order", "Order #", 110), ("buyer", "Buyer", 160), ("date", "Order date", 90),
               ("items", "Items", 430))

    def __init__(self, parent, orders: list[EtsyOrder], total: int, preset_names: list[str],
                 mappings: dict[str, str]):
        super().__init__(parent)
        self.title("Import from Etsy")
        self.transient(parent)
        self.geometry("880x520")
        self.result = None
        self.orders = orders
        self._presets, self._mappings = preset_names, mappings
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        more = f" (newest {len(orders)} of {total})" if total > len(orders) else ""
        ttk.Label(body, text=f"Paid orders not yet marked shipped{more}. Choose one to build the order and fill in "
                             "the customer details.", style="Hint.TLabel", wraplength=840).grid(row=0, column=0,
                                                                                               sticky="w")
        self.tree = ttk.Treeview(body, columns=[c[0] for c in self.COLUMNS], show="headings", selectmode="browse")
        for key, title, width in self.COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w", stretch=key == "items")
        for i, o in enumerate(orders):
            self.tree.insert("", "end", iid=str(i), values=(o.receipt_id, o.buyer_name, o.order_date, o.items_text()))
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.detail = tk.Text(body, height=7, wrap="word", relief="solid", borderwidth=1, font=("Segoe UI", 9),
                              background="#fafafa")
        self.detail.grid(row=2, column=0, sticky="ew")
        btns = ttk.Frame(body)
        btns.grid(row=3, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        self.ok_button = ttk.Button(btns, text="Import", command=self._ok, default="active")
        self.ok_button.pack(side="right", padx=6)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show())
        self.tree.bind("<Double-Button-1>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        if orders:
            self.tree.selection_set("0")
            self.tree.focus("0")
        self._show()

    def selected(self) -> EtsyOrder | None:
        sel = self.tree.selection()
        return self.orders[int(sel[0])] if sel else None

    def _show(self):
        o = self.selected()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if o is not None:
            lines = [f"Order #{o.receipt_id} · {o.order_date} · {o.buyer_name}", o.address.replace("\n", ", "), ""]
            for m in match_items(o, self._presets, self._mappings):
                lines.append(f"{m.item.describe()}   {_match_text(m)}")
                if m.item.personalization:
                    lines.append(f"      Personalization: {m.item.personalization}")
            self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")
        self.ok_button.configure(state="normal" if o else "disabled")

    def _ok(self):
        self.result = self.selected()
        if self.result is not None:
            self.destroy()

    def run(self):
        self.grab_set()
        self.tree.focus_set()
        self.master.wait_window(self)
        return self.result


class UnmatchedDialog(tk.Toplevel):
    """For items whose variation matches no package preset: pick one or skip.
    result: [(preset name or None, remember)] in the same order, or None if cancelled."""

    def __init__(self, parent, unmatched: list[ItemMatch], preset_names: list[str]):
        super().__init__(parent)
        self.title("Import from Etsy: choose packages")
        self.transient(parent)
        self.result = None
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="These items don't match a package preset by name. Choose the package preset for each, "
                             "or skip it (it won't be in the order).", wraplength=620).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.choices, self.remember = [], []
        for i, m in enumerate(unmatched, start=1):
            box = ttk.Frame(body)
            box.grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(box, text=m.item.describe(), font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(box, text=m.item.title, style="Hint.TLabel", wraplength=360).pack(anchor="w")
            var = tk.StringVar(value="")
            ttk.Combobox(body, textvariable=var, values=list(preset_names) + [SKIP], state="readonly",
                         width=30).grid(row=i, column=1, sticky="w", padx=(10, 0))
            rem = tk.BooleanVar(value=True)
            ttk.Checkbutton(body, text="Remember", variable=rem).grid(row=i, column=2, sticky="w", padx=(10, 0))
            self.choices.append(var)
            self.remember.append(rem)
        n = len(unmatched) + 1
        ttk.Label(body, text="Remember: next time this variation is chosen automatically. You can forget remembered "
                             "matches in Settings > Etsy.", style="Hint.TLabel", wraplength=620).grid(
            row=n, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.error = ttk.Label(body, text="", style="Error.TLabel")
        self.error.grid(row=n + 1, column=0, columnspan=3, sticky="w")
        btns = ttk.Frame(body)
        btns.grid(row=n + 2, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Continue", command=self._ok, default="active").pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())

    def _ok(self):
        if any(not v.get() for v in self.choices):
            self.error.configure(text=f"Choose a package preset (or \"{SKIP}\") for every item.")
            return
        self.result = [(None if v.get() == SKIP else v.get(), r.get()) for v, r in zip(self.choices, self.remember)]
        self.destroy()

    def run(self):
        self.grab_set()
        self.master.wait_window(self)
        return self.result
