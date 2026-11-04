"""Genera los DFF de ejemplo (.docx) que usa la demo.

- DFF_Carrito_cupones_v2.4.docx: limpio, casos en tabla (incluye un caso que ya existe en Azure).
- DFF_Checkout_v2.4.docx: casos redactados en prosa, con listas numeradas.
- DFF_Area_cliente_borrador.docx: borrador con huecos (sin resultado esperado, paso vago, dato contradictorio).

Uso: uv run python sample_data/dff/build_dff.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Pt, RGBColor

OUT = Path(__file__).parent


def _base(title: str, meta: dict[str, str], intro: list[str]) -> Document:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    h = doc.add_heading("Documento Funcional · Casos de prueba", level=0)
    h.runs[0].font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    doc.add_heading(title, level=1)
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for k, v in meta.items():
        row = t.add_row().cells
        row[0].text, row[1].text = k, v
    doc.add_heading("Descripción funcional", level=2)
    for p in intro:
        doc.add_paragraph(p)
    return doc


def _cases_table(doc: Document, cases: list[tuple[str, ...]]) -> None:
    doc.add_heading("Casos de prueba", level=2)
    headers = ["ID", "Título", "Precondiciones", "Pasos", "Datos de prueba", "Resultado esperado"]
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, text in zip(t.rows[0].cells, headers, strict=True):
        cell.text = text
    for case in cases:
        for cell, text in zip(t.add_row().cells, case, strict=True):
            cell.text = text


def carrito() -> None:
    doc = _base(
        "Carrito y cupones de descuento",
        {"Proyecto": "Tienda web", "Funcionalidad": "Carrito y cupones", "Feature (Azure DevOps)": "#103",
         "Versión": "2.4", "Autor": "Análisis funcional", "Estado": "Aprobado"},
        ["En la versión 2.4 el carrito admite cupones de descuento. Los cupones vigentes son BIENVENIDA10 (10 %) "
         "y VERANO20 (20 %). Un cupón no válido muestra un mensaje de error y no aplica descuento.",
         "La ficha de producto avisa cuando quedan 5 unidades o menos, y no permite añadir más unidades de las "
         "disponibles."],
    )
    _cases_table(doc, [
        ("TC-CARRITO-001", "Añadir producto al carrito", "Ninguna",
         "1. Abrir el producto 1\n2. Pulsar el botón añadir al carrito", "Producto 1: Auriculares inalámbricos",
         'El mensaje del producto contiene "Producto añadido al carrito"'),
        ("TC-CARRITO-002", "Aplicar un cupón válido", "El producto 3 está en el carrito",
         '1. Añadir el producto 3 al carrito\n2. Abrir la página carrito\n3. Introducir "BIENVENIDA10" en el campo '
         "cupón\n4. Pulsar el botón aplicar cupón", "Cupón BIENVENIDA10. Producto 3: Teclado mecánico, 89,00 €",
         'El mensaje del cupón contiene "10% de descuento"\nSe muestra el descuento\nEl total contiene "80,10"'),
        ("TC-CARRITO-003", "Cupón no válido", "El producto 1 está en el carrito",
         '1. Añadir el producto 1 al carrito\n2. Abrir la página carrito\n3. Introducir "NOEXISTE" en el campo '
         "cupón\n4. Pulsar el botón aplicar cupón", "Cupón inexistente NOEXISTE",
         'El mensaje del cupón contiene "El cupón no es válido"\nNo se muestra el descuento'),
        ("TC-CARRITO-004", "Eliminar el único producto deja el carrito vacío", "El producto 6 está en el carrito",
         "1. Añadir el producto 6 al carrito\n2. Abrir la página carrito\n3. Pulsar el botón eliminar", "Producto 6",
         'Se muestra el mensaje de carrito vacío\nEl contador del carrito contiene "0"'),
        ("TC-CARRITO-005", "Aviso de stock bajo en la ficha de producto", "Producto 2 con 3 unidades en stock",
         "1. Abrir el producto 2", "Producto 2: Altavoz portátil (stock 3)",
         'Se muestra el aviso de stock\nEl aviso de stock contiene "Últimas 3 unidades"'),
        ("TC-CARRITO-006", "No se pueden añadir más unidades que el stock", "Producto 2 con 3 unidades en stock",
         '1. Abrir el producto 2\n2. Introducir "5" en el campo cantidad\n3. Pulsar el botón añadir al carrito',
         "Cantidad 5 (stock 3)", 'El mensaje del producto contiene "Solo quedan 3 unidades"'),
    ])
    doc.save(OUT / "DFF_Carrito_cupones_v2.4.docx")


def checkout() -> None:
    doc = _base(
        "Checkout: datos de envío y confirmación",
        {"Proyecto": "Tienda web", "Funcionalidad": "Checkout y pago", "Feature (Azure DevOps)": "#104",
         "Versión": "2.4", "Autor": "Análisis funcional", "Estado": "En revisión"},
        ["El checkout exige sesión iniciada. Si el cliente pulsa «Tramitar pedido» sin sesión, se le lleva al login. "
         "El formulario valida que el nombre y la dirección no estén vacíos, que el código postal tenga 5 dígitos y "
         "que se elija un método de pago. Al confirmar se muestra el número de pedido."],
    )
    doc.add_heading("Casos de prueba", level=2)
    login = 'Iniciar sesión como "demo@tienda.test" con contraseña "Demo1234"'
    casos = [
        ("TC-CHK-001", "Pedido completo pagando con tarjeta",
         "El cliente demo tiene sesión iniciada y el producto 1 en el carrito.",
         [login, "Añadir el producto 1 al carrito", "Abrir la página checkout",
          'Introducir "Lucía Martín" en el campo nombre', 'Introducir "Calle Mayor 1, Madrid" en el campo dirección',
          'Introducir "28013" en el campo código postal', 'Seleccionar "tarjeta" en el método de pago',
          "Pulsar el botón confirmar pedido"],
         'La confirmación contiene "confirmado"'),
        ("TC-CHK-002", "Código postal con formato no válido",
         "El cliente demo tiene sesión iniciada y el producto 1 en el carrito.",
         [login, "Añadir el producto 1 al carrito", "Abrir la página checkout",
          'Introducir "Lucía Martín" en el campo nombre', 'Introducir "Calle Mayor 1, Madrid" en el campo dirección',
          'Introducir "123" en el campo código postal', 'Seleccionar "tarjeta" en el método de pago',
          "Pulsar el botón confirmar pedido"],
         'El error contiene "5 dígitos"'),
        ("TC-CHK-003", "Tramitar sin sesión lleva al login",
         "No hay sesión iniciada.",
         ["Añadir el producto 1 al carrito", "Abrir la página carrito", "Pulsar el botón tramitar pedido"],
         'La URL contiene "/login"\nSe muestra el campo usuario'),
    ]
    for cid, title, pre, steps, expected in casos:
        doc.add_heading(f"Caso {cid}: {title}", level=3)
        doc.add_paragraph(f"Precondiciones: {pre}")
        doc.add_paragraph("Pasos:")
        for s in steps:
            doc.add_paragraph(s, style="List Number")
        doc.add_paragraph(f"Resultado esperado: {expected}")
    doc.save(OUT / "DFF_Checkout_v2.4.docx")


def area_cliente() -> None:
    doc = _base(
        "Área de cliente (borrador)",
        {"Proyecto": "Tienda web", "Funcionalidad": "Área de cliente", "Feature (Azure DevOps)": "#105",
         "Versión": "2.4", "Autor": "Análisis funcional", "Estado": "Borrador"},
        ["El área de cliente muestra los datos del cliente y su historial de pedidos. Las cuentas bloqueadas no "
         "pueden iniciar sesión.", "Pendiente de cerrar con negocio: textos definitivos de los mensajes de error."],
    )
    _cases_table(doc, [
        ("TC-PERFIL-001", "Ver los datos del perfil", "Cliente demo registrado",
         '1. Iniciar sesión como "demo@tienda.test" con contraseña "Demo1234"', "Usuario demo",
         'El nombre contiene "Lucía Martín"\nEl correo contiene "demo@tienda.test"'),
        ("TC-PERFIL-002", "El pedido aparece en el historial", "Cliente demo registrado",
         "1. Realizar un pedido\n2. Ir al perfil", "", "El pedido aparece en Mis pedidos"),
        ("TC-PERFIL-003", "Una cuenta bloqueada no puede entrar", "Cuenta bloqueada",
         '1. Iniciar sesión como "bloqueado@tienda.test" con contraseña "Demo1234"',
         "Usuario bloqueado@tienda.test, contraseña: Bloq2024", ""),
    ])
    doc.save(OUT / "DFF_Area_cliente_borrador.docx")


if __name__ == "__main__":
    carrito()
    checkout()
    area_cliente()
    print("DFF generados en", OUT)
