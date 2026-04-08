cd "D:\PyCharm\Project\NTA-AutoBot"
Remove-Item -Recurse -Force "build","dist" -ErrorAction SilentlyContinue
python.exe -m PyInstaller --noconfirm --clean "NTA-AutoBot.spec"

