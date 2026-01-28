# ./__manifest__.py
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '19.0.1.0.0', # <--- ACTUALIZADO A 19
    'category': 'Sales/Sales',
    'summary': 'Selección visual agrupada de placas (piedra/mármol) en ventas',
    'description': """
        Módulo profesional para la gestión de ventas de piedra natural.
        Adapta la vista de lista (list view) de ventas para Odoo 19.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'depends': ['sale_management', 'stock'],
    'data': [
        'views/sale_views.xml',
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