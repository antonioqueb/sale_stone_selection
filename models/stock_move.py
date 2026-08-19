# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        res = super(StockMove, self)._recompute_state()
        if self.env.context.get('is_stone_confirming') or self.env.context.get('skip_stone_sync'):
            return res
        return res

    def _sync_stone_sale_lines(self):
        if self.env.context.get('is_stone_confirming'):
            _logger.info("[STONE SYNC] Saltando sync durante confirmación inicial")
            return

        for move in self:
            if not move.sale_line_id:
                continue

            if move.state in ['done', 'cancel']:
                continue

            sol = move.sale_line_id

            all_lot_ids = set()

            for sibling_move in sol.move_ids:
                if sibling_move.state == 'cancel':
                    continue
                for ml in sibling_move.move_line_ids:
                    if ml.lot_id:
                        all_lot_ids.add(ml.lot_id.id)

            existing_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()

            # REGLA DE ORO (2026-08-07, pedida explícitamente): LAS ENTREGAS
            # MANDAN. Lo que viva en los pickings (pick/out) ES la selección:
            # los lotes presentes ahí se OFICIALIZAN en el selector visual,
            # incluidos los que el vendedor no había marcado. Si los pickings
            # no traen ningún lote, gana el selector (este sync no limpia
            # nada — la dirección selector→picking la lleva
            # _sync_lots_to_picking_moves).
            if not all_lot_ids:
                continue

            # ═══ LA ASIGNACIÓN DEL USUARIO NO SE TOCA (2026-08-16) ═══
            # La "regla de oro" de arriba se escribió para que la entrega
            # OFICIALICE lo que el vendedor no había marcado. Pero el write
            # es un (6, 0, ...) — un REEMPLAZO — así que además borraba todo
            # lo asignado que no estuviera en el picking en ese instante.
            #
            # Y eso pasa todo el tiempo sin que nadie toque la venta: si
            # almacén des-reserva la entrega, si Odoo re-reserva y toma
            # otras placas, o si la entrega es parcial, las placas que el
            # usuario asignó desaparecen solas de la orden. Ese es el
            # "asigné material y luego ya no aparece asignado".
            #
            # Regla del negocio: en una orden de venta el material SOLO se
            # desasigna cuando una persona lo desasigna. El sync suma, no
            # resta. Para quitar placas está el selector (que sí baja al
            # picking) y el desasignador de Torre de Control.
            all_lot_ids |= existing_lots

            # Nota histórica: aquí vivían dos parches parciales que
            # preservaban solo algunos lotes (movimientos sin líneas, y lotes
            # reservados en tránsito activo — el caso V/131, que perdió 41
            # placas de EMBARQUE/2026/0035 al recibir el EMBARQUE/2026/0029).
            # La unión de arriba los cubre a los dos y a todos los demás
            # casos que no habíamos encontrado todavía.
            added = all_lot_ids - existing_lots
            if added:
                added_names = self.env['stock.lot'].browse(
                    list(added)).mapped('name')
                _logger.info(
                    "[STONE SYNC] Oficializando en el selector lotes "
                    "presentes en la ENTREGA (SO Line %s): %s",
                    sol.id, added_names)

            if all_lot_ids == existing_lots:
                continue

            _logger.info("[STONE SYNC] Picking %s -> SO Line %s",
                         move.picking_id.name if move.picking_id else 'N/A', sol.id)

            # SEMBRAR EL DESGLOSE de los lotes formato/pieza recién
            # oficializados: sin entrada en x_lot_breakdown_json, el lote se
            # interpretaba como COMPLETO en todos los consumidores (visual,
            # ratchet, re-sync a picking con reparto uniforme). La cantidad
            # sembrada es la de sus move lines en los pickings — exactamente
            # lo que la entrega dice.
            write_vals = {'lot_ids': [(6, 0, list(all_lot_ids))]}
            if added and 'x_lot_breakdown_json' in sol._fields:
                breakdown = dict(sol.x_lot_breakdown_json or {})
                changed_bd = False
                for lot_id in added:
                    lot = self.env['stock.lot'].browse(lot_id)
                    tipo = ''
                    if 'x_tipo' in lot._fields and lot.x_tipo:
                        tipo = str(lot.x_tipo).strip().lower()
                    if tipo not in ('formato', 'pieza'):
                        continue
                    if sol._som_breakdown_qty_for_lot(breakdown, lot) is not None:
                        continue
                    ml_qty = sum(
                        ml.quantity or 0.0
                        for ml in sol.move_ids.mapped('move_line_ids')
                        if ml.lot_id.id == lot_id
                        and ml.state not in ('cancel',)
                    )
                    if ml_qty > 0:
                        breakdown[str(lot_id)] = ml_qty
                        changed_bd = True
                if changed_bd:
                    write_vals['x_lot_breakdown_json'] = breakdown

            try:
                # tc_qty_sync_from_lots: la oficialización viene de la
                # ENTREGA y NO debe derivar el Solicitado. Sin esta marca,
                # el ratchet de Torre de Control subía la cantidad a cobrar
                # al oficializar lotes entregados (V/150: una línea de
                # 13.46 con lotes de entregas previas oficializados saltó a
                # 26.92 EN CALIENTE, infló la orden $80,050.93 y el candado
                # de pago bloqueó la remisión). El Solicitado solo se mueve
                # por decisión comercial, nunca por sincronizar la entrega.
                sol.with_context(
                    skip_stone_sync_picking=True,
                    tc_qty_sync_from_lots=True,
                    som_lot_log_reason=(
                        'Sincronización desde la entrega %s (STONE SYNC): la '
                        'línea de venta se alinea con lo que traen los '
                        'movimientos' % (
                            move.picking_id.name if move.picking_id else 'N/A')
                    ),
                ).write(write_vals)
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes",
                             sol.id, len(all_lot_ids))
            except UserError:
                # Error de negocio (validador de holds, tope de stock…): debe
                # LLEGAR al usuario. Tragarlo dejaba picking y línea de venta
                # divergentes en silencio — justo lo que este sync evita.
                raise
            except Exception:
                _logger.exception(
                    "[STONE SYNC] Error inesperado actualizando SO Line %s",
                    sol.id,
                )
                raise UserError(_(
                    'No se pudo sincronizar los lotes del picking con la línea '
                    'de venta %s. Revisa el registro del servidor.'
                ) % sol.id)

    def write(self, vals):
        res = super(StockMove, self).write(vals)

        if 'move_line_ids' in vals and not self.env.context.get('skip_stone_sync_so'):
            for move in self:
                if move.sale_line_id and move.state not in ['done', 'cancel']:
                    move._sync_stone_sale_lines()

        # LÍNEAS HUÉRFANAS: las move lines creadas a mano por el stone sync
        # cuando el move aún no tenía picking nacían con picking_id vacío y
        # NUNCA se corregían — el pick ticket recorre las líneas del picking
        # y encontraba cero (caso V/458 y 5 pedidos más, 17 moves). Cuando
        # el move recibe su picking, se propaga a sus líneas huérfanas.
        if vals.get('picking_id'):
            for move in self:
                orphans = move.move_line_ids.filtered(
                    lambda ml: not ml.picking_id
                    and ml.state not in ('done', 'cancel'))
                if orphans:
                    orphans.with_context(skip_stone_sync_so=True).write(
                        {'picking_id': move.picking_id.id})
                    _logger.info(
                        '[STONE SYNC] %s move line(s) huérfanas adoptadas '
                        'por el picking %s (move %s).',
                        len(orphans), move.picking_id.name, move.id)

        return res