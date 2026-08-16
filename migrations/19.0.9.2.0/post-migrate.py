"""Reconcilia las órdenes que quedaron con placas en la entrega y el
selector visual vacío.

EL DAÑO QUE REPARA
------------------
Los ganchos de sincronización filtraban por `sale_line_id.lot_ids`: solo
sincronizaban si la línea de venta YA tenía placas. Candado circular — una
línea que nacía vacía no se llenaba nunca. Resultado: la entrega con las
placas reservadas y el selector en blanco.

Desde 19.0.9.1.0 eso ya no vuelve a pasar, pero el sync corre cuando algo
se mueve: las órdenes que YA quedaron torcidas siguen así hasta que alguien
las toque. Esta migración las endereza de una vez.

REGLAS QUE RESPETA
------------------
· SOLO SUMA. Nunca quita una placa de la línea de venta — misma regla que
  el sync: en una orden de venta el material solo lo desasigna una persona.
· Mismo contexto de escritura que el sync (tc_qty_sync_from_lots y
  skip_stone_sync_picking). Sin tc_qty_sync_from_lots, oficializar placas
  MUEVE la cantidad solicitada: hay un caso real de una línea que saltó de
  13.46 a 26.92 m² e infló la orden $80,050.93.
· Solo órdenes en estado 'sale'. Las 'done' son historia cerrada: tocarlas
  no ayuda a nadie y sí puede despertar validaciones sobre documentos ya
  liquidados. Se cuentan y se reportan, pero no se tocan.
· Cada línea va en su propio SAVEPOINT: si una tiene un hold ajeno o
  cualquier otra validación que la rechace, se salta y las demás siguen.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

RAZON = ('Reconciliación 19.0.9.2.0: la entrega ya traía estas placas pero '
         'el selector estaba vacío (candado circular del sync)')


def _lotes_de_la_entrega(line):
    """Lotes presentes en los movimientos vivos de la línea."""
    lotes = set()
    for move in line.move_ids:
        if move.state == 'cancel':
            continue
        for ml in move.move_line_ids:
            if ml.lot_id:
                lotes.add(ml.lot_id.id)
    return lotes


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    SaleOrderLine = env['sale.order.line']
    if 'lot_ids' not in SaleOrderLine._fields:
        _logger.warning('[RECONCILIA] sale.order.line no tiene lot_ids; nada '
                        'que hacer.')
        return

    lineas = SaleOrderLine.search([
        ('order_id.state', '=', 'sale'),
        ('display_type', '=', False),
        ('product_id', '!=', False),
    ])
    _logger.info('[RECONCILIA] Revisando %s línea(s) de órdenes abiertas…',
                 len(lineas))

    ordenes = set()
    lineas_ok = placas = 0
    fallidas = []

    for line in lineas:
        entrega = _lotes_de_la_entrega(line)
        if not entrega:
            continue
        faltantes = entrega - set(line.lot_ids.ids)
        if not faltantes:
            continue

        try:
            with cr.savepoint():
                line.with_context(
                    skip_stone_sync_picking=True,
                    tc_qty_sync_from_lots=True,
                    som_lot_log_reason=RAZON,
                ).write({'lot_ids': [(4, lot_id) for lot_id in sorted(faltantes)]})
        except Exception as exc:
            fallidas.append((line.order_id.name, line.id,
                             str(exc).strip().split('\n')[0][:120]))
            continue

        ordenes.add(line.order_id.name)
        lineas_ok += 1
        placas += len(faltantes)
        _logger.info('[RECONCILIA] %s línea %s: +%s placa(s) al selector',
                     line.order_id.name, line.id, len(faltantes))

    _logger.info(
        '[RECONCILIA] LISTO — %s placa(s) devueltas al selector en %s línea(s) '
        'de %s orden(es): %s',
        placas, lineas_ok, len(ordenes),
        ', '.join(sorted(ordenes)) or '(ninguna)')

    if fallidas:
        _logger.warning(
            '[RECONCILIA] %s línea(s) NO se pudieron reconciliar (revisar a '
            'mano):', len(fallidas))
        for orden, line_id, err in fallidas:
            _logger.warning('[RECONCILIA]   %s línea %s → %s',
                            orden, line_id, err)

    # Las cerradas solo se reportan: son historia y no se tocan.
    cerradas = env['sale.order.line'].search([
        ('order_id.state', '=', 'done'),
        ('display_type', '=', False),
        ('product_id', '!=', False),
    ])
    pendientes_done = {
        l.order_id.name for l in cerradas
        if (_lotes_de_la_entrega(l) - set(l.lot_ids.ids))
    }
    if pendientes_done:
        _logger.info(
            '[RECONCILIA] Además hay %s orden(es) CERRADAS con la misma '
            'diferencia. No se tocan por ser historia; si se quieren '
            'enderezar, pídelo: %s',
            len(pendientes_done), ', '.join(sorted(pendientes_done)))
