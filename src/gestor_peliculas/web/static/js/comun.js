// Utilidades compartidas por todas las paginas.
'use strict';

/** Token CSRF de la pagina, para los fetch con POST. */
function tokenCsrf() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  const campo = document.querySelector('input[name="csrf_token"]');
  return campo ? campo.value : '';
}

/** POST a una ruta propia devolviendo el JSON de respuesta. */
async function enviar(url, datos = {}) {
  const respuesta = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': tokenCsrf(),
    },
    body: JSON.stringify(datos),
  });
  let cuerpo = {};
  try {
    cuerpo = await respuesta.json();
  } catch {
    cuerpo = { ok: false, mensaje: 'El servidor respondio algo inesperado.' };
  }
  return { ok: respuesta.ok && cuerpo.ok !== false, cuerpo };
}

/** Aviso flotante breve, para confirmar una accion sin recargar la pagina. */
function avisar(mensaje, esError = false) {
  let zona = document.getElementById('zonaAvisos');
  if (!zona) {
    zona = document.createElement('div');
    zona.id = 'zonaAvisos';
    zona.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    document.body.append(zona);
  }
  const aviso = document.createElement('div');
  aviso.className = `toast align-items-center text-bg-${esError ? 'danger' : 'primary'} border-0`;
  aviso.setAttribute('role', 'status');
  aviso.innerHTML =
    '<div class="d-flex"><div class="toast-body"></div>' +
    '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"' +
    ' aria-label="Cerrar"></button></div>';
  aviso.querySelector('.toast-body').textContent = mensaje;
  zona.append(aviso);
  const instancia = new bootstrap.Toast(aviso, { delay: esError ? 8000 : 4000 });
  instancia.show();
  aviso.addEventListener('hidden.bs.toast', () => aviso.remove());
}

// Tema claro u oscuro. Se recuerda en el navegador de esta computadora.
(function temaGuardado() {
  const guardado = localStorage.getItem('cinemateca-tema');
  if (guardado === 'dark' || guardado === 'light') {
    document.documentElement.setAttribute('data-bs-theme', guardado);
  }
  const boton = document.getElementById('cambiarTema');
  if (!boton) return;
  boton.addEventListener('click', () => {
    const actual = document.documentElement.getAttribute('data-bs-theme');
    const nuevo = actual === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', nuevo);
    localStorage.setItem('cinemateca-tema', nuevo);
  });
})();
