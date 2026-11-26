// Explorador de carpetas del servidor.
//
// La version anterior usaba showDirectoryPicker() del navegador, que solo
// servia porque alli el navegador ERA la aplicacion. Con un backend, la carpeta
// que hay que elegir esta en el disco de esta computadora, y ningun navegador
// le entrega una ruta local a una pagina. Asi que el servidor lista sus propias
// carpetas (solo nombres de carpeta, nunca contenido de archivos) y aca se
// navega por ellas.
'use strict';

(function explorador() {
  const modal = document.getElementById('modalExplorador');
  if (!modal) return;

  const lista = document.getElementById('explorarLista');
  const rotuloRuta = document.getElementById('explorarRuta');
  const botonArriba = document.getElementById('explorarArriba');
  const botonRaiz = document.getElementById('explorarRaiz');
  const botonElegir = document.getElementById('explorarElegir');
  const campoRuta = document.getElementById('ruta');

  let rutaActual = '';
  let rutaPadre = null;

  function fila(texto, icono, alHacerClic, titulo = '') {
    const elemento = document.createElement('button');
    elemento.type = 'button';
    elemento.className = 'list-group-item list-group-item-action d-flex gap-2 align-items-center';
    elemento.innerHTML = `<span aria-hidden="true">${icono}</span>`;
    const nombre = document.createElement('span');
    nombre.textContent = texto;
    elemento.append(nombre);
    if (titulo) elemento.title = titulo;
    elemento.addEventListener('click', alHacerClic);
    return elemento;
  }

  async function cargar(ruta) {
    lista.replaceChildren();
    const cargando = document.createElement('div');
    cargando.className = 'list-group-item text-secondary';
    cargando.textContent = 'Leyendo la carpeta...';
    lista.append(cargando);

    let datos;
    try {
      const url = ruta
        ? `/ubicaciones/explorar?ruta=${encodeURIComponent(ruta)}`
        : '/ubicaciones/explorar';
      const respuesta = await fetch(url);
      datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'No se pudo abrir la carpeta.');
    } catch (error) {
      lista.replaceChildren();
      const aviso = document.createElement('div');
      aviso.className = 'list-group-item text-danger';
      aviso.textContent = error.message;
      lista.append(aviso);
      return;
    }

    rutaActual = datos.ruta || '';
    rutaPadre = datos.padre || null;
    rotuloRuta.textContent = rutaActual || datos.titulo;
    botonArriba.disabled = !rutaPadre;
    botonElegir.disabled = !rutaActual;

    lista.replaceChildren();

    (datos.atajos || []).forEach((atajo) => {
      lista.append(fila(atajo.nombre, '\u2605', () => cargar(atajo.ruta), atajo.ruta));
    });
    (datos.unidades || []).forEach((unidad) => {
      lista.append(fila(unidad.nombre, '\u{1F4BE}', () => cargar(unidad.ruta), unidad.ruta));
    });
    (datos.carpetas || []).forEach((carpeta) => {
      lista.append(fila(carpeta.nombre, '\u{1F4C1}', () => cargar(carpeta.ruta), carpeta.ruta));
    });

    if (!lista.childElementCount) {
      const vacio = document.createElement('div');
      vacio.className = 'list-group-item text-secondary';
      vacio.textContent = 'Esta carpeta no tiene subcarpetas. Se puede elegir igual.';
      lista.append(vacio);
    }
  }

  botonArriba.addEventListener('click', () => rutaPadre && cargar(rutaPadre));
  botonRaiz.addEventListener('click', () => cargar(''));
  botonElegir.addEventListener('click', () => {
    if (!rutaActual) return;
    campoRuta.value = rutaActual;
    bootstrap.Modal.getInstance(modal)?.hide();
  });

  modal.addEventListener('show.bs.modal', () => {
    cargar(campoRuta.value.trim() || '');
  });
})();
