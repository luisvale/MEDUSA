# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Ajuste_PACASA',
    'version': '2.3',
    'author': 's',
    'category': 'Sales',
    'maintainer': '',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'stock'],
    'data': [
        'views/stock_warehouse.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/main_screen.png'],
}