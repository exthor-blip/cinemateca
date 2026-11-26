# IMDB linker 4.3 - Windows PowerShell 5.1 - WPF
# Encoding: UTF-8 with BOM
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase,System.Windows.Forms
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$script:items = New-Object System.Collections.ObjectModel.ObservableCollection[object]
$script:stopRequested = $false
$script:root = ''
$script:statePath = ''
$script:state = @{}
$script:tmdbKey = [string]$env:TMDB_READ_ACCESS_TOKEN # Opcional: sin botones ni configuración obligatoria
function Normalize-Title([string]$s) {
 $s = $s.ToLowerInvariant().Normalize([Text.NormalizationForm]::FormD)
 $s = [regex]::Replace($s,'\p{Mn}','')
 $s = [regex]::Replace($s,'[^a-z0-9]+',' ')
 return $s.Trim()
}
# Los parentesis de pais/idioma son metadatos, no parte del titulo.
# No se eliminan otros parentesis (por ejemplo, subtitulos oficiales).
$script:originTags = @(
 'argentina','argentino','argentina','alemania','aleman','alemana','germany','german',
 'francia','frances','francesa','france','french','espana','espanol','espanola','spain','spanish',
 'italia','italiano','italiana','italy','italian','inglaterra','ingles','inglesa','england','english',
 'reino unido','gran bretana','uk','britanica','britanico','estados unidos','eeuu','usa','us','american',
 'canada','canadiense','mexico','mexicano','mexicana','brasil','brasileno','brasilena','brazil',
 'portugal','portugues','portuguesa','japon','japones','japonesa','japan','japanese',
 'china','chino','china','corea','coreano','coreana','korea','rusia','ruso','rusa','russia',
 'india','hindi','turquia','turco','turca','iran','irani','israel','hebreo','arabe',
 'suecia','sueco','sueca','noruega','noruego','noruega','dinamarca','danes','danesa',
 'holanda','paises bajos','neerlandes','belgica','belga','suiza','suizo','suiza',
 'australia','australiano','australiana','nueva zelanda','irlanda','irlandes',
 'polonia','polaco','polaca','grecia','griego','griega','austria','austriaco',
 'chile','chileno','chilena','uruguay','uruguayo','uruguaya','colombia','colombiano',
 'peru','peruano','peruana','venezuela','venezolano','cuba','cubano','cubana',
 'tailandia','tailandes','tailandesa','taiwan','hong kong','sudafrica',
 'frances/ingles','ingles/frances','espanol/ingles','ingles/espanol'
 )
function Remove-OriginSuffix([string]$title) {
 $clean=$title.Trim()
 # Solo quitar parentesis finales que sean claramente paises o idiomas.
 while($clean -match '\s*\(([^()]*)\)\s*$') {
  $tag=Normalize-Title $matches[1]
  if($script:originTags -notcontains $tag){break}
  $clean=($clean -replace '\s*\([^()]*\)\s*$','').Trim()
 }
 return $clean
}
function Parse-Folder([string]$name) {
 if ($name -match '^\s*((?:19|20)\d{2})\s*[-–—]\s*(.+?)\s*$') {
  $year=$matches[1]; $raw=$matches[2].Trim()
  $title=Remove-OriginSuffix $raw
  if(-not $title){$title=$raw}
  return @{ Year=$year; Title=$title }
 }
 return $null
}
function Save-State {
 if (-not $script:statePath) { return }
 try { $script:state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:statePath -Encoding UTF8 } catch { }
}
function Read-State {
 $script:state=@{}
 if (Test-Path -LiteralPath $script:statePath) {
  try { $data=Get-Content -LiteralPath $script:statePath -Raw -Encoding UTF8 | ConvertFrom-Json; if($data){ foreach($p in $data.PSObject.Properties){$script:state[$p.Name]=$p.Value} } } catch { }
 }
}
function Get-Candidates([string]$title) {
 # IMDb suggestions: the URL prefix must match the first character of the query.
 $clean=$title.Trim()
 if(-not $clean){return @()}
 $q=[uri]::EscapeDataString($clean)
 $first=([regex]::Replace($clean.ToLowerInvariant().Normalize([Text.NormalizationForm]::FormD),'\p{Mn}','')).Substring(0,1)
 if($first -notmatch '[a-z0-9]'){$first='x'}
 $url="https://v3.sg.media-imdb.com/suggestion/$first/$q.json"
 try {
  $data=Invoke-RestMethod -Uri $url -TimeoutSec 15 -Headers @{ 'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64)' } -ErrorAction Stop
  return @($data.d | Where-Object { $_.id -match '^tt\d+$' -and $_.y })
 } catch { return @() }
}
function Search-Imdb([string]$title,[string]$year) {
 # Buscar primero con ano, despues sin ano. Las sugerencias de IMDb son limitadas.
 $pool=@{}
 $queries=@("$title $year",$title,((Normalize-Title $title) -replace " "," ")) | Select-Object -Unique
 foreach($q in $queries){
  foreach($hit in @(Get-Candidates $q)){
   if($hit -and $hit.id -match '^tt\d+$'){$pool[[string]$hit.id]=$hit}
  }
 }
 $all=@($pool.Values | Where-Object { $_.y -and $_.l })
 $sameTitle=@($all | Where-Object {
  $hit=$_
  (Normalize-Title ([string]$hit.l)) -eq (Normalize-Title $title) -or
  @($hit.akas | Where-Object {(Normalize-Title ([string]$_)) -eq (Normalize-Title $title)}).Count -gt 0
 })
 $exact=@($sameTitle | Where-Object {[string]$_.y -eq $year})
 if($exact.Count -eq 1){
  if((Normalize-Title ([string]$exact[0].l)) -eq (Normalize-Title $title)){
   return @{Kind='Exact';Candidate=$exact[0];Note='Titulo principal y ano coinciden en IMDb'}
  }
  return @{Kind='Review';Candidate=$exact[0];Note='Coincidencia por título alternativo IMDb; confirmar antes de guardar'}
 }
 if($exact.Count -gt 1){return @{Kind='Review';Candidate=$exact[0];Note='Varias fichas IMDb con mismo titulo y ano; verificar'}}
 # No descartar una ficha por diferencia de ano: siempre requiere confirmacion.
 if($sameTitle.Count -gt 0){
  $best=@($sameTitle | Sort-Object @{Expression={[math]::Abs([int]$_.y-[int]$year)}})[0]
  return @{Kind='Review';Candidate=$best;Note="IMDb: mismo titulo pero ano distinto (carpeta $year, ficha $($best.y)); verificar"}
 }
 $sameYear=@($all | Where-Object {[string]$_.y -eq $year})
 # No proponer una película distinta únicamente por coincidir el año.
 return @{Kind='Missing';Candidate=$null;Note='Sin coincidencia en sugerencias IMDb; se intentaran fuentes complementarias'}
}
function Get-WikidataCandidates([string]$title,[string]$year) {
 # Wikidata helps discover original names and IMDb identifiers. Never silently approve a result.
 $found=@()
 foreach($lang in @('es','en','fr','de','it','pt','ja')) {
  try {
   $q=[uri]::EscapeDataString($title)
   $url="https://www.wikidata.org/w/api.php?action=wbsearchentities&search=$q&language=$lang&format=json&limit=8&type=item"
   $r=Invoke-RestMethod -Uri $url -TimeoutSec 14 -Headers @{'User-Agent'='Mozilla/5.0 IMDbLinker/3.8'} -ErrorAction Stop
   foreach($entry in @($r.search)) {
    if($entry.id -and @($found | Where-Object { $_.id -eq $entry.id }).Count -eq 0){$found+= $entry}
   }
  } catch { }
 }
 foreach($entry in $found) {
  try {
   $id=[string]$entry.id
   if($id -notmatch '^Q\d+$'){continue}
   $entityUrl="https://www.wikidata.org/wiki/Special:EntityData/$id.json"
   $entityResponse=Invoke-RestMethod -Uri $entityUrl -TimeoutSec 14 -ErrorAction Stop
   $entity=$entityResponse.entities.$id
   if(-not $entity){continue}
   $imdbIds=@($entity.claims.P345 | ForEach-Object { $_.mainsnak.datavalue.value } | Where-Object { $_ -match '^tt\d+$' })
   $tmdbIds=@($entity.claims.P4947 | ForEach-Object { $_.mainsnak.datavalue.value } | Where-Object { $_ -match '^\d+$' })
   $names=@($title)
   foreach($lang in @('en','es','fr','pt','de','it','ja','ko','ru','zh')) {
    if($entity.labels.$lang){$names+= [string]$entity.labels.$lang.value}
    if($entity.aliases.$lang){$names+= @($entity.aliases.$lang | ForEach-Object {$_.value})}
   }
   $names=@($names | Where-Object {$_} | Select-Object -Unique)
   # Wikidata puede devolver elementos no relacionados: exigir titulo/alias exacto
   # y verificar el ano cuando existe fecha de estreno en la entidad.
   $matchesTitle=@($names | Where-Object {(Normalize-Title ([string]$_)) -eq (Normalize-Title $title)})
   if($matchesTitle.Count -eq 0){continue}
   $releaseYears=@($entity.claims.P577 | ForEach-Object {
     if($_.mainsnak.datavalue.value.time -match '^[+-](\d{4})-'){$matches[1]}
   } | Select-Object -Unique)
   if($releaseYears.Count -gt 0 -and $year -notin $releaseYears){
    # Distintos anos pueden ser legitimos, pero nunca aprobar automaticamente.
    # Se conserva la ficha solo como propuesta de revision.
   }
   foreach($name in $names) {
    $hits=@(Get-Candidates $name | Where-Object { ($imdbIds -contains $_.id) -or (([string]$_.y -eq $year) -and ((Normalize-Title ([string]$_.l)) -eq (Normalize-Title $name))) })
    foreach($hit in $hits){
     if($imdbIds.Count -gt 0 -and $hit.id -notin $imdbIds){continue}
     return @{Kind='Review';Candidate=$hit;Note="IMDb localizado mediante título alternativo en Wikidata ($id): $name"}
    }
   }
   foreach($imdbId in $imdbIds) {
    $byId=@(Get-Candidates $imdbId | Where-Object { $_.id -eq $imdbId })
    if($byId.Count -gt 0){return @{Kind='Review';Candidate=$byId[0];Note='IMDb identificado por Wikidata; confirmar título y año'}}
    # Suggestions may not index a known IMDb identifier; retain it as review-only.
    if($imdbId -match '^tt\d+$'){
     $candidate=[pscustomobject]@{id=$imdbId;l=[string]$entry.label;y=$year;i=$null}
     return @{Kind='Review';Candidate=$candidate;Note='Identificador IMDb obtenido de Wikidata. Título y año pendientes de verificación visual.'}
    }
   }
   # A Wikidata IMDb identifier alone is not proof that the folder matches the movie.
   # An external result remains review-only, with a verifiable provider URL.
   if($tmdbIds.Count -gt 0){
    return @{Kind='External';Provider='TMDb';Url="https://www.themoviedb.org/movie/$($tmdbIds[0])";Title=[string]$entry.label;Year=$year;Poster='';Note="Posible ficha TMDb localizada en Wikidata ($id); requiere confirmación"}
   }
  } catch { }
 }
 return $null
}
function Search-Tmdb([string]$title,[string]$year) {
 if(-not $script:tmdbKey){return $null}
 try {
  $q=[uri]::EscapeDataString($title)
  $url="https://api.themoviedb.org/3/search/movie?query=$q&year=$year&include_adult=false&language=es-ES"
  $headers=@{'Authorization'="Bearer $($script:tmdbKey)";'Accept'='application/json'}
  $r=Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 18 -ErrorAction Stop
  foreach($movie in @($r.results | Select-Object -First 8)) {
   $id=[string]$movie.id
   $ext=Invoke-RestMethod -Uri "https://api.themoviedb.org/3/movie/$id/external_ids" -Headers $headers -TimeoutSec 15 -ErrorAction Stop
   if($ext.imdb_id -match '^tt\d+$') {
    $hits=@(Get-Candidates ([string]$movie.original_title) | Where-Object { $_.id -eq $ext.imdb_id })
    if($hits.Count -gt 0){return @{Kind='Review';Candidate=$hits[0];Note='Ficha IMDb localizada a través de TMDb; confirmar traducción'}}
    $candidate=[pscustomobject]@{id=[string]$ext.imdb_id;l=[string]$movie.original_title;y=([string]$movie.release_date -split '-')[0];i=$null}
    return @{Kind='Review';Candidate=$candidate;Note='Identificador IMDb recuperado de TMDb; verificar título, año y póster.'}
   }
   $poster='';if($movie.poster_path -match '^/[a-zA-Z0-9]+\.(jpg|jpeg|png)$'){$poster="https://image.tmdb.org/t/p/w500$($movie.poster_path)"}
   return @{Kind='External';Provider='TMDb';Url="https://www.themoviedb.org/movie/$id";Title=[string]$movie.title;Year=$year;Poster=$poster;Note='Ficha TMDb posible; IMDb no verificado. Requiere confirmación.'}
  }
 } catch { }
 return $null
}
function Get-WikipediaAlternates([string]$title,[string]$year) {
 $names=New-Object System.Collections.Generic.List[string]
 foreach($lang in @('es','en')) {
  try {
   $q=[uri]::EscapeDataString("$title $year film")
   $url="https://$lang.wikipedia.org/w/api.php?action=query&list=search&srsearch=$q&srlimit=5&format=json"
   $r=Invoke-RestMethod -Uri $url -TimeoutSec 12 -Headers @{'User-Agent'='Mozilla/5.0'} -ErrorAction Stop
   foreach($entry in @($r.query.search)) {
    $name=([string]$entry.title) -replace '\s*\((?:\d{4}\s+)?(?:film|película|movie|filme)\)\s*$',''
    if($name -and (Normalize-Title $name) -eq (Normalize-Title $title) -and -not $names.Contains($name)){$names.Add($name)}
   }
  } catch { }
 }
 return @($names.ToArray())
}
function Search-Multi([string]$title,[string]$year) {
 $primary=Search-Imdb $title $year
 if($primary.Kind -ne 'Missing'){return $primary}
 # Find multilingual names and IMDb identifiers in Wikidata first.
 $wiki=Get-WikidataCandidates $title $year
 if($wiki -and $wiki.Kind -eq 'Review'){return $wiki}
 # TMDb can supply an original title or IMDb identifier when a token is available.
 $tmdb=Search-Tmdb $title $year
 if($tmdb -and $tmdb.Kind -eq 'Review'){return $tmdb}
 # Wikipedia names are suggestions only, never automatic confirmations.
 foreach($alt in @(Get-WikipediaAlternates $title $year)) {
  if((Normalize-Title $alt) -eq (Normalize-Title $title)){continue}
  $found=Search-Imdb $alt $year
  if($found.Kind -in @('Exact','Review')) {
   return @{Kind='Review';Candidate=$found.Candidate;Note="Título alternativo posible en Wikipedia: $alt. Verificar que corresponda a la película antes de guardar."}
  }
 }
 if($tmdb){return $tmdb}
 if($wiki){return $wiki}
 return @{Kind='Missing';Candidate=$null;Note='Sin coincidencia verificable en las fuentes consultadas. Puede quedar pendiente de revisión.'}
}
function Write-ExternalResult($item,$saved) {
 $provider=[string]$saved.Provider
 if($provider -ne 'TMDb'){throw 'Fuente externa no admitida automáticamente.'}
 $url=[string]$saved.ExternalUrl
 if($url -notmatch '^https://www\.themoviedb\.org/movie/\d+/?$'){throw 'URL de TMDb inválida.'}
 if(Test-Path -LiteralPath (Join-Path $item.Path 'imdb.url')){throw 'Ya existe imdb.url: no se creará un enlace alternativo.'}
 $file=Join-Path $item.Path 'tmdb.url'
 if(-not (Test-Path -LiteralPath $file)) {"[InternetShortcut]`r`nURL=$url" | Set-Content -LiteralPath $file -Encoding ASCII}
 $poster=[string]$saved.Poster
 $posterFile=Join-Path $item.Path 'poster.jpg'
 if($poster -match '^https://image\.tmdb\.org/t/p/' -and -not (Test-Path -LiteralPath $posterFile)) {
  $tmp=Join-Path $item.Path ('.poster_'+[guid]::NewGuid().ToString('N')+'.tmp')
  try {
   Invoke-WebRequest -Uri $poster -OutFile $tmp -UseBasicParsing -TimeoutSec 25 -ErrorAction Stop
   $bytes=[IO.File]::ReadAllBytes($tmp)
   if($bytes.Length -gt 3 -and $bytes[0] -eq 255 -and $bytes[1] -eq 216){Move-Item -LiteralPath $tmp -Destination $posterFile -ErrorAction Stop}
  } finally {Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue}
 }
 $item.Status=if(Test-Path -LiteralPath $posterFile){'Completada'}else{'Sin póster'};$item.Detail='Ficha TMDb confirmada; IMDb no verificado';$item.Imdb=''
 $script:state[$item.Path]=@{Status=$item.Status;Detail=$item.Detail;ExternalUrl=$url;Provider=$provider;Title=$item.Title;Year=$item.Year}
 Save-State
}
function Poster-Url($candidate) {
 if($candidate -and $candidate.i -and $candidate.i.imageUrl){return [string]$candidate.i.imageUrl}
 return ''
}
function Write-Result($item,$candidate) {
 $imdbFile=Join-Path $item.Path 'imdb.url'; $posterFile=Join-Path $item.Path 'poster.jpg'
 $link="https://www.imdb.com/title/$($candidate.id)/"
 $newLink=$false; $newPoster=$false
 if(-not (Test-Path -LiteralPath $imdbFile)) {
  "[InternetShortcut]`r`nURL=$link" | Set-Content -LiteralPath $imdbFile -Encoding ASCII
  $newLink=$true
 }
 $poster=Poster-Url $candidate
 if($poster -and -not (Test-Path -LiteralPath $posterFile)) {
  try {
   $temp=Join-Path $item.Path ('poster_' + [guid]::NewGuid().ToString('N') + '.tmp')
   Invoke-WebRequest -Uri $poster -OutFile $temp -TimeoutSec 25 -UseBasicParsing -ErrorAction Stop
   $bytes=[IO.File]::ReadAllBytes($temp)
   # Only save JPEG images as poster.jpg; no extension/content mismatch.
   if($bytes.Length -gt 3 -and $bytes[0] -eq 255 -and $bytes[1] -eq 216) { Move-Item -LiteralPath $temp -Destination $posterFile -ErrorAction Stop; $newPoster=$true }
   else {Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue}
  } catch { if($temp){Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue} }
 }
 $item.Imdb=$link
 if(Test-Path -LiteralPath $imdbFile){
  if(Test-Path -LiteralPath $posterFile){$item.Status='Completada';$item.Detail='Enlace y póster presentes'}
  else {$item.Status='Sin póster';$item.Detail='Enlace guardado; póster no disponible'}
 } else {$item.Status='Error';$item.Detail='No se pudo guardar el enlace'}
 $script:state[$item.Path]=@{Status=$item.Status;Imdb=$item.Imdb;Detail=$item.Detail;Title=$item.Title;Year=$item.Year}
 Save-State
}
[xml]$xaml=@'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="IMDB linker 4.3 - Centro de control" Height="740" Width="1120" MinWidth="860" MinHeight="600" WindowStartupLocation="CenterScreen" Background="#F5F7FB" FontFamily="Segoe UI">
 <Window.Resources>
  <Style TargetType="Button"><Setter Property="Margin" Value="0,0,9,0"/><Setter Property="Padding" Value="14,9"/><Setter Property="Background" Value="#E4ECF7"/><Setter Property="Foreground" Value="#17375B"/><Setter Property="BorderThickness" Value="0"/><Setter Property="Cursor" Value="Hand"/></Style>
  <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#24354B"/></Style>
 </Window.Resources>
 <Grid Margin="22"><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
 <StackPanel Grid.Row="0" Margin="0,0,0,18"><TextBlock Text="IMDB linker 4.3" FontSize="28" FontWeight="Bold"/><TextBlock Text="Centro de control - Procesamiento masivo de películas" Foreground="#66778D" FontSize="14"/></StackPanel>
 <Border Grid.Row="1" Background="White" CornerRadius="9" Padding="16" Margin="0,0,0,14"><StackPanel><TextBlock Text="CARPETA PRINCIPAL" FontWeight="SemiBold" FontSize="12"/><DockPanel Margin="0,10,0,0"><Button x:Name="Choose" Content="Seleccionar carpeta" DockPanel.Dock="Right"/><TextBox x:Name="Folder" IsReadOnly="True" VerticalContentAlignment="Center" FontSize="14" Padding="8" BorderBrush="#DCE3EB"/></DockPanel></StackPanel></Border>
 <Border Grid.Row="2" Background="White" CornerRadius="9" Padding="16" Margin="0,0,0,14"><StackPanel><WrapPanel><Button x:Name="Scan" Content="Analizar carpetas"/><Button x:Name="Run" Content="Iniciar / reanudar"/><Button x:Name="Stop" Content="Detener"/><Button x:Name="Review" Content="Revisar pendientes"/><Button x:Name="OpenFolder" Content="Abrir carpeta"/></WrapPanel><TextBlock x:Name="Counts" Text="Seleccioná una carpeta para comenzar." FontSize="14" Margin="0,12,0,6"/><ProgressBar x:Name="Progress" Height="14" Minimum="0" Maximum="100" Value="0" Foreground="#2677C9"/><TextBlock x:Name="Message" Text="Listo." Foreground="#66778D" Margin="0,8,0,0" TextWrapping="Wrap"/></StackPanel></Border>
 <Border Grid.Row="3" Background="White" CornerRadius="9" Padding="10"><DataGrid x:Name="Results" AutoGenerateColumns="False" IsReadOnly="True" SelectionMode="Single" HeadersVisibility="Column" GridLinesVisibility="Horizontal" RowHeaderWidth="0" AlternatingRowBackground="#F3F7FC" BorderThickness="0"><DataGrid.Columns><DataGridTextColumn Header="Carpeta" Binding="{Binding Name}" Width="2*"/><DataGridTextColumn Header="Año" Binding="{Binding Year}" Width="65"/><DataGridTextColumn Header="Título" Binding="{Binding Title}" Width="2*"/><DataGridTextColumn Header="Estado" Binding="{Binding Status}" Width="120"/><DataGridTextColumn Header="Observaciones" Binding="{Binding Detail}" Width="3*"/></DataGrid.Columns></DataGrid></Border>
 <TextBlock Grid.Row="4" Text="IMDb tiene prioridad absoluta. País e idioma entre paréntesis no forman parte del título. Las coincidencias dudosas requieren confirmación." Margin="2,12,0,0" Foreground="#66778D" FontSize="12"/>
 </Grid>
</Window>
'@
$reader=[System.Xml.XmlNodeReader]::new($xaml)
try { $win=[Windows.Markup.XamlReader]::Load($reader) } finally { $reader.Close() }
$ui=@{}
foreach($n in 'Choose','Folder','Scan','Run','Stop','Review','OpenFolder','Counts','Progress','Message','Results'){$ui[$n]=$win.FindName($n)}
$ui.Results.ItemsSource=$script:items
function Refresh-Stats {
 $total=$script:items.Count
 $complete=@($script:items | Where-Object {$_.Status -eq 'Completada'}).Count
 $pending=@($script:items | Where-Object {$_.Status -in @('Revisar','Rechazada','No encontrada','Pendiente','Error','Sin póster')}).Count
 $missing=@($script:items | Where-Object {$_.Status -eq 'No encontrada'}).Count
 $ui.Counts.Text="Carpetas: $total    Completadas: $complete    Pendientes: $pending    Sin localizar: $missing"
 $done=@($script:items | Where-Object {$_.Status -notin @('Pendiente','Buscando')}).Count
 if($total -gt 0){$ui.Progress.Value=[math]::Round(100*$done/$total)}else{$ui.Progress.Value=0}
 $ui.Results.Items.Refresh()
 [System.Windows.Threading.Dispatcher]::CurrentDispatcher.Invoke([action]{},[System.Windows.Threading.DispatcherPriority]::Background)
}
$ui.Choose.Add_Click({
 $dlg=New-Object System.Windows.Forms.FolderBrowserDialog
 $dlg.Description='Seleccioná la carpeta que contiene las carpetas de películas'
 if($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$script:root=$dlg.SelectedPath;$ui.Folder.Text=$script:root;$ui.Message.Text='Carpeta seleccionada. Presioná Analizar carpetas.'}
})
$ui.Scan.Add_Click({
 if(-not $script:root){[System.Windows.MessageBox]::Show('Primero seleccioná la carpeta principal.');return}
 $script:statePath=Join-Path $script:root '.imdb_linker_estado.json';Read-State
 $script:items.Clear()
 foreach($dir in @(Get-ChildItem -LiteralPath $script:root -Directory -ErrorAction SilentlyContinue | Sort-Object Name)) {
  $parsed=Parse-Folder $dir.Name
  if(-not $parsed){continue}
  $hasLink=Test-Path -LiteralPath (Join-Path $dir.FullName 'imdb.url')
  $hasPoster=Test-Path -LiteralPath (Join-Path $dir.FullName 'poster.jpg')
  $status='Pendiente';$detail='Sin procesar';$imdb='';$candidate=$null
  if(($hasLink -or (Test-Path -LiteralPath (Join-Path $dir.FullName 'tmdb.url'))) -and $hasPoster){$status='Completada';$detail='Enlace y póster ya presentes'}
  elseif($script:state.ContainsKey($dir.FullName)) {
   $saved=$script:state[$dir.FullName]
   if($saved.Status -eq 'Revisar' -and ($saved.CandidateId -or $saved.ExternalUrl)){$status=[string]$saved.Status;$detail=[string]$saved.Detail; if($saved.Imdb){$imdb=[string]$saved.Imdb}}
  }
  $script:items.Add([pscustomobject]@{Name=$dir.Name;Path=$dir.FullName;Year=$parsed.Year;Title=$parsed.Title;Status=$status;Detail=$detail;Imdb=$imdb;Candidate=$candidate})
 }
 Refresh-Stats
 $ui.Message.Text="Se detectaron $($script:items.Count) carpetas válidas. Se analizan subcarpetas directas con formato AÑO - TÍTULO; país/idioma entre paréntesis se ignora al buscar."
 Show-Finished "Análisis de carpetas finalizado."
})
$ui.Stop.Add_Click({$script:stopRequested=$true;$ui.Message.Text='Se detendrá después de la película actual.'})
$ui.Run.Add_Click({
 if($script:items.Count -eq 0){[System.Windows.MessageBox]::Show('Primero analizá las carpetas.');return}
 $script:stopRequested=$false
 $ui.Run.IsEnabled=$false;$ui.Scan.IsEnabled=$false;$ui.Choose.IsEnabled=$false
 try {
  foreach($item in $script:items){
   if($script:stopRequested){break}
   if($item.Status -notin @('Pendiente','Error','Sin póster','No encontrada','Rechazada')){continue}
   # A partial prior run with existing imdb.url must not be rematched to another film.
   if(Test-Path -LiteralPath (Join-Path $item.Path 'imdb.url')){
    $item.Status='Revisar';$item.Detail='Ya existe imdb.url; revisar antes de modificar';Refresh-Stats;continue
   }
   $item.Status='Buscando';$item.Detail='Consultando IMDb...';$ui.Message.Text="Buscando: $($item.Name)";Refresh-Stats
   try {
    $result=Search-Multi $item.Title $item.Year
    if($result.Kind -eq 'Exact'){
     Write-Result $item $result.Candidate
    } elseif($result.Kind -eq 'Review') {
     $item.Status='Revisar';$item.Candidate=$result.Candidate;$item.Imdb="https://www.imdb.com/title/$($result.Candidate.id)/";$item.Detail="$($result.Note): $($result.Candidate.l) ($($result.Candidate.y))"
     $script:state[$item.Path]=@{Status='Revisar';Imdb=$item.Imdb;Detail=$item.Detail;Title=$item.Title;Year=$item.Year;CandidateId=$result.Candidate.id;CandidateTitle=$result.Candidate.l;CandidateYear=$result.Candidate.y;Poster=(Poster-Url $result.Candidate)};Save-State
    } elseif($result.Kind -eq 'External') {
     $item.Status='Revisar';$item.Detail=$result.Note;$item.Imdb=''
     $script:state[$item.Path]=@{Status='Revisar';Provider=$result.Provider;ExternalUrl=$result.Url;CandidateTitle=$result.Title;CandidateYear=$result.Year;Poster=$result.Poster;Detail=$result.Note;Title=$item.Title;Year=$item.Year};Save-State
    } else {
     $item.Status='No encontrada';$item.Detail=$result.Note
     $script:state[$item.Path]=@{Status=$item.Status;Imdb='';Detail=$item.Detail;Title=$item.Title;Year=$item.Year};Save-State
    }
   } catch {$item.Status='Error';$item.Detail=$_.Exception.Message}
   Refresh-Stats
  }
 } finally {$ui.Run.IsEnabled=$true;$ui.Scan.IsEnabled=$true;$ui.Choose.IsEnabled=$true}
 $ui.Message.Text='Lote finalizado. Revisar pendientes incluye propuestas y películas sin coincidencia; las no encontradas podrán reintentarse.'
 Refresh-Stats
 Show-Finished 'Búsqueda del lote finalizada.'
})
# Ventana WPF de revisión con imagen y vínculo real. No se guarda nada hasta pulsar Sí.
function Show-CandidateReview($item,$saved) {
 [xml]$reviewXaml=@'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="IMDb Linker - Confirmar coincidencia" Height="790" Width="1140" MinWidth="920" MinHeight="640" WindowStartupLocation="CenterOwner" Background="#F5F7FB" FontFamily="Segoe UI" ResizeMode="CanResize">
 <Grid Margin="22">
  <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
  <StackPanel Grid.Row="0" Margin="0,0,0,15"><TextBlock Text="Revisar película" FontSize="25" FontWeight="Bold" Foreground="#17375B"/><TextBlock Text="Comprobá el póster y la ficha de la fuente antes de decidir." Foreground="#66778D" FontSize="13"/></StackPanel>
  <Border Grid.Row="1" Background="White" CornerRadius="8" Padding="13" Margin="0,0,0,14"><StackPanel><TextBlock Text="CARPETA ORIGINAL" FontSize="11" FontWeight="Bold" Foreground="#66778D"/><TextBlock x:Name="Original" FontSize="16" FontWeight="SemiBold" TextWrapping="Wrap"/></StackPanel></Border>
  <Border Grid.Row="2" Background="White" CornerRadius="8" Padding="15"><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="390"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
   <Border Grid.Column="0" Background="#EDF1F6" CornerRadius="5" Margin="0,0,16,0"><Grid><Image x:Name="Poster" Stretch="Uniform" Margin="8" Cursor="Hand" ToolTip="Doble clic para ampliar el póster"/><TextBlock x:Name="PosterNotice" Text="Póster no disponible" TextAlignment="Center" TextWrapping="Wrap" VerticalAlignment="Center" HorizontalAlignment="Center" Foreground="#66778D" Margin="12"/></Grid></Border>
   <StackPanel Grid.Column="1"><TextBlock Text="COINCIDENCIA PROPUESTA" FontSize="11" FontWeight="Bold" Foreground="#66778D"/><TextBlock x:Name="CandidateTitle" FontSize="21" FontWeight="SemiBold" TextWrapping="Wrap" Margin="0,10,0,8"/><TextBlock x:Name="CandidateYear" FontSize="14" Margin="0,0,0,15"/><TextBlock x:Name="CandidateNote" TextWrapping="Wrap" Foreground="#66778D" Margin="0,0,0,15"/><TextBlock Text="Enlace de la fuente" FontWeight="SemiBold"/><TextBox x:Name="ImdbUrl" IsReadOnly="True" TextWrapping="NoWrap" Margin="0,5,0,8" Padding="7"/><Button x:Name="OpenImdb" Content="Abrir ficha en el navegador" Padding="12,9" HorizontalAlignment="Left" Background="#DDEBFA" Foreground="#17375B" BorderThickness="0" Cursor="Hand"/></StackPanel>
  </Grid></Border>
  <DockPanel Grid.Row="3" Margin="0,17,0,0"><TextBlock Text="Solo «Sí, es correcta» autoriza guardar." VerticalAlignment="Center" Foreground="#66778D" DockPanel.Dock="Left"/><StackPanel Orientation="Horizontal" HorizontalAlignment="Right"><Button x:Name="Yes" Content="Sí, es correcta" Padding="15,10" Margin="6,0,0,0" Background="#D9F2E3" BorderThickness="0" Cursor="Hand"/><Button x:Name="No" Content="No, otra opción" Padding="15,10" Margin="6,0,0,0" Background="#FCE4E4" BorderThickness="0" Cursor="Hand"/><Button x:Name="Later" Content="Omitir" Padding="15,10" Margin="6,0,0,0" Background="#E7EDF5" BorderThickness="0" Cursor="Hand"/></StackPanel></DockPanel>
 </Grid>
</Window>
'@
 $reader2=[System.Xml.XmlNodeReader]::new($reviewXaml)
 try{$dialog=[Windows.Markup.XamlReader]::Load($reader2)}finally{$reader2.Close()}
 $dialog.Owner=$win
 $controls=@{}
 foreach($n in 'Original','Poster','PosterNotice','CandidateTitle','CandidateYear','CandidateNote','ImdbUrl','OpenImdb','Yes','No','Later'){$controls[$n]=$dialog.FindName($n)}
 $url=if($saved.Provider -eq 'TMDb'){[string]$saved.ExternalUrl}elseif($saved.CandidateId -match '^tt\d+$'){"https://www.imdb.com/title/$($saved.CandidateId)/"}else{''}
 $controls.Original.Text=[string]$item.Name
 $controls.CandidateTitle.Text=[string]$saved.CandidateTitle
 $controls.CandidateYear.Text="Año: $($saved.CandidateYear)"
 $controls.CandidateNote.Text=[string]$saved.Detail
 $controls.ImdbUrl.Text=$url
 $controls.OpenImdb.Add_Click({try{if(-not $url){throw "No hay enlace verificado"};Start-Process -FilePath $url}catch{[System.Windows.MessageBox]::Show("No se pudo abrir la ficha: $($_.Exception.Message)")}})
 $posterUrl=[string]$saved.Poster
 if($posterUrl -match '^https://'){
  try {
   $request=[Net.HttpWebRequest]::Create($posterUrl);$request.Timeout=12000;$request.ReadWriteTimeout=12000;$request.UserAgent='Mozilla/5.0'
   $response=$request.GetResponse()
   try {
    $stream=$response.GetResponseStream()
    $buffer=New-Object IO.MemoryStream
    try{$stream.CopyTo($buffer);$buffer.Position=0;$bitmap=New-Object Windows.Media.Imaging.BitmapImage;$bitmap.BeginInit();$bitmap.CacheOption=[Windows.Media.Imaging.BitmapCacheOption]::OnLoad;$bitmap.StreamSource=$buffer;$bitmap.EndInit();$bitmap.Freeze();$controls.Poster.Source=$bitmap;$controls.PosterNotice.Visibility=[Windows.Visibility]::Collapsed}finally{$stream.Dispose();$buffer.Dispose()}
   } finally {$response.Dispose()}
  } catch {$controls.PosterNotice.Text='No se pudo cargar el póster. Abrí la ficha para comprobar el resultado.'}
 }
 # Doble clic: abrir el póster a tamaño ampliado, sin modificar la imagen guardada.
 $controls.Poster.Add_MouseLeftButtonDown({
  param($sender,$eventArgs)
  if($eventArgs.ClickCount -ne 2 -or $null -eq $sender.Source){return}
  try {
   $zoomWindow=New-Object System.Windows.Window
   $zoomWindow.Title='IMDb Linker - Póster ampliado'
   $zoomWindow.Width=900
   $zoomWindow.Height=950
   $zoomWindow.MinWidth=420
   $zoomWindow.MinHeight=420
   $zoomWindow.WindowStartupLocation=[System.Windows.WindowStartupLocation]::CenterOwner
   $zoomWindow.Background=[System.Windows.Media.Brushes]::Black
   $zoomWindow.Owner=$dialog
   $zoomImage=New-Object System.Windows.Controls.Image
   $zoomImage.Source=$sender.Source
   $zoomImage.Stretch=[System.Windows.Media.Stretch]::Uniform
   $zoomImage.Margin=New-Object System.Windows.Thickness(12)
   $zoomWindow.Content=$zoomImage
   [void]$zoomWindow.ShowDialog()
  }catch{[System.Windows.MessageBox]::Show($dialog,"No se pudo ampliar el póster: $($_.Exception.Message)",'IMDb Linker') | Out-Null}
 })
 $script:reviewDecision='Later'
 $controls.Yes.Add_Click({$script:reviewDecision='Yes';$dialog.Close()})
 $controls.No.Add_Click({$script:reviewDecision='No';$dialog.Close()})
 $controls.Later.Add_Click({$script:reviewDecision='Later';$dialog.Close()})
 [void]$dialog.ShowDialog()
 return $script:reviewDecision
}

function Show-ManualLastResort($item) {
 # Solo se ofrece tras agotar las propuestas automáticas para esta película.
 [xml]$manualXaml=@'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Última alternativa - enlace IMDb" Height="450" Width="760" MinHeight="410" MinWidth="620" WindowStartupLocation="CenterOwner" Background="#F5F7FB" FontFamily="Segoe UI" ResizeMode="CanResize" UseLayoutRounding="True">
 <Grid Margin="22">
  <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
  <ScrollViewer Grid.Row="0" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled">
   <StackPanel Margin="0,0,8,12">
    <TextBlock Text="Última alternativa: enlace manual" FontSize="23" FontWeight="Bold" Foreground="#17375B" TextWrapping="Wrap"/>
    <TextBlock x:Name="MovieName" Margin="0,10,0,0" FontSize="14" TextWrapping="Wrap"/>
    <TextBlock Text="No se confirmó ninguna de las opciones automáticas. Si ya conocés la ficha IMDb, podés pegarla aquí; no es obligatorio." TextWrapping="Wrap" Margin="0,10,0,0" Foreground="#66778D"/>
    <TextBox x:Name="UrlInput" MinHeight="38" Padding="8" Margin="0,18,0,12" VerticalContentAlignment="Center" ToolTip="https://www.imdb.com/title/tt1234567/"/>
    <TextBlock Text="Se aceptan enlaces IMDb en cualquier idioma (por ejemplo /es/title/tt...). Se solicitará confirmación antes de guardar." Foreground="#66778D" TextWrapping="Wrap"/>
   </StackPanel>
  </ScrollViewer>
  <Border Grid.Row="1" Background="#F5F7FB" BorderBrush="#DCE3EB" BorderThickness="0,1,0,0" Padding="0,16,0,0">
   <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
    <Button x:Name="Validate" Content="Verificar enlace" MinWidth="150" MinHeight="42" Padding="16,10" Margin="0,0,12,0"/>
    <Button x:Name="Skip" Content="Dejar pendiente" MinWidth="150" MinHeight="42" Padding="16,10"/>
   </StackPanel>
  </Border>
 </Grid>
</Window>
'@
 $reader=[System.Xml.XmlNodeReader]::new($manualXaml)
 try{$dlg=[Windows.Markup.XamlReader]::Load($reader)}finally{$reader.Close()}
 $dlg.Owner=$win
 $dlg.FindName('MovieName').Text="Carpeta: $($item.Name)"
 $script:manualCandidate=$null
 $dlg.FindName('Skip').Add_Click({$dlg.Close()})
 $dlg.FindName('Validate').Add_Click({
  $inputUrl=[string]$dlg.FindName('UrlInput').Text.Trim()
  if($inputUrl -notmatch '(?i)^https?://(?:(?:www|m)\.)?imdb\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?title/(tt[0-9]+)(?:[/?#].*)?$'){
   [System.Windows.MessageBox]::Show('Ingresá una URL de IMDb que contenga /title/tt..., por ejemplo: https://www.imdb.com/es/title/tt1442519/','Enlace no válido') | Out-Null;return
  }
  $id=$matches[1]
  $candidate=$null
  foreach($hit in @(Get-Candidates $id)) {if($hit.id -eq $id){$candidate=$hit;break}}
  if(-not $candidate){
   # La API de sugerencias no es exhaustiva: no inventar metadatos.
   $candidate=[pscustomobject]@{id=$id;l="IMDb $id (título por verificar)";y='No verificado';i=$null}
  }
  $proposed=@{CandidateId=$id;CandidateTitle=[string]$candidate.l;CandidateYear=[string]$candidate.y;Poster=(Poster-Url $candidate);Detail='Enlace IMDb ingresado manualmente. Verificar la ficha en el navegador antes de aceptar.'}
  $decision=Show-CandidateReview $item $proposed
  if($decision -eq 'Yes'){$script:manualCandidate=$candidate;$dlg.Close()}
 })
 [void]$dlg.ShowDialog()
 return $script:manualCandidate
}
function Offer-ManualLastResort($item) {
 $candidate=Show-ManualLastResort $item
 if($candidate){
  try {Write-Result $item $candidate}
  catch {$item.Status='Error';$item.Detail=$_.Exception.Message}
 }else{
  $item.Status='Pendiente';$item.Detail='Sin coincidencia confirmada; enlace manual opcional disponible al revisar.'
  $script:state[$item.Path]=@{Status='Pendiente';Detail=$item.Detail;Title=$item.Title;Year=$item.Year};Save-State
 }
 Refresh-Stats
}
function Show-Finished([string]$action) {
 $ok=@($script:items | Where-Object {$_.Status -eq 'Completada'}).Count
 $pending=@($script:items | Where-Object {$_.Status -in @('Revisar','Rechazada','No encontrada','Pendiente','Error','Sin póster')}).Count
 $errors=@($script:items | Where-Object {$_.Status -eq 'Error'}).Count
 $review=@($script:items | Where-Object {$_.Status -eq 'Revisar'}).Count
 $message="PROCESO TERMINADO`n`n$action`n`nCompletadas: $ok`nPara verificar: $review`nPendientes y otros estados: $pending`nErrores: $errors`nTotal de carpetas: $($script:items.Count)"
 [System.Windows.MessageBox]::Show($win,$message,'IMDb Linker 4.1 - Proceso terminado',[System.Windows.MessageBoxButton]::OK,[System.Windows.MessageBoxImage]::Information) | Out-Null
}

function Get-ReviewOptions($item,$saved) {
 $options=New-Object System.Collections.ArrayList
 $rejected=@()
 if($saved -and $saved.RejectedIds){$rejected=@($saved.RejectedIds)}
 if($saved -and $saved.CandidateId -and ([string]$saved.CandidateId -notin $rejected)){
  [void]$options.Add(@{CandidateId=[string]$saved.CandidateId;CandidateTitle=[string]$saved.CandidateTitle;CandidateYear=[string]$saved.CandidateYear;Poster=[string]$saved.Poster;Detail=[string]$saved.Detail})
 }
 if($saved -and $saved.ExternalUrl -and -not $saved.CandidateId){
  [void]$options.Add(@{Provider=[string]$saved.Provider;ExternalUrl=[string]$saved.ExternalUrl;CandidateTitle=[string]$saved.CandidateTitle;CandidateYear=[string]$saved.CandidateYear;Poster=[string]$saved.Poster;Detail=[string]$saved.Detail})
 }
 # Retrieve further real IMDb suggestions, rather than recycling a rejected proposal.
 $pool=@{}
 foreach($q in @("$($item.Title) $($item.Year)",[string]$item.Title)){
  foreach($hit in @(Get-Candidates $q)){
   if($hit -and $hit.id -match '^tt\d+$' -and $hit.l){$pool[[string]$hit.id]=$hit}
  }
 }
 $norm=Normalize-Title $item.Title
 $ranked=@($pool.Values | Where-Object {
  $candidateName=Normalize-Title ([string]$_.l)
  $candidateName -eq $norm -or ($candidateName.Length -gt 5 -and $norm.Length -gt 5 -and ($candidateName.Contains($norm) -or $norm.Contains($candidateName)))
 } | Sort-Object @{Expression={if((Normalize-Title ([string]$_.l)) -eq $norm){0}else{1}}},@{Expression={try{[math]::Abs([int]$_.y-[int]$item.Year)}catch{999}}})
 foreach($hit in $ranked){
  $id=[string]$hit.id
  if($id -in $rejected -or @($options | Where-Object {$_.CandidateId -eq $id}).Count -gt 0){continue}
  [void]$options.Add(@{CandidateId=$id;CandidateTitle=[string]$hit.l;CandidateYear=[string]$hit.y;Poster=(Poster-Url $hit);Detail='Otra coincidencia de IMDb; comprobar título, año y póster.'})
  if($options.Count -ge 8){break}
 }
 return ,$options
}
function Review-One($item) {
 $saved=$null
 if($script:state.ContainsKey($item.Path)){$saved=$script:state[$item.Path]}
 if(-not $saved -or (-not $saved.CandidateId -and -not $saved.ExternalUrl)){
  $item.Status='Pendiente'
  $item.Detail='Sin propuesta verificable. Reintentar búsqueda automática con Iniciar / reanudar.'
  Refresh-Stats
  Offer-ManualLastResort $item
  return
 }
 $rejected=@();if($saved.RejectedIds){$rejected=@($saved.RejectedIds)}
 $options=Get-ReviewOptions $item $saved
 if($options.Count -eq 0){
  $item.Status='Pendiente';$item.Detail='Sin alternativas verificables; reintentar búsqueda.'
  Offer-ManualLastResort $item;return
 }
 foreach($option in $options){
  $decision=Show-CandidateReview $item $option
  if($decision -eq 'Later'){return}
  if($decision -eq 'No'){
   if($option.CandidateId){$rejected+=([string]$option.CandidateId)}
   continue
  }
  if($decision -eq 'Yes'){
   if($option.Provider -eq 'TMDb'){
    try{Write-ExternalResult $item $option}catch{$item.Status='Error';$item.Detail=$_.Exception.Message}
   }else{
    $candidate=[pscustomobject]@{id=[string]$option.CandidateId;l=[string]$option.CandidateTitle;y=[string]$option.CandidateYear;i=[pscustomobject]@{imageUrl=[string]$option.Poster}}
    try{Write-Result $item $candidate}catch{$item.Status='Error';$item.Detail=$_.Exception.Message}
   }
   Refresh-Stats
   return
  }
 }
 $item.Status='Pendiente';$item.Detail='Alternativas rechazadas; volverá a buscar.'
 $script:state[$item.Path]=@{Status='Pendiente';Detail=$item.Detail;RejectedIds=@($rejected);Title=$item.Title;Year=$item.Year}
 Save-State;Refresh-Stats
 Offer-ManualLastResort $item
}

$ui.Review.Add_Click({
 $pending=@($script:items | Where-Object {$_.Status -in @('Revisar','Rechazada','No encontrada','Pendiente','Error','Sin póster')})
 if($pending.Count -eq 0){[System.Windows.MessageBox]::Show('No hay películas pendientes.');return}
 foreach($item in $pending){
  $saved=$null;if($script:state.ContainsKey($item.Path)){$saved=$script:state[$item.Path]}
  Review-One $item
 }
 $without=@($script:items | Where-Object {$_.Status -in @('Pendiente','No encontrada','Error')}).Count
 if($without -gt 0){$ui.Message.Text="$without películas continúan pendientes; Iniciar / reanudar volverá a investigarlas."}
 Show-Finished 'Revisión de pendientes finalizada.'
})
$ui.Results.Add_MouseDoubleClick({
 $selected=$ui.Results.SelectedItem
 if($selected -and $selected.Status -in @('Revisar','Rechazada','No encontrada','Pendiente','Error','Sin póster')){Review-One $selected}
})
$ui.OpenFolder.Add_Click({
 $selected=$ui.Results.SelectedItem
 if($selected){Start-Process explorer.exe -ArgumentList ('"'+$selected.Path+'"')}
 elseif($script:root){Start-Process explorer.exe -ArgumentList ('"'+$script:root+'"')}
})
[void]$win.ShowDialog()
