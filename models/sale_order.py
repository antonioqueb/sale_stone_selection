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
        _logger.info("[STONE ORDER CONFIRM] INICIO - Orden(es): %s", self.mapped('name'))
        
        for order in self:
            for line in order.order_line:
                _logger.info("[STONE ORDER CONFIRM] Línea ID %s, lot_ids: %s", 
                            line.id, line.lot_ids.ids)
        
        # Guardar los lotes ANTES de confirmar (porque el proceso puede alterarlos)
        lines_lots_map = {}
        for order in self:
            for line in order.order_line.filtered(lambda l: l.lot_ids):
                lines_lots_map[line.id] = line.lot_ids.ids.copy()
        
        _logger.info("[STONE ORDER CONFIRM] Mapa de lotes guardado: %s", lines_lots_map)
        
        # Confirmar con contexto de protección
        ctx = dict(self.env.context, is_stone_confirming=True, skip_stone_sync=True)
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        # Asignar lotes a los pickings
        for order in self:
            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            
            if not pickings:
                _logger.info("[STONE ORDER CONFIRM] Sin pickings para %s", order.name)
                continue

            for line in order.order_line:
                lot_ids = lines_lots_map.get(line.id, [])
                if not lot_ids:
                    continue
                    
                _logger.info("[STONE ORDER CONFIRM] Asignando lotes %s para línea %s", lot_ids, line.id)
                lots = self.env['stock.lot'].browse(lot_ids)
                self._assign_stone_lots_to_picking(pickings, line, lots)
        
        _logger.info("[STONE ORDER CONFIRM] FIN")
        _logger.info("=" * 80)
        return res

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """
        Asigna los lotes seleccionados al picking de forma correcta para Odoo 19.
        """
        product = sale_line.product_id
        
        if not lots:
            _logger.warning("[STONE] Sin lotes para asignar a línea %s", sale_line.id)
            return

        ctx = dict(self.env.context, skip_stone_sync=True, is_stone_confirming=True)

        for picking in pickings:
            # Buscar el move correspondiente al producto
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.sale_line_id.id == sale_line.id
                and m.state not in ['done', 'cancel']
            )
            
            if not moves:
                # Fallback: buscar solo por producto
                moves = picking.move_ids.filtered(
                    lambda m: m.product_id.id == product.id 
                    and m.state not in ['done', 'cancel']
                )
            
            _logger.info("[STONE] Picking %s, Moves encontrados: %s", picking.name, moves.ids)
            
            for move in moves:
                # 1. Eliminar move_lines existentes (asignaciones automáticas FIFO)
                if move.move_line_ids:
                    _logger.info("[STONE] Eliminando %s move_lines existentes", len(move.move_line_ids))
                    move.move_line_ids.with_context(ctx).unlink()
                
                # 2. Crear move_lines para cada lote seleccionado
                total_assigned = 0.0
                
                for lot in lots:
                    # Buscar quant disponible para este lote
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        _logger.warning("[STONE] Lote %s sin stock en ubicación %s", 
                                       lot.name, move.location_id.name)
                        continue
                    
                    available_qty = quant.quantity - quant.reserved_quantity
                    if available_qty <= 0:
                        _logger.warning("[STONE] Lote %s sin cantidad disponible", lot.name)
                        continue
                    
                    # Cantidad a asignar (toda la disponible del lote)
                    qty_to_assign = available_qty
                    
                    _logger.info("[STONE] Creando move_line: lote=%s, qty=%s, location=%s", 
                                lot.name, qty_to_assign, quant.location_id.name)
                    
                    # Crear move_line con todos los campos requeridos
                    move_line_vals = {
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'lot_id': lot.id,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': qty_to_assign,
                    }
                    
                    # En Odoo 19, algunos campos pueden ser requeridos
                    if hasattr(self.env['stock.move.line'], 'company_id'):
                        move_line_vals['company_id'] = picking.company_id.id
                    
                    try:
                        new_line = self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        _logger.info("[STONE] Move line creado: ID=%s", new_line.id)
                        total_assigned += qty_to_assign
                    except Exception as e:
                        _logger.error("[STONE] Error creando move_line: %s", str(e))
                        continue
                
                _logger.info("[STONE] Total asignado al move %s: %s", move.id, total_assigned)
                
                # 3. Forzar recálculo del estado del move
                move.with_context(ctx)._recompute_state()
            
            # 4. Forzar recálculo del picking
            picking.with_context(ctx)._compute_state()
            
            _logger.info("[STONE] Picking %s estado final: %s", picking.name, picking.state)