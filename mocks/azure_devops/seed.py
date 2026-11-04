"""Datos iniciales del Azure DevOps simulado: Features, casos ya automatizados y Test Plans."""

from __future__ import annotations

from qa_assistant.config import settings

from . import store

FEATURES = {
    101: ("Acceso de usuarios", "Inicio y cierre de sesión, bloqueo de cuentas."),
    102: ("Catálogo y búsqueda", "Listado, filtros y búsqueda de productos."),
    103: ("Carrito y cupones", "Añadir y eliminar productos, cupones de descuento, avisos de stock."),
    104: ("Checkout y pago", "Datos de envío, validaciones y confirmación del pedido."),
    105: ("Área de cliente", "Perfil y pedidos del cliente."),
}

# Casos ya automatizados en el repo de tests (ver sample_data/test-repo-seed/Tests).
EXISTING = [
    (201, 101, "TC-LOGIN-001 · Login correcto", "LoginTests.TC_LOGIN_001_LoginCorrecto",
     [("Abrir la página login", ""), ("Iniciar sesión con el usuario demo", "Se muestra el nombre del usuario en la cabecera")]),
    (202, 101, "TC-LOGIN-002 · Contraseña incorrecta", "LoginTests.TC_LOGIN_002_PasswordIncorrecta",
     [("Iniciar sesión con una contraseña incorrecta", "Se muestra «Usuario o contraseña incorrectos»")]),
    (203, 102, "TC-CAT-001 · Buscar producto por nombre", "CatalogoTests.TC_CAT_001_BuscarProductoPorNombre",
     [("Buscar «teclado»", "Aparece un único producto: Teclado mecánico")]),
    (204, 102, "TC-CAT-002 · Búsqueda sin resultados", "CatalogoTests.TC_CAT_002_BusquedaSinResultados",
     [("Buscar «bicicleta»", "Se muestra el mensaje de sin resultados")]),
    (205, 103, "TC-CARRITO-001 · Añadir producto al carrito", "CarritoTests.TC_CARRITO_001_AnadirProductoAlCarrito",
     [("Abrir el producto 1 y pulsar Añadir al carrito", "Se confirma el producto añadido y el contador muestra 1")]),
]


def seed() -> None:
    store.reset()
    for fid, (title, desc) in FEATURES.items():
        store.create_work_item("Feature", {"System.Title": title, "System.Description": desc,
                                           "System.AreaPath": "QA-Web\\Tienda web"}, wid=fid, by="Product Owner")
    for wid, fid, title, method, steps in EXISTING:
        store.create_work_item(
            "Test Case",
            {
                "System.Title": title,
                "System.State": "Ready",
                "System.AreaPath": "QA-Web\\Tienda web",
                "System.Tags": "regresion; automatizado",
                "Microsoft.VSTS.TCM.Steps": store.steps_xml(steps),
                "Microsoft.VSTS.TCM.AutomatedTestName": f"{settings.test_namespace}.{method}",
                "Microsoft.VSTS.TCM.AutomatedTestStorage": settings.test_assembly,
                "Microsoft.VSTS.TCM.AutomatedTestType": "xUnit",
                "Microsoft.VSTS.TCM.AutomatedTestId": store.new_automation_id(),
                "Microsoft.VSTS.TCM.AutomationStatus": "Automated",
            },
            [{"rel": "Microsoft.VSTS.Common.TestedBy-Reverse", "url": store.wi_url(fid), "attributes": {"name": "Tests"}}],
            wid=wid, by="Equipo QA",
        )

    regresion = store.create_plan("Tienda web · Regresión", pid=10)
    root = regresion["rootSuite"]["id"]
    by_feature = {101: "Acceso", 102: "Catálogo", 103: "Carrito"}
    for fid, name in by_feature.items():
        suite = store.create_suite(10, name, parent=root)
        store.add_test_cases(suite["id"], [w for w, f, *_ in EXISTING if f == fid])

    release = store.create_plan("Release 2.4", pid=20)
    store.create_suite(20, "v2.4 · Nuevas funcionalidades", parent=release["rootSuite"]["id"])
    store.load()["events"].clear()
    store.event("seed", "Proyecto QA-Web inicializado con 5 Features, 5 casos automatizados y 2 Test Plans")
    store.save()
