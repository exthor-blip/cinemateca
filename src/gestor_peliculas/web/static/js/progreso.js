// Sigue el avance de las tareas del servidor y actualiza su barra.
// Reemplaza el <progress> que el HTML original movia desde su propio bucle.
'use strict';

(function seguirTareas() {
  const INTERVALO = 1200;

  function paneles() {
    return [...document.querySelectorAll('.panel-tarea[data-viva]')];
  }

  async function consultar(panel) {
    const id = panel.dataset.tarea;
    if (!id) return false;

    let datos;
    try {
      const respuesta = await fetch(`/tareas/${id}`);
      if (!respuesta.ok) return false;
      datos = await respuesta.json();
    } catch {
      return false;
    }

    const barra = panel.querySelector('.js-barra');
    const mensaje = panel.querySelector('.js-mensaje');
    const estado = panel.querySelector('.js-estado');

    if (barra) {
      barra.style.width = `${datos.porcentaje}%`;
      barra.classList.toggle('progress-bar-animated', datos.viva);
      barra.classList.toggle('progress-bar-striped', datos.viva);
      barra.classList.toggle('bg-danger', datos.estado === 'fallida');
    }
    if (mensaje) {
      const lineas = [datos.mensaje, ...(datos.detalle || [])].filter(Boolean);
      mensaje.textContent = lineas.join('\n');
      mensaje.classList.toggle('error', datos.estado === 'fallida');
    }
    if (estado) {
      estado.textContent = datos.total
        ? `${datos.estado_etiqueta} - ${datos.hechos} de ${datos.total}`
        : datos.estado_etiqueta;
    }

    if (!datos.viva) {
      delete panel.dataset.viva;
      // Al terminar se recarga para que la grilla muestre las fichas nuevas.
      setTimeout(() => window.location.reload(), 1200);
      return false;
    }
    return true;
  }

  async function ciclo() {
    const activos = paneles();
    if (!activos.length) return;
    const siguen = await Promise.all(activos.map(consultar));
    if (siguen.some(Boolean)) setTimeout(ciclo, INTERVALO);
  }

  if (paneles().length) setTimeout(ciclo, 600);
})();
