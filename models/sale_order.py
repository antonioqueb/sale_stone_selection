# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Confirmación con asignación estricta de lotes seleccionados.
        CRÍTICO: Asigna el lote COMPLETO, no cantidades parciales.
        NUEVO: Bloquea doble confirmación y limpia lot_ids de la cotización.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE] ACTION_CONFIRM INICIO - Orden: %s", self.name)

        # =====================================================================
        # 0. BLOQUEAR DOBLE CONFIRMACIÓN
        # Si la orden ya está confirmada (sale/done), redirigir a ella.
        # =====================================================================
        for order in self:
            if order.state in ('sale', 'done'):
                _logger.info("[STONE] Orden %s ya confirmada (state=%s). Redirigiendo.", order.name, order.state)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': order.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Orden de Venta: %s') % order.name,
                }

        # =====================================================================
        # 1. VALIDAR QUE LAS PLACAS NO ESTÉN COMPROMETIDAS POR OTRA ORDEN
        # =====================================================================
        for order in self:
            for line in order.order_line.filtered(lambda l: l.lot_ids):
                conflicting = self._check_lots_availability(line.lot_ids, line.product_id, order)
                if conflicting:
                    lot_names = ', '.join(conflicting.mapped('name'))
                    raise UserError(_(
                        "Las siguientes placas ya están comprometidas en otra orden de venta confirmada:\n\n"
                        "%s\n\n"
                        "Debes deseleccionarlas antes de confirmar."
                    ) % lot_names)

        # =====================================================================
        # 2. GUARDAR los lotes ANTES de confirmar
        # =====================================================================
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
                _logger.info("[STONE] Protegiendo para línea %s: %s lotes", line.id, len(lot_ids))
        
        if not lines_lots_map:
            return super().action_confirm()
        
        # 3. Definir Contexto de Protección
        ctx = dict(self.env.context,
                   skip_picking_clean=True,
                   protected_lot_ids=all_protected_lot_ids,
                   is_stone_confirming=True,
                   skip_stone_sync_so=True)
        
        _logger.info("[STONE] Llamando a super() con skip_picking_clean=True...")
        
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        _logger.info("[STONE] Retorno de super(). Iniciando asignación forzada.")
        
        # 4. Asignación Forzada
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            
            if not pickings:
                _logger.warning("[STONE] No se generaron pickings para la orden %s", order.name)
                continue

            # A. Limpieza Quirúrgica (Solo lo que NO es nuestro)
            for picking in pickings:
                for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    lines_to_remove = move.move_line_ids.filtered(
                        lambda ml: ml.lot_id and ml.lot_id.id not in all_protected_lot_ids
                    )
                    if lines_to_remove:
                        _logger.info("[STONE] Eliminando %s asignaciones automáticas incorrectas (FIFO)", len(lines_to_remove))
                        lines_to_remove.with_context(ctx).unlink()

            # B. Inyectar nuestros lotes con CANTIDAD COMPLETA
            for line in order.order_line:
                line_data = lines_lots_map.get(line.id)
                if not line_data:
                    continue
                    
                lots = self.env['stock.lot'].browse(line_data['lot_ids'])
                if lots:
                    self.with_context(ctx)._assign_stone_lots_to_picking(pickings, line, lots)

        # =====================================================================
        # 5. LIMPIAR lot_ids DE LA COTIZACIÓN (ya están en el picking)
        # Las placas ahora pertenecen a la orden confirmada vía move_line_ids.
        # No deben seguir en lot_ids de la sale.order.line para evitar que
        # la cotización "retenga" la referencia visual y confunda.
        # =====================================================================
        _logger.info("[STONE] Limpiando lot_ids de las líneas de cotización (placas ya asignadas al picking)...")
        for line_id, line_data in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists():
                line.with_context(ctx).write({'lot_ids': [(5, 0, 0)]})
                _logger.info("[STONE] Limpiado lot_ids de línea %s", line_id)
        
        _logger.info("[STONE] ACTION_CONFIRM FIN")
        _logger.info("=" * 80)
        return res

    def _check_lots_availability(self, lots, product, current_order):
        """
        Verifica que los lotes no estén comprometidos en otra orden de venta confirmada.
        Retorna los lotes que tienen conflicto.
        """
        if not lots:
            return self.env['stock.lot']

        # Buscar move.lines activas (no canceladas, no hechas) que tengan estos lotes
        # y que pertenezcan a OTRA orden de venta (no la nuestra)
        conflicting_move_lines = self.env['stock.move.line'].search([
            ('lot_id', 'in', lots.ids),
            ('product_id', '=', product.id),
            ('state', 'not in', ['done', 'cancel']),
            ('move_id.sale_line_id', '!=', False),
            ('move_id.sale_line_id.order_id', '!=', current_order.id),
        ])
        
        if conflicting_move_lines:
            return conflicting_move_lines.mapped('lot_id')
        
        # También verificar lot_ids en otras sale.order.line de órdenes confirmadas
        # (para el caso donde aún no se generaron pickings)
        conflicting_sol = self.env['sale.order.line'].search([
            ('lot_ids', 'in', lots.ids),
            ('order_id', '!=', current_order.id),
            ('order_id.state', 'in', ['sale', 'done']),
            ('product_id', '=', product.id),
        ])
        
        if conflicting_sol:
            conflicting_lot_ids = set()
            for sol in conflicting_sol:
                conflicting_lot_ids.update(set(sol.lot_ids.ids) & set(lots.ids))
            if conflicting_lot_ids:
                return self.env['stock.lot'].browse(list(conflicting_lot_ids))
        
        return self.env['stock.lot']

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """
        Asigna los lotes seleccionados al picking.
        CRÍTICO: Usa la CANTIDAD TOTAL del quant, no cantidades parciales.
        """
        product = sale_line.product_id
        if not lots:
            return

        ctx = dict(self.env.context, 
                   skip_stone_sync=True, 
                   skip_picking_clean=True,
                   skip_hold_validation=True,
                   skip_stone_sync_so=True)

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.state not in ['done', 'cancel']
            )
            
            for move in moves:
                existing_lot_ids = move.move_line_ids.mapped('lot_id').ids
                
                for lot in lots:
                    if lot.id in existing_lot_ids:
                        _logger.info("[STONE] Lote %s ya existe en move %s, verificando cantidad...", lot.name, move.id)
                        existing_line = move.move_line_ids.filtered(lambda ml: ml.lot_id.id == lot.id)
                        if existing_line:
                            quant = self.env['stock.quant'].search([
                                ('lot_id', '=', lot.id),
                                ('product_id', '=', product.id),
                                ('location_id', 'child_of', move.location_id.id),
                                ('quantity', '>', 0)
                            ], limit=1)
                            if quant and existing_line.quantity != quant.quantity:
                                _logger.info("[STONE] Corrigiendo cantidad de %s a %s", existing_line.quantity, quant.quantity)
                                existing_line.with_context(ctx).write({'quantity': quant.quantity})
                        continue
                    
                    # Buscar Stock Físico Total
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', lot.id),
                            ('product_id', '=', product.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0)
                        ], limit=1)
                    
                    if not quant:
                        _logger.warning("[STONE] Lote %s no encontrado físicamente", lot.name)
                        continue
                    
                    qty_to_assign = quant.quantity
                    
                    _logger.info("[STONE] Asignando lote %s con cantidad COMPLETA: %s m²", lot.name, qty_to_assign)
                    
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
                    
                    try:
                        self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        _logger.info("[STONE] ✓ Asignado Lote %s (Qty: %s) a Picking %s", lot.name, qty_to_assign, picking.name)
                    except Exception as e:
                        _logger.error("[STONE] Error asignando lote %s: %s", lot.name, str(e))

    def copy_data(self, default=None):
        return super().copy_data(default)

    def copy(self, default=None):
        return super().copy(default)