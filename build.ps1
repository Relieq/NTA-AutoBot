cd "D:\PyCharm\Project\NTA-AutoBot"
$easyOcrSrc = Join-Path $env:USERPROFILE ".EasyOCR\model"
$easyOcrDst = "D:\PyCharm\Project\NTA-AutoBot\third_party\easyocr\model"

New-Item -ItemType Directory -Path $easyOcrDst -Force | Out-Null

if (Test-Path $easyOcrSrc) {
	Copy-Item -Path (Join-Path $easyOcrSrc "*") -Destination $easyOcrDst -Recurse -Force
	Write-Host "[BUILD] Da copy EasyOCR models tu cache local vao third_party/easyocr/model"
}

$hasEasyOcrModel = Get-ChildItem -Path $easyOcrDst -File -Filter "*.pth" -ErrorAction SilentlyContinue
if (-not $hasEasyOcrModel) {
	Write-Error "Khong tim thay EasyOCR model (.pth) trong '$easyOcrDst'."
	Write-Host "Hay chay app source 1 lan tren may build (co internet) de EasyOCR tai model, sau do build lai."
	exit 1
}

Remove-Item -Recurse -Force "build","dist" -ErrorAction SilentlyContinue
python.exe -m PyInstaller --noconfirm --clean "NTA-AutoBot.spec"

