param(
    [Parameter(Mandatory=$true)][string]$Video,
    [Parameter(Mandatory=$true)][string]$Ass,
    [Parameter(Mandatory=$true)][string]$Output
)

$ErrorActionPreference = "Stop"
$filter = "subtitles='$Ass'"
ffmpeg -y -i $Video -vf $filter -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart $Output
