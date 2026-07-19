# Data

The datasets used in this study are archived on Zenodo (anonymized for double-blind review):

**Zenodo DOI:** `[ANONYMIZED_ZENODO_DOI_HERE]`

Data files are not included in this repository due to size constraints. This README describes the schema and structure of the archived datasets.

## Overview

This study uses two release-level panel datasets constructed from npm and PyPI package repositories, combining OpenSSF Scorecard security practice scores with vulnerability outcome measures.

| Dataset | N (packages) | Outcome |
|---|---|---|
| `monthly_panel_vuln` | 15,598 | Vulnerability count per release-month |
| `monthly_panel_mttu` | 13,654 | Mean Time to Update (MTTU) |


## File structure

```
data/
├── monthly_panel_vuln.csv           # monthly package release level data, including Scorecard checks, time-varying covariates, and Vulnerability Count
├── mttu_panel_mttu.csv                   # monthly package release level data, including Scorecard checks, time-varying covariates, and MTTU
├── sc_data.csv.zip                  # raw MTTR dataset, including Scorecard checks, time-varying covariates, and Vulnerability Count
├── sc_data_mttu_subset.csv.zip      # raw MTTR dataset, including Scorecard checks, time-varying covariates, and MTTU
└── README.md
```

