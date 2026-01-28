# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lot_ids = fields.Many2many(
        'stock.lot', 
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=False
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """ Recalcula cantidad basada en lotes seleccionados """
        if not self.lot_ids:
            return

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])
        
        # Usamos mapped para sumarizar correctamente
        total_qty = sum(quants.mapped('quantity'))
        
        if total_qty > 0:
            self.product_uom_qty = total_qty

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Sobreescritura: Al confirmar la venta (crear movimientos),
        asignamos inmediatamente los lotes seleccionados a los movimientos de stock.
        """
        # CORRECCIÓN ODOO 19: El método padre ya no acepta argumentos.
        res = super(SaleOrderLine, self)._action_launch_stock_rule()
        self._sync_lots_to_stock_moves()
        return res

    def write(self, vals):
        """
        Si se edita lot_ids en una orden ya confirmada, actualizamos la reserva.
        """
        res = super(SaleOrderLine, self).write(vals)
        if 'lot_ids' in vals:
            for line in self:
                if line.state in ['sale', 'done']:
                    line._sync_lots_to_stock_moves()
        return res

    def _sync_lots_to_stock_moves(self):
        """
        Lógica Core: Busca los Stock Moves asociados a esta línea y fuerza
        la reserva (stock.move.line) de los lotes seleccionados en la SO.
        """
        for line in self:
            if not line.lot_ids:
                continue
                
            # Buscar movimientos activos
            moves = line.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])
            
            for move in moves:
                # IMPORTANTE: Usamos un contexto para decir "Soy la SO actualizando el Stock,
                # no me devuelvas la llamada (sync back) porque causará error de registro borrado".
                move = move.with_context(skip_back_sync=True)
                
                # 1. Limpiar reservas existentes. 
                # Al tener el contexto, el unlink -> recompute -> NO llamará a _sync_lots_back_to_so
                move.move_line_ids.unlink()
                
                # 2. Crear nuevas líneas de movimiento (Reserva explícita)
                move_lines_vals = []
                for lot in line.lot_ids:
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('location_id.usage', '=', 'internal'),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        continue 
                        
                    move_lines_vals.append({
                        'move_id': move.id,
                        'lot_id': lot.id,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.product_uom.id,
                        'qty_demand': 0, 
                        'quantity': quant.quantity,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                    })
                
                if move_lines_vals:
                    # Crear con el mismo contexto de protección
                    self.env['stock.move.line'].with_context(skip_back_sync=True).create(move_lines_vals)
                    # Forzar recalculo de estado de reserva
                    move._recompute_state()