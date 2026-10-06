# Creates the local database role and database described by DATABASE_URL in .env.
# Run after installing PostgreSQL 17; prompts for the "postgres" superuser password.

$ErrorActionPreference = "Stop"

$envFile = Join-Path $PSScriptRoot "..\.env"
$line = Get-Content $envFile | Where-Object { $_ -like "DATABASE_URL=*" }
if (-not $line) { throw "DATABASE_URL not found in .env" }
$uri = [Uri]($line -replace "^DATABASE_URL=", "")
$user, $password = $uri.UserInfo.Split(":", 2)
$database = $uri.AbsolutePath.TrimStart("/")

$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
if (-not (Test-Path $psql)) { throw "psql not found at $psql" }

$superPassword = Read-Host "Password for the postgres superuser" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($superPassword))

try {
    & $psql -U postgres -h localhost -v ON_ERROR_STOP=1 -c "CREATE ROLE $user LOGIN CREATEDB PASSWORD '$password';"
    & $psql -U postgres -h localhost -v ON_ERROR_STOP=1 -c "CREATE DATABASE $database OWNER $user;"
    Write-Host "Created role '$user' and database '$database'."
}
finally {
    Remove-Item Env:PGPASSWORD
}
