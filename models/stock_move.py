# -*- coding: utf-8 -*-
from odoo import models, api, logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        """
        Detecta cambios en las reservas del Picking y actualiza la Orden de Venta.
        """
        res = super(StockMove, self)._recompute_state()
        
        # PROTEGER LA SELECCIÓN:
        # Si estamos en medio de la confirmación de la venta (is_stone_confirming),
        # NO sincronizamos hacia atrás. Confiamos en que la SO es la fuente de la verdad.
        if self.env.context.get('is_stone_confirming'):
            return res

        if not self.env.context.get('skip_back_sync'):
            self._sync_lots_back_to_so()
            
        return res

    def _sync_lots_back_to_so(self):
        """ Sincroniza stock.move.line -> sale.order.line.lot_ids """
        for move in self:
            if move.sale_line_id and move.picking_type_id.code == 'outgoing':
                # Obtener lotes actuales en el movimiento
                current_reservation_lots = move.move_line_ids.mapped('lot_id')
                
                # Obtener lotes en la SO
                so_lots = move.sale_line_id.lot_ids
                
                # Comparación de IDs (Set)
                if set(current_reservation_lots.ids) != set(so_lots.ids):
                    _logger.info(f"[STONE] Sincronizando Picking {move.picking_id.name} -> SO {move.sale_line_id.order_id.name}")
                    # Usamos skip_stock_sync para evitar bucles infinitos si escribimos en la SO
                    move.sale_line_id.with_context(skip_stock_sync=True).write({
                        'lot_ids': [(6, 0, current_reservation_lots.ids)]
                    })