# Organizador de Peliculas 5.0 - Windows PowerShell 5.1 / WPF
# No requiere privilegios de administrador. Todas las eliminaciones van a Papelera.
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

$videoExt = @('.mp4','.mkv','.avi','.mov','.wmv','.m4v','.mpg','.mpeg','.ts','.webm','.flv','.3gp')
$subExt = @('.srt','.sub','.txt','.ass','.ssa','.vtt','.spa')
$script:root = $null
$script:folders = @()
$script:pairs = @()
$script:singles = @()
$script:issues = @()
$script:extras = @()
$script:log = [System.Collections.Generic.List[object]]::new()
$script:busy = $false
$script:historyPath = $null
$script:reportPath = $null
$script:scanReady = $false

[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Organizador de Películas 5.2 - Edición clara" Width="1100" Height="790" MinWidth="850" MinHeight="620" WindowStartupLocation="CenterScreen" Background="#F3F6FB" Foreground="#26364D" FontFamily="Segoe UI" FontSize="13">
 <Window.Resources>
  <SolidColorBrush x:Key="Panel" Color="#FFFFFF"/>
  <Style TargetType="Button"><Setter Property="Background" Value="#E5EBF3"/><Setter Property="Foreground" Value="#172B4D"/><Setter Property="BorderThickness" Value="0"/><Setter Property="Padding" Value="13,8"/><Setter Property="Margin" Value="4"/><Setter Property="Cursor" Value="Hand"/><Setter Property="MinHeight" Value="36"/><Style.Triggers><Trigger Property="IsEnabled" Value="False"><Setter Property="Opacity" Value="0.35"/></Trigger></Style.Triggers></Style>
  <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#26364D"/></Style>
  <Style TargetType="DataGridColumnHeader"><Setter Property="Background" Value="#E8F0FC"/><Setter Property="Foreground" Value="#172B4D"/><Setter Property="FontWeight" Value="SemiBold"/><Setter Property="Padding" Value="10,9"/><Setter Property="BorderBrush" Value="#D5E0EF"/><Setter Property="BorderThickness" Value="0,0,1,1"/></Style>
  <Style TargetType="DataGridRow"><Setter Property="Foreground" Value="#26364D"/><Setter Property="BorderThickness" Value="0"/></Style>
  <Style TargetType="DataGridCell"><Setter Property="Foreground" Value="#26364D"/><Setter Property="BorderThickness" Value="0"/><Setter Property="Padding" Value="6,5"/></Style>
  <Style TargetType="DataGrid"><Setter Property="Background" Value="#FFFFFF"/><Setter Property="Foreground" Value="#26364D"/><Setter Property="RowBackground" Value="#FFFFFF"/><Setter Property="AlternatingRowBackground" Value="#F1F5FA"/><Setter Property="BorderThickness" Value="0"/><Setter Property="GridLinesVisibility" Value="None"/><Setter Property="HeadersVisibility" Value="Column"/><Setter Property="CanUserAddRows" Value="False"/><Setter Property="IsReadOnly" Value="True"/><Setter Property="AutoGenerateColumns" Value="False"/><Setter Property="SelectionMode" Value="Extended"/><Setter Property="Margin" Value="0,8,0,8"/></Style>
  <Style TargetType="CheckBox"><Setter Property="Foreground" Value="#26364D"/><Setter Property="Margin" Value="5"/></Style>
  <Style TargetType="TabItem"><Setter Property="Foreground" Value="#172B4D"/><Setter Property="Background" Value="#E8F0FC"/><Setter Property="Padding" Value="14,9"/></Style>
 </Window.Resources>
 <DockPanel Margin="20">
  <StackPanel DockPanel.Dock="Top">
   <TextBlock Text="ORGANIZADOR DE PELÍCULAS" FontSize="26" FontWeight="Bold" Foreground="#2457A6"/>
   <TextBlock Text="Versión 5.2  ·  Análisis, renombramiento y limpieza con control previo" Foreground="#61738D" Margin="0,4,0,14"/>
   <Border Background="#FFFFFF" CornerRadius="10" Padding="12" Margin="0,0,0,12"><DockPanel>
     <Button x:Name="Browse" DockPanel.Dock="Right" Content="Elegir carpeta..." Background="#2457A6" Foreground="White"/>
     <TextBlock x:Name="PathText" Text="Ninguna carpeta seleccionada" TextTrimming="CharacterEllipsis" VerticalAlignment="Center" Foreground="#334155"/>
   </DockPanel></Border>
   <UniformGrid Columns="4" Margin="0,0,0,10">
    <Border Background="#FFFFFF" CornerRadius="9" Margin="3" Padding="12"><StackPanel><TextBlock Text="CARPETAS" Foreground="#61738D"/><TextBlock x:Name="CountFolders" Text="0" FontSize="28" FontWeight="Bold"/></StackPanel></Border>
    <Border Background="#FFFFFF" CornerRadius="9" Margin="3" Padding="12"><StackPanel><TextBlock Text="PARES VÁLIDOS" Foreground="#61738D"/><TextBlock x:Name="CountPairs" Text="0" FontSize="28" FontWeight="Bold"/></StackPanel></Border>
    <Border Background="#FFFFFF" CornerRadius="9" Margin="3" Padding="12"><StackPanel><TextBlock Text="SOLO VIDEO" Foreground="#61738D"/><TextBlock x:Name="CountSingles" Text="0" FontSize="28" FontWeight="Bold"/></StackPanel></Border>
    <Border Background="#FFFFFF" CornerRadius="9" Margin="3" Padding="12"><StackPanel><TextBlock Text="OTROS ARCHIVOS" Foreground="#61738D"/><TextBlock x:Name="CountExtras" Text="0" FontSize="28" FontWeight="Bold"/></StackPanel></Border>
   </UniformGrid>
  </StackPanel>
  <StackPanel DockPanel.Dock="Bottom" Margin="0,10,0,0">
   <ProgressBar x:Name="Progress" Height="8" Minimum="0" Maximum="100" Value="0" Foreground="#3B82F6" Background="#E5EBF3"/>
   <DockPanel Margin="0,8,0,0"><TextBlock x:Name="Status" Text="Seleccioná una carpeta para comenzar." Foreground="#61738D"/><Button x:Name="OpenReport" DockPanel.Dock="Right" Content="Abrir carpeta de informes" IsEnabled="False"/></DockPanel>
  </StackPanel>
  <TabControl x:Name="Tabs" Background="#F3F6FB" BorderThickness="0">
   <TabItem Header="1 · Renombrar pares"><DockPanel Margin="8">
    <StackPanel DockPanel.Dock="Top"><TextBlock Text="Un video y uno o dos subtítulos: el segundo subtítulo recibe el sufijo 1." TextWrapping="Wrap" Margin="0,8"/><StackPanel Orientation="Horizontal"><Button x:Name="RenamePairs" Content="Renombrar pares válidos (confirmar)" Background="#2457A6" Foreground="White" IsEnabled="False"/><Button x:Name="Refresh" Content="Volver a analizar" IsEnabled="False"/><Button x:Name="LowercaseAll" Content="Convertir todo a minúsculas..." Background="#18794E" Foreground="White" IsEnabled="False"/></StackPanel></StackPanel>
    <DataGrid x:Name="PairGrid"><DataGrid.Columns><DataGridTextColumn Header="Carpeta" Binding="{Binding Folder}" Width="2*"/><DataGridTextColumn Header="Video actual" Binding="{Binding Video}" Width="2*"/><DataGridTextColumn Header="Subtítulos actuales" Binding="{Binding Subtitle}" Width="2*"/><DataGridTextColumn Header="Estado" Binding="{Binding State}" Width="*"/></DataGrid.Columns></DataGrid>
   </DockPanel></TabItem>
   <TabItem Header="2 · Solo video"><DockPanel Margin="8">
    <StackPanel DockPanel.Dock="Top"><TextBlock Text="Carpetas con exactamente un video y sin subtítulos. Elegí una modalidad." Margin="0,8"/><WrapPanel><Button x:Name="RenameAllSingles" Content="Renombrar todos (confirmar)" Background="#2457A6" Foreground="White" IsEnabled="False"/><Button x:Name="ReviewSingles" Content="Revisar uno por uno" IsEnabled="False"/><Button x:Name="SkipSingles" Content="Omitir todos" IsEnabled="False"/></WrapPanel></StackPanel>
    <DataGrid x:Name="SingleGrid"><DataGrid.Columns><DataGridTextColumn Header="Carpeta" Binding="{Binding Folder}" Width="2*"/><DataGridTextColumn Header="Video actual" Binding="{Binding Video}" Width="2*"/><DataGridTextColumn Header="Nombre propuesto" Binding="{Binding Proposed}" Width="2*"/><DataGridTextColumn Header="Estado" Binding="{Binding State}" Width="*"/></DataGrid.Columns></DataGrid>
   </DockPanel></TabItem>
   <TabItem Header="3 · Limpieza"><DockPanel Margin="8">
    <StackPanel DockPanel.Dock="Top"><TextBlock Text="Archivos no reconocidos como video o subtítulo. Todas las extensiones comienzan desmarcadas. Ordená haciendo clic en una columna." TextWrapping="Wrap" Margin="0,8"/><WrapPanel><Button x:Name="SelectAll" Content="Seleccionar todas" IsEnabled="False"/><Button x:Name="ClearAll" Content="Desmarcar todas" IsEnabled="False"/><Button x:Name="Recycle" Content="Enviar seleccionados a Papelera..." Background="#B45309" Foreground="White" IsEnabled="False"/></WrapPanel><TextBlock x:Name="SelectedSummary" Text="0 archivos seleccionados" Foreground="#2457A6" Margin="4,7"/></StackPanel>
    <DataGrid x:Name="ExtraGrid" IsReadOnly="False"><DataGrid.Columns><DataGridCheckBoxColumn Header="Elegir" Binding="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" Width="65"/><DataGridTextColumn Header="Extensión" Binding="{Binding Extension}" IsReadOnly="True" Width="*"/><DataGridTextColumn Header="Cantidad" Binding="{Binding Count}" IsReadOnly="True" Width="*"/><DataGridTextColumn Header="Tamaño total (MB)" Binding="{Binding Megabytes}" IsReadOnly="True" Width="*"/></DataGrid.Columns></DataGrid>
   </DockPanel></TabItem>
   <TabItem Header="4 · Incidencias"><DockPanel Margin="8"><TextBlock DockPanel.Dock="Top" Text="Las carpetas ambiguas no se modifican automáticamente." Margin="0,8"/><DataGrid x:Name="IssueGrid"><DataGrid.Columns><DataGridTextColumn Header="Carpeta" Binding="{Binding Folder}" Width="2*"/><DataGridTextColumn Header="Motivo" Binding="{Binding Reason}" Width="3*"/></DataGrid.Columns></DataGrid></DockPanel></TabItem>
  </TabControl>
 </DockPanel>
</Window>
'@
try {
 $reader = [System.Xml.XmlNodeReader]::new($xaml)
 $window = [Windows.Markup.XamlReader]::Load($reader)
} catch {
 $detail = $_ | Out-String
 $logPath = Join-Path $PSScriptRoot 'Error_Inicio_Organizador.txt'
 [IO.File]::WriteAllText($logPath, $detail, [Text.Encoding]::UTF8)
 [System.Windows.MessageBox]::Show("No se pudo iniciar el Organizador. Detalle guardado en:`n$logPath`n`n$($_.Exception.Message)", 'Error de inicio') | Out-Null
 return
}
$names = @('Browse','PathText','CountFolders','CountPairs','CountSingles','CountExtras','Progress','Status','OpenReport','Tabs','RenamePairs','Refresh','LowercaseAll','PairGrid','RenameAllSingles','ReviewSingles','SkipSingles','SingleGrid','SelectAll','ClearAll','Recycle','SelectedSummary','ExtraGrid','IssueGrid')
foreach ($name in $names) { Set-Variable -Name $name -Value $window.FindName($name) -Scope Script }

function Ask($message, $title='Confirmación') {
 return ([System.Windows.MessageBox]::Show($window,$message,$title,[System.Windows.MessageBoxButton]::YesNo,[System.Windows.MessageBoxImage]::Question) -eq [System.Windows.MessageBoxResult]::Yes)
}
function Info($message, $title='Organizador de películas') { [void][System.Windows.MessageBox]::Show($window,$message,$title,[System.Windows.MessageBoxButton]::OK,[System.Windows.MessageBoxImage]::Information) }
function Pump { $window.Dispatcher.Invoke([action]{},[System.Windows.Threading.DispatcherPriority]::Background) }
function SetProgress($index,$total,$label) {
 $Progress.Value = if($total -gt 0){[math]::Round(100*$index/$total)}else{100}
 $Status.Text = $label
 if(($index % 12) -eq 0 -or $index -eq $total){ Pump }
}
function Record($action,$source,$destination,$state,$detail='') {
 $script:log.Add([pscustomobject]@{Fecha=(Get-Date).ToString('s');Accion=$action;Origen=$source;Destino=$destination;Estado=$state;Detalle=$detail})
}
function SafeRename($source,$destination) {
 if([string]::Equals($source,$destination,[StringComparison]::Ordinal)){return 'SIN CAMBIOS'}
 if([string]::Equals($source,$destination,[StringComparison]::OrdinalIgnoreCase)){return (RenameCaseOnly $source ([IO.Path]::GetFileName($destination)))}
 if(Test-Path -LiteralPath $destination){return 'CONFLICTO: destino existente'}
 try {
  Rename-Item -LiteralPath $source -NewName ([IO.Path]::GetFileName($destination)) -ErrorAction Stop
  Record 'RENOMBRAR' $source $destination 'OK'
  return 'RENOMBRADO'
 } catch {Record 'RENOMBRAR' $source $destination 'ERROR' $_.Exception.Message; return "ERROR: $($_.Exception.Message)"}
}
function IsProtected($file) {
 $n = $file.Name
 return (($file.Attributes -band [IO.FileAttributes]::Hidden) -ne 0 -or ($file.Attributes -band [IO.FileAttributes]::System) -ne 0 -or $n -match '^Informe_Peliculas_.*\.csv$' -or $n -match '^Historial_Renombramientos_.*\.csv$' -or $n -in @('Organizador_Peliculas.ps1','Organizador_Peliculas.bat'))
}
# Los archivos sin extension solo se consideran subtitulos si su contenido parece un formato conocido.
function IsSubtitleFile($f) {
 if($f.Extension.ToLowerInvariant() -in $subExt){return $true}
 if($f.Extension){return $false}
 try {
  if($f.Length -gt 10MB -or $f.Length -eq 0){return $false}
  $reader=[IO.StreamReader]::new($f.FullName,$true)
  try { $buffer=New-Object char[] 2048; $n=$reader.Read($buffer,0,$buffer.Length); $sample=-join $buffer[0..([math]::Max(0,$n-1))] }
  finally {$reader.Dispose()}
  return ($sample -match '(?m)^\s*\d+\s*\r?\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->' -or $sample -match '(?m)^WEBVTT' -or $sample -match '(?m)^\[Script Info\]' -or $sample -match '(?m)^Dialogue:')
 } catch {return $false}
}
function DestinationOccupied($dest,$sources) {
 if(-not (Test-Path -LiteralPath $dest)){return $false}
 foreach($src in $sources){if([string]::Equals($dest,$src,[StringComparison]::OrdinalIgnoreCase)){return $false}}
 return $true
}
function Analyze {
 if(-not $script:root){return}
 $script:scanReady=$false
 $script:pairs=@();$script:singles=@();$script:issues=@();$script:extras=@()
 $RenamePairs.IsEnabled=$false;$LowercaseAll.IsEnabled=$false;$RenameAllSingles.IsEnabled=$false;$ReviewSingles.IsEnabled=$false;$SkipSingles.IsEnabled=$false;$Recycle.IsEnabled=$false
 $Status.Text='Analizando carpetas...';$Progress.Value=0;Pump
 try {
  $dirs = @([IO.DirectoryInfo](Get-Item -LiteralPath $script:root -ErrorAction Stop))
  $dirs += @(Get-ChildItem -LiteralPath $script:root -Directory -Recurse -ErrorAction Stop)
  $script:folders=$dirs
  $extraFiles=[System.Collections.Generic.List[object]]::new()
  $i=0
  foreach($dir in $dirs){
   $i++
   $files=@(Get-ChildItem -LiteralPath $dir.FullName -File -ErrorAction Stop)
   $vid=@($files | Where-Object { $_.Extension.ToLowerInvariant() -in $videoExt })
   $subs=@($files | Where-Object { IsSubtitleFile $_ } | Sort-Object Name)
   foreach($f in $files){if($f.Extension.ToLowerInvariant() -notin $videoExt -and -not (IsSubtitleFile $f) -and -not (IsProtected $f)){$extraFiles.Add($f)}}
   if($vid.Count -eq 0 -and $subs.Count -eq 0){continue}
   if($vid.Count -eq 1 -and $subs.Count -ge 1 -and $subs.Count -le 2){
    $dv=Join-Path $dir.FullName ($dir.Name+$vid[0].Extension)
    $subMoves=@()
    for($j=0;$j -lt $subs.Count;$j++){
     $suffix=if($j -eq 0){''}else{'1'}
     $ext=$subs[$j].Extension
     # Si el archivo no tiene extension y se reconocio su estructura SRT, usar .srt.
     if(-not $ext){$ext='.srt'}
     $subMoves+= [pscustomobject]@{Source=$subs[$j].FullName;Dest=(Join-Path $dir.FullName ($dir.Name+$suffix+$ext))}
    }
    $allSources=@($vid[0].FullName)+@($subMoves | ForEach-Object {$_.Source})
    $allDestinations=@($dv)+@($subMoves | ForEach-Object {$_.Dest})
    $unique=@($allDestinations | Select-Object -Unique)
    $conflict=($unique.Count -ne $allDestinations.Count)
    foreach($dest in $allDestinations){if(DestinationOccupied $dest $allSources){$conflict=$true}}
    if($conflict){$script:issues+= [pscustomobject]@{Folder=$dir.FullName;Reason='Nombre de destino ocupado o destinos duplicados'};continue}
    $correct=([string]::Equals($vid[0].FullName,$dv,[StringComparison]::Ordinal))
    foreach($m in $subMoves){if(-not [string]::Equals($m.Source,$m.Dest,[StringComparison]::Ordinal)){$correct=$false}}
    $state=if($correct){'Correcto'}else{'Pendiente'}
    $script:pairs += [pscustomobject]@{Folder=$dir.FullName;Video=$vid[0].Name;Subtitle=(($subs|ForEach-Object {$_.Name}) -join ' | ');VideoPath=$vid[0].FullName;VideoDest=$dv;SubMoves=$subMoves;State=$state}
   } elseif($vid.Count -eq 1 -and $subs.Count -eq 0){
    $dv=Join-Path $dir.FullName ($dir.Name+$vid[0].Extension)
    if((Test-Path -LiteralPath $dv) -and ($dv -cne $vid[0].FullName)){$script:issues += [pscustomobject]@{Folder=$dir.FullName;Reason='Nombre de destino ocupado'};continue}
    $script:singles += [pscustomobject]@{Folder=$dir.FullName;Video=$vid[0].Name;Proposed=([IO.Path]::GetFileName($dv));VideoPath=$vid[0].FullName;Dest=$dv;State=$(if($vid[0].FullName -ceq $dv){'Correcto'}else{'Pendiente'})}
   } else {$script:issues += [pscustomobject]@{Folder=$dir.FullName;Reason="Videos: $($vid.Count); subtítulos: $($subs.Count)"}}
   SetProgress $i $dirs.Count "Analizando $i de $($dirs.Count) carpetas..."
  }
  $script:extras=@($extraFiles.ToArray())
  $groupRows=[System.Collections.ObjectModel.ObservableCollection[object]]::new()
  foreach($group in ($script:extras | Group-Object {if($_.Extension){$_.Extension.ToUpperInvariant()}else{'(SIN EXTENSIÓN)'}} | Sort-Object Name)){
   $sum=($group.Group | Measure-Object -Property Length -Sum).Sum
   $groupRows.Add([pscustomobject]@{Selected=$false;Extension=$group.Name;Count=$group.Count;Megabytes=[math]::Round($sum/1MB,3);Bytes=$sum})
  }
  $PairGrid.ItemsSource=@($script:pairs);$SingleGrid.ItemsSource=@($script:singles);$IssueGrid.ItemsSource=@($script:issues);$ExtraGrid.ItemsSource=$groupRows
  $CountFolders.Text=[string]$dirs.Count;$CountPairs.Text=[string]$script:pairs.Count;$CountSingles.Text=[string]$script:singles.Count;$CountExtras.Text=[string]$script:extras.Count
  $RenamePairs.IsEnabled=(@($script:pairs|Where-Object State -eq 'Pendiente').Count -gt 0)
  $RenameAllSingles.IsEnabled=($script:singles.Count -gt 0);$ReviewSingles.IsEnabled=$RenameAllSingles.IsEnabled;$SkipSingles.IsEnabled=$RenameAllSingles.IsEnabled
  $SelectAll.IsEnabled=($groupRows.Count -gt 0);$ClearAll.IsEnabled=$SelectAll.IsEnabled;$Recycle.IsEnabled=$SelectAll.IsEnabled
  $script:scanReady=$true
  $LowercaseAll.IsEnabled=$true
  UpdateSelected
  $Status.Text="Análisis finalizado. $($dirs.Count) carpetas; $($script:issues.Count) incidencias."
  $Progress.Value=100
 } catch { $Status.Text='Error durante el análisis'; Info "No se pudo completar el análisis:`n$($_.Exception.Message)" 'Error' }
}
function UpdateSelected {
 $ExtraGrid.CommitEdit([System.Windows.Controls.DataGridEditingUnit]::Cell,$true) | Out-Null
 $ExtraGrid.CommitEdit([System.Windows.Controls.DataGridEditingUnit]::Row,$true) | Out-Null
 $rows=@($ExtraGrid.ItemsSource | Where-Object {$_.Selected})
 $num=($rows|Measure-Object -Property Count -Sum).Sum
 $bytes=($rows|Measure-Object -Property Bytes -Sum).Sum
 $SelectedSummary.Text="$([int]$num) archivos seleccionados · $([math]::Round($bytes/1MB,2)) MB"
}
function RenamePairBatch {
 $pending=@($script:pairs|Where-Object State -eq 'Pendiente')
 if(-not $pending.Count){Info 'No hay pares pendientes.';return}
 if(-not (Ask "Se renombrarán $($pending.Count) carpetas con video y uno o dos subtítulos (hasta $($pending.Count*3) archivos).`n`n¿Continuar?" 'Confirmar renombramiento')){return}
 $i=0
 foreach($p in $pending){
  $i++
  $v=SafeRename $p.VideoPath $p.VideoDest
  $subResults=@()
  foreach($move in $p.SubMoves){$subResults+=SafeRename $move.Source $move.Dest}
  $p.State="$v / $($subResults -join ' / ')"
  SetProgress $i $pending.Count "Renombrando pares $i de $($pending.Count)..."
 }
 SaveReports
 Analyze
 Info 'Renombramiento de pares finalizado. Revisá las incidencias y el informe.'
}
function RenameSingles($individual){
 $pending=@($script:singles|Where-Object State -eq 'Pendiente')
 if(-not $pending.Count){Info 'No hay videos pendientes de renombrar.';return}
 if(-not $individual -and -not (Ask "Se renombrarán $($pending.Count) videos sin subtítulos.`n`n¿Continuar con todo el lote?" 'Confirmar lote')){return}
 $i=0
 foreach($p in $pending){
  $i++
  if($individual -and -not (Ask "Carpeta: $($p.Folder)`n`nActual: $($p.Video)`nNuevo: $($p.Proposed)`n`n¿Renombrar este video?" 'Revisión individual')){Record 'OMITIR' $p.VideoPath '' 'OMITIDO';continue}
  $p.State=SafeRename $p.VideoPath $p.Dest
  SetProgress $i $pending.Count "Videos sin subtítulos $i de $($pending.Count)..."
 }
 SaveReports; Analyze; Info 'Revisión de videos sin subtítulos finalizada.'
}
function SaveReports {
 if(-not $script:root){return}
 try {
  $dir=Join-Path $script:root '_Informes_Organizador'
  if(-not (Test-Path -LiteralPath $dir)){[void](New-Item -ItemType Directory -Path $dir -ErrorAction Stop)}
  $stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fff'
  $script:reportPath=Join-Path $dir "Informe_Peliculas_$stamp.csv"
  $script:historyPath=Join-Path $dir "Historial_Renombramientos_$stamp.csv"
  @($script:log.ToArray()) | Export-Csv -LiteralPath $script:historyPath -NoTypeInformation -Delimiter ';' -Encoding UTF8
  $rows=[System.Collections.Generic.List[object]]::new()
  foreach($p in $script:pairs){$rows.Add([pscustomobject]@{Carpeta=$p.Folder;Categoria='Par';Estado=$p.State;Detalle="$($p.Video) | $($p.Subtitle)"})}
  foreach($p in $script:singles){$rows.Add([pscustomobject]@{Carpeta=$p.Folder;Categoria='Solo video';Estado=$p.State;Detalle=$p.Video})}
  foreach($p in $script:issues){$rows.Add([pscustomobject]@{Carpeta=$p.Folder;Categoria='Incidencia';Estado='REVISAR';Detalle=$p.Reason})}
  $rows.ToArray() | Export-Csv -LiteralPath $script:reportPath -NoTypeInformation -Delimiter ';' -Encoding UTF8
  $OpenReport.IsEnabled=$true
 }catch{Info "No se pudo guardar el informe: $($_.Exception.Message)" 'Advertencia'}
}
function RecycleSelected {
 UpdateSelected
 $chosen=@($ExtraGrid.ItemsSource | Where-Object {$_.Selected} | ForEach-Object {$_.Extension})
 if(-not $chosen.Count){Info 'Seleccioná una o más extensiones.';return}
 $selectedFiles=@($script:extras | Where-Object {$e=if($_.Extension){$_.Extension.ToUpperInvariant()}else{'(SIN EXTENSIÓN)'}; $e -in $chosen})
 $total=($selectedFiles|Measure-Object -Property Length -Sum).Sum
 $preview=($chosen -join ', ')
 if(-not (Ask "Extensiones: $preview`nArchivos: $($selectedFiles.Count)`nTamaño total: $([math]::Round($total/1MB,2)) MB`n`nSe enviarán a la Papelera de reciclaje (no se borrarán definitivamente).`n`n¿CONFIRMÁS la eliminación del lote?" 'Confirmación final de limpieza')){return}
 $i=0;$ok=0;$fail=0
 foreach($f in $selectedFiles){
  $i++
  try {
   [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($f.FullName,[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)
   Record 'PAPELERA' $f.FullName '' 'OK';$ok++
  }catch{Record 'PAPELERA' $f.FullName '' 'ERROR' $_.Exception.Message;$fail++}
  SetProgress $i $selectedFiles.Count "Limpieza $i de $($selectedFiles.Count)..."
 }
 SaveReports;Analyze;Info "Limpieza finalizada.`nEnviados a Papelera: $ok`nErrores: $fail"
}


# Convierte todos los nombres dentro de la carpeta elegida, sin modificar la carpeta raiz.
# Se procesan primero los archivos y luego los directorios, de mayor a menor profundidad.
# El cambio de nombre en dos pasos resuelve las diferencias exclusivas de mayusculas/minusculas.
function RenameCaseOnly($source, $newName) {
 $parent=[IO.Path]::GetDirectoryName($source)
 $target=Join-Path $parent $newName
 $oldName=[IO.Path]::GetFileName($source)
 if([string]::Equals($oldName,$newName,[StringComparison]::Ordinal)){return 'SIN CAMBIOS'}
 if(-not [string]::Equals($oldName,$newName,[StringComparison]::OrdinalIgnoreCase)){
  if(Test-Path -LiteralPath $target){return 'CONFLICTO: destino existente'}
  try {Rename-Item -LiteralPath $source -NewName $newName -ErrorAction Stop; Record 'MINUSCULAS' $source $target 'OK';return 'RENOMBRADO'}
  catch {Record 'MINUSCULAS' $source $target 'ERROR' $_.Exception.Message;return 'ERROR'}
 }
 $temporary=$null
 for($attempt=0;$attempt -lt 20;$attempt++){
  $candidate='.__organizador_tmp_'+[guid]::NewGuid().ToString('N')
  $tempPath=Join-Path $parent $candidate
  if(-not (Test-Path -LiteralPath $tempPath)){$temporary=$candidate;break}
 }
 if(-not $temporary){Record 'MINUSCULAS' $source $target 'ERROR' 'No se pudo reservar nombre temporal';return 'ERROR'}
 try {
  Rename-Item -LiteralPath $source -NewName $temporary -ErrorAction Stop
  try {
   Rename-Item -LiteralPath (Join-Path $parent $temporary) -NewName $newName -ErrorAction Stop
   Record 'MINUSCULAS' $source $target 'OK'
   return 'RENOMBRADO'
  } catch {
   $message=$_.Exception.Message
   try {Rename-Item -LiteralPath (Join-Path $parent $temporary) -NewName $oldName -ErrorAction Stop} catch {$message += '; No se pudo restaurar el nombre original: '+$_.Exception.Message}
   Record 'MINUSCULAS' $source $target 'ERROR' $message
   return 'ERROR'
  }
 } catch {Record 'MINUSCULAS' $source $target 'ERROR' $_.Exception.Message;return 'ERROR'}
}
function ConvertAllToLowercase {
 if(-not $script:root -or -not $script:scanReady){return}
 try {
  # No se recorren carpetas de informes ni enlaces simbolicos o puntos de union.
  $dirs=[System.Collections.Generic.List[object]]::new()
  $files=[System.Collections.Generic.List[object]]::new()
  $pending=[System.Collections.Generic.Stack[string]]::new()
  $pending.Push($script:root)
  while($pending.Count -gt 0){
   $current=$pending.Pop()
   foreach($entry in @(Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop)){
    if(($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){continue}
    if(($entry.Attributes -band [IO.FileAttributes]::Hidden) -ne 0 -or ($entry.Attributes -band [IO.FileAttributes]::System) -ne 0){continue}
    if($entry.PSIsContainer){
     if($entry.Name -ieq '_Informes_Organizador'){continue}
     $dirs.Add($entry)
     $pending.Push($entry.FullName)
    } elseif(-not (IsProtected $entry)){$files.Add($entry)}
   }
  }
  $fileJobs=@($files.ToArray() | Where-Object {$_.Name -cne $_.Name.ToLowerInvariant()})
  $dirJobs=@($dirs.ToArray() | Where-Object {$_.Name -cne $_.Name.ToLowerInvariant()} | Sort-Object @{Expression={$_.FullName.Length};Descending=$true})
  $count=$fileJobs.Count+$dirJobs.Count
  if($count -eq 0){Info 'Todos los nombres de carpetas y archivos ya están en minúsculas.';return}
  $question="Se convertirán a minúsculas:`n`nCarpetas: $($dirJobs.Count)`nArchivos: $($fileJobs.Count)`nTotal: $count`n`nSe conservarán las extensiones, tildes y eñes. No se modificará la carpeta principal elegida, los informes ni los archivos protegidos.`n`n¿Ejecutar la conversión automática?"
  if(-not (Ask $question 'Confirmar conversión a minúsculas')){return}
  $LowercaseAll.IsEnabled=$false
  $ok=0;$errors=0;$done=0
  foreach($entry in $fileJobs){
   $result=RenameCaseOnly $entry.FullName ($entry.Name.ToLowerInvariant())
   if($result -eq 'RENOMBRADO'){$ok++}else{$errors++}
   $done++;SetProgress $done $count "Convirtiendo archivos: $done de $count..."
  }
  foreach($entry in $dirJobs){
   $result=RenameCaseOnly $entry.FullName ($entry.Name.ToLowerInvariant())
   if($result -eq 'RENOMBRADO'){$ok++}else{$errors++}
   $done++;SetProgress $done $count "Convirtiendo carpetas: $done de $count..."
  }
  SaveReports
  Analyze
  Info "Conversión finalizada.`nNombres convertidos: $ok`nErrores o conflictos: $errors`n`nLos resultados se registraron en el historial."
 } catch {
  Record 'MINUSCULAS' $script:root '' 'ERROR' $_.Exception.Message
  Info "No se pudo completar la conversión: $($_.Exception.Message)" 'Error'
  Analyze
 }
}

$LowercaseAll.Add_Click({ConvertAllToLowercase})
$Browse.Add_Click({
 $dlg=New-Object System.Windows.Forms.FolderBrowserDialog
 $dlg.Description='Elegí la carpeta principal de películas'
 $dlg.ShowNewFolderButton=$false
 if($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$script:root=$dlg.SelectedPath;$PathText.Text=$script:root;$script:log.Clear();Analyze}
})
$Refresh.Add_Click({Analyze})
$RenamePairs.Add_Click({RenamePairBatch})
$RenameAllSingles.Add_Click({RenameSingles $false})
$ReviewSingles.Add_Click({RenameSingles $true})
$SkipSingles.Add_Click({if(Ask '¿Omitir todos los videos sin subtítulos en esta ejecución?'){Record 'OMITIR LOTE' $script:root '' 'OMITIDO';Info 'No se modificaron los videos sin subtítulos.'}})
$SelectAll.Add_Click({foreach($r in $ExtraGrid.ItemsSource){$r.Selected=$true};$ExtraGrid.Items.Refresh();UpdateSelected})
$ClearAll.Add_Click({foreach($r in $ExtraGrid.ItemsSource){$r.Selected=$false};$ExtraGrid.Items.Refresh();UpdateSelected})
$ExtraGrid.Add_CellEditEnding({$window.Dispatcher.BeginInvoke([action]{UpdateSelected},[System.Windows.Threading.DispatcherPriority]::Background) | Out-Null})
$Recycle.Add_Click({RecycleSelected})
$OpenReport.Add_Click({if($script:root){$dir=Join-Path $script:root '_Informes_Organizador';if(Test-Path -LiteralPath $dir){Start-Process explorer.exe -ArgumentList ('"'+$dir+'"')}}})
$window.Add_Closing({if($script:root -and $script:log.Count -gt 0){SaveReports}})
[void]$window.ShowDialog()
