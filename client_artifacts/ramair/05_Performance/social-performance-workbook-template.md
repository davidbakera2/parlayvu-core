# Social Performance Workbook Template

Use this as the Excel workbook layout if the client prefers to edit one workbook instead of separate CSV files. Each worksheet should keep the exact columns from the matching CSV so it can be exported back to SharePoint or connected directly to Power BI.

## Worksheets

- `social_posts`: copy the columns from `data/social_posts.csv`.
- `social_daily_metrics`: copy the columns from `data/social_daily_metrics.csv`.
- `social_kpi_targets`: copy the columns from `data/social_kpi_targets.csv`.
- `nathan_notes`: optional human notes with `note_date`, `author`, `summary`, `approved_for_client`.

## MVP Workflow

1. Keep the workbook in `05_Performance/` in the RamAir channel Files tab.
2. Export or save the three structured worksheets as CSV files in `05_Performance/data/`.
3. Refresh the Power BI report from the SharePoint folder data source.
4. Ask Nathan for a client-safe summary only after the CSV data has been updated.
