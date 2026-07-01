# Roll back the live HF Space to a previous deploy.
#
# Every successful .\deploy-hf.ps1 run tags the commit it shipped as
# hf-deploy-YYYYMMDD-HHMMSS on your current branch. This script pulls the
# file contents from that tag into a FRESH orphan branch and re-runs the
# same LFS-tracking + clean-history treatment deploy-hf.ps1 uses — it does
# NOT just push the tagged commit directly, because that commit's raw
# history predates the Git-LFS/no-wheels cleanup and HF will reject it
# with the same "contains binary files" error we hit the first time.
#
# Usage:
#   .\rollback-hf.ps1                    # lists available deploy tags, does nothing else
#   .\rollback-hf.ps1 hf-deploy-20260701-143000   # rolls back to that tag

param(
    [string]$Tag
)

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

$tags = git tag -l "hf-deploy-*" | Sort-Object -Descending

if (-not $Tag) {
    Write-Host "Available deploy tags (newest first):`n" -ForegroundColor Cyan
    if (-not $tags) {
        Write-Host "  (none yet — run .\deploy-hf.ps1 at least once first)" -ForegroundColor DarkGray
    } else {
        $tags | ForEach-Object {
            $sha = git rev-parse --short $_
            $msg = git log -1 --format=%s $_
            Write-Host "  $_  ($sha)  $msg"
        }
    }
    Write-Host "`nUsage: .\rollback-hf.ps1 <tag>" -ForegroundColor Yellow
    exit 0
}

if ($tags -notcontains $Tag) {
    Write-Host "Tag '$Tag' not found. Run .\rollback-hf.ps1 with no args to list valid tags." -ForegroundColor Red
    exit 1
}

$src = git branch --show-current
if (-not $src) { $src = "main" }

Write-Host "Rolling back HF Space to tag '$Tag'..." -ForegroundColor Cyan

# Fresh orphan branch, populated with that tag's file contents — same clean-
# history approach as deploy-hf.ps1, just sourced from an old tag instead of
# current HEAD.
git branch -D hf-rollback 2>$null
git checkout --orphan hf-rollback | Out-Null
git reset | Out-Null
git checkout $Tag -- . | Out-Null

git lfs install | Out-Null
git lfs track "*.pt" | Out-Null

git add .gitattributes
git add -A ":!PPT Layout.pptx"
git add -f data/pipeline_cache.json data/multignn_model.pt data/multignn_meta.json 2>$null
git commit -m "Rollback to $Tag ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" | Out-Null

git push hf hf-rollback:main --force
$ok = ($LASTEXITCODE -eq 0)

git checkout -f $src | Out-Null
git branch -D hf-rollback | Out-Null

if ($ok) {
    Write-Host "`nRolled back. Space is rebuilding from '$Tag' -> https://huggingface.co/spaces/VirajSanghavi/Argus" -ForegroundColor Green
    Write-Host "Note: your local '$src' branch is untouched — this only reset what's deployed." -ForegroundColor DarkGray
} else {
    Write-Host "`nRollback push failed. Check the 'hf' remote token (needs WRITE)." -ForegroundColor Red
}
