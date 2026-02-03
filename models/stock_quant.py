# -*- coding: utf-8 -*-
from odoo import models, api

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        Búsqueda alineada con la lógica visual:
        Muestra stock disponible O stock que ya tengo seleccionado (aunque esté reservado).
        """
        if not filters:
            filters = {}
        
        # Limpieza de IDs
        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                # Filtrar solo enteros válidos
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]
            elif isinstance(current_lot_ids, str):
                pass 

        # --- DOMINIO BASE ---
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # --- LÓGICA DE DISPONIBILIDAD ---
        # Un lote se muestra SI:
        # 1. (Está libre Y No tiene Hold)
        #    O
        # 2. (Es uno de los lotes que YO tengo seleccionados en esta línea)
        
        # Condición 1: Libre
        free_domain = ['&', ('reserved_quantity', '=', 0)]
        if hasattr(self, 'x_tiene_hold'):
            free_domain.append(('x_tiene_hold', '=', False))
        else:
            free_domain.append(('id', '!=', False)) # Dummy siempre verdadero

        # Condición Final: (Lote está en mis seleccionados) OR (Condición 1)
        if safe_current_ids:
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + free_domain
        else:
            availability_domain = free_domain
            
        domain = base_domain + availability_domain

        # --- FILTROS DE TEXTO Y DIMENSIONES ---
        if filters.get('bloque'):
            domain.append(('x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'):
            domain.append(('x_atado', 'ilike', filters['atado']))
        if filters.get('contenedor'):
            domain.append(('x_contenedor', 'ilike', filters['contenedor']))
        if filters.get('pedimento'):
            domain.append(('x_pedimento', 'ilike', filters['pedimento']))
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))

        if filters.get('alto_min'):
            try:
                domain.append(('x_alto', '>=', float(filters['alto_min'])))
            except: pass
        if filters.get('ancho_min'):
            try:
                domain.append(('x_ancho', '>=', float(filters['ancho_min'])))
            except: pass
        if filters.get('grosor'):
            try:
                val = float(filters['grosor'])
                domain.append(('x_grosor', '>=', val - 0.1))
                domain.append(('x_grosor', '<=', val + 0.1))
            except: pass

        # Campos a leer
        fields = [
            'lot_id', 'location_id', 'quantity', 'reserved_quantity',
            'x_bloque', 'x_alto', 'x_ancho', 
            'x_atado', 'x_contenedor', 'x_grosor', 'x_tipo'
        ]
        if hasattr(self, 'x_tiene_hold'):
            fields.append('x_tiene_hold')

        quants = self.search_read(domain, fields, limit=300, order='x_bloque, lot_id')
        
        return quants