import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from sklearn.linear_model import BayesianRidge
from scipy.spatial import Delaunay

# ---------- CONSTANTS ----------
INPUT  = ['MFR', 'Mw', 'PDI', 'D', 'rho', 'E', 'W_impact', 'mu_G', 'el_resistance', 'Tm']
OUTPUT = ['T_avg', 'P_avg', 'stirrerN', 'Tau', 'V_reactor', 'K*']
COMPONENTS = ['n-hexane', 'ethylene', 'propylene', 'hydrogen', '1-buten',
              '1-hexen', '1-octen', 'toluene', 'nitrogen', 'Catalyst',
              'MAO', 'TIA', 'Donor', 'Polymer']
SUFFIXES = ['m_start', 'mdot_in', 'mdot_out']  # for component naming


class Model:
    def __init__(self):
        self.base   = None
        self.m_s    = None
        self.m_in   = None
        self.m_out  = None
        self.design = None
        self.X_cols = None
        self.hull   = None

    def load_files(self, base_path, m_start_path, mdot_in_path, mdot_out_path):
        # base file
        base_df = pd.read_csv(base_path, sep=';')

        # component files (must match row count)
        files = {'m_start': m_start_path,
                 'mdot_in': mdot_in_path,
                 'mdot_out': mdot_out_path}
        comp_dfs = {}
        for name, path in files.items():
            if not path:
                raise ValueError(f"{name} CSV not provided")
            df = pd.read_csv(path, sep=';')
            if len(df) != len(base_df):
                raise ValueError(f"{name} CSV has {len(df)} rows, expected {len(base_df)}")
            comp_dfs[name] = df

        # build combined dataset
        design = base_df.join(comp_dfs['m_start'], how='left') \
                        .join(comp_dfs['mdot_in'],  how='left') \
                        .join(comp_dfs['mdot_out'], how='left') \
                        .dropna()
        self.design = design
        self.X_cols = INPUT + [c for c in design.columns if c in COMPONENTS]

        # convex hull
        need = len(self.X_cols) + 1
        self.hull = Delaunay(design[self.X_cols].values) if len(design) >= need else None

    def inside(self, props):
        return False if self.hull is None else self.hull.find_simplex(props) >= 0

    def predict(self, props):
        props_df = pd.DataFrame([props], columns=self.X_cols)
        preds = {}
        # scalar outputs
        for y in OUTPUT:
            mdl = BayesianRidge().fit(self.design[self.X_cols], self.design[y])
            mu, std = mdl.predict(props_df, return_std=True)
            preds[y] = (float(mu), float(std))
        # component outputs
        for suf in SUFFIXES:
            for col in self.design.filter(regex=f'^{suf}_').columns:
                mdl = BayesianRidge().fit(self.design[self.X_cols], self.design[col])
                mu, std = mdl.predict(props_df, return_std=True)
                preds[col] = (float(mu), float(std))
        return preds


class GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Polyolefin – Four-CSV Dashboard")
        self.geometry("1350x900")
        self.model     = None
        self.view_mode = tk.StringVar(value="Inputs")

        # ---------- file buttons ----------
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=6)
        self.paths = {k: None for k in ['base', 'm_start', 'mdot_in', 'mdot_out']}
        for k in self.paths:
            ttk.Button(btn_frame, text=f"Load {k.replace('_', ' ')} CSV",
                       command=lambda k=k: self.load_single(k)).pack(side="left", padx=4)

        # ---------- toggle ----------
        top = ttk.Frame(self)
        top.pack(pady=4)
        ttk.Button(top, text="Toggle View", command=self.toggle_view).pack(side="left", padx=5)
        self.warn_lbl = ttk.Label(top, text="", foreground="red")
        self.warn_lbl.pack(side="left", padx=10)

        # ---------- input boxes ----------
        frm = ttk.Frame(self)
        frm.pack(pady=5)
        self.entries = {}
        for col in INPUT:
            f = ttk.Frame(frm)
            f.pack(side="left", padx=4)
            ttk.Label(f, text=col, width=7).pack()
            sv = tk.StringVar()
            sv.trace("w", lambda *args: self.on_change())
            ttk.Entry(f, textvariable=sv, width=10).pack()
            self.entries[col] = sv

        # ---------- table ----------
        self.table = ttk.Treeview(self, columns=("Value", "±95%CI"),
                                  show="tree headings", height=15)
        self.table.pack(fill="x", padx=10, pady=5)
        self.table.heading("#0", text="Parameter")
        self.table.heading("Value", text="Value")
        self.table.heading("±95%CI", text="±95%CI")

        # ---------- canvas ----------
        self.fig = Figure(figsize=(13, 8))
        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)

    # ---------- helpers ----------
    def load_single(self, key):
        path = filedialog.askopenfilename(title=f"Select {key} CSV",
                                          filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        self.paths[key] = path
        if all(self.paths.values()):
            self.load_all()

    def load_all(self):
        try:
            self.model = Model()
            self.model.load_files(self.paths['base'],
                                  self.paths['m_start'],
                                  self.paths['mdot_in'],
                                  self.paths['mdot_out'])
            self.view_mode.set("Inputs")
            self.plot_static()
            self.on_change()
        except Exception as e:
            messagebox.showerror("CSV error", str(e))

    def toggle_view(self):
        params = OUTPUT + [c for c in self.model.design.columns
                           if c.startswith(tuple(SUFFIXES))]
        self.view_mode.set("Outputs" if self.view_mode.get() == "Inputs" else "Inputs")
        self.plot_static()
        self.on_change()

    def plot_static(self):
        if self.model is None:
            return
        self.fig.clear()
        params = INPUT if self.view_mode.get() == "Inputs" else \
                 OUTPUT + [c for c in self.model.design.columns
                           if c.startswith(tuple(SUFFIXES))]
        rows = (len(params) + 2) // 3
        axes = self.fig.subplots(rows, 3).flatten()
        self.axes = {}
        for ax, p in zip(axes, params):
            ax.clear()
            for val in self.model.design[p]:
                ax.axhline(val, color='grey', lw=1)
            ax.set_title(p)
            marker, = ax.plot(0, 0, 'o', markersize=10, color='none')
            self.axes[p] = marker
        for ax in axes[len(params):]:
            ax.set_visible(False)
        self.fig.tight_layout()
        self.canvas.draw()

    def on_change(self, *args):
        if self.model is None:
            return
        try:
            props = [float(self.entries[c].get() or 0) for c in INPUT]
            inside = self.model.inside(props)
            preds = self.model.predict(props)

            # table
            self.table.delete(*self.table.get_children())
            color = 'green' if inside else 'red'
            for k, (mu, std) in preds.items():
                val = f"{mu:.2f}" if mu >= 0 else "Negative output"
                ci  = f"{1.96*std:.2f}" if mu >= 0 else ""
                self.table.insert("", "end", text=k, values=(val, ci), tags=("color",))
                self.table.tag_configure("color", foreground=color)

            # update markers
            for p in self.axes:
                val = preds[p][0] if p not in INPUT else props[INPUT.index(p)]
                val = val if val >= 0 else np.nan
                self.axes[p].set_data([0], [val])
                self.axes[p].set_color(color)
                self.axes[p].axes.relim()
                self.axes[p].axes.autoscale_view()

            self.canvas.draw_idle()

            # hull warning
            if self.model.hull is None:
                self.warn_lbl.config(text="Need ≥ {} rows".format(len(self.model.X_cols)+1))
            else:
                self.warn_lbl.config(text="")

        except ValueError:
            self.table.delete(*self.table.get_children())
            self.table.insert("", "end", text="Error", values=("Enter valid numbers", ""))


if __name__ == "__main__":
    GUI().mainloop()