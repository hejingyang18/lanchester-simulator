"""Lanchester Simulator. Python 3.10+ with the standard library only."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from expert_assessment import ExpertPage


LINEAR = "Linear Law (Constant Attrition)"
SQUARE = "Lanchester Square Law"#Lanchester Square Law
BG = "#edf5f5"#Background color
PANEL = "#ffffff"#Panel color
INK = "#17394b"#Text color
MUTED = "#617d89"# Muted color
RED = "#d94e58"#Red
BLUE = "#3375c5"


@dataclass(frozen=True)
class Parameters:
    red: float = 50.0
    blue: float = 70.0
    a: float = 0.3
    b: float = 0.8
    horizon: float = 100.0
    model: str = LINEAR

    def validate(self) -> None:#Validate parameters
        for name, value, limit in (
            ("Initial Red force", self.red, 1e9),
            ("Initial Blue force", self.blue, 1e9),
            ("Red attrition coefficient", self.a, 1e6),
            ("Blue attrition coefficient", self.b, 1e6),
            ("Display time limit", self.horizon, 1e9),
        ):
            if not math.isfinite(value) or value < 0 or value > limit:
                raise ValueError(f"{name} must be a finite number between 0 and {limit:g}.")
            if 0 < value < 1e-9:
                raise ValueError(f"{name} must be at least 1e-9 when nonzero.")
        if self.horizon == 0:
            raise ValueError("The time limit must be greater than zero.")
        if self.model not in (LINEAR, SQUARE):
            raise ValueError("Select a valid model.")


@dataclass(frozen=True)
class Result:
    parameters: Parameters
    winner: str
    end_time: float
    red_remaining: float
    blue_remaining: float
    samples: tuple[tuple[float, float, float], ...]


def simulate(p: Parameters, sample_count: int = 601) -> Result:
    """Sample the analytical solution up to the first force reaching zero."""
    p.validate()
    if sample_count < 2:
        raise ValueError("At least two samples are required.")
    r, z, a, b = p.red, p.blue, p.a, p.b
    end, rr, bb = math.inf, r, z
    winner = "Stalemate"

    if r == 0 or z == 0:
        end = 0.0
        winner = "Draw" if r == z == 0 else ("Red" if r else "Blue")
    elif p.model == LINEAR:
        tr = r / a if a else math.inf
        tb = z / b if b else math.inf
        end = min(tr, tb)
        if math.isfinite(end):
            rr, bb = max(0.0, r - a * end), max(0.0, z - b * end)
            if tr == tb:
                winner, rr, bb = "Draw", 0.0, 0.0
            elif tr < tb:
                winner, rr = "Blue", 0.0
            else:
                winner, bb = "Red", 0.0
    elif a == 0 and b == 0:
        pass
    elif a == 0:
        end, winner, bb = z / (b * r), "Red", 0.0
    elif b == 0:
        end, winner, rr = r / (a * z), "Blue", 0.0
    else:
        x, y = math.sqrt(b) * r, math.sqrt(a) * z
        k = math.sqrt(a) * math.sqrt(b)
        if x == y:
            winner, rr, bb = "Balanced (asymptotic attrition)", 0.0, 0.0
        else:
            # log1p avoids division by zero near balance and cancellation for unequal forces.
            end = 0.5 * math.log1p(2 * min(x, y) / abs(x - y)) / k
            if x > y:
                winner, rr, bb = "Red", math.sqrt((x - y) * (x + y) / b), 0.0
            else:
                winner, rr, bb = "Blue", 0.0, math.sqrt((y - x) * (y + x) / a)

    stop = min(end, p.horizon)

    def state(t: float) -> tuple[float, float]:#Evaluate force levels at time t
        if t == 0:
            return r, z
        if math.isfinite(end) and t >= end:
            return rr, bb
        if p.model == LINEAR:
            return max(0.0, r - a * t), max(0.0, z - b * t)
        if a == 0:
            return r, max(0.0, z - b * r * t)
        if b == 0:
            return max(0.0, r - a * z * t), z
        k = math.sqrt(a) * math.sqrt(b)
        if not math.isfinite(end):
            return r * math.exp(-k * t), z * math.exp(-k * t)
        # Work backward from the final state to avoid cancellation that can zero out the weaker force early.
        u = k * (end - t)
        if winner == "Red":
            red = rr * math.cosh(u)
            blue = rr * math.sqrt(b / a) * math.sinh(u)
        else:
            red = bb * math.sqrt(a / b) * math.sinh(u)
            blue = bb * math.cosh(u)
        # Clamp rounding errors to keep force levels within their initial bounds.
        return (
            min(r, max(0.0, red)),
            min(z, max(0.0, blue)),
        )

    times = [0.0] if stop == 0 else [stop * i / (sample_count - 1) for i in range(sample_count)]
    samples = tuple((t, *state(t)) for t in times)
    return Result(p, winner, end, rr, bb, samples)


def number(value: float) -> str:#Format a numeric result
    if math.isinf(value):#Check for infinity
        return "∞ (no finite end time)"
    if value != 0 and (abs(value) < 0.001 or abs(value) >= 1e7):#Use compact formatting for very small or large values
        return f"{value:.5g}"#Format with five significant digits
    return f"{value:,.4f}".rstrip("0").rstrip(".")#Use thousands separators and omit trailing zeros


class TwoForcePage(tk.Frame):
    def __init__(self, parent: ttk.Notebook, on_close) -> None:
        super().__init__(parent, bg=BG)
        self.on_close = on_close
        self.result: Result | None = None
        self.after_id: str | None = None
        self.visible_count = 0
        self.running = False
        self.variables = {key: tk.StringVar(value=value) for key, value in {
            "red": "50", "blue": "70", "a": "0.3", "b": "0.8", "horizon": "100",
        }.items()}
        self.model = tk.StringVar(value=LINEAR)
        self.status = tk.StringVar(value="")
        self.summary = {key: tk.StringVar(value="—") for key in ("winner", "time", "red", "blue")}
        self._styles()
        self._build()
        self.run_simulation(animate=False)

    def _styles(self) -> None:#Set widget styles
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", padding=7, fieldbackground=PANEL)
        style.configure("TEntry", padding=7, fieldbackground=PANEL)
        style.configure("TButton", padding=(14, 9), font=("Microsoft YaHei UI", 10))
        style.configure("Primary.TButton", background="#176e79", foreground="white")
        style.map("Primary.TButton", background=[("active", "#125d66")])

    def label(self, parent: tk.Widget, text: str = "", **kwargs) -> tk.Label:
        kwargs.setdefault("bg", PANEL)
        kwargs.setdefault("fg", INK)
        return tk.Label(parent, text=text, **kwargs)

    def _build(self) -> None:#Build the interface
        header = tk.Frame(self, bg="#173e52", padx=26, pady=18)
        header.pack(fill="x")
        self.label(header, "Lanchester Equations", bg="#173e52", fg="white",
                   font=("Microsoft YaHei UI", 23, "bold")).pack(anchor="w")
        self.label(header, "Force Attrition Simulation / Linear and Square Laws", bg="#173e52",
                   fg="#b8d9e4", font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(5, 0))

        toolbar = tk.Frame(self, bg=BG, padx=24, pady=15)
        toolbar.pack(fill="x")
        self.label(toolbar, "Model", bg=BG).pack(side="left", padx=(0, 10))
        combo = ttk.Combobox(toolbar, textvariable=self.model, values=(LINEAR, SQUARE),
                             state="readonly", width=29)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _event: self.run_simulation(animate=False))
        self.label(toolbar, "Time limit", bg=BG).pack(side="left", padx=(24, 10))
        ttk.Entry(toolbar, textvariable=self.variables["horizon"], width=10).pack(side="left")
        self.label(toolbar, "t (chosen units)", bg=BG, fg=MUTED).pack(side="left", padx=8)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=365)
        plot = tk.Frame(body, bg=PANEL, padx=12, pady=12)
        plot.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        plot_header = tk.Frame(plot, bg=PANEL)
        plot_header.pack(fill="x", padx=8, pady=(0, 5))
        self.label(plot_header, "Force Levels Over Time", font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        self.label(plot_header, "━ Red", fg=RED).pack(side="right", padx=10)
        self.label(plot_header, "━ Blue", fg=BLUE).pack(side="right")
        self.canvas = tk.Canvas(plot, bg=PANEL, highlightthickness=0, width=570, height=335)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw_plot())

        sidebar = tk.Frame(body, bg=PANEL, padx=18, pady=16)
        sidebar.grid(row=0, column=1, sticky="nsew")
        self.label(sidebar, "Parameters", font=("Microsoft YaHei UI", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))
        for col, text in enumerate(("Side", "Initial Force", "Attrition Coefficient *")):
            self.label(sidebar, text, fg=MUTED).grid(row=1, column=col, sticky="w", padx=(0, 12))
        for row, (name, color, force, rate) in enumerate((
            ("Red", RED, "red", "a"), ("Blue", BLUE, "blue", "b")
        ), start=2):
            self.label(sidebar, name, fg=color, font=("Microsoft YaHei UI", 11, "bold")).grid(
                row=row, column=0, sticky="w", pady=9, padx=(0, 14))
            ttk.Entry(sidebar, textvariable=self.variables[force], width=10).grid(row=row, column=1, padx=(0, 12))
            ttk.Entry(sidebar, textvariable=self.variables[rate], width=10).grid(row=row, column=2)
        self.label(sidebar, "* a is the Red attrition coefficient and b is the Blue coefficient.\n  Higher values mean faster losses. Zero is allowed.",
                   fg=MUTED, justify="left", font=("Microsoft YaHei UI", 9)).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(3, 16))
        ttk.Separator(sidebar).grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)
        self.label(sidebar, "Predicted Outcome", font=("Microsoft YaHei UI", 13, "bold")).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(15, 9))
        for row, (title, key, color) in enumerate((
            ("Winner / status", "winner", INK), ("Battle duration", "time", INK),
            ("Red remaining", "red", RED), ("Blue remaining", "blue", BLUE)
        ), start=7):
            self.label(sidebar, title, fg=MUTED).grid(row=row, column=0, columnspan=2, sticky="w", pady=6)
            self.label(sidebar, textvariable=self.summary[key], fg=color,
                       font=("Microsoft YaHei UI", 10, "bold")).grid(row=row, column=1, columnspan=2, sticky="e", pady=6)
        self.label(sidebar, "The chart shows the selected time range.\nFor a balanced square-law case, remaining forces are the limits as t → ∞.",
                   fg=MUTED, justify="left", font=("Microsoft YaHei UI", 9)).grid(
            row=11, column=0, columnspan=3, sticky="sw", pady=(14, 0))
        sidebar.rowconfigure(11, weight=1)

        self.formula = tk.StringVar()
        self.label(self, textvariable=self.formula, bg=BG, fg=MUTED, justify="left",
                   anchor="w", font=("Microsoft YaHei UI", 10)).pack(fill="x", padx=29, pady=(13, 5))
        self.label(self, textvariable=self.status, bg=BG, fg=INK, anchor="w",
                   font=("Microsoft YaHei UI", 9)).pack(fill="x", padx=29, pady=(0, 8))

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=24, pady=(0, 20))
        ttk.Button(bottom, text="Run Simulation", style="Primary.TButton",
                   command=self.run_simulation).pack(side="left", padx=(0, 10))
        self.pause_button = ttk.Button(bottom, text="Pause", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=(0, 10))
        ttk.Button(bottom, text="Reset Example", command=self.reset).pack(side="left", padx=(0, 10))
        ttk.Button(bottom, text="Export CSV", command=self.export_csv).pack(side="left")
        ttk.Button(bottom, text="Close", command=self.on_close).pack(side="right")

    def read_parameters(self) -> Parameters:
        try:
            values = {key: float(var.get().strip()) for key, var in self.variables.items()}
        except ValueError as exc:
            raise ValueError("Enter valid numbers for force levels, attrition coefficients, and the time limit.") from exc
        return Parameters(**values, model=self.model.get())

    def cancel_animation(self) -> None:
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None
        self.running = False

    def run_simulation(self, animate: bool = True) -> None:
        try:
            result = simulate(self.read_parameters())
        except ValueError as exc:
            messagebox.showerror("Invalid Input", str(exc), parent=self)
            return
        self.cancel_animation()
        self.result = result
        self.summary["winner"].set(result.winner)
        self.summary["time"].set(number(result.end_time))
        self.summary["red"].set(number(result.red_remaining))
        self.summary["blue"].set(number(result.blue_remaining))
        if result.parameters.model == LINEAR:
            self.formula.set("Linear law: dR/dt = −a, dB/dt = −b. Both forces decline at constant rates until one reaches zero.")
        else:
            self.formula.set("Square law: dR/dt = −aB, dB/dt = −bR. The quantity bR² − aB² is conserved until one force reaches zero.")
        self.visible_count = 1 if animate else len(result.samples)
        self.draw_plot()
        self.running = animate and len(result.samples) > 1
        self.pause_button.configure(text="Pause", state="normal" if self.running else "disabled")
        if self.running:
            self.tick()
        else:
            self.update_status()

    def tick(self) -> None:
        self.after_id = None
        if not self.running or self.result is None:
            return
        self.visible_count = min(len(self.result.samples), self.visible_count + 6)
        self.draw_plot()
        self.update_status()
        if self.visible_count < len(self.result.samples):
            self.after_id = self.after(30, self.tick)
        else:
            self.running = False
            self.pause_button.configure(state="disabled", text="Pause")

    def update_status(self) -> None:
        if self.result is None:
            return
        t, r, b = self.result.samples[self.visible_count - 1]
        prefix = "Simulating" if self.visible_count < len(self.result.samples) else "Plot complete"
        if self.visible_count == len(self.result.samples) and t < self.result.end_time:
            prefix += " · Time limit reached before the battle ended"
        self.status.set(f"{prefix}    t = {number(t)}    Red = {number(r)}    Blue = {number(b)}")

    def toggle_pause(self) -> None:
        if self.result is None or self.visible_count >= len(self.result.samples):
            return
        if self.running:
            self.cancel_animation()
            self.pause_button.configure(text="Resume")
            self.status.set(self.status.get().replace("Simulating", "Paused", 1))
        else:
            self.running = True
            self.pause_button.configure(text="Pause")
            self.tick()

    def draw_plot(self) -> None:
        c = self.canvas
        c.delete("all")
        if self.result is None:
            return
        p = self.result.parameters
        w, h = max(c.winfo_width(), 240), max(c.winfo_height(), 180)
        left, right, top, bottom = 68, w - 23, 26, h - 52
        ymax = max(1.0, p.red, p.blue) * 1.12

        def xy(t: float, force: float) -> tuple[float, float]:
            return left + t / p.horizon * (right - left), bottom - force / ymax * (bottom - top)

        font = ("Microsoft YaHei UI", 9)
        for i in range(6):
            x = left + (right - left) * i / 5
            y = bottom - (bottom - top) * i / 5
            c.create_line(x, top, x, bottom, fill="#e2ebee", dash=(3, 4))
            c.create_line(left, y, right, y, fill="#e2ebee", dash=(3, 4))
            c.create_text(x, bottom + 17, text=f"{p.horizon * i / 5:.4g}", font=font, fill=MUTED)
            c.create_text(left - 10, y, text=f"{ymax * i / 5:.4g}", anchor="e", font=font, fill=MUTED)
        c.create_line(left, top, left, bottom, right, bottom, fill="#9bb0ba", width=1.5)
        c.create_text(left, 10, text="Force Level", anchor="w", fill=MUTED, font=font)
        c.create_text((left + right) / 2, h - 10, text="Time t", fill=MUTED, font=font)
        points = self.result.samples[:self.visible_count]
        for column, color in ((1, RED), (2, BLUE)):
            coords = [n for point in points for n in xy(point[0], point[column])]
            if len(coords) >= 4:
                c.create_line(*coords, fill=color, width=2.6, capstyle="round", joinstyle="round")
            if coords:
                x, y = coords[-2:]
                c.create_oval(x - 3.5, y - 3.5, x + 3.5, y + 3.5, fill=color, outline=PANEL)
        if points:
            t = points[-1][0]
            x, _ = xy(t, 0)
            c.create_line(x, top, x, bottom, fill="#a9b9c0", dash=(2, 5))

    def reset(self) -> None:
        for key, value in {"red": "50", "blue": "70", "a": "0.3", "b": "0.8", "horizon": "100"}.items():
            self.variables[key].set(value)
        self.model.set(LINEAR)
        self.run_simulation(animate=False)

    def export_csv(self) -> None:
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Export Simulation Data", defaultextension=".csv",
            initialfile="lanchester_simulation.csv", filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            export_result(self.result, path)
        except OSError as exc:
            messagebox.showerror("Export Failed", str(exc), parent=self)
        else:
            self.status.set("Exported all samples from the most recent simulation run.")

def export_result(result: Result, path: str) -> None:
    """Export all samples as UTF-8 with a BOM for Excel compatibility."""
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Time t", "Remaining Red force R", "Remaining Blue force B"))
        writer.writerows(result.samples)


@dataclass
class BattleInput:
    red: float = 260.0
    blue_a: float = 200.0
    blue_b: float = 60.0
    red_to_a: float = 0.1
    red_to_b: float = 0.5
    blue_a_to_red: float = 0.1
    blue_b_to_red: float = 1.5
    share_a: float = 0.5
    share_b: float = 0.5


def combat_indices(p: BattleInput) -> tuple[float, float | None]:
    """Normalize the red left eigenvector to 1 for this one-versus-two case."""
    eigenvalue = p.blue_a_to_red * p.red_to_a * p.share_a + p.blue_b_to_red * p.red_to_b * p.share_b
    return p.red, (
        (p.blue_a_to_red * p.blue_a + p.blue_b_to_red * p.blue_b)
        / math.sqrt(eigenvalue) if eigenvalue > 0 else None
    )


def _derivative(state, p, active):
    red, blue_a, blue_b = state
    active_a, active_b = active
    share_a = (p.share_a if active_b else 1.0) if active_a else 0.0
    share_b = (p.share_b if active_a else 1.0) if active_b else 0.0
    return (
        -(p.blue_a_to_red * blue_a + p.blue_b_to_red * blue_b),
        -p.red_to_a * red * share_a,
        -p.red_to_b * red * share_b,
    )


def simulate_three_forces(
    p: BattleInput,
    dt: float = 0.01,
    max_time: float = 500.0,
) -> tuple[list[tuple[float, float, float, float]], str]:
    """Use RK4 to return (time, Red, Blue A, Blue B) samples and the outcome."""
    state = (p.red, p.blue_a, p.blue_b)
    t = 0.0
    rows = [(t, *state)]
    step_count = 0

    while t < max_time and state[0] > 0 and (state[1] > 0 or state[2] > 0):
        active = (state[1] > 0, state[2] > 0)

        def advance(h):
            k1 = _derivative(state, p, active)
            k2 = _derivative(tuple(x + h * k / 2 for x, k in zip(state, k1)), p, active)
            k3 = _derivative(tuple(x + h * k / 2 for x, k in zip(state, k2)), p, active)
            k4 = _derivative(tuple(x + h * k for x, k in zip(state, k3)), p, active)
            return tuple(x + h * (a + 2*b + 2*c + d) / 6
                         for x, a, b, c, d in zip(state, k1, k2, k3, k4))

        h = min(dt, max_time - t)
        next_state = advance(h)
        crossing = [i for i in range(3) if state[i] > 0 and next_state[i] <= 0]
        if crossing:
            low, high = 0.0, h
            for _ in range(40):
                mid = (low + high) / 2
                if any(advance(mid)[i] <= 0 for i in crossing):
                    high = mid
                else:
                    low = mid
            h = high
            next_state = advance(h)
        t += h
        state = tuple(max(0.0, x) for x in next_state)
        step_count += 1
        if crossing or step_count % 5 == 0:
            rows.append((t, *state))

    if rows[-1][0] != t:
        rows.append((t, *state))
    if t >= max_time and max(state) > 1e-8:
        outcome = "Time limit reached with forces remaining"
    elif max(state) <= 1e-8:
        outcome = "Mutual depletion"
    elif state[0] > 1e-8:
        outcome = "Red wins"
    elif state[1] > 1e-8 or state[2] > 1e-8:
        outcome = "Blue wins"
    else:
        outcome = "Battle ended"
    return rows, outcome


class Chart(tk.Canvas):
    COLORS = ("#b56c4e", "#79bd45", "#4169c9")

    def __init__(self, master: tk.Misc, title: str, **kwargs: object) -> None:
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)
        self.title = title
        self.bind("<Configure>", lambda _event: self.redraw())
        self.data: list[tuple[float, float, float, float]] = []
        self.initial: tuple[float, float, float] | None = None
        self.duration = 0.0
        self.redraw()

    def set_data(self, data: list[tuple[float, float, float, float]]) -> None:
        self.data = data
        self.initial = tuple(data[0][1:]) if data else None
        self.duration = data[-1][0] if data else 0.0
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 240), max(self.winfo_height(), 180)
        self.create_text(w / 2, 18, text=self.title, font=("Microsoft YaHei UI", 12, "bold"), fill="#243247")
        if not self.data:
            self.create_text(w / 2, h / 2, text="Enter the parameters and select Run Simulation", fill="#718096", font=("Microsoft YaHei UI", 10))
            return

        if len(self.data) == 1:
            names = ("Red", "Blue A", "Blue B")
            values = self.data[0][1:]
            max_value = max(max(values), 1.0)
            baseline = h - 36
            top = 47
            self.create_line(38, baseline, w - 20, baseline, fill="#9aa8b8")
            slot = (w - 70) / 3
            bar_width = min(56, slot * 0.48)
            for i, (name, value, color) in enumerate(zip(names, values, self.COLORS)):
                center = 45 + slot * (i + 0.5)
                bar_h = (baseline - top) * value / max_value
                self.create_rectangle(center - bar_width / 2, baseline - bar_h, center + bar_width / 2, baseline, fill=color, outline="")
                self.create_text(center, baseline - bar_h - 12, text=f"{value:.1f}", fill="#334155", font=("Arial", 8, "bold"))
                self.create_text(center, baseline + 14, text=name, fill="#526174", font=("Microsoft YaHei UI", 8))
            return

        left, right, top, bottom = 58, w - 22, 48, h - 46
        max_y = max(max(row[1:]) for row in self.data)
        min_y = min(0.0, min(min(row[1:]) for row in self.data))
        max_y = max(max_y, 1.0)
        span_y = max(max_y - min_y, 1.0)
        max_t = max(self.duration, 0.01)
        for n in range(6):
            yv = min_y + span_y * n / 5
            y = bottom - (yv - min_y) / span_y * (bottom - top)
            self.create_line(left, y, right, y, fill="#e8edf3")
            self.create_text(left - 8, y, text=f"{yv:.0f}", anchor="e", fill="#607087", font=("Arial", 8))
        for n in range(6):
            xv = max_t * n / 5
            x = left + xv / max_t * (right - left)
            self.create_line(x, top, x, bottom, fill="#f1f3f6")
            self.create_text(x, bottom + 15, text=f"{xv:.1f}", fill="#607087", font=("Arial", 8))
        self.create_line(left, top, left, bottom, fill="#9aa8b8")
        self.create_line(left, bottom, right, bottom, fill="#9aa8b8")
        self.create_text(18, (top + bottom) / 2, text="Force Level", angle=90, fill="#526174", font=("Microsoft YaHei UI", 9))
        self.create_text((left + right) / 2, h - 9, text="Time (hours)", fill="#526174", font=("Microsoft YaHei UI", 9))
        for index, (name, color) in enumerate(zip(("Red", "Blue A", "Blue B"), self.COLORS)):
            y = top + index * 15
            self.create_line(right - 180, y, right - 158, y, fill=color, width=3)
            self.create_text(right - 152, y, text=name, anchor="w", fill="#3c4a5d", font=("Microsoft YaHei UI", 8))
        for col, color in zip((1, 2, 3), self.COLORS):
            points: list[float] = []
            for row in self.data:
                x = left + row[0] / max_t * (right - left)
                y = bottom - (row[col] - min_y) / span_y * (bottom - top)
                points.extend((x, y))
            if len(points) >= 4:
                self.create_line(*points, fill=color, width=2.5, smooth=True)


class ThreeForcePage(tk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent, bg="#eef2f6")
        self.vars: dict[str, tk.StringVar] = {}
        self._build_ui()
        self.run()

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg="#183b5b", height=58)
        header.pack(fill="x")
        tk.Label(header, text="Lanchester Attrition Simulator", bg="#183b5b", fg="white", font=("Microsoft YaHei UI", 18, "bold")).pack(side="left", padx=22, pady=12)
        tk.Label(header, text="Three-Force Model · RK4", bg="#183b5b", fg="#c8d8e8", font=("Microsoft YaHei UI", 10)).pack(side="right", padx=24)

        body = tk.Frame(self, bg="#eef2f6")
        body.pack(fill="both", expand=True, padx=14, pady=14)
        panel = tk.Frame(body, bg="white", width=340, highlightbackground="#d8e0e8", highlightthickness=1)
        panel.pack(side="left", fill="y", padx=(0, 14))
        panel.pack_propagate(False)
        tk.Label(panel, text="Battle Parameters", bg="white", fg="#26384b", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=18, pady=(18, 10))

        groups = [
            ("Initial Force", [("red", "Total Red force", 260), ("blue_a", "Blue A force", 200), ("blue_b", "Blue B force", 60)]),
            ("Attrition Coefficients (per hour)", [("red_to_a", "Red vs. Blue A", 0.1), ("red_to_b", "Red vs. Blue B", 0.5), ("blue_a_to_red", "Blue A vs. Red", 0.1), ("blue_b_to_red", "Blue B vs. Red", 1.5)]),
            ("Red Fire Allocation", [("share_a", "Share for Blue A", 0.5), ("share_b", "Share for Blue B", 0.5)]),
        ]
        for group_name, fields in groups:
            tk.Label(panel, text=group_name, bg="white", fg="#41627e", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=18, pady=(8, 3))
            for key, label, default in fields:
                row = tk.Frame(panel, bg="white")
                row.pack(fill="x", padx=18, pady=3)
                tk.Label(row, text=label, bg="white", fg="#4b5969", font=("Microsoft YaHei UI", 9), width=17, anchor="w").pack(side="left")
                var = tk.StringVar(value=str(default))
                self.vars[key] = var
                tk.Entry(row, textvariable=var, justify="right", relief="solid", bd=1, width=10, font=("Arial", 10)).pack(side="right", ipady=4)

        tk.Button(panel, text="Run Simulation", command=self.run, bg="#39a84b", fg="white", activebackground="#2d903d", activeforeground="white", relief="flat", font=("Microsoft YaHei UI", 12, "bold"), cursor="hand2").pack(fill="x", padx=18, pady=(17, 8), ipady=9)
        tk.Label(panel, text="The model computes losses for each force.\nWhen one Blue force reaches zero, Red\nshifts all fire to the remaining force.", justify="left", bg="white").pack(anchor="w", padx=18)

        results = tk.Frame(body, bg="#eef2f6")
        results.pack(side="left", fill="both", expand=True)
        cards = tk.Frame(results, bg="#eef2f6")
        cards.pack(fill="x", pady=(0, 12))
        self.kpis: dict[str, tk.Label] = {}
        for key, title, initial in (("outcome", "Outcome", "Awaiting simulation"), ("duration", "Battle Duration", "— hours"), ("survivors", "Final Forces (Red / Blue A / Blue B)", "— / — / —")):
            card = tk.Frame(cards, bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, bg="white", fg="#69788b", font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=12, pady=(9, 1))
            label = tk.Label(card, text=initial, bg="white", fg="#203b58", font=("Microsoft YaHei UI", 12, "bold"))
            label.pack(anchor="w", padx=12, pady=(0, 10))
            self.kpis[key] = label

        top = tk.Frame(results, bg="#eef2f6", height=225)
        top.pack(fill="x", pady=(0, 12))
        top.pack_propagate(False)
        self.initial_chart = Chart(top, "Initial Force Levels", bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
        self.initial_chart.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.final_chart = Chart(top, "Final Force Levels", bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
        self.final_chart.pack(side="left", fill="both", expand=True)
        self.line_chart = Chart(results, "Red and Blue Forces Over Time", bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
        self.line_chart.pack(fill="both", expand=True)
        self.status = tk.Label(self, text="Ready", bg="#e2e9f0", fg="#536477", anchor="w", padx=14, font=("Microsoft YaHei UI", 8))
        self.status.pack(fill="x", side="bottom")

    def read_input(self) -> BattleInput:
        values = {key: float(var.get().strip()) for key, var in self.vars.items()}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("Parameters must be finite numbers.")
        p = BattleInput(**values)
        if min(p.red, p.blue_a, p.blue_b) <= 0:
            raise ValueError("Initial force levels must be greater than zero.")
        if min(p.red_to_a, p.red_to_b, p.blue_a_to_red, p.blue_b_to_red) < 0:
            raise ValueError("Attrition coefficients must be nonnegative.")
        if not math.isclose(p.share_a + p.share_b, 1.0, abs_tol=1e-6):
            raise ValueError("Fire allocation shares for Blue A and Blue B must sum to 1.")
        if not (0 <= p.share_a <= 1 and 0 <= p.share_b <= 1):
            raise ValueError("Fire allocation shares must be between 0 and 1.")
        return p

    def run(self) -> None:
        try:
            p = self.read_input()
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid Parameters", str(exc), parent=self)
            return
        data, outcome = simulate_three_forces(p)
        final = data[-1][1:]
        self.kpis["outcome"].configure(text=outcome)
        self.kpis["duration"].configure(text=f"{data[-1][0]:.2f} hours")
        self.kpis["survivors"].configure(text=" / ".join(f"{x:.1f}" for x in final))
        self.initial_chart.set_data([(0, p.red, p.blue_a, p.blue_b)])
        self.final_chart.set_data([(0, *final)])
        self.line_chart.set_data(data)
        red_index, blue_index = combat_indices(p)
        index_text = f"{blue_index:.1f}" if blue_index is not None else "Undefined"
        self.status.configure(text=f"Initial combat index: Red {red_index:.1f} / Blue {index_text}")


class SimulatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Lanchester Simulator")
        self.geometry("1320x850")
        self.minsize(1050, 750)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.two_force = TwoForcePage(self.tabs, self.close)
        self.three_force = ThreeForcePage(self.tabs)
        self.tabs.add(self.two_force, text="Two Forces · Linear / Square Law")
        self.tabs.add(self.three_force, text="Three Forces · RK4")
        self.expert = ExpertPage(self.tabs, self.two_force, self.three_force)
        self.tabs.add(self.expert, text="Expert Assessment")
        self.tabs.enable_traversal()
        self.bind("<Return>", self.run_two_force)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def run_two_force(self, _event: tk.Event) -> None:
        if self.tabs.select() == str(self.two_force):
            self.two_force.run_simulation()

    def close(self) -> None:
        self.two_force.cancel_animation()
        self.destroy()


if __name__ == "__main__":
    SimulatorApp().mainloop()
