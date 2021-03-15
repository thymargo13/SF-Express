# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': "SF Express Shipping",
    'description': "Send your parcels through SF Express and track them online",
    'category': 'Inventory/Delivery',
    'version': '1.0',
    'application': True,
    'depends': ['delivery', 'mail'],
    'author': "Margo Tang",
    'data': [
	    'data/delivery_sf_data.xml',
        # 'security/ir.model.access.csv',
        # 'security/delivery_carrier_security.xml',
        'views/delivery_carrier_views.xml',
        'views/res_config_settings_views.xml',
        # 'wizard/carrier_type_views.xml',
    ],
}
