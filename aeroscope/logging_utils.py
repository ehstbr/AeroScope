"""Logs de diagnóstico do AeroScope, visíveis no terminal.

Por padrão apenas eventos relevantes de fotografias são exibidos; `--debug`
ativa detalhes de validação e processamento. Sem registrar o conteúdo de imagens.
"""
from __future__ import annotations
import logging
import sys


def configure_logging(debug: bool = False) -> None:
    logger = logging.getLogger('aeroscope')
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    ))
    logger.addHandler(handler)
