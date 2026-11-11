# Lanchester Simulator

An educational Python and Tkinter application for exploring Lanchester attrition models. Adjust initial force levels, attrition coefficients, and fire allocation to see how force levels change over time.

## Running the simulator

Use Python 3.10 or later with Tkinter. No third-party Python packages are required. From the project directory, run:

```powershell
py lanchester_simulator_combined.py
```

If your system uses `python` or `python3`, substitute that command for `py`.

## Simulation modes

- **Two Forces** supports the linear law (constant attrition) and the Lanchester square law. You can export the simulation data as CSV.
- **Three Forces** uses the fourth-order Runge–Kutta method (RK4). Red splits its fire between Blue A and Blue B according to the specified shares. When one Blue force reaches zero, Red directs all its fire at the remaining force.

With the default three-force settings, Blue B reaches zero first. The simulation ends after about 24.48 hours, with Red winning and retaining about 36.66 of its initial force of 260.

## Expert assessment

The **Expert Assessment** tab offers two educational methods for combining expert judgments. It comes with a dimensionless classroom effectiveness-score example; click **Calculate** to try it. The default group decision result is approximately 0.77127.

- **Expert assessment** calculates the mean, sample standard deviation and coefficient of variation. When the coefficient is at most 0.2, the mean is offered as the assessment; otherwise a new round of expert judgments is needed. This threshold is a course convention.
- **Group decision** ranks first-round absolute deviations from the mean, assigns weights based on those ranks, and applies them to the second-round judgments. Tied deviations receive average ranks. Leaving round two blank reuses round one.

To estimate a model coefficient, select the corresponding target and enter expert estimates directly in the correct model units. After calculating, use **Apply to model** and run the simulation in the selected tab. The default example is an effectiveness score and cannot be applied as a coefficient. Expert judgments are estimates, not measurements; the application cannot establish their physical validity. Keep `expert_assessment.py` alongside the main script.

## License

This project is available under the [MIT License](LICENSE).
