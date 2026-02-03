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
        Método que prepara los datos para copiar una línea.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE COPY_DATA] INICIO - Línea ID: %s", self.id)
        _logger.info("[STONE COPY_DATA] self.lot_ids ANTES: %s (IDs: %s)", self.lot_ids, self.lot_ids.ids if self.lot_ids else [])
        _logger.info("[STONE COPY_DATA] default recibido: %s", default)
        _logger.info("[STONE COPY_DATA] Contexto: %s", self.env.context)
        
        if default is None:
            default = {}
        
        # Verificar si lot_ids ya está en default
        if 'lot_ids' in default:
            _logger.info("[STONE COPY_DATA] lot_ids YA está en default: %s", default['lot_ids'])
        else:
            if self.lot_ids:
                _logger.info("[STONE COPY_DATA] Agregando lot_ids a default: %s", self.lot_ids.ids)
                default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
            else:
                _logger.info("[STONE COPY_DATA] NO hay lot_ids para copiar")
        
        result = super(SaleOrderLine, self).copy_data(default)
        
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
        _logger.info("=" * 80)
        _logger.info("[STONE LINE COPY] INICIO - Línea ID: %s", self.id)
        _logger.info("[STONE LINE COPY] lot_ids actuales: %s", self.lot_ids.ids if self.lot_ids else [])
        _logger.info("[STONE LINE COPY] default recibido: %s", default)
        _logger.info("[STONE LINE COPY] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).copy(default)
        
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
        Interceptar escritura para ver cambios en lot_ids.
        """
        if 'lot_ids' in vals:
            _logger.info("=" * 80)
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            _logger.info("[STONE LINE WRITE] lot_ids ANTES: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
            _logger.info("[STONE LINE WRITE] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).write(vals)
        
        if 'lot_ids' in vals:
            _logger.info("[STONE LINE WRITE] lot_ids DESPUÉS: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] FIN")
            _logger.info("=" * 80)
        
        return result

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