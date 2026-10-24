Add-Type -AssemblyName System.Speech
$out = "C:\Users\LOU0122\booktool\promo\audio"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$lines = @(
  @("v1", "做一本书，最难的不是写，是把它拼成能装订的样子。"),
  @("v2", "八百多页的稿子，骑马钉、胶装、A6，点一下，两秒出结果。页序、空白页、中缝，全部算好。"),
  @("v3", "封面只要填页数，书脊厚度自动出来。A4居中排版，裁切线画在成品外面。"),
  @("v4", "打印能按面挑，双面走短边还是长边，看你打印机支持什么，它自己定。"),
  @("v5", "全部在本机运行，稿子不上传。免费，免安装，解压就能用。")
)
foreach ($l in $lines) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice("Microsoft Huihui Desktop")
  $s.Rate = 0
  $s.Volume = 100
  $s.SetOutputToWaveFile((Join-Path $out ($l[0] + ".wav")))
  $s.Speak($l[1])
  $s.Dispose()
  Write-Output ("ok " + $l[0])
}
