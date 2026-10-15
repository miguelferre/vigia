"""Servicio de lectura y escritura de ajustes.

Los ajustes editables viven en la tabla `setting` (una fila por clave). `puerto`
solo tiene efecto en el próximo arranque; `data_dir` se muestra pero no se
edita (409); `mcp_token` se genera de forma perezosa en el primer acceso
(`ensure_mcp_token`), sin engancharlo al lifespan, y se devuelve enmascarado salvo `?reveal=true`. `llm.api_key`
nunca sale en claro fuera de la escritura misma: ni en `GET /settings` (con o
sin `?reveal=true`) ni en el evento `ajuste.cambiado`.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlmodel import Session

from vigia.app.bus import EventBus
from vigia.app.events import Actor, record_event
from vigia.app.models import Setting, now_iso

__all__ = [
    "EDITABLES",
    "ensure_mcp_token",
    "get_settings",
    "mask_secret",
    "patch_settings",
]

try:  # el módulo está en build/publico/privados.txt: el árbol público no lo trae
    from vigia.app.services.temas_privados import TEMAS_PRIVADOS
except ImportError:
    TEMAS_PRIVADOS = ()

_META_TEMA = re.compile(r'<meta\s+name="vigia-tema"\s+content="([a-z][a-z0-9_-]{0,31})"')


def _tema_unico_del_estatico() -> str | None:
    """Tema único del estático: la marca `<meta name="vigia-tema">` de un build con un
    solo tema (ni `miguel` ni `todos`). `None` si no hay estático o no es tema único."""
    index = Path(__file__).resolve().parents[2] / "static" / "index.html"
    try:
        marca = _META_TEMA.search(index.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if marca is None or marca.group(1) in ("miguel", "todos"):
        return None
    return marca.group(1)


TEMA_UNICO = _tema_unico_del_estatico()
TEMA_POR_DEFECTO = TEMA_UNICO or "miguel"
TEMAS = (TEMA_UNICO,) if TEMA_UNICO else (TEMA_POR_DEFECTO, *TEMAS_PRIVADOS)
MODOS_COLOR = ("claro", "oscuro", "sistema")
ROLES = ("gestor", "clinico", "auditor", "cliente")
IDIOMAS = ("es", "en")
LLM_BACKENDS = ("none", "ollama", "anthropic")

EDITABLES = ("tema", "modo_color", "rol", "idioma", "llm", "puerto")

_DEFAULTS: dict[str, Any] = {
    "tema": TEMA_POR_DEFECTO,
    "modo_color": "sistema",
    "rol": "clinico",
    "idioma": "es",
    "llm": {"backend": "none", "model": "", "base_url": "", "api_key": ""},
}


def url_es_local(url: str) -> bool:
    """`http(s)://` con host 127.0.0.1, localhost o ::1 (con o sin puerto)."""
    try:
        partes = urlsplit(url.strip())
        host = partes.hostname
        _ = partes.port  # un puerto no numérico lanza ValueError
    except ValueError:
        return False
    return partes.scheme in ("http", "https") and not partes.username and host in ("127.0.0.1", "localhost", "::1")


def mask_secret(value: str) -> str:
    """Enmascara un secreto dejando visibles como mucho los últimos cuatro caracteres."""
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def _get_value(session: Session, key: str, default: Any) -> Any:
    row = session.get(Setting, key)
    return row.value_json if row is not None else default


def _set_value(session: Session, key: str, value: Any) -> None:
    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value_json=value)
    else:
        row.value_json = value
        row.updated_at = now_iso()
    session.add(row)


def ensure_mcp_token(session: Session) -> str:
    """Devuelve el token MCP, generándolo si aún no existe. Idempotente."""
    row = session.get(Setting, "mcp_token")
    if row is not None and row.value_json:
        return str(row.value_json)
    token = secrets.token_hex(24)
    _set_value(session, "mcp_token", token)
    session.commit()
    return token


def get_settings(
    session: Session,
    *,
    port_default: int,
    data_dir: str,
    reveal: bool = False,
) -> dict[str, Any]:
    """Ajustes actuales, con `mcp_token` y `llm.api_key` enmascarados salvo `reveal=True`."""
    valores: dict[str, Any] = {clave: _DEFAULTS[clave] for clave in _DEFAULTS}
    for clave in EDITABLES:
        if clave == "puerto":
            continue
        valores[clave] = _get_value(session, clave, valores.get(clave))
    valores["puerto"] = _get_value(session, "puerto", port_default)
    # Un tema guardado que este build no admite (p. ej. uno privado en el árbol
    # público) cae al personal sin error.
    if valores["tema"] not in TEMAS:
        valores["tema"] = TEMA_POR_DEFECTO

    # `llm.api_key` no tiene excepción `reveal`, a diferencia de `mcp_token`: el diseño
    # exige que nunca se devuelva en claro por este endpoint (§3.10).
    llm = dict(valores.get("llm") or {})
    if llm.get("api_key"):
        llm = {**llm, "api_key": "***"}
    valores["llm"] = llm

    token = ensure_mcp_token(session)
    valores["mcp_token"] = token if reveal else mask_secret(token)
    valores["data_dir"] = data_dir
    return valores


def _validar(clave: str, valor: Any, *, actual: Any = None) -> Any:
    if clave == "tema":
        if valor not in TEMAS:
            raise HTTPException(422, f"tema debe ser uno de {', '.join(TEMAS)}; se recibió {valor!r}")
        return valor
    if clave == "modo_color":
        if valor not in MODOS_COLOR:
            raise HTTPException(
                422, f"modo_color debe ser uno de {', '.join(MODOS_COLOR)}; se recibió {valor!r}"
            )
        return valor
    if clave == "rol":
        if valor not in ROLES:
            raise HTTPException(422, f"rol debe ser uno de {', '.join(ROLES)}; se recibió {valor!r}")
        return valor
    if clave == "idioma":
        if valor not in IDIOMAS:
            raise HTTPException(422, f"idioma debe ser uno de {', '.join(IDIOMAS)}; se recibió {valor!r}")
        return valor
    if clave == "puerto":
        if not isinstance(valor, int) or isinstance(valor, bool) or not (1024 <= valor <= 65535):
            raise HTTPException(422, "puerto debe ser un entero entre 1024 y 65535")
        return valor
    if clave == "llm":
        if not isinstance(valor, dict):
            raise HTTPException(422, "llm debe ser un objeto")
        previo = dict(_DEFAULTS["llm"]) if not isinstance(actual, dict) else dict(actual)
        fusionado = {**previo, **valor}
        backend = fusionado.get("backend", "none")
        # Al cambiar de backend, la URL base de la configuración anterior no se arrastra.
        if backend != previo.get("backend", "none") and "base_url" not in valor:
            fusionado["base_url"] = ""
        if backend not in LLM_BACKENDS:
            raise HTTPException(
                422, f"llm.backend debe ser uno de {', '.join(LLM_BACKENDS)}; se recibió {backend!r}"
            )
        # activar un backend no local (`anthropic`, frente a `ollama`
        # que es local) exige la confirmación explícita de que los
        # formularios del dossier no llevan datos de personas afectadas.
        # `confirmacion_no_local` no se valida como parte del objeto `llm`
        # persistido (nunca se guarda en `Setting`): la lee `patch_settings`.
        backend_previo = previo.get("backend", "none")
        if backend == "anthropic" and backend_previo != "anthropic":
            confirmacion = str(valor.get("confirmacion_no_local", "") or "").strip()
            if not confirmacion:
                raise HTTPException(
                    422, "activar un backend no local exige la confirmación explícita"
                )
        # Ollama debe estar en este equipo; otro destino exige `confirmar_remoto`
        # (como `confirmacion_no_local`, no se guarda en `Setting("llm")`).
        base_url = str(fusionado.get("base_url", ""))
        cambia_destino = backend != previo.get("backend", "none") or base_url != str(previo.get("base_url", ""))
        sin_confirmar = valor.get("confirmar_remoto") is not True
        if backend == "ollama" and base_url and cambia_destino and sin_confirmar and not url_es_local(base_url):
            raise HTTPException(
                422,
                "la URL de Ollama no es de este equipo (127.0.0.1 o localhost): "
                "confirma el destino con confirmar_remoto",
            )
        api_key = str(fusionado.get("api_key", ""))
        # GET enmascara `llm.api_key` con el literal "***" (ver `get_settings`). Un PATCH
        # que reenvía ese valor tal cual, sin haberlo editado, no debe sustituir la clave
        # real por el literal: se trata como "sin cambio".
        if "api_key" in valor and api_key == "***" and previo.get("api_key"):
            api_key = str(previo.get("api_key", ""))
        return {
            "backend": backend,
            "model": str(fusionado.get("model", "")),
            "base_url": str(fusionado.get("base_url", "")),
            "api_key": api_key,
        }
    raise HTTPException(422, f"ajuste desconocido o de solo lectura: {clave!r}")


def patch_settings(
    session: Session,
    *,
    actor: Actor,
    motivo: str,
    values: dict[str, Any],
    port_default: int,
    data_dir: str,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Valida y aplica los cambios de `values`; deja un evento `ajuste.cambiado`."""
    if not values:
        raise HTTPException(422, "values no puede estar vacío")

    after_evento: dict[str, Any] = {}
    confirmacion_registrada: str | None = None
    destino_remoto: str | None = None
    for clave, valor in values.items():
        if clave == "data_dir":
            raise HTTPException(409, "data_dir no se puede editar; se cambia con --data-dir o la variable VIGIA_HOME")
        if clave == "mcp_token":
            raise HTTPException(422, "mcp_token es de solo lectura")
        if clave not in EDITABLES:
            raise HTTPException(422, f"ajuste desconocido: {clave!r}")
        actual = _get_value(session, clave, _DEFAULTS.get(clave)) if clave == "llm" else None
        validado = _validar(clave, valor, actual=actual)
        if clave == "llm":
            backend_previo = (actual or {}).get("backend", "none") if isinstance(actual, dict) else "none"
            if validado.get("backend") == "anthropic" and backend_previo != "anthropic":
                confirmacion_registrada = str(valor.get("confirmacion_no_local", "")).strip()
            url = str(validado.get("base_url", ""))
            if validado.get("backend") == "ollama" and url and not url_es_local(url) and valor.get("confirmar_remoto") is True:
                destino_remoto = url
        _set_value(session, clave, validado)
        if clave == "llm":
            copia = dict(validado)
            if copia.get("api_key"):
                copia["api_key"] = "***"
            after_evento[clave] = copia
        else:
            after_evento[clave] = validado

    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="ajuste.cambiado",
        object_type="setting",
        motivo=motivo,
        after=after_evento,
        bus=bus,
    )
    # la confirmación en sí no se persiste en `Setting("llm")` (solo
    # en este segundo evento, append-only), con actor y fecha.
    if confirmacion_registrada:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="ajuste.llm_confirmado",
            object_type="setting",
            motivo=motivo,
            after={"backend": "anthropic", "confirmacion": confirmacion_registrada},
            bus=bus,
        )
    if destino_remoto:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="ajuste.llm_confirmado",
            object_type="setting",
            motivo=motivo,
            after={"backend": "ollama", "destino_remoto": destino_remoto},
            bus=bus,
        )
    session.commit()
    return get_settings(session, port_default=port_default, data_dir=data_dir)
