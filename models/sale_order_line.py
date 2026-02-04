# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=True
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    # =========================================================================
    # DIAGNÓSTICO: Interceptar TODOS los métodos de copia/duplicación
    # =========================================================================

    def copy_data(self, default=None):
        """
        Método que prepara los datos para copiar líneas.
        NOTA: Puede recibir múltiples registros (NO es singleton).
        """
        if default is None:
            default = {}
        
        # Solo procesar individualmente si es singleton
        if len(self) == 1:
            _logger.info("=" * 80)
            _logger.info("[STONE COPY_DATA] INICIO - Línea ID: %s", self.id)
            _logger.info("[STONE COPY_DATA] self.lot_ids ANTES: %s (IDs: %s)", self.lot_ids, self.lot_ids.ids if self.lot_ids else [])
            _logger.info("[STONE COPY_DATA] default recibido: %s", default)
            _logger.info("[STONE COPY_DATA] Contexto: %s", self.env.context)
            
            # Verificar si lot_ids ya está en default
            if 'lot_ids' in default:
                _logger.info("[STONE COPY_DATA] lot_ids YA está en default: %s", default['lot_ids'])
            else:
                if self.lot_ids:
                    _logger.info("[STONE COPY_DATA] Agregando lot_ids a default: %s", self.lot_ids.ids)
                    default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
                else:
                    _logger.info("[STONE COPY_DATA] NO hay lot_ids para copiar")
        else:
            _logger.info("[STONE COPY_DATA] Multi-registro: %s líneas, delegando a super()", len(self))
        
        result = super(SaleOrderLine, self).copy_data(default)
        
        if len(self) == 1:
            _logger.info("[STONE COPY_DATA] Resultado de super().copy_data: %s", result)
            
            # Verificar si lot_ids está en el resultado
            if result:
                for idx, data in enumerate(result):
                    if 'lot_ids' in data:
                        _logger.info("[STONE COPY_DATA] lot_ids EN RESULTADO[%s]: %s", idx, data['lot_ids'])
                    else:
                        _logger.info("[STONE COPY_DATA] lot_ids NO ESTÁ en resultado[%s]", idx)
            
            _logger.info("[STONE COPY_DATA] FIN")
            _logger.info("=" * 80)
        
        return result

    def copy(self, default=None):
        """
        Método copy directo de la línea.
        """
        if len(self) == 1:
            _logger.info("=" * 80)
            _logger.info("[STONE LINE COPY] INICIO - Línea ID: %s", self.id)
            _logger.info("[STONE LINE COPY] lot_ids actuales: %s", self.lot_ids.ids if self.lot_ids else [])
            _logger.info("[STONE LINE COPY] default recibido: %s", default)
            _logger.info("[STONE LINE COPY] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).copy(default)
        
        if len(self) == 1:
            _logger.info("[STONE LINE COPY] Nueva línea creada ID: %s", result.id if result else None)
            _logger.info("[STONE LINE COPY] lot_ids en nueva línea: %s", result.lot_ids.ids if result and result.lot_ids else [])
            _logger.info("[STONE LINE COPY] FIN")
            _logger.info("=" * 80)
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """
        Interceptar creación para ver qué valores llegan.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE LINE CREATE] INICIO - Creando %s línea(s)", len(vals_list))
        
        for idx, vals in enumerate(vals_list):
            _logger.info("[STONE LINE CREATE] vals[%s] completo: %s", idx, vals)
            if 'lot_ids' in vals:
                _logger.info("[STONE LINE CREATE] vals[%s] lot_ids: %s", idx, vals['lot_ids'])
            else:
                _logger.info("[STONE LINE CREATE] vals[%s] SIN lot_ids", idx)
        
        _logger.info("[STONE LINE CREATE] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).create(vals_list)
        
        _logger.info("[STONE LINE CREATE] Líneas creadas IDs: %s", result.ids)
        for line in result:
            _logger.info("[STONE LINE CREATE] Línea ID %s - lot_ids DESPUÉS de create: %s", 
                        line.id, line.lot_ids.ids if line.lot_ids else [])
        
        _logger.info("[STONE LINE CREATE] FIN")
        _logger.info("=" * 80)
        return result

    def write(self, vals):
        """
        Interceptar escritura para ver cambios en lot_ids y sincronizar Pickings.
        """
        # --- LOGGING PREVIO ---
        if 'lot_ids' in vals:
            _logger.info("=" * 80)
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            _logger.info("[STONE LINE WRITE] lot_ids ANTES: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
            _logger.info("[STONE LINE WRITE] Contexto: %s", self.env.context)
        
        # --- EJECUCIÓN SUPER ---
        result = super(SaleOrderLine, self).write(vals)
        
        # --- SINCRONIZACIÓN BIDIRECCIONAL (SO -> PICKING) ---
        # Si cambiaron lot_ids, la orden no es nueva y no venimos del Picking (evitar bucle)
        if 'lot_ids' in vals and not self.env.context.get('skip_stone_sync_picking'):
            for line in self:
                # Solo sincronizar si la orden ya generó movimientos
                if line.state in ['sale', 'done'] and line.move_ids:
                    _logger.info("[STONE SYNC] Detectado cambio en lotes SO para línea %s. Sincronizando Picking...", line.id)
                    line._sync_lots_to_picking_moves()

        # --- LOGGING POSTERIOR ---
        if 'lot_ids' in vals:
            _logger.info("[STONE LINE WRITE] lot_ids DESPUÉS: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] FIN")
            _logger.info("=" * 80)
        
        return result

    def _sync_lots_to_picking_moves(self):
        """
        Refleja los cambios de lotes de la SO hacia los movimientos de stock (Pickings).
        Maneja adiciones y eliminaciones.
        """
        # Contexto para:
        # 1. skip_stone_sync_so: Evitar que el Picking intente escribir de vuelta a la SO (Loop Infinito)
        # 2. skip_picking_clean: Evitar que otros módulos borren lo que estamos haciendo
        # 3. skip_hold_validation: Permitir mover lotes aunque tengan reserva/hold
        ctx = dict(self.env.context, 
                   skip_stone_sync_so=True,
                   skip_picking_clean=True,
                   skip_hold_validation=True)

        target_lots = self.lot_ids
        
        # Iterar sobre movimientos asociados que no estén cancelados ni finalizados
        moves = self.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])
        
        for move in moves:
            picking = move.picking_id
            existing_move_lines = move.move_line_ids
            existing_lots = existing_move_lines.mapped('lot_id')

            # A. DETECTAR QUÉ BORRAR (Están en Picking pero ya no en SO)
            lots_to_remove = existing_lots - target_lots
            if lots_to_remove:
                lines_to_unlink = existing_move_lines.filtered(lambda ml: ml.lot_id in lots_to_remove)
                _logger.info("[STONE SYNC] Eliminando %s lotes del picking %s", len(lines_to_unlink), picking.name)
                lines_to_unlink.with_context(ctx).unlink()

            # B. DETECTAR QUÉ AGREGAR (Están en SO pero no en Picking)
            lots_to_add = target_lots - existing_lots
            if lots_to_add:
                _logger.info("[STONE SYNC] Agregando %s lotes al picking %s", len(lots_to_add), picking.name)
                for lot in lots_to_add:
                    # 1. Buscar disponibilidad física real (donde esté el lote actualmente)
                    # Intentamos primero en la ubicación del movimiento o sus hijos
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', self.product_id.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    # 2. Fallback: Si no está ahí (ej. se movió), buscar en cualquier ubicación interna
                    if not quant:
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', lot.id),
                            ('product_id', '=', self.product_id.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0)
                        ], limit=1)

                    if quant:
                        move_line_vals = {
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': self.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'lot_id': lot.id,
                            'location_id': quant.location_id.id, # Usar ubicación real del lote
                            'location_dest_id': move.location_dest_id.id,
                            'quantity': quant.quantity, # Cantidad total del quant
                        }
                        try:
                            self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        except Exception as e:
                            _logger.error("[STONE SYNC] Error creando move line para lote %s: %s", lot.name, str(e))
                    else:
                        _logger.warning("[STONE SYNC] No se pudo sincronizar lote %s: No stock físico encontrado", lot.name)

    def read(self, fields=None, load='_classic_read'):
        """
        Interceptar lectura para ver qué se está leyendo.
        """
        result = super(SaleOrderLine, self).read(fields, load)
        
        # Solo loguear si se está leyendo lot_ids específicamente
        if fields and 'lot_ids' in fields:
            _logger.info("[STONE LINE READ] IDs: %s, fields: %s", self.ids, fields)
            for record_data in result:
                if 'lot_ids' in record_data:
                    _logger.info("[STONE LINE READ] ID %s -> lot_ids: %s", 
                                record_data.get('id'), record_data.get('lot_ids'))
        
        return result

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """Actualiza la cantidad (m2) de la línea al seleccionar placas"""
        _logger.info("=" * 80)
        _logger.info("[STONE ONCHANGE lot_ids] Línea ID: %s (origin: %s)", 
                    self.id, self._origin.id if hasattr(self, '_origin') else 'N/A')
        _logger.info("[STONE ONCHANGE lot_ids] lot_ids: %s", self.lot_ids.ids if self.lot_ids else [])
        _logger.info("[STONE ONCHANGE lot_ids] Contexto: %s", self.env.context)
        
        if not self.lot_ids:
            _logger.info("[STONE ONCHANGE lot_ids] Sin lotes, saliendo")
            return

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])

        total_qty = sum(quants.mapped('quantity'))
        _logger.info("[STONE ONCHANGE lot_ids] Total qty calculado: %s", total_qty)
        
        if total_qty > 0:
            self.product_uom_qty = total_qty
            _logger.info("[STONE ONCHANGE lot_ids] product_uom_qty actualizado a: %s", total_qty)
        
        _logger.info("[STONE ONCHANGE lot_ids] FIN")
        _logger.info("=" * 80)