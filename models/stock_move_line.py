# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # ══════════════════════════════════════════════════════════════════
    # POR QUÉ YA NO SE EXIGE QUE LA LÍNEA TENGA LOTES (2026-08-16)
    #
    # Estos tres ganchos filtraban por `sale_line_id.lot_ids`: solo
    # sincronizaban si la línea de venta YA tenía placas. Es un candado
    # circular — una línea que nace vacía no puede llenarse nunca:
    #
    #   picking recibe placas → sync se salta porque lot_ids está vacío
    #                        → lot_ids sigue vacío → se vuelve a saltar
    #
    # Ese es el "en la entrega están las placas pero el selector visual no
    # las muestra", y es la razón de que los tres caminos de asignación
    # (carrito, migración de apartado y selector directo) no se comportaran
    # igual: el selector directo llenaba lot_ids primero y por eso a él sí
    # le funcionaba el sync; los otros dos dependían de código especial
    # propio, y cuando ese código no aplicaba, quedaban desincronizados.
    #
    # Quitar el candado es seguro AHORA porque el sync es ADITIVO: solo
    # oficializa lo que trae la entrega y jamás quita lo que una persona
    # asignó (ver stock_move.py). Antes de ese cambio, soltarlo habría
    # dejado que la entrega borrara selecciones.
    #
    # Se filtra por ml.lot_id: una línea de movimiento sin lote no tiene
    # nada que oficializar y no vale la pena despertar el sync.
    # ══════════════════════════════════════════════════════════════════


    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear líneas en el Picking, sincronizar hacia la SO SOLO si la línea
        de venta tiene lotes seleccionados manualmente.
        """
        lines = super(StockMoveLine, self).create(vals_list)
        
        if (not self.env.context.get('skip_stone_sync_so') 
            and not self.env.context.get('is_stone_confirming')):
            # Toda línea con lote que cuelgue de una venta se oficializa.
            lines_to_sync = lines.filtered(
                lambda ml: ml.lot_id and ml.move_id.sale_line_id
            )
            if lines_to_sync:
                lines_to_sync._sync_to_sale_order_line()
        
        return lines

    def write(self, vals):
        res = super(StockMoveLine, self).write(vals)
        
        if (('lot_id' in vals or 'quantity' in vals) 
            and not self.env.context.get('skip_stone_sync_so')):
            lines_to_sync = self.filtered(
                lambda ml: ml.lot_id and ml.move_id.sale_line_id
            )
            if lines_to_sync:
                lines_to_sync._sync_to_sale_order_line()
        
        return res

    def unlink(self):
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        res = super(StockMoveLine, self).unlink()
        
        if (not self.env.context.get('skip_stone_sync_so') 
            and not self.env.context.get('is_stone_confirming')):
            if moves_to_sync:
                moves_to_sync._sync_stone_sale_lines()
        
        return res

    def _sync_to_sale_order_line(self):
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        if moves_to_sync:
            _logger.info("[STONE SYNC] Sincronizando %s movimientos hacia SO", len(moves_to_sync))
            moves_to_sync._sync_stone_sale_lines()