# ./__manifest__.py
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '19.0.1.2.0',
    'category': 'Sales/Sales',
    'summary': 'Selección visual de placas con reserva estricta',
    'description': """
        Módulo profesional para la gestión de ventas de piedra natural.
        - Selección visual (Grid) en líneas de venta.
        - Reserva estricta de lotes seleccionados (Bypass FIFO).
        - Integración con stock_lot_dimensions para limpieza de asignaciones automáticas.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    # IMPORTANTE: Se agrega stock_lot_dimensions para garantizar el orden de ejecución correcto
    'depends': ['sale_management', 'stock', 'stock_lot_dimensions', 'inventory_shopping_cart'],
    'data': [
        'views/sale_views.xml',
        'views/stock_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_stone_selection/static/src/scss/stone_styles.scss',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.xml',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.js',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.js',
        
        ],
    },
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}