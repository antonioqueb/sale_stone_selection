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
        # Quitamos 'previous_product_uom_qty' de la llamada a super().
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
                
            # Buscar movimientos activos (no cancelados ni hechos completamente si queremos permitir re-asignación parcial)
            # Generalmente nos interesa modificar los que están en espera o asignados.
            moves = line.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])
            
            for move in moves:
                # 1. Limpiar reservas existentes automáticas o manuales previas
                # Esto es necesario para "resetear" y aplicar la selección visual exacta
                move.move_line_ids.unlink()
                
                # 2. Crear nuevas líneas de movimiento (Reserva explícita)
                move_lines_vals = []
                for lot in line.lot_ids:
                    # Buscar el quant para saber dónde está y cuánto hay
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('location_id.usage', '=', 'internal'),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        continue # El lote no está disponible físicamente
                        
                    move_lines_vals.append({
                        'move_id': move.id,
                        'lot_id': lot.id,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.product_uom.id,
                        'qty_demand': 0, # En Odoo moderno, qty_demand va en el move, aqui reservamos
                        'quantity': quant.quantity, # Reservar todo lo que tenga la placa
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                    })
                
                if move_lines_vals:
                    self.env['stock.move.line'].create(move_lines_vals)
                    # Forzar recalculo de estado de reserva
                    move._recompute_state()