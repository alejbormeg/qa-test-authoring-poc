// Tienda demo: datos, sesión y carrito en localStorage. Sin dependencias.
const PRODUCTOS = [
  { id: 1, nombre: "Auriculares inalámbricos", precio: 59.9, categoria: "audio", stock: 25 },
  { id: 2, nombre: "Altavoz portátil", precio: 39.5, categoria: "audio", stock: 3 },
  { id: 3, nombre: "Teclado mecánico", precio: 89.0, categoria: "informatica", stock: 12 },
  { id: 4, nombre: "Ratón ergonómico", precio: 29.99, categoria: "informatica", stock: 0 },
  { id: 5, nombre: "Monitor 27 pulgadas", precio: 249.0, categoria: "informatica", stock: 7 },
  { id: 6, nombre: "Lámpara de escritorio", precio: 24.9, categoria: "hogar", stock: 40 },
];
const USUARIOS = {
  "demo@tienda.test": { password: "Demo1234", nombre: "Lucía Martín", bloqueado: false },
  "bloqueado@tienda.test": { password: "Demo1234", nombre: "Cuenta Bloqueada", bloqueado: true },
};
const CUPONES = { BIENVENIDA10: 10, VERANO20: 20 };
const STOCK_BAJO = 5;

const $ = (sel) => document.querySelector(sel);
const euros = (n) => n.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
const leer = (k, def) => { try { return JSON.parse(localStorage.getItem(k)) ?? def; } catch { return def; } };
const guardar = (k, v) => localStorage.setItem(k, JSON.stringify(v));

const sesion = () => leer("sesion", null);
const carrito = () => leer("carrito", []);
const cupon = () => leer("cupon", null);

function producto(id) { return PRODUCTOS.find((p) => p.id === Number(id)); }

function anadirAlCarrito(id, cantidad = 1) {
  const c = carrito();
  const linea = c.find((l) => l.id === Number(id));
  if (linea) linea.cantidad += cantidad; else c.push({ id: Number(id), cantidad });
  guardar("carrito", c);
}

function totales() {
  const subtotal = carrito().reduce((s, l) => s + producto(l.id).precio * l.cantidad, 0);
  const pct = cupon() ? CUPONES[cupon()] : 0;
  const descuento = +(subtotal * pct / 100).toFixed(2);
  return { subtotal, descuento, total: +(subtotal - descuento).toFixed(2), pct };
}

function cabecera() {
  const s = sesion();
  const unidades = carrito().reduce((n, l) => n + l.cantidad, 0);
  const h = document.createElement("header");
  h.innerHTML = `
    <a href="/" class="logo" data-testid="cabecera-logo">Tienda<span>demo</span></a>
    <form class="buscador" data-testid="cabecera-buscador">
      <input data-testid="cabecera-buscador-input" name="q" placeholder="Buscar productos" aria-label="Buscar productos">
      <button data-testid="cabecera-buscador-boton" type="submit">Buscar</button>
    </form>
    <nav>
      <a href="/carrito" data-testid="cabecera-carrito-enlace">Carrito <b data-testid="cabecera-carrito-contador">${unidades}</b></a>
      ${s ? `<a href="/perfil" data-testid="cabecera-usuario">${s.nombre}</a>
             <button class="enlace" data-testid="cabecera-logout">Salir</button>`
          : `<a href="/login" data-testid="cabecera-login-enlace">Iniciar sesión</a>`}
    </nav>`;
  document.body.prepend(h);
  h.querySelector("form").addEventListener("submit", (e) => {
    e.preventDefault();
    location.href = "/?q=" + encodeURIComponent(h.querySelector("input").value.trim());
  });
  const out = h.querySelector("[data-testid=cabecera-logout]");
  if (out) out.addEventListener("click", () => { localStorage.removeItem("sesion"); location.href = "/"; });
}

function login(email, password) {
  const u = USUARIOS[email.trim().toLowerCase()];
  if (!u || u.password !== password) return "Usuario o contraseña incorrectos";
  if (u.bloqueado) return "La cuenta está bloqueada. Contacta con atención al cliente";
  guardar("sesion", { email: email.trim().toLowerCase(), nombre: u.nombre });
  return null;
}

document.addEventListener("DOMContentLoaded", cabecera);
