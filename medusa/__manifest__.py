{
    'name': 'Invoice Sale Order Relation',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Relación entre facturas y pedidos de venta',
    'description': """
        Este módulo añade un campo a las facturas para relacionarlas con los pedidos de venta.
        Al confirmar la factura, se validan los movimientos de inventario del pedido de venta relacionado.
    """,
    'author': 'MEDUSA',
    'depends': ['account', 'sale', 'stock'],  # Dependencias del módulo
    'data': [
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}