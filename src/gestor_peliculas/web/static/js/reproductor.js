// Boton "Video": pide al servidor que abra el archivo original en VLC.
// Reemplaza el <video> embebido, el protocolo micinemateca-vlc: y el
// ejecutable Mi_Cinemateca_VLC.exe que usaba la version anterior.
'use strict';

document.addEventListener('click', async (evento) => {
  const boton = evento.target.closest('.btn-reproducir');
  if (!boton) return;

  const id = boton.dataset.pelicula;
  if (!id) return;

  const textoOriginal = boton.textContent;
  boton.disabled = true;
  boton.textContent = 'Abriendo...';

  const { ok, cuerpo } = await enviar(`/peliculas/${id}/reproducir`);
  avisar(cuerpo.mensaje || (ok ? 'Abriendo en VLC.' : 'No se pudo reproducir.'), !ok);

  boton.disabled = false;
  boton.textContent = textoOriginal;
});

document.addEventListener('click', async (evento) => {
  const boton = evento.target.closest('.btn-abrir-carpeta');
  if (!boton) return;
  const id = boton.dataset.pelicula;
  if (!id) return;
  const { ok, cuerpo } = await enviar(`/peliculas/${id}/carpeta`);
  avisar(cuerpo.mensaje || (ok ? 'Carpeta abierta.' : 'No se pudo abrir.'), !ok);
});
