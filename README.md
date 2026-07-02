# Longitudinal-Analysis

## Collecting Control Variable Data

We collected release level control variable data. 

1. Download Count 
PyPI Download count queries: \
a. https://console.cloud.google.com/bigquery?ws=!1m7!1m6!12m5!1m3!1scollectingdatadec2025!2sus-central1!3sd789316d-f467-4f2e-9589-6acbf0ed4c64!2e1 \
b. https://console.cloud.google.com/bigquery?ws=!1m7!1m6!12m5!1m3!1scollectingdatadec2025!2sus-central1!3s02e03ee9-1c6d-4d2a-9841-f2e3501f6761!2e1

npm Download count: Utilized npm APIs: https://api.npmjs.org/versions/{package}/last-week and https://registry.npmjs.org/{package}
- Jupyter notebook can be found -> control_variables/download_count/npm_download_count.ipynb

2. Dependent Count (from deps.dev)
3. Package age (version release date - first release date, in days) 
5. Lines of code
6. Maintained Score https://github.com/ossf/scorecard/blob/main/docs/checks.md#maintained

## Extract vulnerability count, calculating aggregate scores, and EDA
Located within eda_and_aggregate_score directory
- aggregated_sc_score_and_extract_vuln_count.ipynb -> Calculating aggregate score and extracting vulnerability count from "Vulnerability Reason" column from running Scorecard locally
- eda_data.ipynb -> EDA

## Create Monthly Panel dataframe
Located within models directory 
- create_agg_monthly_panel_data.ipynb -> Aggregating releases via the average in months where a package has multiple releases 

## Data Preprocessing *update to this section in progress*
1. merging_non_local_check_data/extracting_scores_from_nonlocal_checks.ipynb: Extracting SC non-local check data from json formatting
2. merging_non_local_check_data/merging_data_and_calc_agg_score.ipynb: Merging non-local check data and control variables with local check data and calculating aggregate SC score
Resulting data: 
sc_data_with_vuln_count_agg_score.csv, located here: https://drive.google.com/file/d/1q2uFAz6bUDlLQ2Wkwj0_8EyZfwIDv96q/view?usp=share_link. 
3. For the **adoption** models, extract the rows containing the repositories that either remained 0 for all versions (control group), or transitioned from 0 to greater than 0, and remained greater than 0, for the rest of the releases. For the abandonment models, extract the rows containing the repositories that either remained >0 for all versions (control group), or transitioned from greater than 0 to 0, and remained 0 for the rest of the releases. \
The script to creating the code review subset can be found here: RQ2/creating_subset_for_analysis.ipynb.
4. RQ1/vulnerability_count_distributions.ipynb: script examining the vulnerability counts, with and without outliers in the data.


