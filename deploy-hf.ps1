# One-command redeploy to Hugging Face Spaces.
# Rebuilds a clean single-commit branch (no wheel history, model via Git LFS,
# no PPT, HF metadata in README) and force-pushes it to the Space's main branch.
#
# Prerequisite (one time): the 'hf' remote must exist with a WRITE token, e.g.
#   git remote add hf https://VirajSanghavi:hf_XXXX@huggingface.co/spaces/VirajSanghavi/Argus
#
# Usage:  .\deploy-hf.ps1

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

$src = git branch --show-current
if (-not $src) { $src = "main" }
Write-Host "Deploying current state of '$src' to HF Space..." -ForegroundColor Cyan

# Fresh orphan branch = clean history (no wheel blobs)
git branch -D hf-deploy 2>$null
git checkout --orphan hf-deploy
git reset | Out-Null

# Model (.pt) must go through Git LFS — HF rejects raw binaries
git lfs install | Out-Null
git lfs track "*.pt" | Out-Null

# HF Space metadata (this branch only; keeps main's README clean)
$fm = @"
---
title: UBIArgus
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

"@
Set-Content "README.md" ($fm + (Get-Content "README.md" -Raw)) -Encoding utf8 -NoNewline

# Stage everything except the PPT; force-add the gitignored demo artifacts
git add .gitattributes
git add -A ":!PPT Layout.pptx"
git add -f data/pipeline_cache.json data/multignn_model.pt data/multignn_meta.json data/whitelist.json
git commit -m "HF Spaces deploy $(Get-Date -Format 'yyyy-MM-dd HH:mm')" | Out-Null

# Ship it
git push hf hf-deploy:main --force
$ok = ($LASTEXITCODE -eq 0)

# Return to where you started (-f handles the untracked PPT)
git checkout -f $src | Out-Null

if ($ok) {
  Write-Host "`nDeployed. Space is rebuilding -> https://huggingface.co/spaces/VirajSanghavi/Argus" -ForegroundColor Green
} else {
  Write-Host "`nPush failed. Check the 'hf' remote token (needs WRITE)." -ForegroundColor Red
}
