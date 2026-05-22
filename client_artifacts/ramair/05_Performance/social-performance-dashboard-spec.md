# RamAir Social Performance Dashboard Starter

This is the MVP dashboard spec for a client-facing Power BI tab in the RamAir Teams channel. The first version is backed by CSV files stored in the channel SharePoint `Files` tab so Nathan and operators can update the data layer without a custom connector.

## Data Layer

Store these files in `05_Performance/data/` in the RamAir channel Files folder:

- `social_posts.csv`: one row per published or planned social post.
- `social_daily_metrics.csv`: one row per channel/campaign/date.
- `social_kpi_targets.csv`: target values for KPI cards and variance checks.

Refresh cadence for the MVP is manual before each client review. Nathan should only summarize metrics present in these files or in project memory.

## Power BI Pages

Page 1: Executive Snapshot

- KPI cards: impressions, engagements, engagement rate, clicks, video views, follower growth.
- Filters: date range, platform, campaign, episode, content pillar.
- Callout: "Data last updated" from the newest `date` in `social_daily_metrics.csv`.

Page 2: Content Performance

- Table: post date, platform, campaign, post title, status, impressions, engagements, clicks, engagement rate.
- Bar chart: top posts by engagement rate.
- Scatter: impressions vs engagement rate by platform.

Page 3: Channel Trends

- Line charts: impressions, engagements, clicks, follower count by date.
- Small multiples by platform.
- Target variance cards using `social_kpi_targets.csv`.

Page 4: Nathan Notes

- Text box for the weekly narrative.
- Table of missing data flags from blank metric fields.
- Approval note: do not publish claims externally unless the supporting row exists in the data layer.

## Starter Measures

```text
Total Impressions = SUM(social_daily_metrics[impressions])
Total Engagements = SUM(social_daily_metrics[engagements])
Engagement Rate = DIVIDE([Total Engagements], [Total Impressions])
Total Clicks = SUM(social_daily_metrics[clicks])
Follower Growth = MAX(social_daily_metrics[follower_count]) - MIN(social_daily_metrics[follower_count])
```

## Teams Tab Setup

1. Upload the `05_Performance/data/` CSV files to the RamAir channel `Files` tab.
2. In Power BI Desktop, choose `Get data` > `SharePoint folder`.
3. Use the SharePoint site URL for the Team, then filter to `05_Performance/data/`.
4. Build the pages above and publish the report to the workspace used by the client Team.
5. In Teams, select the RamAir channel, add a `Power BI` tab, and choose the published report.

## Nathan Update Rule

Nathan or an operator updates the CSV files in SharePoint, refreshes the Power BI dataset, and logs a project-memory event when the data layer changes. Nathan must say "performance data is not connected yet" for any KPI not represented in the CSV files.
