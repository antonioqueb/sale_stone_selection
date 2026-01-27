# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Relación para almacenar los lotes (placas) seleccionados
    lot_ids = fields.Many2many(
        'stock.lot', 
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=False
    )

    # Campo técnico para controlar el estado visual (expandido/colapsado) en la sesión
    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """
        Recalcula la cantidad de la línea basándose en la suma
        de las cantidades disponibles de los lotes seleccionados.
        """
        if not self.lot_ids:
            return

        # Buscamos los quants para obtener la cantidad real disponible en stock interno
        # Esto previene usar cantidades de lotes que ya no existen o están en clientes
        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])
        
        # Agrupar por lote para evitar duplicados si un lote está fragmentado en ubicaciones
        # (Aunque en placas únicas esto es raro, es buena práctica)
        total_qty = sum(quants.mapped('quantity'))
        
        if total_qty > 0:
            self.product_uom_qty = total_qty
            
            # Opcional: Actualizar el precio si depende de características específicas del lote
            # self.price_unit = ... 
