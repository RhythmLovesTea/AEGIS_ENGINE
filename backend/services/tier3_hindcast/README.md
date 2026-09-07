# Tier 3 Service — Hydrodynamic Advection-Diffusion Modeling

**Responsibility:** Ingest CMEMS GLO12 surface currents and ERA5 winds; execute backward Lagrangian particle advection with OpenDrift/OpenOil ($N \ge 10,000$, $\Delta t = -15\text{ min}$); compute 2D Gaussian KDE origin cloud $(\mu_p, \Sigma_p)$ and forward $+72\text{h}$ weathering forecast.

- **Input Contract:** `SlickDetection` polygon, `SlickCharacterization` ($t_{age}$), met-ocean forcing fields.
- **Output Contract (`OriginEstimate`):** `centroid` $[\bar{lat}, \bar{lon}]$, `covariance_matrix` $\Sigma_p$, `time_window`, `confidence_pct`, `particle_trajectory_ref`.
