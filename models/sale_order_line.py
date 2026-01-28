# -*- coding: utf-8 -*-
from odoo import models, fields, api

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

        total_qty = sum(quants.mapped('quantity'))
        if total_qty > 0:
            self.product_uom_qty = total_qty

    def _action_launch_stock_rule(self, *args, **kwargs):
        """
        Sobreescritura: Al confirmar la venta (crear movimientos),
        asignamos inmediatamente los lotes seleccionados a los movimientos de stock.
        """
        res = super()._action_launch_stock_rule(*args, **kwargs)

        # Si esto viene "desde stock" (sync back), no vuelvas a empujar a stock para evitar bucles.
        if not self.env.context.get('skip_stock_sync'):
            self._sync_lots_to_stock_moves()

        return res

    def write(self, vals):
        """
        Si se edita lot_ids en una orden ya confirmada, actualizamos la reserva.
        """
        res = super().write(vals)

        # Si el write viene desde STOCK -> SO, no vuelvas a sincronizar SO -> STOCK.
        if self.env.context.get('skip_stock_sync'):
            return res

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
        StockQuant = self.env['stock.quant']
        StockMoveLine = self.env['stock.move.line']

        for line in self:
            if not line.lot_ids:
                continue

            # En Odoo 19 el campo correcto es product_uom_id (no product_uom).
            uom_id = (line.product_uom_id or line.product_id.uom_id).id

            # Buscar movimientos activos
            moves = line.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])

            for move in moves:
                # Evitar que el recompute_state dispare sync back mientras limpiamos/creamos líneas
                move_ctx = move.with_context(skip_back_sync=True)

                # 1) Limpiar reservas existentes
                move_ctx.move_line_ids.unlink()

                # 2) Crear nuevas líneas de movimiento (Reserva explícita)
                move_lines_vals = []
                for lot in line.lot_ids:
                    quant = StockQuant.search([
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
                        'product_uom_id': uom_id,
                        # Nota: en Odoo moderno el campo operativo es `quantity`.
                        # Aquí lo usas como “cantidad reservada/planeada” para forzar la línea.
                        'quantity': quant.quantity,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                    })

                if move_lines_vals:
                    StockMoveLine.with_context(skip_back_sync=True).create(move_lines_vals)

                # 3) Forzar recalculo de estado de reserva
                move_ctx._recompute_state()
