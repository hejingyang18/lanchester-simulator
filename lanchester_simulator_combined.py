"""兰彻斯特仿真合集。Python 3.10+，仅使用标准库。"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


LINEAR = "线性律（图示恒定损耗）"
SQUARE = "Lanchester 平方律"#Lanchester 平方律
BG = "#edf5f5"#背景色
PANEL = "#ffffff"#面板色
INK = "#17394b"#墨水色
MUTED = "#617d89"# muted 颜色
RED = "#d94e58"#红色
BLUE = "#3375c5"


@dataclass(frozen=True)
class Parameters:
    red: float = 50.0
    blue: float = 70.0
    a: float = 0.3
    b: float = 0.8
    horizon: float = 100.0
    model: str = LINEAR

    def validate(self) -> None:#参数验证
        for name, value, limit in (
            ("红方初始兵力", self.red, 1e9),
            ("蓝方初始兵力", self.blue, 1e9),
            ("红方损耗系数", self.a, 1e6),
            ("蓝方损耗系数", self.b, 1e6),
            ("显示时间上限", self.horizon, 1e9),
        ):
            if not math.isfinite(value) or value < 0 or value > limit:
                raise ValueError(f"{name}须为 0 到 {limit:g} 之间的有限数值。")
            if 0 < value < 1e-9:
                raise ValueError(f"{name}的非零数值不能小于 1e-9。")
        if self.horizon == 0:
            raise ValueError("显示时间上限必须大于 0。")
        if self.model not in (LINEAR, SQUARE):
            raise ValueError("请选择有效的模型。")


@dataclass(frozen=True)
class Result:
    parameters: Parameters
    winner: str
    end_time: float
    red_remaining: float
    blue_remaining: float
    samples: tuple[tuple[float, float, float], ...]


def simulate(p: Parameters, sample_count: int = 601) -> Result:
    """解析求解并采样，在首个兵力归零时停止，避免负兵力。"""
    p.validate()
    if sample_count < 2:
        raise ValueError("采样点数量至少为 2。")
    r, z, a, b = p.red, p.blue, p.a, p.b
    end, rr, bb = math.inf, r, z
    winner = "僵持"

    if r == 0 or z == 0:
        end = 0.0
        winner = "平局" if r == z == 0 else ("红方" if r else "蓝方")
    elif p.model == LINEAR:
        tr = r / a if a else math.inf
        tb = z / b if b else math.inf
        end = min(tr, tb)
        if math.isfinite(end):
            rr, bb = max(0.0, r - a * end), max(0.0, z - b * end)
            if tr == tb:
                winner, rr, bb = "平局", 0.0, 0.0
            elif tr < tb:
                winner, rr = "蓝方", 0.0
            else:
                winner, bb = "红方", 0.0
    elif a == 0 and b == 0:
        pass
    elif a == 0:
        end, winner, bb = z / (b * r), "红方", 0.0
    elif b == 0:
        end, winner, rr = r / (a * z), "蓝方", 0.0
    else:
        x, y = math.sqrt(b) * r, math.sqrt(a) * z
        k = math.sqrt(a) * math.sqrt(b)
        if x == y:
            winner, rr, bb = "均衡（渐近消耗）", 0.0, 0.0
        else:
            # log1p 同时避免接近平衡的除零，以及悬殊兵力下对数相减的消去误差。
            end = 0.5 * math.log1p(2 * min(x, y) / abs(x - y)) / k
            if x > y:
                winner, rr, bb = "红方", math.sqrt((x - y) * (x + y) / b), 0.0
            else:
                winner, rr, bb = "蓝方", 0.0, math.sqrt((y - x) * (y + x) / a)

    stop = min(end, p.horizon)

    def state(t: float) -> tuple[float, float]:#定义状态函数
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
        # 从结束状态向前重建，避免两大数相减导致弱势一方提前变成 0。
        u = k * (end - t)
        if winner == "红方":
            red = rr * math.cosh(u)
            blue = rr * math.sqrt(b / a) * math.sinh(u)
        else:
            red = bb * math.sqrt(a / b) * math.sinh(u)
            blue = bb * math.cosh(u)
        # 浮点误差不能让剩余兵力超出初始值。
        return (
            min(r, max(0.0, red)),
            min(z, max(0.0, blue)),
        )

    times = [0.0] if stop == 0 else [stop * i / (sample_count - 1) for i in range(sample_count)]
    samples = tuple((t, *state(t)) for t in times)
    return Result(p, winner, end, rr, bb, samples)


def number(value: float) -> str:#定义数字格式化函数
    if math.isinf(value):#判断是否为无穷大
        return "∞（无有限终点）"
    if value != 0 and (abs(value) < 0.001 or abs(value) >= 1e7):#判断是否为科学计数法
        return f"{value:.5g}"#返回科学计数法表示
    return f"{value:,.4f}".rstrip("0").rstrip(".")#返回带千分位分隔符的浮点数表示


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

    def _styles(self) -> None:#定义界面样式
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

    def _build(self) -> None:#定义界面布局
        header = tk.Frame(self, bg="#173e52", padx=26, pady=18)
        header.pack(fill="x")
        self.label(header, "Lanchester 方程", bg="#173e52", fg="white",
                   font=("Microsoft YaHei UI", 23, "bold")).pack(anchor="w")
        self.label(header, "兵力对抗仿真  /  LINEAR & SQUARE LAW", bg="#173e52",
                   fg="#b8d9e4", font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(5, 0))

        toolbar = tk.Frame(self, bg=BG, padx=24, pady=15)
        toolbar.pack(fill="x")
        self.label(toolbar, "选择模型", bg=BG).pack(side="left", padx=(0, 10))
        combo = ttk.Combobox(toolbar, textvariable=self.model, values=(LINEAR, SQUARE),
                             state="readonly", width=29)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _event: self.run_simulation(animate=False))
        self.label(toolbar, "时间上限", bg=BG).pack(side="left", padx=(24, 10))
        ttk.Entry(toolbar, textvariable=self.variables["horizon"], width=10).pack(side="left")
        self.label(toolbar, "t（单位自定）", bg=BG, fg=MUTED).pack(side="left", padx=8)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=365)
        plot = tk.Frame(body, bg=PANEL, padx=12, pady=12)
        plot.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        plot_header = tk.Frame(plot, bg=PANEL)
        plot_header.pack(fill="x", padx=8, pady=(0, 5))
        self.label(plot_header, "兵力随时间变化", font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        self.label(plot_header, "━ 红方", fg=RED).pack(side="right", padx=10)
        self.label(plot_header, "━ 蓝方", fg=BLUE).pack(side="right")
        self.canvas = tk.Canvas(plot, bg=PANEL, highlightthickness=0, width=570, height=335)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw_plot())

        sidebar = tk.Frame(body, bg=PANEL, padx=18, pady=16)
        sidebar.grid(row=0, column=1, sticky="nsew")
        self.label(sidebar, "参数设置", font=("Microsoft YaHei UI", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))
        for col, text in enumerate(("阵营", "初始兵力", "损耗系数 *")):
            self.label(sidebar, text, fg=MUTED).grid(row=1, column=col, sticky="w", padx=(0, 12))
        for row, (name, color, force, rate) in enumerate((
            ("红方", RED, "red", "a"), ("蓝方", BLUE, "blue", "b")
        ), start=2):
            self.label(sidebar, name, fg=color, font=("Microsoft YaHei UI", 11, "bold")).grid(
                row=row, column=0, sticky="w", pady=9, padx=(0, 14))
            ttk.Entry(sidebar, textvariable=self.variables[force], width=10).grid(row=row, column=1, padx=(0, 12))
            ttk.Entry(sidebar, textvariable=self.variables[rate], width=10).grid(row=row, column=2)
        self.label(sidebar, "* 系数表示该方所受损耗。红方为 a，蓝方为 b。\n  系数越大，该方损耗越快；允许为 0。",
                   fg=MUTED, justify="left", font=("Microsoft YaHei UI", 9)).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(3, 16))
        ttk.Separator(sidebar).grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)
        self.label(sidebar, "理论战斗结果", font=("Microsoft YaHei UI", 13, "bold")).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(15, 9))
        for row, (title, key, color) in enumerate((
            ("胜方 / 状态", "winner", INK), ("战斗时间", "time", INK),
            ("红方剩余", "red", RED), ("蓝方剩余", "blue", BLUE)
        ), start=7):
            self.label(sidebar, title, fg=MUTED).grid(row=row, column=0, columnspan=2, sticky="w", pady=6)
            self.label(sidebar, textvariable=self.summary[key], fg=color,
                       font=("Microsoft YaHei UI", 10, "bold")).grid(row=row, column=1, columnspan=2, sticky="e", pady=6)
        self.label(sidebar, "结果按模型推算；曲线仅显示设定的时间范围。\n均衡平方律的剩余兵力为 t → ∞ 时的极限。",
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
        ttk.Button(bottom, text="Simulation · 开始仿真", style="Primary.TButton",
                   command=self.run_simulation).pack(side="left", padx=(0, 10))
        self.pause_button = ttk.Button(bottom, text="暂停", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=(0, 10))
        ttk.Button(bottom, text="恢复示例", command=self.reset).pack(side="left", padx=(0, 10))
        ttk.Button(bottom, text="导出 CSV", command=self.export_csv).pack(side="left")
        ttk.Button(bottom, text="关闭", command=self.on_close).pack(side="right")

    def read_parameters(self) -> Parameters:
        try:
            values = {key: float(var.get().strip()) for key, var in self.variables.items()}
        except ValueError as exc:
            raise ValueError("请在兵力、损耗系数和时间上限中输入有效数字。") from exc
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
            messagebox.showerror("输入有误", str(exc), parent=self)
            return
        self.cancel_animation()
        self.result = result
        self.summary["winner"].set(result.winner)
        self.summary["time"].set(number(result.end_time))
        self.summary["red"].set(number(result.red_remaining))
        self.summary["blue"].set(number(result.blue_remaining))
        if result.parameters.model == LINEAR:
            self.formula.set("图示线性模式：dR/dt = −a，dB/dt = −b。双方兵力匀速下降，一方归零即停止。")
        else:
            self.formula.set("平方律：dR/dt = −aB，dB/dt = −bR。守恒量：bR² − aB²；一方归零即停止。")
        self.visible_count = 1 if animate else len(result.samples)
        self.draw_plot()
        self.running = animate and len(result.samples) > 1
        self.pause_button.configure(text="暂停", state="normal" if self.running else "disabled")
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
            self.pause_button.configure(state="disabled", text="暂停")

    def update_status(self) -> None:
        if self.result is None:
            return
        t, r, b = self.result.samples[self.visible_count - 1]
        prefix = "仿真中" if self.visible_count < len(self.result.samples) else "显示完成"
        if self.visible_count == len(self.result.samples) and t < self.result.end_time:
            prefix += " · 已到时间上限，战斗尚未结束"
        self.status.set(f"{prefix}    t = {number(t)}    红方 = {number(r)}    蓝方 = {number(b)}")

    def toggle_pause(self) -> None:
        if self.result is None or self.visible_count >= len(self.result.samples):
            return
        if self.running:
            self.cancel_animation()
            self.pause_button.configure(text="继续")
            self.status.set(self.status.get().replace("仿真中", "已暂停", 1))
        else:
            self.running = True
            self.pause_button.configure(text="暂停")
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
        c.create_text(left, 10, text="兵力", anchor="w", fill=MUTED, font=font)
        c.create_text((left + right) / 2, h - 10, text="时间 t", fill=MUTED, font=font)
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
            parent=self, title="导出当前仿真数据", defaultextension=".csv",
            initialfile="lanchester_simulation.csv", filetypes=[("CSV 文件", "*.csv")],
        )
        if not path:
            return
        try:
            export_result(self.result, path)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
        else:
            self.status.set("当前曲线的完整采样数据已导出（对应上次点击仿真的参数）。")

def export_result(result: Result, path: str) -> None:
    """UTF-8 BOM 编码便于 Excel 打开中文表头；导出当前仿真完整数据。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("时间 t", "红方剩余兵力 R", "蓝方剩余兵力 B"))
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
    """使用 RK4 积分，返回 (时间, 红方, 蓝A, 蓝B) 时间序列和结局说明。"""
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
        outcome = "达到仿真时限（兵力未归零）"
    elif max(state) <= 1e-8:
        outcome = "双方均失去战斗力"
    elif state[0] > 1e-8:
        outcome = "红方胜利"
    elif state[1] > 1e-8 or state[2] > 1e-8:
        outcome = "蓝方胜利"
    else:
        outcome = "战斗结束"
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
            self.create_text(w / 2, h / 2, text="输入参数后点击“开始仿真”", fill="#718096", font=("Microsoft YaHei UI", 10))
            return

        if len(self.data) == 1:
            names = ("红方", "蓝方 A", "蓝方 B")
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
        self.create_text(18, (top + bottom) / 2, text="兵力", angle=90, fill="#526174", font=("Microsoft YaHei UI", 9))
        self.create_text((left + right) / 2, h - 9, text="时间（小时）", fill="#526174", font=("Microsoft YaHei UI", 9))
        for index, (name, color) in enumerate(zip(("红方", "蓝方 A", "蓝方 B"), self.COLORS)):
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
        tk.Label(header, text="兰彻斯特战损仿真系统", bg="#183b5b", fg="white", font=("Microsoft YaHei UI", 18, "bold")).pack(side="left", padx=22, pady=12)
        tk.Label(header, text="三兵力模型 · RK4 数值积分", bg="#183b5b", fg="#c8d8e8", font=("Microsoft YaHei UI", 10)).pack(side="right", padx=24)

        body = tk.Frame(self, bg="#eef2f6")
        body.pack(fill="both", expand=True, padx=14, pady=14)
        panel = tk.Frame(body, bg="white", width=340, highlightbackground="#d8e0e8", highlightthickness=1)
        panel.pack(side="left", fill="y", padx=(0, 14))
        panel.pack_propagate(False)
        tk.Label(panel, text="作战参数设置", bg="white", fg="#26384b", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=18, pady=(18, 10))

        groups = [
            ("初始兵力", [("red", "红方总兵力", 260), ("blue_a", "蓝方 A 兵力", 200), ("blue_b", "蓝方 B 兵力", 60)]),
            ("毁伤系数（每小时）", [("red_to_a", "红方对 A 毁伤", 0.1), ("red_to_b", "红方对 B 毁伤", 0.5), ("blue_a_to_red", "蓝方 A 对红方毁伤", 0.1), ("blue_b_to_red", "蓝方 B 对红方毁伤", 1.5)]),
            ("红方火力分配", [("share_a", "分配给 A 的比例", 0.5), ("share_b", "分配给 B 的比例", 0.5)]),
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

        tk.Button(panel, text="开始仿真", command=self.run, bg="#39a84b", fg="white", activebackground="#2d903d", activeforeground="white", relief="flat", font=("Microsoft YaHei UI", 12, "bold"), cursor="hand2").pack(fill="x", padx=18, pady=(17, 8), ipady=9)
        tk.Label(panel, text="双方按课件方程计算损耗。\n一个蓝方兵种归零后，红方将火力\n全部转向另一兵种。", justify="left", bg="white").pack(anchor="w", padx=18)

        results = tk.Frame(body, bg="#eef2f6")
        results.pack(side="left", fill="both", expand=True)
        cards = tk.Frame(results, bg="#eef2f6")
        cards.pack(fill="x", pady=(0, 12))
        self.kpis: dict[str, tk.Label] = {}
        for key, title, initial in (("outcome", "仿真结果", "等待仿真"), ("duration", "战斗持续时间", "— 小时"), ("survivors", "战斗结束兵力（红 / 蓝A / 蓝B）", "— / — / —")):
            card = tk.Frame(cards, bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, bg="white", fg="#69788b", font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=12, pady=(9, 1))
            label = tk.Label(card, text=initial, bg="white", fg="#203b58", font=("Microsoft YaHei UI", 12, "bold"))
            label.pack(anchor="w", padx=12, pady=(0, 10))
            self.kpis[key] = label

        top = tk.Frame(results, bg="#eef2f6", height=225)
        top.pack(fill="x", pady=(0, 12))
        top.pack_propagate(False)
        self.initial_chart = Chart(top, "初始兵力对比", bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
        self.initial_chart.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.final_chart = Chart(top, "战斗结束兵力对比", bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
        self.final_chart.pack(side="left", fill="both", expand=True)
        self.line_chart = Chart(results, "红蓝双方兵力随时间变化", bg="white", highlightbackground="#d8e0e8", highlightthickness=1)
        self.line_chart.pack(fill="both", expand=True)
        self.status = tk.Label(self, text="就绪", bg="#e2e9f0", fg="#536477", anchor="w", padx=14, font=("Microsoft YaHei UI", 8))
        self.status.pack(fill="x", side="bottom")

    def read_input(self) -> BattleInput:
        values = {key: float(var.get().strip()) for key, var in self.vars.items()}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("参数必须是有限数值。")
        p = BattleInput(**values)
        if min(p.red, p.blue_a, p.blue_b) <= 0:
            raise ValueError("初始兵力必须大于 0。")
        if min(p.red_to_a, p.red_to_b, p.blue_a_to_red, p.blue_b_to_red) < 0:
            raise ValueError("毁伤系数不能为负数。")
        if not math.isclose(p.share_a + p.share_b, 1.0, abs_tol=1e-6):
            raise ValueError("分配给 A、B 的火力比例之和必须等于 1。")
        if not (0 <= p.share_a <= 1 and 0 <= p.share_b <= 1):
            raise ValueError("火力分配比例应在 0 到 1 之间。")
        return p

    def run(self) -> None:
        try:
            p = self.read_input()
        except (ValueError, TypeError) as exc:
            messagebox.showerror("参数有误", str(exc), parent=self)
            return
        data, outcome = simulate_three_forces(p)
        final = data[-1][1:]
        self.kpis["outcome"].configure(text=outcome)
        self.kpis["duration"].configure(text=f"{data[-1][0]:.2f} 小时")
        self.kpis["survivors"].configure(text=" / ".join(f"{x:.1f}" for x in final))
        self.initial_chart.set_data([(0, p.red, p.blue_a, p.blue_b)])
        self.final_chart.set_data([(0, *final)])
        self.line_chart.set_data(data)
        red_index, blue_index = combat_indices(p)
        index_text = f"{blue_index:.1f}" if blue_index is not None else "未定义"
        self.status.configure(text=f"初始作战指数：红方 {red_index:.1f} / 蓝方 {index_text}")


class SimulatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("兰彻斯特仿真合集")
        self.geometry("1320x850")
        self.minsize(1050, 750)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.two_force = TwoForcePage(self.tabs, self.close)
        self.three_force = ThreeForcePage(self.tabs)
        self.tabs.add(self.two_force, text="双方兵力 · 线性律 / 平方律")
        self.tabs.add(self.three_force, text="三兵力 · RK4")
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
