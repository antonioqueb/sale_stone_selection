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

    def action_confirm(self):
        """
        Confirmación con protección de contexto para evitar
        que la sincronización bidireccional sobrescriba nuestra selección
        durante el proceso de reserva inicial.
        """
        # 1. Marcamos en el contexto que estamos en proceso de confirmación "Stone"
        # Esto detendrá a _sync_lots_back_to_so en stock.move
        ctx = dict(self.env.context, is_stone_confirming=True)
        
        # 2. Ejecutar confirmación estándar (Genera Pickings y reserva FIFO)
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        # 3. Limpieza de reservas automáticas
        self._clear_auto_assigned_lots()
        
        # 4. Asignación Estricta de Lotes Seleccionados
        for order in self:
            # Solo procesar líneas que tengan lotes seleccionados manualmente
            lines_with_stone = order.order_line.filtered(lambda l: l.lot_ids)
            if not lines_with_stone:
                continue

            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            
            if not pickings:
                continue

            _logger.info(f"[STONE] Iniciando asignación estricta para Orden {order.name}")
            for line in lines_with_stone:
                order._assign_stone_lots_strict(pickings, line)
        
        return res

    def _clear_auto_assigned_lots(self):
        """Limpia las reservas que Odoo hizo automáticamente por FIFO."""
        if PickingLotCleaner:
            # _logger.info("[STONE] Ejecutando PickingLotCleaner...")
            cleaner = PickingLotCleaner(self.env)
            for order in self:
                if order.picking_ids:
                    cleaner.clear_pickings_lots(order.picking_ids)
        else:
            _logger.warning("[STONE] PickingLotCleaner no disponible. La reserva inicial no se limpió correctamente.")

    def _assign_stone_lots_strict(self, pickings, line):
        """
        Crea las líneas de movimiento (stock.move.line) para los lotes seleccionados.
        """
        product = line.product_id
        selected_lots = line.lot_ids
        
        if not selected_lots:
            return

        for picking in pickings:
            # Buscamos movimientos del producto de la línea
            moves = picking.move_ids.filtered(lambda m: m.product_id.id == product.id and m.state not in ['done', 'cancel'])
            
            for move in moves:
                # Doble check: Asegurar que el movimiento esté limpio
                if move.move_line_ids:
                    # Si quedó algo sucio, limpiamos (solo si no está done)
                    move.move_line_ids.unlink()
                
                remaining_demand = move.product_uom_qty
                
                for lot in selected_lots:
                    if remaining_demand <= 0:
                        break
                        
                    # --- CORRECCIÓN CRÍTICA DE BÚSQUEDA ---
                    # No basta con quantity > 0, debe ser quantity - reserved > 0
                    # Además, debemos buscar en la ubicación hija donde esté el lote
                    
                    domain = [
                        ('lot_id', '=', lot.id),
                        ('location_id.usage', '=', 'internal'),
                        ('location_id', 'child_of', move.location_id.id) # Debe estar dentro del almacén del movimiento
                    ]
                    
                    # Buscamos todos los quants de ese lote
                    quants = self.env['stock.quant'].search(domain)
                    
                    target_quant = None
                    for q in quants:
                        # Calculamos disponibilidad REAL para nosotros
                        available_qty = q.quantity - q.reserved_quantity
                        if available_qty > 0:
                            target_quant = q
                            break
                    
                    if not target_quant:
                        _logger.warning(f"[STONE] Lote {lot.name} seleccionado en SO pero SIN STOCK DISPONIBLE (Físico o Reservado por otro).")
                        continue

                    # Reservar lo que necesitemos o lo que haya
                    qty_to_reserve = min(target_quant.quantity - target_quant.reserved_quantity, remaining_demand)
                    
                    if qty_to_reserve <= 0:
                        continue

                    try:
                        # Crear la reserva manual
                        # IMPORTANTE: location_id debe ser la ubicación REAL del quant (ej. Stock/Estante1)
                        # aunque el movimiento sea generico (Stock).
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': product.id,
                            'lot_id': lot.id,
                            'quantity': qty_to_reserve, # En Odoo 17+ 'quantity' es la reserva
                            'location_id': target_quant.location_id.id, 
                            'location_dest_id': move.location_dest_id.id,
                            'product_uom_id': product.uom_id.id,
                        })
                        
                        remaining_demand -= qty_to_reserve
                        # _logger.info(f"[STONE] Reservado {lot.name} ({qty_to_reserve}) en {picking.name}")
                        
                    except Exception as e:
                        _logger.error(f"[STONE] Error técnico reservando lote {lot.name}: {e}")
            
            # Forzar actualización del estado del picking para que refleje las reservas
            # y Odoo no intente re-asignar automáticamente por FIFO
            try:
                picking.move_ids._recompute_state()
            except:
                pass