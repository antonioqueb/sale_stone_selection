# -*- coding: utf-8 -*-
from odoo import models

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        """
        Enganche para detectar cambios en la reserva y actualizar la SO.
        """
        res = super(StockMove, self)._recompute_state()
        
        # CORRECCIÓN: Si estamos en medio de una sincronización "SO -> Stock", 
        # saltamos la sincronización inversa para evitar errores de MissingError 
        # y bucles infinitos.
        if not self.env.context.get('skip_back_sync'):
            self._sync_lots_back_to_so()
            
        return res

    def _sync_lots_back_to_so(self):
        """
        Si cambian los lotes en el albarán (stock.move.line), actualizamos la SO.
        """
        for move in self:
            # CORRECCIÓN ODOO 19: Usar picking_type_id.code en lugar de picking_type_code
            if move.sale_line_id and move.picking_type_id.code == 'outgoing':
                # Obtener los lotes actualmente reservados en el movimiento
                current_reservation_lots = move.move_line_ids.mapped('lot_id')
                
                # Comparar con lo que tiene la SO
                so_lots = move.sale_line_id.lot_ids
                
                # Si son diferentes, actualizar la SO
                if set(current_reservation_lots.ids) != set(so_lots.ids):
                    # Escribimos en el contexto para que el write de la SO sepa que viene del stock
                    move.sale_line_id.with_context(skip_stock_sync=True).write({
                        'lot_ids': [(6, 0, current_reservation_lots.ids)]
                    })