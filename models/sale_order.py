# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Confirmación con asignación estricta de lotes seleccionados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE] ACTION_CONFIRM INICIO - Órdenes: %s", self.mapped('name'))
        
        # 1. GUARDAR los lotes ANTES de confirmar (Snapshot de selección)
        lines_lots_map = {}
        all_protected_lot_ids = []
        
        for order in self:
            for line in order.order_line.filtered(lambda l: l.lot_ids):
                lot_ids = line.lot_ids.ids.copy()
                lines_lots_map[line.id] = {
                    'lot_ids': lot_ids,
                    'product_id': line.product_id.id,
                }
                all_protected_lot_ids.extend(lot_ids)
                _logger.info("[STONE] Guardando línea %s (%s): lotes=%s", 
                             line.id, line.product_id.display_name, lot_ids)
        
        if not lines_lots_map:
            _logger.info("[STONE] No hay líneas con lotes seleccionados, confirmación estándar.")
            return super().action_confirm()
        
        # 2. Confirmar con contexto especial
        # is_stone_confirming: Señal para otros métodos de no interferir
        # skip_picking_clean: Evita que el limpiador automático borre todo indiscriminadamente
        ctx = dict(self.env.context,
                   skip_picking_clean=True,
                   protected_lot_ids=all_protected_lot_ids,
                   is_stone_confirming=True)
        
        _logger.info("[STONE] Ejecutando super().action_confirm()...")
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        _logger.info("[STONE] Confirmación base completada.")
        
        # 3. Limpiar residuos automáticos y forzar asignación de nuestros lotes
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            
            if not pickings:
                _logger.warning("[STONE] Orden %s confirmada pero sin pickings activos.", order.name)
                continue

            # A. Limpiar move_lines que Odoo asignó automáticamente (FIFO) pero que NO son los nuestros
            for picking in pickings:
                for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    lines_to_remove = move.move_line_ids.filtered(
                        lambda ml: ml.lot_id.id not in all_protected_lot_ids
                    )
                    if lines_to_remove:
                        _logger.info("[STONE] Limpiando %s asignaciones automáticas (FIFO) no deseadas en %s", 
                                     len(lines_to_remove), move.product_id.display_name)
                        lines_to_remove.unlink()

            # B. Asignar nuestros lotes explícitamente
            for line in order.order_line:
                line_data = lines_lots_map.get(line.id)
                if not line_data:
                    continue
                    
                lots = self.env['stock.lot'].browse(line_data['lot_ids'])
                if lots:
                    _logger.info("[STONE] Procesando asignación forzada para línea %s: %s lotes", line.id, len(lots))
                    # Pasamos el contexto actualizado aquí también
                    self.with_context(ctx)._assign_stone_lots_to_picking(pickings, line, lots)
        
        # 4. Restaurar lot_ids en las líneas de venta (por si el proceso estándar los borró)
        for line_id, line_data in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists() and set(line.lot_ids.ids) != set(line_data['lot_ids']):
                _logger.info("[STONE] Restaurando selección visual de lotes en línea %s", line_id)
                line.with_context(ctx).write({'lot_ids': [(6, 0, line_data['lot_ids'])]})
        
        _logger.info("[STONE] ACTION_CONFIRM FIN")
        _logger.info("=" * 80)
        return res

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """
        Asigna los lotes seleccionados al picking, saltando validaciones de hold.
        """
        product = sale_line.product_id
        if not lots:
            return

        # === CORRECCIÓN CRÍTICA: Contexto para saltar validaciones ===
        # skip_hold_validation: Permite usar lotes con 'Hold' (Apartado)
        # skip_stone_sync: Evita bucles recursivos en recompute
        ctx = dict(self.env.context, 
                   skip_stone_sync=True, 
                   skip_picking_clean=True,
                   skip_hold_validation=True) 

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.state not in ['done', 'cancel']
            )
            
            if not moves:
                _logger.warning("[STONE] No se encontraron movimientos para %s en picking %s", product.name, picking.name)
                continue
            
            for move in moves:
                _logger.info("[STONE] Procesando Movimiento ID: %s (Demanda: %s)", move.id, move.product_uom_qty)
                
                # Verificar qué lotes ya están asignados para no duplicar
                existing_lot_ids = move.move_line_ids.mapped('lot_id').ids
                
                for lot in lots:
                    # 1. Chequeo de duplicados
                    if lot.id in existing_lot_ids:
                        _logger.info("[STONE] > Lote %s ya está asignado. Omitiendo.", lot.name)
                        continue
                    
                    # 2. Buscar existencias físicas (Quant)
                    # Buscamos en hijos de la ubicación del movimiento
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        _logger.error("[STONE] > ❌ Lote %s NO encontrado físicamente en %s o cantidad es 0.", 
                                      lot.name, move.location_id.name)
                        continue
                    
                    # === CORRECCIÓN CRÍTICA: Cálculo de Cantidad ===
                    # Usamos 'quantity' total. Ignoramos 'reserved_quantity' porque
                    # acabamos de limpiar las reservas automáticas y estamos forzando
                    # la asignación. Si usáramos (qty - reserved), daría 0 en muchos casos.
                    qty_to_assign = quant.quantity
                    
                    _logger.info("[STONE] > Intentando asignar Lote %s. Stock Físico: %s. Ubicación: %s", 
                                 lot.name, qty_to_assign, quant.location_id.name)
                    
                    if qty_to_assign <= 0:
                        _logger.warning("[STONE] > ⚠️ Cantidad inválida (%s) para lote %s.", qty_to_assign, lot.name)
                        continue
                    
                    move_line_vals = {
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'lot_id': lot.id,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': qty_to_assign, # Cantidad forzada
                        # quantity en Odoo >= 16 suele ser la cantidad reservada/hecha
                        # dependiendo del estado del picking.
                    }
                    
                    try:
                        # 3. Crear línea de movimiento (Move Line) con contexto privilegiado
                        new_ml = self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        _logger.info("[STONE] > ✅ ÉXITO: MoveLine %s creada. Lote %s asignado.", new_ml.id, lot.name)
                    except Exception as e:
                        _logger.error("[STONE] > ❌ ERROR CRÍTICO al asignar lote %s: %s", lot.name, str(e))

    def copy_data(self, default=None):
        _logger.info("[STONE ORDER COPY_DATA] Orden: %s", self.name)
        return super().copy_data(default)

    def copy(self, default=None):
        _logger.info("[STONE ORDER COPY] Orden: %s", self.name)
        for line in self.order_line:
            _logger.info("[STONE ORDER COPY] Línea %s lot_ids: %s", line.id, line.lot_ids.ids)
        result = super().copy(default)
        for line in result.order_line:
            _logger.info("[STONE ORDER COPY] Nueva línea %s lot_ids: %s", line.id, line.lot_ids.ids)
        return result