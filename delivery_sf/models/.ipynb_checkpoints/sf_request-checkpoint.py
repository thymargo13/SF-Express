import json
import time
import uuid
import requests
import hashlib
import base64
import urllib.parse
import logging
from odoo import _
from odoo import release
from odoo.exceptions import UserError
from odoo.tools import float_repr

API_BASE_URL = 'https://sfapi-sbox.sf-express.com/std/service'
_logger = logging.getLogger(__name__)


class SFRequest:
    # "Implementation of SF Express API"
    def __init__(self, debug_logger, client_code, check_word):
        self.debug_logger = debug_logger
        self.client_code = client_code
        self.check_word = check_word

    def _set_shipper(self, shipper):
        shipper_info = dict()
        address = "%s\n%s\n%s\n%s\n%s" % (shipper.street, shipper.street2, shipper.city,
                                          shipper.zip, shipper.country_id.name)
        shipper_info['address'] = address
        shipper_info['contact'] = shipper.name
        shipper_info['contactType'] = 1
        shipper_info['postCode'] = shipper.zip
        shipper_info['tel'] = shipper.phone
        if shipper.country_id.code in "HK":
            shipper_info['zoneCode'] = '852'
            shipper_info['country'] = '852'
        else:
            shipper_info['country'] = shipper.country_id.code
        return shipper_info

    def _set_recipient(self, recipient):
        recipient_info = dict()
        recipient_info['address'] = recipient.contact_address
        recipient_info['contact'] = recipient.name
        recipient_info['contactType'] = 2
        recipient_info['postCode'] = recipient.zip
        recipient_info['tel'] = recipient.phone
        if recipient.country_id.code in "HK":
            recipient_info['zoneCode'] = '852'
            recipient_info['country'] = '852'
        else:
            recipient_info['country'] = recipient.country_id.code
        return recipient_info

    def _set_cargo_detail(self, picking, product, order_line):
        cargo_info = dict()
        cargo_info['count'] = order_line.product_uom._compute_quantity(order_line.product_uom_qty, order_line.product_id.uom_id)
        cargo_info['unit'] = product.weight_uom_name
        cargo_info['amount'] = order_line.price_total
        cargo_info['name'] = order_line.product_id.name
        cargo_info['sourceArea'] = 'CHN'
        cargo_info['currency'] = product.currency_id.name
        cargo_info['declaredValueDeclaredCurrency'] = product.currency_id.name
        cargo_info['cargoDeclaredValue'] = order_line.price_total
        _logger.info(order_line.product_id.name)
        _logger.info(order_line.is_delivery)
        _logger.info(order_line.price_total)
        _logger.info(order_line.product_uom._compute_quantity(order_line.product_uom_qty, order_line.product_id.uom_id))
        return cargo_info

    def _make_api_request(self, request_id, service_code, msg_data, request_type="post"):
        try:
            timestamp = str(int(time.time()))
            data_str = urllib.parse.quote_plus(msg_data + timestamp + self.check_word)
            # 先md5加密然后base64加密
            m = hashlib.md5()
            m.update(data_str.encode('utf-8'))
            md5_str = m.digest()
            msg_digest = base64.b64encode(md5_str).decode('utf-8')
            data = {"partnerID": self.client_code, "requestID": request_id, "serviceCode": service_code,
                    "timestamp": timestamp,
                    "msgDigest": msg_digest, "msgData": msg_data}
            response = requests.post(API_BASE_URL, data=data)
            result = json.loads(response.text)
            if self.debug_logger:
                self.debug_logger("%s\n%s" % (result['apiResultCode'], result['apiResultData']),
                                  'SF_request_%s' % msg_data)
            resp_data = json.loads(result['apiResultData'])
            if not resp_data['success']:
                raise UserError(_('SF returned an error: %s', resp_data['errorMsg']))
            else:
                return resp_data
        except Exception as e:
            raise e
