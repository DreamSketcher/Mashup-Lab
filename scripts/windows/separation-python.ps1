# Windows PowerShell 5.1. A project-local CPython runtime; no registry or PATH changes.
param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$destination = Join-Path $ProjectRoot '.python-separation'
$python = Join-Path $destination 'python.exe'
$probe = Join-Path $PSScriptRoot 'check-python312.py'
$url = 'https://api.nuget.org/v3-flatcontainer/python/3.12.10/python.3.12.10.nupkg'
$expected = '0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8'

function CheckPython([string]$exe) {
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { return $false }
    & $exe $probe | Out-Host
    return ($LASTEXITCODE -eq 0)
}

if (Test-Path -LiteralPath $destination) {
    if (CheckPython $python) { return }
    throw 'Каталог .python-separation существует, но Python повреждён или несовместим. Он не удалён; проверьте его вручную.'
}
$stage = Join-Path $ProjectRoot ('.python-separation-download-' + [Guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
    $createdStage = $true
    $archive = Join-Path $stage 'python.nupkg'
    [Console]::WriteLine('Загрузка официального CPython 3.12.10 x64 с nuget.org в каталог проекта...')
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($archive)
        try { $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
        finally { $stream.Dispose() }
    } finally { $sha.Dispose() }
    if ($actual -ne $expected) { throw 'SHA-256 пакета Python не совпал; пакет не установлен.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $unpacked = Join-Path $stage 'unpacked'
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $unpacked)
    $tools = Join-Path $unpacked 'tools'
    if (-not (CheckPython (Join-Path $tools 'python.exe'))) { throw 'Проверка загруженного Python не прошла.' }
    # Do not overwrite an existing runtime, even if another process created it.
    [IO.Directory]::Move($tools, $destination)
    [Console]::WriteLine('Локальный Python установлен в .python-separation.')
} finally {
    if ($createdStage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
