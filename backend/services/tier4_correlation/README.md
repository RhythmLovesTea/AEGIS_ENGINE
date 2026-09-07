# Tier 4 Service — AIS Correlation & Attribution Scoring

**Responsibility:** Ingest historical AIS transponder traffic within the spatio-temporal origin window; reconstruct continuous vessel trajectories with cubic splines; detect kinematic anomalies and dark gaps ($A_{dark}$); compute AHP-weighted composite score $S_{culprit} \in [0, 100]$.

- **Input Contract:** `OriginEstimate` $(\mu_p, \Sigma_p)$, `SlickCharacterization` $(\theta_{slick})$, AIS reports.
- **Output Contract (`VesselCandidate`):** `mmsi`, `imo`, `name`, `vessel_type`, `s_culprit`, `sub_scores: {spatial, temporal, kinematic, anomaly, type}`, `anomaly_flags`, `ais_coverage`.
