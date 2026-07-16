# Security Practices and Vulnerability Outcomes

> **Note:** This repo's organization is still in progress and will be restructured — treat this README as a living document, not a final map.

Empirical analysis of whether OpenSSF Scorecard security practices are associated with security outcomes (vulnerability count, MTTU) across npm and PyPI packages.

## Overview
This repository supports a project examining whether OpenSSF Scorecard checks are associated with vulnerability counts and Mean Time to Update (MTTU) across ~15,000 npm and PyPI packages, using PPML two-way fixed effects models (`fixest::fepois()`).

## Getting started

### Prerequisites
- Python 3.12 with packages pandas, re, numpy
- R (≥ 4.x) with `fixest`, `dplyr`, `ggplot2`, `reshape2`, `moments`, `tidyr`, `lubridate`
- Jupyter (for the `.ipynb` notebooks)
- replicated_checks/ each have their own requirements, listed either in requirements.txt or ReadMe


## Repository structure

```
.
├── analysis/                        # scripts for analysis (fluctuation table and skewness, cofluctuation matrix, PPML-TWFE models) 
├── formatting_version_data/         # script for version-level formatting
├── local_checks/                    # local computation of Scorecard checks using --commit flag
├── replicated_checks/               # scripts for replicating Fuzzing, Maintained, Dependency-Update-Tool, and Contributors checks 
├── scorecard_checks/                # scripts for running Scorecard locally, providing the commit sha
├── code_review_analysis/            # comparison of Code-Review scores before and after scores transition from 0 to >0  
└── .gitignore
```