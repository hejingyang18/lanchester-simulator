"""Two-round expert assessment using ranked deviations."""
import math
import re
import statistics
import tkinter as tk
from tkinter import ttk, messagebox

EXAMPLE = [0.84, 0.63, 0.77, 0.54, 0.91, 0.85, 0.79, 0.82, 0.68, 0.75]

def assess(first, second):
    if len(first) < 2 or len(first) != len(second):
        raise ValueError('Both rounds need the same number of experts (at least two).')
    if any(not math.isfinite(x) or x < 0 for x in first + second):
        raise ValueError('Values must be finite and nonnegative.')
    mean = statistics.mean(first)
    deviations = [abs(x - mean) for x in first]
    # 相同离差采用平均名次，保持权重之和为 1。
    ranks = []
    for deviation in deviations:
        larger = sum(d > deviation and not math.isclose(d, deviation, rel_tol=1e-12, abs_tol=1e-12) for d in deviations)
        tied = sum(math.isclose(d, deviation, rel_tol=1e-12, abs_tol=1e-12) for d in deviations)
        ranks.append(larger + (tied + 1) / 2)
    n = len(first)
    weights = [2 * rank / (n * (n + 1)) for rank in ranks]
    std = statistics.stdev(first)
    result = sum(w*y for w, y in zip(weights, second))
    if not all(math.isfinite(v) for v in (mean, std, result, *deviations)):
        raise ValueError('Values are too large; check the units.')
    return mean, std, deviations, ranks, weights, result


def parse_values(value):
    return [float(v) for v in re.split(r'[,，;；\s]+', value.strip()) if v]


class ExpertPage(ttk.Frame):
    def __init__(self, parent, two, three):
        super().__init__(parent, padding=18)
        self.targets = {
            'Two forces: red loss coefficient a': (two.variables['a'], 'Two-force model', 'coefficient in model time units'),
            'Two forces: blue loss coefficient b': (two.variables['b'], 'Two-force model', 'coefficient in model time units'),
            'Three forces: red against A': (three.vars['red_to_a'], 'Three-force model', 'per hour'),
            'Three forces: red against B': (three.vars['red_to_b'], 'Three-force model', 'per hour'),
            'Three forces: blue A against red': (three.vars['blue_a_to_red'], 'Three-force model', 'per hour'),
            'Three forces: blue B against red': (three.vars['blue_b_to_red'], 'Three-force model', 'per hour'),
        }
        self.value = None
        self.method = tk.StringVar(value='Group decision')
        self.target = tk.StringVar(value=next(iter(self.targets)))
        self.round1 = tk.StringVar(value='0.84, 0.63, 0.77, 0.54, 0.91, 0.85, 0.79, 0.82, 0.68, 0.75')
        self.round2 = tk.StringVar()
        ttk.Label(self, text='Expert assessment of model coefficients', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(self, text='Method:').pack(anchor='w')
        ttk.Combobox(self, textvariable=self.method, values=['Expert assessment', 'Group decision'], state='readonly', width=20).pack(anchor='w')
        ttk.Label(self, text='Expert assessment uses round one. Group decision uses both rounds; leave round two blank to reuse round one.').pack(anchor='w', pady=8)
        ttk.Label(self, text='The default example is an effectiveness score, not a model coefficient.', foreground='#a54b1f').pack(anchor='w', pady=(0, 6))
        ttk.Label(self, text='Select a coefficient:').pack(anchor='w')
        ttk.Combobox(self, textvariable=self.target, values=list(self.targets), state='readonly', width=48).pack(anchor='w', pady=4)
        for label, var in [('Round one (comma or space separated)', self.round1), ('Round two (same expert order; optional)', self.round2)]:
            ttk.Label(self, text=label).pack(anchor='w', pady=(8, 2))
            ttk.Entry(self, textvariable=var, width=100).pack(fill='x')
        controls = ttk.Frame(self)
        controls.pack(anchor='w', pady=10)
        ttk.Button(controls, text='Calculate', command=self.calculate).pack(side='left', padx=(0, 12))
        ttk.Button(controls, text='Apply to model', command=self.apply).pack(side='left')
        ttk.Label(self, text='The result summarizes judgments, not measurements. Verify units and applicability.').pack(anchor='w', pady=4)
        self.output = tk.Text(self, height=18, width=100, wrap='word')
        self.output.pack(fill='both', expand=True, pady=8)
        for var in (self.round1, self.round2, self.target, self.method):
            var.trace_add('write', lambda *_: self.invalidate())

    def invalidate(self):
        self.value = None

    def calculate(self):
        self.value = None
        try:
            first = parse_values(self.round1.get())
            second = parse_values(self.round2.get()) if self.method.get() == 'Group decision' and self.round2.get().strip() else first[:]
            mean, std, deviations, ranks, weights, result = assess(first, second)
        except (ValueError, OverflowError) as exc:
            messagebox.showerror('Invalid input', str(exc), parent=self)
            return
        example = first == EXAMPLE
        unit = 'dimensionless effectiveness score' if example else self.targets[self.target.get()][2]
        title = 'Course example: effectiveness score' if example else self.target.get()
        lines = [f'Target: {title}（{unit}）', f'Round-one mean: {mean:.6g}; sample standard deviation: {std:.6g}',
                 f'Coefficient of variation: {std / mean:.2%}' if mean else 'Coefficient of variation: undefined when the mean is zero']
        if self.method.get() == 'Expert assessment':
            if not mean:
                lines.append('Consistency cannot be determined using the coefficient of variation.')
            elif std / mean <= 0.2:
                self.value = mean
                lines.append(f'At or below the course threshold of 0.2; mean assessment: {mean:.8g}（{unit}）')
            else:
                lines.append('Above the course threshold of 0.2; obtain a new round of expert assessments.')
            lines.append('Enter the new expert assessments in the round-one field.')
        else:
            self.value = result
            lines.append('Expert  Round 1      Deviation     Rank      Weight       Round 2')
            for i, (x, d, q, w, y) in enumerate(zip(first, deviations, ranks, weights, second), 1):
                lines.append(f'{i:>3}   {x:>10.6g}  {d:>10.6g}  {q:>7.3g}  {w:>10.6f}  {y:>10.6g}')
            lines.append(f'\nRound-two weighted assessment: {result:.8g}（{unit}）')
            lines.append('Equal deviations receive average ranks; round-one ranks weight round-two values.')
        self.output.delete('1.0', 'end')
        self.output.insert('end', '\n'.join(lines))

    def apply(self):
        if self.value is None:
            messagebox.showwarning('Calculate first', 'Recalculate after changing inputs or target.', parent=self)
            return
        if parse_values(self.round1.get()) == EXAMPLE:
            messagebox.showwarning('Example cannot be applied', 'The default is an effectiveness score. Enter direct estimates of the chosen coefficient.', parent=self)
            return
        variable, model, unit = self.targets[self.target.get()]
        if not messagebox.askyesno('Confirm coefficient units', 'Only apply direct expert estimates of the selected model coefficient in matching units. The default example is not a coefficient.\n\nConfirm the values match the selected coefficient and its units.', parent=self):
            return
        if model == 'Two-force model' and self.value > 1e6:
            messagebox.showerror('Out of range', 'This coefficient must not exceed 1,000,000.', parent=self)
            return
        variable.set(format(self.value, '.12g'))
        messagebox.showinfo('Applied', f'Applied to {model}. Switch to that tab and run the simulation.', parent=self)
