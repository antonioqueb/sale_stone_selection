# -*- coding: utf-8 -*-
from odoo import models, api
import logging
_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        Búsqueda de inventario para selección de piedra.
        Devuelve datos completos del lote incluyendo todos los campos personalizados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE QUANT SEARCH] INICIO")
        _logger.info("[STONE QUANT SEARCH] product_id: %s", product_id)
        _logger.info("[STONE QUANT SEARCH] filters: %s", filters)
        _logger.info("[STONE QUANT SEARCH] current_lot_ids (raw): %s", current_lot_ids)
        
        if not filters:
            filters = {}
        
        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]
            _logger.info("[STONE QUANT SEARCH] safe_current_ids: %s", safe_current_ids)

        # 1. Dominio base
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # 2. Disponibilidad: (Es mío) OR (Está libre)
        free_domain = [('reserved_quantity', '=', 0)]
        if 'x_tiene_hold' in self.env['stock.quant']._fields:
            free_domain.append(('x_tiene_hold', '=', False))
        
        if safe_current_ids:
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + ['&'] + free_domain
        else:
            availability_domain = free_domain
            
        domain = base_domain + availability_domain

        # 3. Filtros UI
        if filters.get('bloque'):
            domain.append(('lot_id.x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'):
            domain.append(('lot_id.x_atado', 'ilike', filters['atado']))
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))
        if filters.get('alto_min'):
            try:
                domain.append(('lot_id.x_alto', '>=', float(filters['alto_min'])))
            except:
                pass
        if filters.get('ancho_min'):
            try:
                domain.append(('lot_id.x_ancho', '>=', float(filters['ancho_min'])))
            except:
                pass

        # 4. Buscar quants
        quants = self.search(domain, limit=300, order='lot_id')
        
        # 5. Obtener IDs de lotes únicos para traer datos completos
        lot_ids = quants.mapped('lot_id').ids
        
        # 6. Leer TODOS los campos del lote de una sola vez (eficiente)
        lots_data = {}
        if lot_ids:
            lots = self.env['stock.lot'].browse(lot_ids)
            for lot in lots:
                lots_data[lot.id] = {
                    'name': lot.name,
                    # Dimensiones
                    'x_grosor': lot.x_grosor or 0,
                    'x_alto': lot.x_alto or 0,
                    'x_ancho': lot.x_ancho or 0,
                    'x_peso': lot.x_peso or 0,
                    # Clasificación
                    'x_tipo': lot.x_tipo or '',
                    'x_numero_placa': lot.x_numero_placa or '',
                    'x_bloque': lot.x_bloque or '',
                    'x_atado': lot.x_atado or '',
                    'x_grupo': lot.x_grupo or '',
                    'x_color': lot.x_color or '',
                    # Logística
                    'x_pedimento': lot.x_pedimento or '',
                    'x_contenedor': lot.x_contenedor or '',
                    'x_referencia_proveedor': lot.x_referencia_proveedor or '',
                    'x_proveedor': [lot.x_proveedor.id, lot.x_proveedor.name] if lot.x_proveedor else False,
                    'x_origen': lot.x_origen or '',
                    # Fotografías
                    'x_fotografia_principal': lot.x_fotografia_principal or False,
                    'x_tiene_fotografias': lot.x_tiene_fotografias or False,
                    'x_cantidad_fotos': lot.x_cantidad_fotos or 0,
                    # Detalles
                    'x_detalles_placa': lot.x_detalles_placa or '',
                }
        
        # 7. Construir resultado enriquecido
        result = []
        for q in quants:
            lot_id = q.lot_id.id if q.lot_id else False
            lot_info = lots_data.get(lot_id, {})
            
            result.append({
                'id': q.id,
                'lot_id': [lot_id, lot_info.get('name', '')] if lot_id else False,
                'location_id': [q.location_id.id, q.location_id.display_name] if q.location_id else False,
                'quantity': q.quantity,
                'reserved_quantity': q.reserved_quantity,
                # Todos los campos del lote
                'x_grosor': lot_info.get('x_grosor', 0),
                'x_alto': lot_info.get('x_alto', 0),
                'x_ancho': lot_info.get('x_ancho', 0),
                'x_peso': lot_info.get('x_peso', 0),
                'x_tipo': lot_info.get('x_tipo', ''),
                'x_numero_placa': lot_info.get('x_numero_placa', ''),
                'x_bloque': lot_info.get('x_bloque', ''),
                'x_atado': lot_info.get('x_atado', ''),
                'x_grupo': lot_info.get('x_grupo', ''),
                'x_color': lot_info.get('x_color', ''),
                'x_pedimento': lot_info.get('x_pedimento', ''),
                'x_contenedor': lot_info.get('x_contenedor', ''),
                'x_referencia_proveedor': lot_info.get('x_referencia_proveedor', ''),
                'x_proveedor': lot_info.get('x_proveedor', False),
                'x_origen': lot_info.get('x_origen', ''),
                'x_fotografia_principal': lot_info.get('x_fotografia_principal', False),
                'x_tiene_fotografias': lot_info.get('x_tiene_fotografias', False),
                'x_cantidad_fotos': lot_info.get('x_cantidad_fotos', 0),
                'x_detalles_placa': lot_info.get('x_detalles_placa', ''),
            })
        
        _logger.info("[STONE QUANT SEARCH] Encontrados: %s quants con datos completos", len(result))
        _logger.info("[STONE QUANT SEARCH] FIN")
        _logger.info("=" * 80)
        
        return result