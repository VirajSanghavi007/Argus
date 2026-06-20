# Run all benchmarks sequentially — Medium datasets take ~30-60 min each
# Usage: .\run_benchmarks.ps1

$py   = ".\venv\Scripts\python.exe"
$bm   = "backend\benchmark.py"
$data = "data\IBM"
$ext  = "data"

$datasets = @(
    "$data\HI-Medium_Trans.csv",
    "$data\LI-Medium_Trans.csv",
    "data\SAML-D\SAML-D.csv",
    "data\TransXion\data\tx.csv"
)

foreach ($ds in $datasets) {
    Write-Host "`n=== Running benchmark on $ds ===" -ForegroundColor Cyan
    & $py $bm --dataset $ds
    Write-Host "=== Done ===" -ForegroundColor Green
}

Write-Host "`nAll benchmarks complete. Results in data\benchmark_results_*.txt" -ForegroundColor Yellow
