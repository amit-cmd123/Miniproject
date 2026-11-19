# Update every field in the generated report and export a PDF.
#
# python-docx cannot evaluate Word fields, so the table of contents, the list
# of figures, the list of tables and all page numbers are placeholders until
# Word computes them. This does that computation headlessly, reports the
# resulting page count, and leaves both a refreshed .docx and a .pdf.
#
#   powershell -ExecutionPolicy Bypass -File scripts\report\finalise.ps1

param(
    [string]$Docx = "docs\report\EvalNova_Mini_Project_Report.docx"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$path = Join-Path $root $Docx
$pdf = [System.IO.Path]::ChangeExtension($path, ".pdf")

if (-not (Test-Path $path)) {
    Write-Host "No report at $path - run build_report.py first." -ForegroundColor Red
    exit 1
}

Write-Host "Opening Word ..." -ForegroundColor Cyan
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    $doc = $word.Documents.Open($path, $false, $false)

    # Fields appear in the body and in the headers and footers; the table of
    # contents needs its own update call, and page numbers only settle after
    # repagination, so this is done twice.
    foreach ($pass in 1..2) {
        $doc.Fields.Update() | Out-Null
        foreach ($toc in $doc.TablesOfContents) { $toc.Update() | Out-Null }
        foreach ($tof in $doc.TablesOfFigures) { $tof.Update() | Out-Null }
        foreach ($section in $doc.Sections) {
            foreach ($header in $section.Headers) { $header.Range.Fields.Update() | Out-Null }
            foreach ($footer in $section.Footers) { $footer.Range.Fields.Update() | Out-Null }
        }
        $doc.Repaginate()
    }

    $pages = $doc.ComputeStatistics(2)   # wdStatisticPages
    $words = $doc.ComputeStatistics(0)   # wdStatisticWords

    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17)   # wdExportFormatPDF

    Write-Host ""
    Write-Host "Pages : $pages" -ForegroundColor Green
    Write-Host "Words : $words" -ForegroundColor Green
    Write-Host "DOCX  : $path"
    Write-Host "PDF   : $pdf"

    $doc.Close($false)
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
