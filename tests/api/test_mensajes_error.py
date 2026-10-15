"""Regresión de mensajes de error.

Recorre con `ast` los `HTTPException` de `src/vigia/app/` y falla si un texto
interpola la excepción (`{exc}`, cola en inglés de pandas o pydantic) o nombra
una ruta de la API (`PUT /`, `GET /`, `POST /`...) fuera de la lista blanca.
Más una muestra de 422 con el `msg` en español.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

APP = Path(__file__).resolve().parents[2] / "src" / "vigia" / "app"

RUTA_DE_API = re.compile(r"\b(PUT|GET|POST|PATCH|DELETE) /")
NOMBRES_DE_EXCEPCION = {"exc", "e", "err", "error", "ex"}

MARCA_STR = "<str(excepción)>"

# Lista blanca justificada: (fichero relativo a app/, fragmento del texto).
LISTA_BLANCA: set[tuple[str, str]] = {
    # `HTTPException(422, str(exc))` solo con errores propios que ya traen un
    # texto en español hecho para el usuario (no pandas, pydantic ni libreria):
    # DatosNoValidos de `read_csv_smart`, DossierInvalido y
    # ModeloEjecutableInvalido.
    ("services/ingest.py", MARCA_STR),
    ("services/human_layer.py", MARCA_STR),
    ("services/outcomes.py", MARCA_STR),
    ("services/dossiers.py", MARCA_STR),
    ("services/model_registry.py", MARCA_STR),
    # `tarea.py` traduce el `DatosNoValidos` de `validar_mapeo_por_tipo`.
    ("services/tarea.py", MARCA_STR),
}

# Los textos con `?confirm=true` solo los ve quien llama a la API o al MCP, y
# necesitan nombrar el parámetro: no llevan ruta, así que no entran en las
# reglas de arriba; este test no los toca.


def _constantes_de_modulo(arbol: ast.Module) -> dict[str, ast.expr]:
    return {
        t.id: n.value
        for n in arbol.body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }


def _detalle(llamada: ast.Call) -> ast.expr | None:
    if len(llamada.args) >= 2:
        return llamada.args[1]
    for k in llamada.keywords:
        if k.arg == "detail":
            return k.value
    return None


def _partes(
    nodo: ast.expr, constantes: dict[str, ast.expr], hondura: int = 0
) -> tuple[list[str], list[str]]:
    """(texto literal por trozos, nombres interpolados) de un detalle."""
    if hondura > 3:
        return [], []
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return [nodo.value], []
    if isinstance(nodo, ast.JoinedStr):
        textos: list[str] = []
        nombres: list[str] = []
        for v in nodo.values:
            if isinstance(v, ast.Constant):
                textos.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                base = v.value
                if isinstance(base, ast.Name):
                    nombres.append(base.id)
                elif (
                    isinstance(base, ast.Call)
                    and isinstance(base.func, ast.Name)
                    and base.func.id in ("str", "repr")
                    and base.args
                    and isinstance(base.args[0], ast.Name)
                ):
                    nombres.append(base.args[0].id)
        return textos, nombres
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        t1, n1 = _partes(nodo.left, constantes, hondura + 1)
        t2, n2 = _partes(nodo.right, constantes, hondura + 1)
        return t1 + t2, n1 + n2
    if isinstance(nodo, ast.Name) and nodo.id in constantes:
        return _partes(constantes[nodo.id], constantes, hondura + 1)
    # `HTTPException(422, str(exc))` pasa la excepción tal cual: se marca como
    # interpolada y solo la lista blanca (errores propios en español) la admite.
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Name)
        and nodo.func.id in ("str", "repr")
        and nodo.args
        and isinstance(nodo.args[0], ast.Name)
    ):
        return [MARCA_STR], [nodo.args[0].id]
    return [], []


def _recoger() -> list[tuple[str, int, str, list[str]]]:
    hallazgos = []
    for ruta in sorted(APP.rglob("*.py")):
        relativa = ruta.relative_to(APP).as_posix()
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        constantes = _constantes_de_modulo(arbol)
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, "id", getattr(nodo.func, "attr", None))
            if nombre != "HTTPException":
                continue
            detalle = _detalle(nodo)
            if detalle is None:
                continue
            textos, nombres = _partes(detalle, constantes)
            hallazgos.append((relativa, nodo.lineno, "".join(textos), nombres))
    return hallazgos


def _en_lista_blanca(fichero: str, texto: str) -> bool:
    return any(f == fichero and frag in texto for f, frag in LISTA_BLANCA)


def test_el_recorrido_encuentra_los_httpexception_de_la_app():
    hallazgos = _recoger()
    assert len(hallazgos) > 150
    assert any(f == "errores.py" or f.startswith("routers/") for f, *_ in hallazgos)


def test_ningun_mensaje_interpola_la_excepcion():
    fallos = [
        f"{f}:{n}: {texto!r} interpola {nombres}"
        for f, n, texto, nombres in _recoger()
        if not _en_lista_blanca(f, texto) and NOMBRES_DE_EXCEPCION & set(nombres)
    ]
    assert not fallos, "mensajes con cola de excepción:\n" + "\n".join(fallos)


def test_ningun_mensaje_nombra_una_ruta_de_la_api():
    fallos = [
        f"{f}:{n}: {texto!r}"
        for f, n, texto, _ in _recoger()
        if not _en_lista_blanca(f, texto) and RUTA_DE_API.search(texto)
    ]
    assert not fallos, "mensajes que nombran una ruta de la API:\n" + "\n".join(fallos)


def test_str_de_excepcion_solo_con_errores_propios_en_espanol():
    """`HTTPException(422, str(exc))` solo dentro de un `except` de un error propio
    (no pandas ni librería): la lista blanca de arriba es por fichero y esto la acota."""
    permitidos = {"DatosNoValidos", "DossierInvalido", "ModeloEjecutableInvalido", "KeyError"}
    sueltos = []
    for relativa, _ in {(f, 0) for f, frag in LISTA_BLANCA if frag == MARCA_STR}:
        arbol = ast.parse((APP / relativa).read_text(encoding="utf-8"))
        for manejador in (n for n in ast.walk(arbol) if isinstance(n, ast.ExceptHandler)):
            tipo = ast.unparse(manejador.type) if manejador.type is not None else ""
            nombres = {t.strip(" ()").split(".")[-1] for t in tipo.split(",")}
            for nodo in ast.walk(manejador):
                if (
                    isinstance(nodo, ast.Call)
                    and getattr(nodo.func, "id", None) == "HTTPException"
                    and MARCA_STR in "".join(_partes(_detalle(nodo) or nodo, {})[0])
                    and not nombres <= permitidos
                ):
                    sueltos.append(f"{relativa}:{nodo.lineno} captura {tipo!r}")
    assert not sueltos, "str(exc) con una excepción que no es propia: " + "; ".join(sueltos)


def test_los_404_de_los_routers_usan_la_plantilla_unica():
    """Los 404 de los routers pasan por `no_encontrado`."""
    sueltos = []
    for ruta in sorted((APP / "routers").glob("*.py")):
        relativa = f"routers/{ruta.name}"
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if (
                isinstance(nodo, ast.Call)
                and getattr(nodo.func, "id", None) == "HTTPException"
                and nodo.args
                and isinstance(nodo.args[0], ast.Constant)
                and nodo.args[0].value == 404
                and "no existe: vuelve" not in "".join(_partes(_detalle(nodo) or nodo, {})[0])
                and "no_encontrado" not in ast.unparse(nodo)
            ):
                sueltos.append(f"{relativa}:{nodo.lineno}")
    assert not sueltos, f"404 que no usan errores.no_encontrado: {sueltos}"


def test_la_plantilla_del_404_en_la_api_usa_el_vocabulario_de_la_interfaz(client: TestClient):
    casos = {
        "/api/projects/99999/alerts": "modelo 99999 no existe: vuelve a la lista de modelos",
        "/api/alerts/99999": "alerta 99999 no existe: vuelve a la lista de alertas",
        "/api/jobs/99999": "trabajo 99999 no existe: vuelve a la lista de trabajos",
        "/api/risks/99999": "riesgo 99999 no existe: vuelve a la lista de riesgos",
    }
    for ruta, esperado in casos.items():
        resp = client.get(ruta)
        assert resp.status_code == 404, (ruta, resp.text)
        assert resp.json()["detail"] == esperado, ruta


def test_muestra_de_422_en_espanol_sobre_la_app_real(client: TestClient):
    muestras = [
        client.post("/api/projects", json={"domain": "reuma"}),
        client.post("/api/projects", json={"name": ["a"], "domain": "reuma"}),
        client.post(
            "/api/projects", content=b"{roto", headers={"content-type": "application/json"}
        ),
        client.get("/api/events", params={"limit": "muchos"}),
    ]
    ingles = (
        "Field required",
        "Input should",
        "Extra inputs",
        "String should",
        "Value error",
        "valid integer",
    )
    for resp in muestras:
        assert resp.status_code == 422, resp.text
        for error in resp.json()["detail"]:
            assert set(error) >= {"loc", "msg", "type"}
            assert not any(t in error["msg"] for t in ingles), error
