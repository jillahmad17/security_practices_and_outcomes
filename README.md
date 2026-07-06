# Security Practices and Vulnerability Outcomes

> **Note:** This repo's organization is still in progress and will be restructured — treat this README as a living document, not a final map.

Empirical analysis of whether OpenSSF Scorecard security practices are associated with security outcomes (vulnerability count, MTTU) across npm and PyPI packages.

## Overview
This repository supports a project examining whether OpenSSF Scorecard checks are associated with vulnerability counts and Mean Time to Update (MTTU) across ~15,000 npm and PyPI packages, using PPML two-way fixed effects models (`fixest::fepois()`).

## Getting started

### Prerequisites
- Python 3.x (pandas, etc.) — used for panel construction
- R (≥ 4.x) with `fixest`, `dplyr`, and related packages — used for estimation
- Jupyter (for the `.ipynb` notebooks)
- *(Add specific version numbers / package lists as they stabilize, e.g. via `requirements.txt` and `renv.lock`)*

*(Update once you've settled on dependency management — e.g. `requirements.txt`/`renv.lock` vs. a conda env file.)*

## Repository structure

```
.
├── formatting_version_data/         # script for version-level formatting and cleanup
├── local_checks/                    # local computation of Scorecard checks using --commit flag
├── merging_data/                    # scripts for joining data sources
├── replicated_metrics/              # scripts for replicating Fuzzing, Maintained, Dependency-Update-Tool, and Contributors checks 
├── rq1/                             # analysis for RQ1 (PPML-TWFE models)
├── time_varying_covariates/         # construction of time-varying covariates for the panel
│
├── github_repositories_unique.csv         # deduplicated list of GitHub repos in the sample
├── inclusion_exclusion_criteria.ipynb     # notebook defining sample inclusion/exclusion logic
├── longitudinal_study_package_criteria_octo....ipynb   # package-level criteria for the longitudinal panel
├── release_history.ipynb                  # release history via GitHub REST API
└── .gitignore
```

## Notes for future organization

- [ ] Add a top-level `data/` vs `analysis/` split if folder count keeps growing
- [ ] Consolidate `local_metrics/` and `replicated_metrics/` if overlap becomes redundant
- [ ] Document what's in `old/` before deciding whether to delete or archive it
- [ ] Rename notebooks with clearer, non-truncated names

## Reproducing the analysis

*(Add setup/run instructions here once the pipeline stabilizes.)*


