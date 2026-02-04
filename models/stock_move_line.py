# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear líneas en el Picking (desde la Grilla o manualmente), 
        sincronizar hacia la Orden de Venta.
        """
        lines = super(StockMoveLine, self).create(vals_list)
        
        # Sincronizar solo si no venimos de la confirmación inicial o sync inverso
        if not self.env.context.get('skip_stone_sync_so') and not self.env.context.get('is_stone_confirming'):
            lines._sync_to_sale_order_line()
        
        return lines

    def write(self, vals):
        """
        Al modificar líneas (ej. cambiar cantidad o lote), sincronizar.
        """
        res = super(StockMoveLine, self).write(vals)
        
        # Si cambió el lote o la cantidad, sincronizar hacia SO
        if ('lot_id' in vals or 'quantity' in vals) and not self.env.context.get('skip_stone_sync_so'):
            self._sync_to_sale_order_line()
        
        return res

    def unlink(self):
        """
        Al borrar líneas en el Picking, quitar los lotes de la Orden de Venta.
        """
        # Antes de borrar, identificamos qué moves/sale_lines se verán afectados
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        res = super(StockMoveLine, self).unlink()
        
        if not self.env.context.get('skip_stone_sync_so') and not self.env.context.get('is_stone_confirming'):
            moves_to_sync._sync_stone_sale_lines()
        
        return res

    def _sync_to_sale_order_line(self):
        """
        Helper para disparar la sincronización desde las líneas hacia SO.
        Solo sincroniza movimientos que tienen línea de venta asociada.
        """
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        if moves_to_sync:
            _logger.info("[STONE SYNC] Sincronizando %s movimientos hacia SO", len(moves_to_sync))
            moves_to_sync._sync_stone_sale_lines()