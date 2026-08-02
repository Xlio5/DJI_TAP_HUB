param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

Add-Type -AssemblyName System.Drawing

$source = [System.Drawing.Bitmap]::FromFile($InputPath)
$bitmap = New-Object System.Drawing.Bitmap($source.Width, $source.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$graphics.DrawImageUnscaled($source, 0, 0)

$font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
$legendFont = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$group1Color = [System.Drawing.Color]::FromArgb(255, 22, 101, 216)
$group2Color = [System.Drawing.Color]::FromArgb(255, 0, 151, 117)
$boxFill = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 255, 255, 255))
$group1Brush = New-Object System.Drawing.SolidBrush($group1Color)
$group2Brush = New-Object System.Drawing.SolidBrush($group2Color)
$group1Pen = New-Object System.Drawing.Pen($group1Color, 2)
$group2Pen = New-Object System.Drawing.Pen($group2Color, 2)
$group1Pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$group2Pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

function Draw-Label {
    param(
        [System.Drawing.Graphics]$Canvas,
        [string]$Text,
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height,
        [int]$PadX,
        [int]$PadY,
        [string]$Group
    )

    $pen = if ($Group -eq 'G1') { $group1Pen } else { $group2Pen }
    $brush = if ($Group -eq 'G1') { $group1Brush } else { $group2Brush }
    $rect = New-Object System.Drawing.Rectangle($X, $Y, $Width, $Height)
    $Canvas.FillRectangle($boxFill, $rect)
    $Canvas.DrawRectangle($pen, $rect)

    $anchorX = [Math]::Max($X, [Math]::Min($PadX, $X + $Width))
    $anchorY = [Math]::Max($Y, [Math]::Min($PadY, $Y + $Height))
    $Canvas.DrawLine($pen, $PadX, $PadY, $anchorX, $anchorY)

    $textSize = $Canvas.MeasureString($Text, $font)
    $textX = [single]($X + (($Width - $textSize.Width) / 2))
    $textY = [single]($Y + (($Height - $textSize.Height) / 2))
    $Canvas.DrawString($Text, $font, $brush, $textX, $textY)
}

# 顶边：Pin 1、2 属于组 2，Pin 10～12 属于组 1。
$topPins = @(
    @{ Text = '1 PH2'; X = 650; PadX = 601; Group = 'G2' }
    @{ Text = '2 PC13'; X = 725; PadX = 646; Group = 'G2' }
    @{ Text = '10 PA0'; X = 800; PadX = 1007; Group = 'G1' }
    @{ Text = '11 PA1'; X = 875; PadX = 1052; Group = 'G1' }
    @{ Text = '12 PA2'; X = 950; PadX = 1097; Group = 'G1' }
)
foreach ($pin in $topPins) {
    Draw-Label $graphics $pin.Text $pin.X 250 70 21 $pin.PadX 201 $pin.Group
}

# 底边：Pin 13～20 属于组 1，Pin 21 属于组 2。
$bottomPins = @(
    @{ Text = '13 PA3'; X = 960; Y = 720; PadX = 1097; Group = 'G1' }
    @{ Text = '14 PA4'; X = 915; Y = 750; PadX = 1052; Group = 'G1' }
    @{ Text = '15 PA5'; X = 870; Y = 720; PadX = 1007; Group = 'G1' }
    @{ Text = '16 PA6'; X = 825; Y = 750; PadX = 962; Group = 'G1' }
    @{ Text = '17 PA7'; X = 780; Y = 720; PadX = 917; Group = 'G1' }
    @{ Text = '18 PB0'; X = 735; Y = 750; PadX = 870; Group = 'G1' }
    @{ Text = '19 PB1'; X = 690; Y = 720; PadX = 824; Group = 'G1' }
    @{ Text = '20 PB2'; X = 645; Y = 750; PadX = 779; Group = 'G1' }
    @{ Text = '21 PB10'; X = 600; Y = 720; PadX = 735; Group = 'G2' }
)
foreach ($pin in $bottomPins) {
    Draw-Label $graphics $pin.Text $pin.X $pin.Y 76 21 $pin.PadX 809 $pin.Group
}

# 左边：Pin 25～28 属于组 2，Pin 29～34 属于组 1。
$leftPins = @(
    @{ Text = '25 PB12'; PadY = 240; Group = 'G2' }
    @{ Text = '26 PB13'; PadY = 289; Group = 'G2' }
    @{ Text = '27 PB14'; PadY = 336; Group = 'G2' }
    @{ Text = '28 PB15'; PadY = 382; Group = 'G2' }
    @{ Text = '29 PA8'; PadY = 428; Group = 'G1' }
    @{ Text = '30 PA9'; PadY = 475; Group = 'G1' }
    @{ Text = '31 PA10'; PadY = 521; Group = 'G1' }
    @{ Text = '32 PA11'; PadY = 568; Group = 'G1' }
    @{ Text = '33 PA12'; PadY = 614; Group = 'G1' }
    @{ Text = '34 PA13'; PadY = 660; Group = 'G1' }
)
foreach ($pin in $leftPins) {
    Draw-Label $graphics $pin.Text 561 ($pin.PadY - 11) 78 22 542 $pin.PadY $pin.Group
}

# 右边：Pin 37～38 属于组 1，Pin 39～43、45～46 属于组 2。
$rightPins = @(
    @{ Text = '37 PA14'; PadY = 240; Group = 'G1' }
    @{ Text = '38 PA15'; PadY = 289; Group = 'G1' }
    @{ Text = '39 PB3'; PadY = 336; Group = 'G2' }
    @{ Text = '40 PB4'; PadY = 382; Group = 'G2' }
    @{ Text = '41 PB5'; PadY = 428; Group = 'G2' }
    @{ Text = '42 PB6'; PadY = 475; Group = 'G2' }
    @{ Text = '43 PB7'; PadY = 521; Group = 'G2' }
    @{ Text = '45 PB8'; PadY = 614; Group = 'G2' }
    @{ Text = '46 PB9'; PadY = 660; Group = 'G2' }
)
foreach ($pin in $rightPins) {
    Draw-Label $graphics $pin.Text 1020 ($pin.PadY - 11) 82 22 1147 $pin.PadY $pin.Group
}

# 中央图例同时说明功能编号。
$legendRect = New-Object System.Drawing.Rectangle(680, 400, 330, 145)
$graphics.FillRectangle((New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(230, 255, 255, 255))), $legendRect)
$graphics.DrawRectangle((New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(150, 80, 80, 80), 1)), $legendRect)
$graphics.DrawString('HC32F460JEUA UART PIN MAP', $legendFont, [System.Drawing.Brushes]::Black, 700, 412)
$graphics.DrawString('BLUE   USART1: TX F32  RX F33', $font, $group1Brush, 700, 445)
$graphics.DrawString('BLUE   USART2: TX F36  RX F37', $font, $group1Brush, 700, 467)
$graphics.DrawString('GREEN USART3: TX F32  RX F33', $font, $group2Brush, 700, 495)
$graphics.DrawString('GREEN USART4: TX F36  RX F37', $font, $group2Brush, 700, 517)

$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}

$bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)

$graphics.Dispose()
$bitmap.Dispose()
$source.Dispose()
$font.Dispose()
$legendFont.Dispose()
$boxFill.Dispose()
$group1Brush.Dispose()
$group2Brush.Dispose()
$group1Pen.Dispose()
$group2Pen.Dispose()

Write-Output "output=$OutputPath"
Write-Output 'group1=19'
Write-Output 'group2=14'
