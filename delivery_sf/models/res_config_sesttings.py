from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	module_delivery_sf = fields.Boolean("SF Express Connector")
