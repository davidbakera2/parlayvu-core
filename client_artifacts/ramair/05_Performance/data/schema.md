# RamAir Social Performance Data Schema

These CSV files are the MVP data layer for Power BI in Teams. Keep column names stable so Power BI refreshes do not break.

## `social_posts.csv`

- `post_id`: stable unique ID.
- `campaign_id`: campaign or episode identifier.
- `episode_title`: source episode or content theme.
- `platform`: LinkedIn, Instagram, Facebook, YouTube, TikTok, or other.
- `post_date`: planned or published date in `YYYY-MM-DD`.
- `post_title`: client-facing content label.
- `content_pillar`: strategy category.
- `status`: planned, drafted, approved, published, or archived.
- `post_url`: final URL when available.
- `owner`: responsible person or agent.

## `social_daily_metrics.csv`

- `date`: metric date in `YYYY-MM-DD`.
- `campaign_id`: joins to `social_posts.csv` when applicable.
- `platform`: social platform.
- `impressions`: total impressions.
- `reach`: total reach.
- `engagements`: likes, comments, shares, saves, and reactions.
- `clicks`: link or profile clicks.
- `video_views`: video views.
- `followers`: follower count for the account on that date.
- `spend`: paid spend if applicable; use `0` when not paid.
- `data_source`: native export, manual entry, or connector name.

## `social_kpi_targets.csv`

- `kpi_name`: display name for the KPI.
- `metric_column`: matching metric in the daily metrics file.
- `target_value`: numeric target.
- `target_period`: weekly, monthly, campaign, or custom.
- `notes`: assumptions or client-approved target context.
