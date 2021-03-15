# -*- coding: utf-8 -*-

import json
import requests
from werkzeug.urls import url_join

from odoo.tools.safe_eval import safe_eval
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round
from .sf_request import SFRequest
import uuid
import logging

_logger = logging.getLogger(__name__)

class DeliverCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[
        ('sf', "SF Express")
    ], ondelete={'sf': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    sf_client_code = fields.Char(string="SF Client Code", groups="base.group_system")
    sf_check_word = fields.Char(string="SF Check Word", groups="base.group_system")
    sf_language = fields.Selection([('C', 'Simplified Chinese'),
                                    ('E', 'English')
                                    ],
                                   default='C',
                                   string='SF Language')
    sf_monthlyCard = fields.Char(string="Monthly Card number")
    sf_pay_monthly = fields.Boolean()
    sf_fixed_price = fields.Boolean()

    def sf_rate_shipment(self, order):
        price = 0.00
        if self.sf_fixed_price:
            price = self.fixed_price
            company = self.company_id or order.company_id or self.env.company
            if company.currency_id and company.currency_id != order.currency_id:
                price = company.currency_id._convert(price, order.currency_id, company, fields.Date.today())
        else:
            try:
                price = self._get_price_available(order)
            except UserError as e:
                return {'success': False,
                        'price': 0.0,
                        'error_message': e.args[0],
                        'warning_message': False}
            if order.company_id.currency_id.id != order.pricelist_id.currency_id.id:
                price = order.company_id.currency_id._convert(
                    price, order.pricelist_id.currency_id, order.company_id,
                    order.date_order or fields.Date.today())

        return {'success': True,
                'price': price,
                'error_message': False,
                'warning_message': False}

    def _get_price_available(self, order):
        self.ensure_one()
        self = self.sudo()
        order = order.sudo()
        total = weight = volume = quantity = 0
        total_delivery = 0.0
        for line in order.order_line:
            if line.state == 'cancel':
                continue
            if line.is_delivery:
                total_delivery += line.price_total
            if not line.product_id or line.is_delivery:
                continue
            qty = line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
            weight += (line.product_id.weight or 0.0) * qty
            volume += (line.product_id.volume or 0.0) * qty
            quantity += qty
        total = (order.amount_total or 0.0) - total_delivery

        total = order.currency_id._convert(
            total, order.company_id.currency_id, order.company_id, order.date_order or fields.Date.today())

        return self._get_price_from_picking(total, weight, volume, quantity)

    def _get_price_from_picking(self, total, weight, volume, quantity):
        price = 0.0
        criteria_found = False
        price_dict = {'price': total, 'volume': volume, 'weight': weight, 'wv': volume * weight, 'quantity': quantity}
        for line in self.price_rule_ids:
            test = safe_eval(line.variable + line.operator + str(line.max_value), price_dict)
            if test:
                price = line.list_base_price + line.list_price * price_dict[line.variable_factor]
                criteria_found = True
                break
        if not criteria_found:
            raise UserError(_("No price rule matching this order; delivery cost cannot be computed."))

        return price

    def sf_send_shipping(self, pickings):
        res = []
        if not pickings.carrier_tracking_ref:
            client_code = self.sudo().sf_client_code
            check_word = self.sudo().sf_check_word
            service_code = "EXP_RECE_CREATE_ORDER"
            request_id = uuid.uuid1()
            sf = SFRequest(self.log_xml, self.sf_client_code, self.sf_check_word)
            # json.loads = str to dict
            # json.dumps = dict to str
            for picking in pickings:
                _logger.info('product Detail:\n%s',  picking.product_id)
                
                msg_data = dict()
                msg_data['cargoDetails'] = []
                for line in picking.sale_id.order_line:
                    if not line.is_delivery:
                        cargoDetail = sf._set_cargo_detail(picking, picking.product_id, line)
                        msg_data['cargoDetails'].append(cargoDetail)
                        _logger.info('cargo Detail:\n%s', cargoDetail)
                _logger.info(msg_data['cargoDetails'])
                msg_data['contactInfoList'] = []
                recipient = sf._set_recipient(picking.partner_id)
                shipper = sf._set_shipper(picking.company_id)
                msg_data['contactInfoList'].append(shipper)
                msg_data['contactInfoList'].append(recipient)
                if self.sf_language in "E":
                    msg_data['language'] = 'en'
                if self.sf_language in "C":
                    msg_data['language'] = 'zh_CN'
                msg_data['orderId'] = picking.display_name
                msg_data = json.dumps(msg_data)
                resp = sf._make_api_request(request_id, service_code, msg_data)
                result = dict()
                result['tracking_number'] = resp['msgData']['waybillNoInfoList'][0]['waybillNo']
                result['exact_price'] = 100
                res.append(result)
        else:
            res.append({
                'tracking_number': pickings.carrier_tracking_ref,
                'exact_price': 100
            })
        return res

    def sf_get_tracking_link(self, picking):
        return 'https://htm.sf-express.com/hk/tc/dynamic_function/waybill/#search/bill-number/%s' % picking.carrier_tracking_ref

    def sf_cancel_shipment(self, pickings):
        service_code = 'EXP_RECE_UPDATE_ORDER'
        request_id = uuid.uuid1()
        sf = SFRequest(self.log_xml, self.sf_client_code, self.sf_check_word)
        res = []
        for picking in pickings:
            msg_data = dict()
            waybillNoInfoList = dict()
            waybillNoInfoList['waybillNo'] = picking.carrier_tracking_ref
            waybillNoInfoList['waybillType'] = 1
            msg_data['dealType'] = 2
            msg_data['orderId'] = picking.display_name
            msg_data['waybillNoInfoList'] = []
            msg_data['waybillNoInfoList'].append(waybillNoInfoList)
            msg_data = json.dumps(msg_data)
            resp = sf._make_api_request(request_id, service_code, msg_data)
            if resp['success']:
                picking.message_post(body=_(u'Shipment #%s has been cancelled', picking.carrier_tracking_ref))
                picking.write({'carrier_tracking_ref': '',
                               'carrier_price': 0.0})
            else:
                raise UserError(resp['errorMsg'])

# {"success":true,"errorCode":"S0000","errorMsg":null,"msgData":{"orderId":"WH/OUT/00018","waybillNoInfoList":[{"waybillType":1,"waybillNo":"SF7444424929038"}],"resStatus":2,"extraInfoList":null}}
