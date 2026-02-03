# ./__manifest__.py
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '19.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Selección visual de placas con reserva estricta (Anti-FIFO)',
    'description': """
        Módulo de venta de piedra natural.
        1. Selección visual mediante Grid (Widget Stone Expand).
        2. Reserva forzada de lotes seleccionados al confirmar la venta.
        3. Visualización de asignaciones en Albaranes.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'depends': ['sale_management', 'stock'],
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
            'sale_stone_selection/static/src/components/stone_move_grid/stone_move_grid.xml',
            'sale_stone_selection/static/src/components/stone_move_grid/stone_move_grid.js', 
        ],
    },
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}