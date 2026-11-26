"""Clasificacion de carpetas en pares, sueltos, incidencias y sobrantes."""

from gestor_peliculas.organizador import analizador, deteccion_subtitulos

SRT = "1\n00:00:01,000 --> 00:00:02,000\nHola\n"


def por_nombre(analisis, atributo):
    return {x.nombre_carpeta for x in getattr(analisis, atributo)}


def test_clasifica_las_cuatro_categorias(coleccion):
    analisis = analizador.analizar(coleccion)

    assert "1975 - Tiburon" in por_nombre(analisis, "pares")
    assert "1972 - El Padrino" in por_nombre(analisis, "sueltos")
    assert "2000 - Ambigua" in por_nombre(analisis, "incidencias")
    # Una carpeta sin video ni subtitulo no entra en ninguna categoria.
    assert "_Notas" not in por_nombre(analisis, "pares") | por_nombre(analisis, "sueltos")


def test_una_carpeta_con_varias_peliculas_no_es_un_problema(coleccion):
    """Una carpeta de saga es legitima: el catalogo la indexa por separado."""
    analisis = analizador.analizar(coleccion)
    ambigua = next(i for i in analisis.incidencias if i.nombre_carpeta == "2000 - Ambigua")

    assert ambigua.es_saga
    assert "2 peliculas" in ambigua.motivo
    assert ambigua in analisis.sagas
    assert ambigua not in analisis.problemas


def test_una_carpeta_rota_si_es_un_problema(tmp_path):
    """Un video con tres subtitulos no se puede organizar solo."""
    carpeta = tmp_path / "1975 - Tiburon"
    carpeta.mkdir()
    (carpeta / "video.mkv").write_bytes(b"\x00")
    for nombre in ("a.srt", "b.srt", "c.srt"):
        (carpeta / nombre).write_text(SRT, encoding="utf-8")

    analisis = analizador.analizar(tmp_path)
    problema = analisis.problemas[0]

    assert not problema.es_saga
    assert "subtitulos: 3" in problema.motivo
    assert analisis.pares == []


def test_propone_el_nombre_de_la_carpeta(coleccion):
    analisis = analizador.analizar(coleccion)
    pulp = next(s for s in analisis.sueltos if s.nombre_carpeta == "1994 - Pulp Fiction")
    assert pulp.destino.name == "1994 - Pulp Fiction.mp4"
    assert not pulp.correcto


def test_un_par_ya_correcto_se_marca_como_tal(coleccion):
    analisis = analizador.analizar(coleccion)
    tiburon = next(p for p in analisis.pares if p.nombre_carpeta == "1975 - Tiburon")
    assert tiburon.correcto
    assert tiburon.estado == "Correcto"


def test_el_segundo_subtitulo_lleva_sufijo_1(tmp_path):
    carpeta = tmp_path / "1975 - Tiburon"
    carpeta.mkdir()
    (carpeta / "video.mkv").write_bytes(b"\x00")
    (carpeta / "a.srt").write_text(SRT, encoding="utf-8")
    (carpeta / "b.srt").write_text(SRT, encoding="utf-8")

    analisis = analizador.analizar(tmp_path)
    par = analisis.pares[0]

    assert par.destino_video.name == "1975 - Tiburon.mkv"
    assert [d.name for d in par.destinos_subtitulos] == [
        "1975 - Tiburon.srt", "1975 - Tiburon1.srt",
    ]


def test_los_archivos_sueltos_se_agrupan_por_extension(coleccion):
    analisis = analizador.analizar(coleccion)
    extensiones = {g.extension: g.cantidad for g in analisis.extras}

    assert extensiones.get(".TMP") == 1
    # Un .nfo sin identificador es un archivo suelto como cualquier otro.
    assert extensiones.get(".NFO") == 1
    # imdb.url y poster.jpg estan protegidos: nunca se ofrecen para borrar.
    assert ".URL" not in extensiones
    assert ".JPG" not in extensiones


def test_un_nfo_con_identificador_imdb_esta_protegido(tmp_path):
    """El catalogo lee los .nfo: borrarlos perderia el enlace de la pelicula."""
    carpeta = tmp_path / "1994 - Pulp Fiction"
    carpeta.mkdir()
    (carpeta / "video.mkv").write_bytes(b"\x00")
    con_id = carpeta / "pelicula.nfo"
    con_id.write_text('<movie><uniqueid type="imdb">tt0110912</uniqueid></movie>',
                      encoding="utf-8")
    sin_id = carpeta / "notas.nfo"
    sin_id.write_text("solo texto", encoding="utf-8")

    assert analizador.esta_protegido(con_id)
    assert not analizador.esta_protegido(sin_id)

    analisis = analizador.analizar(tmp_path)
    sueltos = {a.name for g in analisis.extras for a in g.archivos}
    assert "pelicula.nfo" not in sueltos
    assert "notas.nfo" in sueltos


def test_un_txt_cualquiera_no_se_trata_como_subtitulo(coleccion):
    """Arreglo respecto del original: .txt estaba en la lista de subtitulos,
    asi que la publicidad de los grupos de release terminaba renombrada."""
    analisis = analizador.analizar(coleccion)
    totoro = next(p for p in analisis.sueltos if "Totoro" in p.nombre_carpeta)

    assert totoro.destino.name.endswith(".mkv")
    assert ".TXT" in {g.extension for g in analisis.extras}


def test_un_txt_con_contenido_srt_si_es_subtitulo(tmp_path):
    carpeta = tmp_path / "1975 - Tiburon"
    carpeta.mkdir()
    (carpeta / "video.mkv").write_bytes(b"\x00")
    (carpeta / "subs.txt").write_text(SRT, encoding="utf-8")

    analisis = analizador.analizar(tmp_path)

    assert len(analisis.pares) == 1
    assert analisis.pares[0].destinos_subtitulos[0].name == "1975 - Tiburon.txt"


def test_un_archivo_sin_extension_con_contenido_srt_se_guarda_como_srt(tmp_path):
    carpeta = tmp_path / "1975 - Tiburon"
    carpeta.mkdir()
    (carpeta / "video.mkv").write_bytes(b"\x00")
    (carpeta / "subtitulo").write_text(SRT, encoding="utf-8")

    analisis = analizador.analizar(tmp_path)
    assert analisis.pares[0].destinos_subtitulos[0].name == "1975 - Tiburon.srt"


def test_archivos_protegidos(tmp_path):
    carpeta = tmp_path / "x"
    carpeta.mkdir()
    for nombre in ("imdb.url", "poster.jpg", "Informe_Peliculas_20250101_000000_000.csv",
                   "Historial_Renombramientos_20250101_000000_000.csv", "desktop.ini"):
        archivo = carpeta / nombre
        archivo.write_bytes(b"x")
        assert analizador.esta_protegido(archivo), nombre
    suelto = carpeta / "cualquiera.tmp"
    suelto.write_bytes(b"x")
    assert not analizador.esta_protegido(suelto)


def test_no_recorre_la_carpeta_de_informes(tmp_path):
    (tmp_path / "_Informes_Organizador").mkdir()
    (tmp_path / "_Informes_Organizador" / "viejo.mkv").write_bytes(b"\x00")
    analisis = analizador.analizar(tmp_path)
    assert analisis.pares == [] and analisis.sueltos == []


def test_carpeta_inexistente_devuelve_analisis_vacio(tmp_path):
    analisis = analizador.analizar(tmp_path / "no-existe")
    assert analisis.carpetas == 0
    assert analisis.pares == []


class TestDeteccionSubtitulos:
    def test_reconoce_los_formatos_conocidos(self, tmp_path):
        casos = {
            "srt": SRT,
            "vtt": "WEBVTT\n\n00:01.000 --> 00:02.000\nHola\n",
            "ass": "[Script Info]\nTitle: x\n",
            "dialogue": "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hola\n",
            "microdvd": "{100}{200}Hola\n",
        }
        for nombre, contenido in casos.items():
            archivo = tmp_path / nombre
            archivo.write_text(contenido, encoding="utf-8")
            assert deteccion_subtitulos.es_subtitulo(archivo), nombre

    def test_no_confunde_texto_comun(self, tmp_path):
        archivo = tmp_path / "leeme.txt"
        archivo.write_text("Visitanos en ejemplo.invalid para mas peliculas\n",
                           encoding="utf-8")
        assert not deteccion_subtitulos.es_subtitulo(archivo)

    def test_extension_segun_el_contenido(self, tmp_path):
        srt = tmp_path / "sin_extension"
        srt.write_text(SRT, encoding="utf-8")
        assert deteccion_subtitulos.extension_para(srt) == ".srt"

        vtt = tmp_path / "otro"
        vtt.write_text("WEBVTT\n\n00:01.000 --> 00:02.000\nHola\n", encoding="utf-8")
        assert deteccion_subtitulos.extension_para(vtt) == ".vtt"

        ya_tiene = tmp_path / "x.ass"
        ya_tiene.write_text("[Script Info]\n", encoding="utf-8")
        assert deteccion_subtitulos.extension_para(ya_tiene) == ".ass"

    def test_archivo_vacio_no_es_subtitulo(self, tmp_path):
        vacio = tmp_path / "vacio"
        vacio.write_bytes(b"")
        assert not deteccion_subtitulos.es_subtitulo(vacio)
