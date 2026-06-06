param(
    [Parameter(Mandatory=$true)][string]$Video,
    [Parameter(Mandatory=$true)][string]$Time,
    [Parameter(Mandatory=$true)][string]$Output
)

$ErrorActionPreference = "Stop"
ffmpeg -y -i $Video -ss $Time -frames:v 1 -update 1 $Output
