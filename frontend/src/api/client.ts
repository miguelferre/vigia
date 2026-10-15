/**
 * Cliente HTTP de la API de Vigía.
 *
 * Base `/api` (en desarrollo el proxy de Vite lo redirige al backend; en la
 * app empaquetada FastAPI sirve el estático y la API en el mismo origen).
 * Cada petición lleva las cabeceras de actor de la sesión: el backend las usa
 * para el diario de tres carriles.
 */

import type { JsonValue } from "./types";

export const API_BASE = "/api";

/** Texto de la red caída: el programa local ya no responde. */
export const MENSAJE_RED_CAIDA =
  "no se puede contactar con Vigía: comprueba que la ventana del programa sigue abierta y vuelve a intentarlo";

/** Cabeceras de actor que envía el cliente en cada petición. */
export interface ActorHeaders {
  actor: string;
  role: string;
}

/**
 * Actor vigente. `SessionProvider` lo mantiene al día con `setActorHeaders`
 * para que el cliente no dependa de React.
 */
let actorActual: ActorHeaders = { actor: "anonimo", role: "gestor" };

export function setActorHeaders(next: ActorHeaders): void {
  actorActual = next;
}

export function getActorHeaders(): ActorHeaders {
  return actorActual;
}

/** Error de la API con el código y el detalle que devuelve FastAPI. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: JsonValue;

  constructor(status: number, detail: JsonValue, message?: string) {
    super(message ?? detalleATexto(detail, status));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Convierte el `detail` de FastAPI (texto o lista de errores 422) a una línea. */
export function detalleATexto(detail: JsonValue, status?: number): string {
  if (typeof detail === "string" && detail.length > 0) return detail;
  if (Array.isArray(detail)) {
    const lineas = detail.map((item) => {
      if (item && typeof item === "object" && !Array.isArray(item)) {
        const campo = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        const msg = typeof item.msg === "string" ? item.msg : "valor no válido";
        return campo ? `${campo}: ${msg}` : msg;
      }
      return String(item);
    });
    if (lineas.length > 0) return lineas.join("; ");
  }
  return status === undefined ? "error de la API" : `error ${status} de la API`;
}

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue | QueryValue[]>;

/** Construye la query string omitiendo `null` y `undefined`. */
export function buildQuery(params?: QueryParams): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [clave, valor] of Object.entries(params)) {
    if (valor === null || valor === undefined) continue;
    if (Array.isArray(valor)) {
      const unidos = valor.filter((v) => v !== null && v !== undefined).join(",");
      if (unidos) sp.set(clave, unidos);
      continue;
    }
    sp.set(clave, String(valor));
  }
  const texto = sp.toString();
  return texto ? `?${texto}` : "";
}

function cabeceras(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  h.set("X-Vigia-Actor-Kind", "humano");
  h.set("X-Vigia-Actor", actorActual.actor);
  h.set("X-Vigia-Role", actorActual.role);
  return h;
}

async function parsear<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const texto = await res.text();
  let cuerpo: JsonValue = null;
  if (texto) {
    try {
      cuerpo = JSON.parse(texto) as JsonValue;
    } catch {
      cuerpo = texto;
    }
  }
  if (!res.ok) {
    const detalle =
      cuerpo && typeof cuerpo === "object" && !Array.isArray(cuerpo) && "detail" in cuerpo
        ? (cuerpo.detail as JsonValue)
        : cuerpo;
    throw new ApiError(res.status, detalle);
  }
  return cuerpo as T;
}

export interface RequestOptions {
  params?: QueryParams;
  signal?: AbortSignal;
  headers?: HeadersInit;
}

async function pedir<T>(
  metodo: string,
  ruta: string,
  cuerpo?: unknown,
  opciones: RequestOptions = {},
): Promise<T> {
  const h = cabeceras(opciones.headers);
  let body: BodyInit | undefined;
  if (cuerpo !== undefined) {
    h.set("Content-Type", "application/json");
    body = JSON.stringify(cuerpo);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${ruta}${buildQuery(opciones.params)}`, {
      method: metodo,
      headers: h,
      body,
      signal: opciones.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, MENSAJE_RED_CAIDA);
  }
  return parsear<T>(res);
}

export const api = {
  get: <T>(ruta: string, opciones?: RequestOptions) => pedir<T>("GET", ruta, undefined, opciones),
  post: <T>(ruta: string, cuerpo?: unknown, opciones?: RequestOptions) =>
    pedir<T>("POST", ruta, cuerpo ?? {}, opciones),
  put: <T>(ruta: string, cuerpo?: unknown, opciones?: RequestOptions) =>
    pedir<T>("PUT", ruta, cuerpo ?? {}, opciones),
  patch: <T>(ruta: string, cuerpo?: unknown, opciones?: RequestOptions) =>
    pedir<T>("PATCH", ruta, cuerpo ?? {}, opciones),
  /** `DELETE`; admite cuerpo porque `DELETE /batches/{id}` exige `ActorBody`. */
  del: <T>(ruta: string, cuerpo?: unknown, opciones?: RequestOptions) =>
    pedir<T>("DELETE", ruta, cuerpo, opciones),

  /** Envío multipart (subida de datasets y de registros de uso). */
  upload: async <T>(
    ruta: string,
    form: FormData,
    opciones: RequestOptions = {},
  ): Promise<T> => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${ruta}${buildQuery(opciones.params)}`, {
        method: "POST",
        headers: cabeceras(opciones.headers),
        body: form,
        signal: opciones.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, MENSAJE_RED_CAIDA);
    }
    return parsear<T>(res);
  },

  /** Descarga un fichero de la API y dispara el guardado en el navegador. */
  download: async (ruta: string, nombre: string, opciones: RequestOptions = {}): Promise<void> => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${ruta}${buildQuery(opciones.params)}`, {
        headers: cabeceras(opciones.headers),
        signal: opciones.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, MENSAJE_RED_CAIDA);
    }
    if (!res.ok) await parsear(res);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    a.click();
    // Revocar en la misma tarea que el click aborta la descarga de forma
    // intermitente en Chromium: se difiere para dar tiempo al navegador.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

/** Mensaje legible de cualquier error para toasts y pantallas. */
export function mensajeDeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "error desconocido";
}
