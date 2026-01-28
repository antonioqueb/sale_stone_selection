# -*- coding: utf-8 -*-
from odoo import models, api

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None):
        """
        Búsqueda especializada para la vista de selección de ventas.
        Aplica lógica de filtrado similar al módulo visual de inventario.
        """
        if not filters:
            filters = {}

        # Dominio base: Producto específico, ubicación interna, stock disponible
        domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # --- Filtros de Texto (ilike) ---
        if filters.get('bloque'):
            domain.append(('x_bloque', 'ilike', filters['bloque']))
        
        if filters.get('atado'):
            domain.append(('x_atado', 'ilike', filters['atado']))
            
        if filters.get('contenedor'):
            domain.append(('x_contenedor', 'ilike', filters['contenedor']))
            
        if filters.get('pedimento'):
            domain.append(('x_pedimento', 'ilike', filters['pedimento']))
            
        if filters.get('lot_name'):
            # Búsqueda por nombre de lote
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))

        # --- Filtros Numéricos (con tolerancia técnica si aplica) ---
        # Alto Mínimo
        if filters.get('alto_min'):
            try:
                val = float(filters['alto_min'])
                domain.append(('x_alto', '>=', val))
            except (ValueError, TypeError):
                pass

        # Ancho Mínimo
        if filters.get('ancho_min'):
            try:
                val = float(filters['ancho_min'])
                domain.append(('x_ancho', '>=', val))
            except (ValueError, TypeError):
                pass
                
        # Grosor (con tolerancia pequeña para flotantes)
        if filters.get('grosor'):
            try:
                val = float(filters['grosor'])
                domain.append(('x_grosor', '>=', val - 0.1))
                domain.append(('x_grosor', '<=', val + 0.1))
            except (ValueError, TypeError):
                pass

        # Campos a leer
        fields = [
            'lot_id', 'location_id', 'quantity', 
            'x_bloque', 'x_alto', 'x_ancho', 
            'x_atado', 'x_contenedor', 'x_grosor'
        ]
        
        # Búsqueda
        quants = self.search_read(domain, fields, limit=200, order='x_bloque, lot_id')
        
        return quants