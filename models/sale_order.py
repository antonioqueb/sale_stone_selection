# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.stock_lot_dimensions.models.utils.picking_cleaner import PickingLotCleaner
except ImportError:
    PickingLotCleaner = None

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # =========================================================================
    # DIAGNÓSTICO: Interceptar métodos de copia de la orden
    # =========================================================================

    def copy_data(self, default=None):
        """
        Método que prepara los datos para copiar una orden.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE ORDER COPY_DATA] INICIO - Orden ID: %s, Name: %s", self.id, self.name)
        _logger.info("[STONE ORDER COPY_DATA] default recibido: %s", default)
        _logger.info("[STONE ORDER COPY_DATA] Contexto: %s", self.env.context)
        
        # Loguear lot_ids de cada línea ANTES de copiar
        for line in self.order_line:
            _logger.info("[STONE ORDER COPY_DATA] Línea ID %s, Producto: %s, lot_ids: %s", 
                        line.id, 
                        line.product_id.name if line.product_id else 'N/A',
                        line.lot_ids.ids if line.lot_ids else [])
        
        result = super(SaleOrder, self).copy_data(default)
        
        _logger.info("[STONE ORDER COPY_DATA] Resultado tipo: %s", type(result))
        
        # Inspeccionar el resultado para ver si las líneas tienen lot_ids
        if result:
            for idx, data in enumerate(result):
                _logger.info("[STONE ORDER COPY_DATA] Resultado[%s] keys: %s", idx, data.keys() if isinstance(data, dict) else 'NO ES DICT')
                if isinstance(data, dict) and 'order_line' in data:
                    _logger.info("[STONE ORDER COPY_DATA] order_line en resultado: %s", data['order_line'])
                    for line_idx, line_data in enumerate(data.get('order_line', [])):
                        _logger.info("[STONE ORDER COPY_DATA] order_line[%s]: %s", line_idx, line_data)
        
        _logger.info("[STONE ORDER COPY_DATA] FIN")
        _logger.info("=" * 80)
        return result

    def copy(self, default=None):
        """
        Método copy de la orden - usado al duplicar.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE ORDER COPY] INICIO - Orden ID: %s, Name: %s", self.id, self.name)
        _logger.info("[STONE ORDER COPY] default: %s", default)
        _logger.info("[STONE ORDER COPY] Contexto: %s", self.env.context)
        
        # Loguear lot_ids ANTES de duplicar
        _logger.info("[STONE ORDER COPY] === LÍNEAS ORIGEN ===")
        for line in self.order_line:
            _logger.info("[STONE ORDER COPY] Línea ID %s -> lot_ids: %s (count: %s)", 
                        line.id, line.lot_ids.ids, len(line.lot_ids))
        
        result = super(SaleOrder, self).copy(default)
        
        _logger.info("[STONE ORDER COPY] === ORDEN COPIADA ===")
        _logger.info("[STONE ORDER COPY] Nueva orden ID: %s, Name: %s", result.id, result.name)
        
        _logger.info("[STONE ORDER COPY] === LÍNEAS DESTINO ===")
        for line in result.order_line:
            _logger.info("[STONE ORDER COPY] Nueva línea ID %s -> lot_ids: %s (count: %s)", 
                        line.id, line.lot_ids.ids, len(line.lot_ids))
        
        _logger.info("[STONE ORDER COPY] FIN")
        _logger.info("=" * 80)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """
        Interceptar creación de órdenes.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE ORDER CREATE] INICIO - Creando %s orden(es)", len(vals_list))
        _logger.info("[STONE ORDER CREATE] Contexto: %s", self.env.context)
        
        for idx, vals in enumerate(vals_list):
            _logger.info("[STONE ORDER CREATE] vals[%s] keys: %s", idx, vals.keys())
            if 'order_line' in vals:
                _logger.info("[STONE ORDER CREATE] vals[%s] order_line: %s", idx, vals['order_line'])
        
        result = super(SaleOrder, self).create(vals_list)
        
        _logger.info("[STONE ORDER CREATE] Órdenes creadas: %s", result.mapped('name'))
        for order in result:
            _logger.info("[STONE ORDER CREATE] Orden %s líneas:", order.name)
            for line in order.order_line:
                _logger.info("[STONE ORDER CREATE]   Línea ID %s -> lot_ids: %s", 
                            line.id, line.lot_ids.ids)
        
        _logger.info("[STONE ORDER CREATE] FIN")
        _logger.info("=" * 80)
        return result

    def action_confirm(self):
        """
        Confirmación con protección de contexto.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE ORDER CONFIRM] INICIO - Orden(es): %s", self.mapped('name'))
        
        for order in self:
            _logger.info("[STONE ORDER CONFIRM] Orden %s - Estado: %s", order.name, order.state)
            for line in order.order_line:
                _logger.info("[STONE ORDER CONFIRM] Línea ID %s, lot_ids: %s", 
                            line.id, line.lot_ids.ids)
        
        ctx = dict(self.env.context, is_stone_confirming=True)
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        self._clear_auto_assigned_lots()
        
        for order in self:
            lines_with_stone = order.order_line.filtered(lambda l: l.lot_ids)
            if not lines_with_stone:
                continue

            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            
            if not pickings:
                continue

            _logger.info("[STONE ORDER CONFIRM] Asignando lotes para Orden %s", order.name)
            for line in lines_with_stone:
                order._assign_stone_lots_strict(pickings, line)
        
        _logger.info("[STONE ORDER CONFIRM] FIN")
        _logger.info("=" * 80)
        return res

    def _clear_auto_assigned_lots(self):
        """Limpia las reservas que Odoo hizo automáticamente por FIFO."""
        if PickingLotCleaner:
            cleaner = PickingLotCleaner(self.env)
            for order in self:
                if order.picking_ids:
                    cleaner.clear_pickings_lots(order.picking_ids)
        else:
            _logger.warning("[STONE] PickingLotCleaner no disponible.")

    def _assign_stone_lots_strict(self, pickings, line):
        """
        Crea las líneas de movimiento para los lotes seleccionados.
        """
        product = line.product_id
        selected_lots = line.lot_ids
        
        if not selected_lots:
            return

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id and m.state not in ['done', 'cancel']
            )
            
            for move in moves:
                if move.move_line_ids:
                    move.move_line_ids.unlink()
                
                remaining_demand = move.product_uom_qty
                
                for lot in selected_lots:
                    if remaining_demand <= 0:
                        break
                        
                    domain = [
                        ('lot_id', '=', lot.id),
                        ('location_id.usage', '=', 'internal'),
                        ('location_id', 'child_of', move.location_id.id)
                    ]
                    
                    quants = self.env['stock.quant'].search(domain)
                    
                    target_quant = None
                    for q in quants:
                        available_qty = q.quantity - q.reserved_quantity
                        if available_qty > 0:
                            target_quant = q
                            break
                    
                    if not target_quant:
                        _logger.warning("[STONE] Lote %s sin stock disponible.", lot.name)
                        continue

                    qty_to_reserve = min(
                        target_quant.quantity - target_quant.reserved_quantity, 
                        remaining_demand
                    )
                    
                    if qty_to_reserve <= 0:
                        continue

                    try:
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': product.id,
                            'lot_id': lot.id,
                            'quantity': qty_to_reserve,
                            'location_id': target_quant.location_id.id, 
                            'location_dest_id': move.location_dest_id.id,
                            'product_uom_id': product.uom_id.id,
                        })
                        remaining_demand -= qty_to_reserve
                    except Exception as e:
                        _logger.error("[STONE] Error reservando lote %s: %s", lot.name, e)
            
            try:
                picking.move_ids._recompute_state()
            except:
                pass