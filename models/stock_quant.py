# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        API para el Grid Visual JS.
        Devuelve: Stock Disponible + Stock Seleccionado (aunque esté reservado).
        """
        if not filters: filters = {}
        
        # Limpieza y Logging de IDs entrantes
        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]
            _logger.info(f"[STONE] Buscando inventario ProdID: {product_id}. IDs actuales recibidos: {safe_current_ids}")
        else:
            _logger.info(f"[STONE] Buscando inventario ProdID: {product_id}. Sin selección previa.")

        # 1. Base
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # 2. Disponibilidad: (Es mío) OR (Está libre)
        # IMPORTANTE: Si safe_current_ids tiene datos, el dominio debe incluirlos explícitamente
        # para que aparezcan aunque estén reservados (reserved_quantity > 0)
        free_domain = [('reserved_quantity', '=', 0)]
        if hasattr(self, 'x_tiene_hold'):
            free_domain.append(('x_tiene_hold', '=', False))

        if safe_current_ids:
            # Lógica: (Es uno de mis lotes) OR (No está reservado)
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + ['&'] + free_domain
        else:
            availability_domain = free_domain
            
        domain = base_domain + availability_domain

        # 3. Filtros UI
        if filters.get('bloque'): domain.append(('x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'): domain.append(('x_atado', 'ilike', filters['atado']))
        if filters.get('lot_name'): domain.append(('lot_id.name', 'ilike', filters['lot_name']))
        
        if filters.get('alto_min'):
            try: domain.append(('x_alto', '>=', float(filters['alto_min'])))
            except: pass
        if filters.get('ancho_min'):
            try: domain.append(('x_ancho', '>=', float(filters['ancho_min'])))
            except: pass

        fields_to_read = [
            'lot_id', 'location_id', 'quantity', 'reserved_quantity',
            'x_bloque', 'x_alto', 'x_ancho', 'x_atado', 'x_grosor', 'x_tipo'
        ]
        
        results = self.search_read(domain, fields_to_read, limit=300, order='x_bloque, lot_id')
        
        # Log de verificación de resultados
        found_lots = [r['lot_id'][0] for r in results if r.get('lot_id')]
        missing_ids = [lid for lid in safe_current_ids if lid not in found_lots]
        
        if missing_ids:
            _logger.warning(f"[STONE] ALERTA: IDs seleccionados {missing_ids} NO encontrados en búsqueda de stock (¿Vendidos/Movidos?).")
        else:
            _logger.info(f"[STONE] Búsqueda exitosa. {len(results)} registros encontrados.")

        return results