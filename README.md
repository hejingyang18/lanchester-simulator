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

## License

This project is available under the [MIT License](LICENSE).
