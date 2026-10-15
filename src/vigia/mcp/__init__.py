"""Servidor MCP de Vigía: FastMCP por stdio sobre la API HTTP local.

Nunca abre la base de datos: habla con `vigia serve` por loopback con las
cabeceras `X-Vigia-*`.
"""
