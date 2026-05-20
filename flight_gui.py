#!/usr/bin/env python3
"""
Flight Search GUI - tkinter interface for SkyScanner flight price search.
"""

import datetime
import json
import os
import threading
import webbrowser
from tkinter import ttk, messagebox
from tkinter import *

from skyscanner.types import CabinClass
from skyscanner import SkyScanner

RESULTS_DIR = "results"
CABIN_NAMES = ["Economy", "Premium Economy", "Business", "First"]
CABIN_VALUES = {
    "Economy": CabinClass.ECONOMY,
    "Premium Economy": CabinClass.PREMIUM_ECONOMY,
    "Business": CabinClass.BUSINESS,
    "First": CabinClass.FIRST,
}
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY", "HKD", "KRW", "AUD", "CAD", "CHF", "SGD", "THB", "TWD"]


class FlightSearchGUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("Flight Search")
        self.root.geometry("520x320+580+200")
        self.root.resizable(False, False)
        self._build_ui()
        self.scanner = None

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=BOTH, expand=True)

        # Input grid
        row = 0
        ttk.Label(main, text="Origin").grid(row=row, column=0, sticky=E, padx=(0, 6), pady=3)
        self.origin = ttk.Entry(main, width=12)
        self.origin.grid(row=row, column=1, sticky=W, pady=3)

        ttk.Label(main, text="Destination").grid(row=row, column=2, sticky=E, padx=(12, 6), pady=3)
        self.dest = ttk.Entry(main, width=12)
        self.dest.grid(row=row, column=3, sticky=W, pady=3)

        row += 1
        ttk.Label(main, text="Depart").grid(row=row, column=0, sticky=E, padx=(0, 6), pady=3)
        self.depart = ttk.Entry(main, width=12)
        self.depart.insert(0, "2026-09-15")
        self.depart.grid(row=row, column=1, sticky=W, pady=3)

        ttk.Label(main, text="Return").grid(row=row, column=2, sticky=E, padx=(12, 6), pady=3)
        self.return_frame = ttk.Frame(main)
        self.return_frame.grid(row=row, column=3, columnspan=2, sticky=W, pady=3)
        self.return_date = ttk.Entry(self.return_frame, width=12)
        self.return_date.insert(0, "2026-09-22")
        self.return_date.pack(side=LEFT)
        self.oneway_var = BooleanVar()
        self.oneway_chk = ttk.Checkbutton(self.return_frame, text="One-way",
                                          variable=self.oneway_var, command=self._toggle_oneway)
        self.oneway_chk.pack(side=LEFT, padx=(6, 0))

        row += 1
        ttk.Label(main, text="Adults").grid(row=row, column=0, sticky=E, padx=(0, 6), pady=3)
        self.adults = ttk.Spinbox(main, from_=1, to=9, width=10)
        self.adults.set(1)
        self.adults.grid(row=row, column=1, sticky=W, pady=3)

        ttk.Label(main, text="Children").grid(row=row, column=2, sticky=E, padx=(12, 6), pady=3)
        self.children = ttk.Entry(main, width=12)
        self.children.grid(row=row, column=3, sticky=W, pady=3)
        ttk.Label(main, text="ages e.g. 9,13", font=("", 8)).grid(row=row, column=4, sticky=W, padx=4)

        row += 1
        ttk.Label(main, text="Cabin").grid(row=row, column=0, sticky=E, padx=(0, 6), pady=3)
        self.cabin = ttk.Combobox(main, values=CABIN_NAMES, state="readonly", width=12)
        self.cabin.current(0)
        self.cabin.grid(row=row, column=1, sticky=W, pady=3)

        ttk.Label(main, text="Currency").grid(row=row, column=2, sticky=E, padx=(12, 6), pady=3)
        self.currency = ttk.Combobox(main, values=CURRENCIES, state="readonly", width=10)
        self.currency.current(0)
        self.currency.grid(row=row, column=3, sticky=W, pady=3)

        # Buttons
        row += 1
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=5, pady=(12, 4))
        self.search_btn = ttk.Button(btn_frame, text="Search", command=self._on_search)
        self.search_btn.pack(side=LEFT, padx=4)
        self.open_btn = ttk.Button(btn_frame, text="Open Last Report", command=self._on_open, state=DISABLED)
        self.open_btn.pack(side=LEFT, padx=4)

        # Status
        row += 1
        self.status = StringVar()
        ttk.Label(main, textvariable=self.status, font=("", 9), foreground="#555").grid(
            row=row, column=0, columnspan=5, pady=(6, 0), sticky=W
        )
        self.status.set("Ready.")

        # Progress bar
        row += 1
        self.progress = ttk.Progressbar(main, mode="indeterminate", length=400)
        self.progress.grid(row=row, column=0, columnspan=5, pady=(6, 0), sticky=EW)

        self.last_html = None

    def _set_busy(self, busy):
        state = DISABLED if busy else NORMAL
        for w in (self.search_btn,):
            w.config(state=state)
        for e in (self.origin, self.dest, self.depart, self.return_date,
                  self.adults, self.children, self.cabin):
            e.config(state=state)
        if busy:
            self.progress.start(10)
            self.status.set("Searching...")
        else:
            self.progress.stop()
        self.root.update()

    def _toggle_oneway(self):
        state = DISABLED if self.oneway_var.get() else NORMAL
        self.return_date.config(state=state)

    def _on_search(self):
        self._set_busy(True)
        threading.Thread(target=self._search, daemon=True).start()

    def _search(self):
        origin_code = self.origin.get().strip().upper()
        dest_code = self.dest.get().strip().upper()
        depart_str = self.depart.get().strip()
        return_str = self.return_date.get().strip()
        adults_str = self.adults.get().strip()
        children_str = self.children.get().strip()
        cabin_name = self.cabin.get()

        is_oneway = self.oneway_var.get()

        if not origin_code or not dest_code:
            self._fail("Please enter origin and destination.")
            return
        if not depart_str:
            self._fail("Please enter a depart date.")
            return
        if not is_oneway and not return_str:
            self._fail("Please enter a return date.")
            return

        try:
            depart_dt = datetime.datetime.strptime(depart_str, "%Y-%m-%d")
            return_dt = datetime.datetime.strptime(return_str, "%Y-%m-%d") if not is_oneway and return_str else None
        except ValueError:
            self._fail("Dates must be YYYY-MM-DD format.")
            return

        child_ages = []
        if children_str:
            try:
                child_ages = [int(a.strip()) for a in children_str.split(",") if a.strip()]
            except ValueError:
                self._fail("Children ages must be comma-separated numbers.")
                return

        try:
            adults = int(adults_str) if adults_str else 1
        except ValueError:
            self._fail("Adults must be a number.")
            return

        cabin_class = CABIN_VALUES.get(cabin_name, CabinClass.ECONOMY)
        currency = self.currency.get()

        try:
            self.root.after(0, lambda: self.status.set("Initializing..."))
            self.scanner = SkyScanner(currency=currency)

            self.root.after(0, lambda: self.status.set(f"Looking up airports..."))
            origin = self.scanner.get_airport_by_code(origin_code)
            dest = self.scanner.get_airport_by_code(dest_code)

            label = f"{origin_code} → {dest_code}" + (" (one-way)" if is_oneway else "")
            self.root.after(0, lambda: self.status.set(f"Searching {label}..."))
            prices = self.scanner.get_flight_prices(
                origin=origin,
                destination=dest,
                depart_date=depart_dt,
                return_date=return_dt if not is_oneway else None,
                adults=adults,
                childAges=child_ages,
                cabinClass=cabin_class,
            )

            data = prices.json
            buckets = data["itineraries"]["buckets"]
            total = sum(len(b["items"]) for b in buckets)
            self.root.after(0, lambda: self.status.set(f"Found {total} flights. Generating report..."))

            # Collect airline logos
            from flight_search import collect_airline_codes, download_logos, generate_html

            codes = collect_airline_codes(data)
            logo_paths = download_logos(codes)

            # Build config for HTML generation
            from flight_search import SearchConfig

            config = SearchConfig(
                origin=origin_code,
                destination=dest_code,
                depart_date=depart_str,
                return_date=return_str if not is_oneway else "",
                adults=adults,
                child_ages=child_ages,
                cabin_class=cabin_class,
            )

            html = generate_html(data, config, logo_paths)

            # Save files to results directory
            os.makedirs(RESULTS_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = "ow" if is_oneway else ""
            base = f"{origin_code}_{dest_code}_{depart_str.replace('-', '')}{suffix}_{timestamp}"
            json_path = os.path.join(RESULTS_DIR, f"{base}.json")
            html_path = os.path.join(RESULTS_DIR, f"{base}.html")

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            self.last_html = os.path.abspath(html_path)
            self.root.after(0, lambda: self._done(total, json_path, html_path))

        except Exception as e:
            self._fail(str(e))

    def _done(self, total, json_path, html_path):
        self._set_busy(False)
        self.open_btn.config(state=NORMAL)
        self.status.set(f"{total} flights · JSON saved → {json_path}")
        webbrowser.open(f"file://{os.path.abspath(html_path)}")

    def _fail(self, msg):
        self.root.after(0, lambda: self._set_busy(False))
        self.root.after(0, lambda: self.status.set(f"Error: {msg}"))
        self.root.after(0, lambda: messagebox.showerror("Error", msg))

    def _on_open(self):
        if self.last_html and os.path.exists(self.last_html):
            webbrowser.open(f"file://{self.last_html}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    FlightSearchGUI().run()
